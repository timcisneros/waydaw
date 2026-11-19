"""Verify that the disposable control cannot proceed without an external grant."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
import os
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class RealtimeBudgetControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / "rt-budget-transition"
        subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "validation/rt-budget-transition.c"), "-o", str(cls.binary)],
                       check=True, capture_output=True)
        source = Path(cls.temp.name) / "protocol-child.c"
        source.write_text('''
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    int target = getpid() + (argc > 1 && !strcmp(argv[1], "forge"));
    printf("ready 0 %d %d 0\\n", target, target);
    fflush(stdout);
    for (;;) pause();
}
''')
        cls.protocol_child = Path(cls.temp.name) / "protocol-child"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(source), "-o", str(cls.protocol_child)], check=True, capture_output=True)
        spec = importlib.util.spec_from_file_location("rt_transition", ROOT / "validation/rt-budget-transition.py")
        cls.driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.driver)

    def test_running_child_expires_without_a_grant(self):
        result = subprocess.run([str(self.binary), "ordinary-block", "running"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertTrue(result.stdout.startswith("ready 0 "))

    def test_waiting_child_stops_when_its_controller_closes_input(self):
        result = subprocess.run([str(self.binary), "rr-block", "waiting"], input="",
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertTrue(result.stdout.startswith("ready 0 "))

    def test_forged_thread_is_rejected_before_any_grant(self):
        rt = SimpleNamespace(MakeThreadRealtimeWithPID=lambda *a, **k: self.fail("Unexpected grant"))
        dbus = SimpleNamespace(UInt64=int, UInt32=int)
        result = self.driver.compare(self.protocol_child, "running", "forge", rt, dbus)
        self.assertIn("another process/thread", result["error"])
        self.assertFalse(result["grants"])
        self.assertTrue(result["controller_killed"])
        with self.assertRaises(ProcessLookupError):
            os.kill(result["pid"], 0)

    def test_failed_request_stops_and_reaps_only_its_child(self):
        def disconnect(*args, **kwargs):
            raise RuntimeError("Injected lost reply")
        rt = SimpleNamespace(MakeThreadRealtimeWithPID=disconnect)
        result = self.driver.compare(self.protocol_child, "running", "valid", rt,
                                     SimpleNamespace(UInt64=int, UInt32=int))
        self.assertEqual(result["error"], "Injected lost reply")
        self.assertFalse(result["grants"])
        self.assertTrue(result["controller_killed"])
        with self.assertRaises(ProcessLookupError):
            os.kill(result["pid"], 0)


if __name__ == "__main__":
    unittest.main()
