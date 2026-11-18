"""MIDI discovery and ownership tests; no host ALSA ports are changed."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("midi_routing", ROOT / "config/midi-routing.py")
midi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(midi)

INVENTORY = """client 14: 'Midi Through' [type=kernel]
    0 'Midi Through Port-0'
client 20: 'Launchpad S' [type=kernel,card=1]
    0 'Launchpad S MIDI 1'
client 24: 'Virtual Raw MIDI 2-0' [type=kernel,card=2]
    0 'VirMIDI 2-0     '
client 25: 'Virtual Raw MIDI 2-1' [type=kernel,card=2]
    0 'VirMIDI 2-1     '
client 128: 'WINE midi driver' [type=user,pid=4300]
    0 'WINE ALSA Input '
client 129: 'WINE midi driver' [type=user,pid=4200]
    0 'WINE ALSA Input '
"""


class MidiPortsTests(unittest.TestCase):
    def setUp(self):
        self.ports, self.links = midi.parse_ports(INVENTORY)
        self.selected = midi.select_ports(self.ports, 4200, {})

    def test_sequencer_bus_is_independent_of_raw_virtual_card_numbers(self):
        self.assertEqual(self.selected["bus"], "14:0")
        for card in (1, 3, 12):
            ports, _ = midi.parse_ports(INVENTORY.replace("MIDI 2-", f"MIDI {card}-"))
            self.assertEqual(midi.select_ports(ports, 4200, {})["bus"], "14:0")

    def test_bome_and_other_wine_clients_are_not_ableton(self):
        self.assertEqual(self.selected["ableton"], "129:0")
        self.assertIsNone(midi.select_ports(self.ports, 9999, {})["ableton"])

    def test_ambiguous_sequencer_buses_require_explicit_selection(self):
        ports, _ = midi.parse_ports(INVENTORY + "client 30: 'Midi Through' [type=kernel]\n    0 'Midi Through Port-0'\n")
        with self.assertRaisesRegex(midi.RoutingError, "Ambiguous midi_bus"):
            midi.select_ports(ports, 4200, {})
        self.assertEqual(midi.select_ports(ports, 4200, {"WAYDAW_MIDI_BUS_PORT": "30:0"})["bus"], "30:0")

    def test_override_cannot_select_an_unrelated_port(self):
        selected = midi.select_ports(self.ports, 4200, {"WAYDAW_MIDI_BUS_PORT": "128:0"})
        self.assertIsNone(selected["bus"])
        with self.assertRaises(midi.RoutingError):
            midi.changes(selected, set(), "bome")

    def test_connection_parser_preserves_port_and_direction(self):
        ports, links = midi.parse_ports("""client 20: 'Launchpad S' [type=kernel,card=1]
    0 'Launchpad S MIDI 1'
        Connecting To: 129:0, 2129:0
                       150:1
    1 'Launchpad second port'
        Connected From: 200:0
client 129: 'WINE midi driver' [type=user,pid=4200]
    0 'WINE ALSA Input '
        Connected From: 20:0
""")
        self.assertEqual(links, {("20:0", "129:0"), ("20:0", "2129:0"),
                                 ("20:0", "150:1"), ("200:0", "20:1")})

    def test_translated_route_connects_before_removing_bypass(self):
        plan = midi.changes(self.selected, {("20:0", "129:0")}, "bome")
        self.assertEqual(plan, [("connect", "14:0", "129:0"), ("disconnect", "20:0", "129:0")])

    def test_repeated_route_has_no_changes(self):
        self.assertEqual(midi.changes(self.selected, {("14:0", "129:0")}, "bome"), [])

    def test_direct_bome_output_bypass_is_removed_without_breaking_virtual_output(self):
        links = {("128:1", "129:0"), ("128:1", "14:0"), ("14:0", "129:0")}
        self.assertEqual(midi.changes(self.selected, links, "bome", bome_outputs=["128:1"]),
                         [("disconnect", "128:1", "129:0")])

    def test_bome_thread_group_is_used_instead_of_main_pid(self):
        ports, _ = midi.parse_ports(INVENTORY + "client 150: 'WINE midi driver' [type=user,pid=4301]\n    1 'WINE ALSA Output #4'\nclient 151: 'WINE midi driver' [type=user,pid=4401]\n    1 'WINE ALSA Output #5'\n")
        with patch.object(midi, "process", side_effect=lambda pid, root: (1, {4300: 4120, 4301: 4120}.get(pid, 9999))):
            self.assertEqual(midi.bome_ports(ports, {"owner": ["4120", "220", "process-group-v1"]}), {"inputs": ["128:0"], "outputs": ["150:1"]})

    def test_unrelated_routes_are_preserved(self):
        links = {("14:0", "129:0"), ("24:0", "128:0"), ("24:0", "129:0")}
        self.assertEqual(midi.changes(self.selected, links, "bome"), [])

    def test_clear_can_remove_virtual_route_with_launchpad_unplugged(self):
        selected = dict(self.selected, launchpad=None)
        self.assertEqual(midi.changes(selected, {("14:0", "129:0")}, "bome", clear=True),
                         [("disconnect", "14:0", "129:0")])

    def test_missing_ports_fail_before_any_change_plan(self):
        with self.assertRaisesRegex(midi.RoutingError, "launchpad"):
            midi.changes(dict(self.selected, launchpad=None), set(), "direct")

    def test_direct_input_does_not_require_a_virtual_bus(self):
        self.assertEqual(midi.changes(dict(self.selected, bus=None), set(), "direct"),
                         [("connect", "20:0", "129:0")])

    def test_direct_mode_removes_both_translated_input_paths(self):
        links = {("14:0", "129:0"), ("128:1", "129:0"), ("128:1", "14:0")}
        self.assertEqual(midi.changes(self.selected, links, "direct", bome_outputs=["128:1"]),
                         [("connect", "20:0", "129:0"), ("disconnect", "128:1", "129:0"),
                          ("disconnect", "14:0", "129:0")])

    def test_bome_project_requires_both_input_and_output_subscriptions(self):
        bome = {"inputs": ["128:0"], "outputs": ["128:1"]}
        self.assertEqual(midi.project_connections(self.selected, bome, {("20:0", "128:0")}),
                         {"input_connected": True, "output_connected": False})
        self.assertTrue(all(midi.project_connections(self.selected, bome,
                         {("20:0", "128:0"), ("128:1", "14:0")}).values()))


class MidiOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.runtime, self.proc = base / "checkout", base / "runtime", base / "proc"
        for path in (self.root, self.runtime, self.proc):
            path.mkdir()
        self.prefix = base / "prefix"
        self.prefix.mkdir()
        log = base / "log/session.log"
        log.parent.mkdir()
        self.session = ["4100", "100", str(self.prefix), str(self.root), str(log)]
        self.owner = ["4110", "110", "process-group-v1"]
        (self.runtime / "session.state").write_text("\n".join(self.session))
        (self.runtime / "ableton.state").write_text("\n".join(self.owner))
        self.add_process(4100, 100, 4100, ["bash", str(self.root / "bin/waydaw"), "start"])
        self.add_process(4110, 110, 4110, ["python3", str(self.root / "config/session-worker.py"),
                                        "run", str(self.runtime / "ableton.state")])
        self.add_process(4200, 120, 4110, ["C:\\ProgramData\\Ableton\\Live 12 Suite\\Program\\Ableton Live 12 Suite.exe"])

    def add_process(self, pid, birth, group, argv, prefix=None):
        node = self.proc / str(pid)
        node.mkdir(exist_ok=True)
        fields = ["S", "1", str(group)] + ["0"] * 16 + [str(birth)]
        (node / "stat").write_text(f"{pid} (fixture) " + " ".join(fields))
        (node / "cmdline").write_bytes(b"\0".join(os.fsencode(s) for s in argv))
        (node / "environ").write_bytes(os.fsencode("WINEPREFIX=" + str(prefix or self.prefix)))

    def test_matching_guarded_application(self):
        result = midi.guarded_application(self.root, self.runtime, proc_root=self.proc)
        self.assertEqual((result["pid"], result["birth"]), (4200, 120))

    def test_reused_supervisor_is_rejected(self):
        self.session[1] = "999"
        (self.runtime / "session.state").write_text("\n".join(self.session))
        with self.assertRaisesRegex(midi.RoutingError, "reused"):
            midi.guarded_application(self.root, self.runtime, proc_root=self.proc)

    def test_cancelled_session_is_rejected(self):
        (Path(self.session[4]).parent / "cancelled").touch()
        with self.assertRaisesRegex(midi.RoutingError, "stopping"):
            midi.guarded_application(self.root, self.runtime, proc_root=self.proc)

    def test_unrelated_worker_command_is_rejected(self):
        (self.proc / "4110/cmdline").write_bytes(b"python3\0unrelated.py")
        with self.assertRaisesRegex(midi.RoutingError, "worker"):
            midi.guarded_application(self.root, self.runtime, proc_root=self.proc)

    def test_application_in_another_prefix_is_rejected(self):
        (self.proc / "4200/environ").write_bytes(b"WINEPREFIX=/other/prefix")
        with self.assertRaisesRegex(midi.RoutingError, "one running"):
            midi.guarded_application(self.root, self.runtime, proc_root=self.proc)


class MidiCommandTests(unittest.TestCase):
    def test_missing_bome_project_prevents_route_mutation_and_ready_check(self):
        ports, _ = midi.parse_ports(INVENTORY)
        with patch.object(midi, "snapshot", return_value=(ports, {("14:0", "129:0")})), \
             patch.object(midi, "guarded_application", return_value={"pid": 4200, "owner": ["4120", "1", "process-group-v1"]}), \
             patch.object(midi.subprocess, "run") as run, patch("builtins.print"):
            self.assertEqual(midi.main(["check"]), 1)
            with self.assertRaisesRegex(midi.RoutingError, "Bome project ports"):
                midi.main(["route", "--apply"])
            run.assert_not_called()

    def test_inspect_accepts_ableton_only_session_and_uses_runtime_fallback(self):
        ports, links = midi.parse_ports(INVENTORY)
        with tempfile.TemporaryDirectory() as state, \
             patch.dict(os.environ, {"XDG_RUNTIME_DIR": "", "XDG_STATE_HOME": state}), \
             patch.object(midi, "snapshot", return_value=(ports, links)), \
             patch.object(midi, "guarded_application", return_value={"pid": 4200}) as discover, \
             patch("builtins.print"):
            self.assertEqual(midi.main(["inspect"]), 0)
            discover.assert_called_once_with(ROOT, Path(state) / "waydaw")

    def test_dry_run_and_failed_check_do_not_change_alsa(self):
        ports, links = midi.parse_ports(INVENTORY)
        with patch.object(midi, "snapshot", return_value=(ports, links)), \
             patch.object(midi, "guarded_application", return_value={"pid": 4200, "owner": ["4120", "1", "process-group-v1"]}), \
             patch.object(midi.subprocess, "run") as run, patch("builtins.print"):
            self.assertEqual(midi.main(["route"]), 0)
            self.assertEqual(midi.main(["check"]), 1)
            run.assert_not_called()

    def test_session_change_aborts_before_connecting(self):
        ports, links = midi.parse_ports(INVENTORY)
        links |= {("20:0", "128:0"), ("128:1", "14:0")}
        with patch.object(midi, "bome_ports", return_value={"inputs": ["128:0"], "outputs": ["128:1"]}), \
             patch.object(midi, "snapshot", return_value=(ports, links)), \
             patch.object(midi, "guarded_application", side_effect=[{"pid": 4200}, {"pid": 4300, "owner": ["4120", "1", "process-group-v1"]}, {"pid": 9999}]), \
             patch.object(midi.subprocess, "run") as run, patch("builtins.print"):
            with self.assertRaisesRegex(midi.RoutingError, "Session changed"):
                midi.main(["route", "--apply"])
            run.assert_not_called()

    def test_port_renumbering_aborts_before_connecting(self):
        ports, links = midi.parse_ports(INVENTORY)
        changed, _ = midi.parse_ports(INVENTORY.replace("client 14:", "client 34:"))
        links |= {("20:0", "128:0"), ("128:1", "14:0")}
        with patch.object(midi, "bome_ports", return_value={"inputs": ["128:0"], "outputs": ["128:1"]}), \
             patch.object(midi, "snapshot", side_effect=[(ports, links), (changed, links)]), \
             patch.object(midi, "guarded_application", return_value={"pid": 4200, "owner": ["4120", "1", "process-group-v1"]}), \
             patch.object(midi.subprocess, "run") as run, patch("builtins.print"):
            with self.assertRaisesRegex(midi.RoutingError, "ports changed"):
                midi.main(["route", "--apply"])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
