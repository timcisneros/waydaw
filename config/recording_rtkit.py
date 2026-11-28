"""Apply and release realtime priorities on the owned Live audio threads."""
from pathlib import Path
import os
import resource
import signal
import time

from recording_lease import publish

RTKIT = 'org.freedesktop.RealtimeKit1'
BUDGET = 200000
RESET = os.SCHED_RESET_ON_FORK
ORDINARY = {os.SCHED_OTHER, os.SCHED_OTHER | RESET}


def process_stat(path):
    try:
        data = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return (int(data[19]), data[0]) if data[0] not in {'Z', 'X'} else None


def audio_threads(app):
    process = Path('/proc') / str(app['pid'])
    state = process_stat(process)
    if state is None or state[0] != app['birth']:
        return []
    threads = []
    for task in (process / 'task').iterdir():
        try:
            role = (task / 'comm').read_text().strip()
        except FileNotFoundError:
            continue
        data = process_stat(task)
        if data and role in {'AudioCalc', 'data-loop.0'}:
            threads.append({'tid': int(task.name), 'birth': data[0], 'role': role,
                            'priority': 10 if role == 'AudioCalc' else 9})
    return sorted(threads, key=lambda thread: (thread['priority'] == 9, thread['tid']))


def thread_live(app, thread):
    task = Path('/proc') / str(app['pid']) / 'task' / str(thread['tid'])
    try:
        stat = process_stat(task)
        return (stat is not None and stat[0] == thread['birth'] and task.stat().st_uid == os.getuid()
                and (task / 'comm').read_text().strip() == thread['role'])
    except FileNotFoundError:
        return False


def require_ordinary_threads(app, threads):
    if len(threads) != 15 or sum(thread['role'] == 'AudioCalc' for thread in threads) != 14:
        raise RuntimeError('Live does not have the qualified 15 audio thread roles')
    if audio_threads(app) != threads:
        raise RuntimeError('Live audio threads are still changing during startup')
    for thread in threads:
        if not thread_live(app, thread):
            raise RuntimeError('A Live audio thread changed before application of the profile')
        tid = thread['tid']
        if os.sched_getscheduler(tid) not in ORDINARY or os.sched_getaffinity(tid) != set(range(8)):
            raise RuntimeError(f"Live {thread['role']} scheduling or affinity differs from qualification")


class Peer:
    def __init__(self, bus, dbus):
        self.bus = bus
        self.dbus = dbus
        self.name = str(self.query('GetNameOwner', RTKIT))
        if not self.name.startswith(':'):
            raise RuntimeError('RTKit did not supply an exact peer name')
        self.pid = int(self.query('GetConnectionUnixProcessID', self.name))
        state = process_stat(Path('/proc') / str(self.pid))
        if not state:
            raise RuntimeError('RTKit exited during discovery')
        self.birth = state[0]
        obj = bus.get_object(self.name, '/org/freedesktop/RealtimeKit1', introspect=False)
        self.broker = dbus.Interface(obj, RTKIT)
        self.properties = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
        if (int(self.properties.Get(RTKIT, 'MaxRealtimePriority', timeout=.4)) < 10
                or int(self.properties.Get(RTKIT, 'RTTimeUSecMax', timeout=.4)) < BUDGET):
            raise RuntimeError('RTKit has lower limits than the qualified profile')
        self.next_request = 0.0

    def query(self, method, value):
        service = 'org.freedesktop.DBus'
        return self.bus.call_blocking(service, '/org/freedesktop/DBus', service,
                                      method, 's', (value,), timeout=.3)

    def verify(self):
        state = process_stat(Path('/proc') / str(self.pid))
        if not state or state[0] != self.birth or self.query('GetNameOwner', RTKIT) != self.name:
            raise RuntimeError('RTKit changed during startup')

    def grant(self, app, thread, deadline):
        delay = self.next_request - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.verify()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Realtime startup exceeded its deadline')
        self.broker.MakeThreadRealtimeWithPID(self.dbus.UInt64(app['pid']),
                                              self.dbus.UInt64(thread['tid']),
                                              self.dbus.UInt32(thread['priority']),
                                              timeout=min(.5, remaining))
        self.next_request = time.monotonic() + .07

    def settle(self):
        # Use the same connection and unique peer as the timed-out request.
        try:
            self.properties.Get(RTKIT, 'MaxRealtimePriority', timeout=.7)
            self.verify()
            return True
        except (self.dbus.DBusException, RuntimeError):
            state = process_stat(Path('/proc') / str(self.pid))
            return state is None or state[0] != self.birth


def wait_quiescent(process):
    deadline = time.monotonic() + 1.25
    while time.monotonic() < deadline:
        states = [process_stat(task) for task in (process / 'task').iterdir()]
        if states and all(state and state[1] in ('T', 't') for state in states):
            return
        time.sleep(.005)
    raise RuntimeError('The owned Live process did not quiesce')


def demote(receipt, owner):
    if receipt['owner'] != list(owner):
        raise RuntimeError('Realtime receipt belongs to a different WayDAW session')
    app = receipt['application']
    process = Path('/proc') / str(app['pid'])
    state = process_stat(process)
    if state is None or state[0] != app['birth']:
        return
    descriptor = os.pidfd_open(app['pid'])
    resume = False
    try:
        current = process_stat(process)
        if current is None or current[0] != app['birth']:
            return
        if current[1] not in ('T', 't'):
            signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
            resume = True
        else:
            resume = receipt['paused']
        wait_quiescent(process)
        for thread in receipt['threads']:
            if not thread_live(app, thread):
                continue
            tid = thread['tid']
            policy = os.sched_getscheduler(tid)
            if policy == (os.SCHED_RR | RESET) and os.sched_getparam(tid).sched_priority == thread['priority']:
                os.sched_setscheduler(tid, os.SCHED_OTHER | RESET, os.sched_param(0))
            elif policy not in ORDINARY:
                raise RuntimeError('A recorded Live thread changed scheduling ownership')
    except (FileNotFoundError, ProcessLookupError):
        if process_stat(process) is not None:
            raise
    finally:
        try:
            if resume:
                signal.pidfd_send_signal(descriptor, signal.SIGCONT)
        except ProcessLookupError:
            pass
        finally:
            os.close(descriptor)


def apply(app, threads, owner, path, require_live):
    import dbus

    bus = dbus.SystemBus(private=True)
    descriptor = None
    stopped = False
    try:
        peer = Peer(bus, dbus)
        descriptor = os.pidfd_open(app['pid'])
        require_live(app)
        receipt = {'owner': list(owner), 'application': {'pid': app['pid'], 'birth': app['birth']},
                   'threads': threads, 'paused': True, 'confirmed': False,
                   'broker_pid': peer.pid, 'broker_birth': peer.birth}
        publish(path, receipt, initial=True)
        signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
        stopped = True
        process = Path('/proc') / str(app['pid'])
        wait_quiescent(process)
        require_ordinary_threads(app, threads)

        resource.prlimit(app['pid'], resource.RLIMIT_RTTIME, (BUDGET, BUDGET))
        deadline = time.monotonic() + 3
        for thread in threads:
            require_live(app)
            if not thread_live(app, thread):
                raise RuntimeError('An owned Live thread changed before its grant')
            peer.grant(app, thread, deadline)
        peer.verify()
        if any(not thread_live(app, thread) or os.sched_getscheduler(thread['tid']) != (os.SCHED_RR | RESET)
               or os.sched_getparam(thread['tid']).sched_priority != thread['priority']
               for thread in threads):
            raise RuntimeError('Live realtime grants could not be confirmed')
        receipt['confirmed'] = True
    except BaseException as error:
        if stopped:
            uncertain = isinstance(error, dbus.DBusException) and error.get_dbus_name() in (
                'org.freedesktop.DBus.Error.Timeout', 'org.freedesktop.DBus.Error.NoReply')
            if uncertain:
                receipt['unsettled'] = not peer.settle()
            try:
                demote(receipt, owner)
            finally:
                publish(path, receipt)
        raise
    finally:
        if descriptor is not None:
            try:
                if stopped:
                    signal.pidfd_send_signal(descriptor, signal.SIGCONT)
            except ProcessLookupError:
                pass
            finally:
                os.close(descriptor)
        bus.close()

    receipt['paused'] = False
    publish(path, receipt)
