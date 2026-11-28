import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'config'))
import recording_profile as profile


class RecordingProfileTest(unittest.TestCase):
    def test_activation_waits_for_stable_audio_thread_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            owner = (11, 22)
            app = {'pid': 33, 'birth': 44, 'session': ['11', '22']}
            endpoint = {'id': 77}
            journal = runtime / 'recording-lease.json'
            (runtime / 'session.state').write_text(f'11\n22\nprefix\ncheckout\n{runtime}/session.log\n')
            journal.write_text(json.dumps({'version': 1, 'owner': list(owner), 'phase': 'applied',
                                           'original': 0, 'working': 1024, 'endpoint': endpoint}))
            initial = [{'role': 'AudioCalc', 'tid': tid, 'birth': 90, 'priority': 10}
                       for tid in range(50, 64)]
            initial.append({'role': 'data-loop.0', 'tid': 64, 'birth': 90, 'priority': 9})
            stable = [{**initial[0], 'tid': 65, 'birth': 91}, *initial[1:]]

            with (patch.object(profile.runpy, 'run_path', return_value={'guarded_application': lambda *_: app}),
                  patch.object(profile.realtime, 'process_stat', return_value=(owner[1], 'S')),
                  patch.object(profile.realtime, 'audio_threads', side_effect=(initial, stable, stable, stable)),
                  patch.object(profile.realtime, 'thread_live', return_value=True),
                  patch.object(profile.os, 'sched_getscheduler', return_value=os.SCHED_OTHER),
                  patch.object(profile.os, 'sched_getaffinity', return_value=set(range(8))),
                  patch.object(profile.realtime, 'apply') as apply,
                  patch.object(profile, 'read_graph', return_value=[]),
                  patch.object(profile, 'command', return_value=''),
                  patch.object(profile, 'inspect_clock', return_value=(78, 98)),
                  patch.object(profile.PipeWire, 'read', return_value=1024),
                  patch.object(profile.time, 'sleep') as wait,
                  patch('builtins.print')):
                profile.activate(runtime, owner, journal)

            wait.assert_called_once()
            apply.assert_called_once()
            self.assertEqual(apply.call_args.args[:4], (app, stable, owner, runtime / 'recording-realtime.json'))
