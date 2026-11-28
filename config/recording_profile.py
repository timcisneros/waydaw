"""Guard the host audio settings qualified for WayDAW recording."""
import argparse
import json
import os
from pathlib import Path
import re
import resource
import runpy
import subprocess
import sys
import time

import recording_lease as lease
import recording_rtkit as realtime

ROOT = Path(__file__).resolve().parents[1]
HEADROOM = ROOT / '.local-tools/waydaw-recording/headroom'
# The Live JACK configuration is for the application, not host control tools.
HOST_ENV = {key: value for key, value in os.environ.items() if not key.startswith('PIPEWIRE_')}


def command(*args, timeout=5):
    return subprocess.check_output(args, env=HOST_ENV, text=True, timeout=timeout)


def load(path):
    return json.loads(path.read_text())


def read_graph():
    return json.loads(command('pw-dump'))


def node_info(graph):
    return {item['id']: item['info'] for item in graph if item['type'] == 'PipeWire:Interface:Node'}


def playback_identity(profile):
    output = command('wpctl', 'inspect', '@DEFAULT_AUDIO_SINK@')
    detected = re.match(r'^id (\d+), type PipeWire:Interface:Node', output)
    if not detected:
        raise RuntimeError('Cannot identify the default physical playback sink')
    ident = int(detected[1])
    graph = read_graph()
    hardware = node_info(graph).get(ident, {})
    props = hardware.get('props', {})
    if props.get('node.name') != profile['sink_name'] or props.get('api.alsa.path') != profile['alsa_path']:
        raise lease.MutationRefused('The default playback device is outside the qualified profile')
    if hardware['state'] != 'suspended' or any(
        node['type'] == 'PipeWire:Interface:Link' and node['info']['input-node-id'] == ident
        for node in graph
    ):
        raise lease.MutationRefused('The qualified playback sink is busy')
    pid = int(command('systemctl', '--user', 'show', 'pipewire.service', '-p', 'MainPID', '--value'))
    current = realtime.process_stat(Path('/proc') / str(pid))
    if not current:
        raise RuntimeError('The original PipeWire daemon is unavailable')
    return {'id': ident, 'serial': props['object.serial'], 'name': props['node.name'],
            'path': props['api.alsa.path'], 'server_pid': pid, 'server_birth': current[0]}


class PipeWire:
    def __init__(self, runtime):
        self.socket = runtime.parent / 'pipewire-0'

    def call(self, endpoint, *values):
        args = [str(HEADROOM), str(self.socket),
                *(str(endpoint[key]) for key in ('server_pid','server_birth','id','serial','name','path')),
                *(str(value) for value in values)]
        result = subprocess.run(args, env=HOST_ENV, capture_output=True, text=True, timeout=5, check=False)
        message = result.stderr.strip() or 'The bound PipeWire request did not complete'
        if result.returncode == 2:
            raise lease.EndpointRetired(message)
        if result.returncode in (3, 4):
            raise lease.MutationRefused(message)
        if result.returncode:
            raise RuntimeError(message)
        return result.stdout.strip()

    def read(self, endpoint):
        return int(self.call(endpoint))

    def change(self, endpoint, before, after, *, require_suspended):
        if require_suspended != (after == lease.WORKING):
            raise RuntimeError('The PipeWire lease request has an unexpected direction')
        self.call(endpoint, before, after)


def inspect_clock(graph, endpoint, app, top):
    nodes = node_info(graph)
    hardware = nodes.get(endpoint['id'], {})
    props = hardware.get('props', {})
    if (props.get('object.serial') != endpoint['serial'] or props.get('node.name') != endpoint['name']
            or props.get('api.alsa.path') != endpoint['path'] or hardware['state'] != 'running'
            or props.get('node.driver') is not True
            or not any(item.get('rate') == 48000 and item.get('mediaType') == 'audio'
                       for item in hardware['params'].get('Format', []))):
        raise RuntimeError('The original playback clock is inactive or has changed')
    clients = {item['id']: item['info']['props'] for item in graph
               if item['type'] == 'PipeWire:Interface:Client'}
    owned = [(ident, node['props']['object.serial'])
             for ident, node in nodes.items()
             if node['props'].get('node.name') == 'Ableton Live 12 Suite'
             and clients.get(node['props'].get('client.id'), {}).get('pipewire.sec.pid') == app['pid']
             and node['props'].get('node.driver-id') == endpoint['id'] and node['state'] == 'running']
    if len(owned) != 1:
        raise RuntimeError('Live is not the expected follower of the physical clock')
    live_id, live_serial = owned[0]
    rows = {}
    for line in top.splitlines():
        row = line.split()
        if row[:2] == ['S', 'ID']:
            rows.clear()
        elif len(row) >= 9 and row[1].isdigit():
            rows[int(row[1])] = row
    if (rows.get(endpoint['id'], [])[:4] != ['R', str(endpoint['id']), '1024', '48000']
            or rows.get(live_id, [])[:1] != ['R']):
        raise RuntimeError('The running ALSA clock did not negotiate 1024 frames at 48 kHz')
    return live_id, live_serial


def activate(runtime, owner, journal):
    guard = runpy.run_path(str(ROOT / 'config/midi-routing.py'))['guarded_application']

    def require_live(app):
        if guard(ROOT, runtime) != app or app['session'][:2] != [str(field) for field in owner]:
            raise RuntimeError('Live ownership changed during realtime setup')

    saved = lease.read_receipt(journal, owner)
    if saved is None or saved['phase'] != 'applied':
        raise RuntimeError('The ALSA lease is unavailable for realtime setup')
    endpoint = saved['endpoint']
    pipewire = PipeWire(runtime)
    deadline = time.monotonic() + 36
    cancelled = Path((runtime / 'session.state').read_text().splitlines()[4]).parent / 'cancelled'
    last = None
    while time.monotonic() < deadline:
        state = realtime.process_stat(Path('/proc') / str(owner[0]))
        if state is None or state[0] != owner[1] or cancelled.exists():
            raise RuntimeError('The owning WayDAW session stopped during audio setup')
        try:
            app = guard(ROOT, runtime)
            require_live(app)
            threads = realtime.audio_threads(app)
            if len(threads) != 15:
                raise RuntimeError('The qualified Live audio roles have not initialized')
            before = read_graph()
            top = command('pw-top', '-b', '-n', '2')
            clock = inspect_clock(before, endpoint, app, top)
            if inspect_clock(read_graph(), endpoint, app, top) != clock or pipewire.read(endpoint) != 1024:
                raise RuntimeError('The graph or ALSA lease changed during startup')
            require_live(app)
            realtime.require_ordinary_threads(app, threads)
            break
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            last = error
            time.sleep(.25)
    else:
        raise RuntimeError(f'Live did not reach the qualified audio profile: {last}')
    path = runtime / 'recording-realtime.json'
    realtime.apply(app, threads, owner, path, require_live)
    print('recording_profile=active quantum=1024 rate=48000 alsa_headroom=1024 realtime_threads=15', flush=True)


def session_owner(runtime):
    fields = (runtime / 'session.state').read_text().splitlines()
    if len(fields) != 5 or fields[3] != str(ROOT):
        raise RuntimeError('Audio settings require the owning WayDAW session')
    return tuple(int(item) for item in fields[:2])


def status(runtime, owner, journal, rt_path):
    rt = load(rt_path)
    receipt = lease.read_receipt(journal, owner)
    if (receipt is None or receipt['phase'] != 'applied' or rt['owner'] != list(owner)
            or not rt['confirmed'] or rt['paused']):
        raise RuntimeError('The realtime and device leases are not both confirmed')
    guard = runpy.run_path(str(ROOT / 'config/midi-routing.py'))['guarded_application']
    app = guard(ROOT, runtime)
    if rt['application'] != {'pid': app['pid'], 'birth': app['birth']}:
        raise RuntimeError('The protected Live process has changed')
    threads = realtime.audio_threads(app)
    if threads != rt['threads'] or any(
        not realtime.thread_live(app, item) or os.sched_getscheduler(item['tid']) != (os.SCHED_RR | realtime.RESET)
        or os.sched_getparam(item['tid']).sched_priority != item['priority']
        or os.sched_getaffinity(item['tid']) != set(range(8)) for item in threads
    ):
        raise RuntimeError('The protected Live thread policy has changed')
    if resource.prlimit(app['pid'], resource.RLIMIT_RTTIME) != (realtime.BUDGET, realtime.BUDGET):
        raise RuntimeError('The protected Live realtime budget has changed')
    endpoint = receipt['endpoint']
    graph = read_graph()
    top = command('pw-top', '-b', '-n', '2')
    seen = inspect_clock(graph, endpoint, app, top)
    if (PipeWire(runtime).read(endpoint) != lease.WORKING or guard(ROOT, runtime) != app
            or inspect_clock(read_graph(), endpoint, app, top) != seen):
        raise RuntimeError('The original Live and device leases could not be reverified')
    print('recording_profile=active quantum=1024 rate=48000 alsa_headroom=1024 realtime_threads=15', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('acquire','activate','demote','restore','status'))
    parser.add_argument('runtime', type=Path)
    parser.add_argument('profile', type=Path, nargs='?')
    args = parser.parse_args()
    runtime = args.runtime
    journal = runtime / 'recording-lease.json'
    rt_path = runtime / 'recording-realtime.json'
    if args.action in ('demote','restore') and not (journal.exists() or rt_path.exists()):
        return 0
    owner = session_owner(runtime)
    if args.action == 'acquire':
        if args.profile is None or not args.profile.is_file() or args.profile.is_symlink():
            raise RuntimeError('Expected an ordinary local recording profile file')
        configuration = load(args.profile)
        if configuration.get('version') != 1 or not all(
            isinstance(configuration.get(key), str) and configuration[key] for key in ('sink_name','alsa_path')
        ):
            raise RuntimeError('Invalid recording profile')
        try:
            lease.apply(journal, owner, playback_identity(configuration), PipeWire(runtime))
        except lease.MutationRefused as error:
            print(f'WARN: recording profile unavailable: {error}', file=sys.stderr, flush=True)
            return 3
    elif args.action == 'activate':
        activate(runtime, owner, journal)
    elif args.action == 'demote':
        if rt_path.exists():
            realtime.demote(load(rt_path), owner)
    elif args.action == 'status':
        status(runtime, owner, journal, rt_path)
    else:
        release = None
        if rt_path.exists():
            record = load(rt_path)
            if record['owner'] != list(owner):
                raise RuntimeError('The realtime owner differs from this session')
            app = record['application']
            state = realtime.process_stat(Path('/proc') / str(app['pid']))
            if state and state[0] == app['birth']:
                raise RuntimeError('Live must close before restoring its audio lease')
            release = lease.restore(journal, owner, PipeWire(runtime))
            if record.get('unsettled'):
                peer = realtime.process_stat(Path('/proc') / str(record['broker_pid']))
                if peer and peer[0] == record['broker_birth']:
                    raise RuntimeError('An unconfirmed RTKit request still needs recovery')
            rt_path.unlink()
        if release is None:
            release = lease.restore(journal, owner, PipeWire(runtime))
        print(f'recording_profile_release={release}', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'ERROR: recording profile: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
