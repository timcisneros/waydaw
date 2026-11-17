"""Behavior tests in a disposable HOME and checkout, using fake host services."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GuardedSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="waydaw-test-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "checkout with spaces"
        for name in ("bin", "config"):
            shutil.copytree(ROOT / name, self.root / name)
        self.home = base / "home"
        self.prefix = self.home / "WinePrefixes/ableton12-winebase-protonexp-test"
        self.working = self.home / "WinePrefixes/ableton12"
        for prefix in (self.prefix, self.working):
            system = prefix / "drive_c/windows/system32"
            system.mkdir(parents=True)
            (system / "d3d11.dll").write_bytes(b"fixture d3d11")
            (system / "dxgi.dll").write_bytes(b"fixture dxgi")
            (system / "d3d10core.dll").write_bytes(b"fixture d3d10core")
        self.program = self.prefix / "drive_c/ProgramData/Ableton/Live 12 Suite/Program"
        self.program.mkdir(parents=True)
        (self.program / "Ableton Live 12 Suite.exe").touch()
        bome = self.prefix / "drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe"
        bome.parent.mkdir(parents=True)
        bome.touch()
        shim = self.root / ".local-tools/ableton-sizing-shim/version.dll"
        shim.parent.mkdir(parents=True)
        shim.write_bytes(b"MZfixture shim")
        helper = self.root / ".local-tools/waydaw-launch/wait-bome.exe"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b"MZfixture readiness helper")
        # Fixture hashes replace the recorded baseline only inside this copy.
        manifest = self.root / "config/validated-runtime.sh"
        manifest.write_text(manifest.read_text() + "\n" + "\n".join(
            f"WAYDAW_{key}_SHA256={hashlib.sha256(value).hexdigest()}"
            for key, value in (("D3D11", b"fixture d3d11"), ("DXGI", b"fixture dxgi"),
                               ("D3D10CORE", b"fixture d3d10core"))
        ) + "\n")
        self.fake = base / "fake-bin"
        self.fake.mkdir()
        self.events = base / "events"
        self.stop = base / "wine-stop"
        self.bome_stop = base / "bome-stop"
        self.env = {
            **os.environ,
            "HOME": str(self.home), "USER": "fixture",
            "PATH": str(self.fake) + ":/usr/bin:/bin",
            "XDG_RUNTIME_DIR": str(base / "runtime"),
            "XDG_STATE_HOME": str(base / "state"),
            "XDG_DATA_HOME": str(base / "data"),
            "XDG_CONFIG_HOME": str(base / "config"),
            "DISPLAY": ":99", "WAYLAND_DISPLAY": "wayland-fixture",
            "TEST_EVENTS": str(self.events), "TEST_STOP": str(self.stop),
            "TEST_BOME_STOP": str(self.bome_stop),
            "TEST_KWIN": str(base / "kwin-loaded"),
            "TEST_BRIDGE": str(base / "bridge"),
        }
        for key in list(self.env):
            if key.startswith("WAYDAW_"):
                del self.env[key]
        self.processes = []
        self.releases = set()
        # Registered after temp.cleanup so processes are gone before deletion.
        self.addCleanup(self.finish_fixture)
        self.script(self.fake / "pw-jack", 'printf "pw-jack:%s\\n" "$*" >> "$TEST_EVENTS"\nexec "$@"')
        self.script(self.fake / "systemctl", 'exit "${TEST_PIPEWIRE_FAIL:-0}"')
        self.script(self.fake / "notify-send", 'printf "notification:%s\\n" "$*" >> "$TEST_EVENTS"')
        self.script(self.fake / "pgrep", '[[ "${TEST_BRIDGE_EXISTING:-0}" == 1 ]]')
        self.script(self.fake / "a2jmidid", '''
printf '%s' "$$" > "$TEST_BRIDGE"
trap 'rm -f "$TEST_BRIDGE"; exit 0' TERM INT
while :; do sleep 0.05; done
''')
        self.script(self.fake / "busctl", '''
printf 'busctl:%s\\n' "$*" >> "$TEST_EVENTS"
case "$*" in
  *isScriptLoaded*) [[ -e "$TEST_KWIN" ]] && echo 'b true' || echo 'b false' ;;
  *unloadScript*) rm -f "$TEST_KWIN"; echo 'b true' ;;
  *loadScript*) [[ "${TEST_CONTROLLER_FAIL:-0}" != 1 ]] || exit 1; touch "$TEST_KWIN"; echo 'i 7' ;;
esac
''')
        runner = self.root / ".local-runners/kron4ek-proton-exp-11.0/bin"
        runner.mkdir(parents=True)
        self.runner = runner
        self.script(runner / "winepath", 'shift; printf "%s\\n" "$@"')
        self.script(runner / "wine", '''
if [[ "$1" == *wait-bome.exe ]]; then
  ready="$2"
  shift 3
else
  ready=""
fi
printf 'wine:%s:%s:overrides=%s:wayland=%s\\n' "$WINEPREFIX" "$*" "${WINEDLLOVERRIDES:-}" "${WAYLAND_DISPLAY:-unset}" >> "$TEST_EVENTS"
[[ "$1" != reg ]] || exit 91
if [[ "$1" == *MIDITranslator* ]]; then
  if [[ -n "${TEST_BOME_INITIALIZING:-}" ]]; then
    touch "$TEST_BOME_INITIALIZING"
    while [[ ! -e "$TEST_BOME_RELEASE" ]]; do sleep 0.02; done
  fi
  if [[ "${TEST_BOME_DRIFT:-0}" == 1 ]]; then
    printf 'runner-prefix-updated' > "$WINEPREFIX/drive_c/windows/system32/d3d11.dll"
  fi
  [[ "${TEST_BOME_EXIT:-hold}" == hold ]] || exit "$TEST_BOME_EXIT"
  [[ -z "$ready" ]] || printf 'ready\\n' > "$ready"
  if [[ "${TEST_BOME_RUNTIME_EXIT:-hold}" != hold ]]; then
    while [[ ! -e "$TEST_BOME_STOP" && ! -e "$TEST_STOP" ]]; do sleep 0.03; done
    [[ ! -e "$TEST_BOME_STOP" ]] || exit "$TEST_BOME_RUNTIME_EXIT"
  fi
elif [[ "${TEST_WINE_HOLD:-0}" != 1 ]]; then
  exit "${TEST_WINE_EXIT:-0}"
fi
while [[ ! -e "$TEST_STOP" ]]; do sleep 0.05; done
exit "${TEST_WINE_FINAL_EXIT:-0}"
''')
        self.script(runner / "wineserver", '''
printf 'wineserver:%s:%s\\n' "$WINEPREFIX" "$*" >> "$TEST_EVENTS"
[[ "$1" != -k ]] || touch "$TEST_STOP"
exit "${TEST_CLEANUP_FAIL:-0}"
''')

    @staticmethod
    def script(path, text):
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + text + "\n")
        path.chmod(0o755)

    def run_command(self, *args, env=None, executable="waydaw"):
        return subprocess.run(
            [str(self.root / "bin" / executable), *args],
            env={**self.env, **(env or {})}, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=12,
        )

    def event_text(self):
        return self.events.read_text() if self.events.exists() else ""

    def session_log_text(self):
        logs = Path(self.env["XDG_STATE_HOME"]) / "waydaw/logs"
        return "\n".join(path.read_text() for path in sorted(logs.glob("*/session.log")))

    def snapshot(self):
        return {str(p.relative_to(self.home)): p.read_bytes()
                for p in self.home.rglob("*") if p.is_file()}

    def wait_for(self, predicate, process=None):
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline:
            if predicate():
                return
            if process is not None and process.poll() is not None:
                self.fail("Supervisor exited early: " + process.communicate(timeout=2)[0])
            time.sleep(0.03)
        self.fail("Timed out waiting for fixture state")

    def launch(self, *args, relative=False, **env):
        process = subprocess.Popen(
            ["./bin/waydaw" if relative else str(self.root / "bin/waydaw"), "start", *args],
            env={**self.env, **env}, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=self.root,
        )
        self.processes.append(process)
        for key in ("TEST_RELEASE", "TEST_BOME_RELEASE"):
            if key in env:
                self.releases.add(Path(env[key]))
        return process

    def start_command(self, *args, env=None):
        process = subprocess.Popen([str(self.root / "bin/waydaw"), *args],
                                   env={**self.env, **(env or {})}, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.processes.append(process)
        return process

    @staticmethod
    def process_birth(pid):
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
            return fields[19] if fields[0] not in ("Z", "X") else None
        except (OSError, IndexError):
            return None

    def fixture_processes(self):
        # Exact environment markers identify only this disposable fixture,
        # including orphaned workers whose receipt was lost or corrupted.
        markers = {os.fsencode("TEST_EVENTS=" + str(self.events)),
                   os.fsencode("HOME=" + str(self.home))}
        owned = {}
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                environment = set((entry / "environ").read_bytes().split(b"\0"))
                birth = self.process_birth(entry.name)
                if markers <= environment and birth is not None:
                    owned[int(entry.name)] = birth
            except OSError:
                continue
        return owned

    def finish_fixture(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        self.stop.touch()
        for release in self.releases:
            release.touch()
        for process in self.processes:
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        if list(directory.glob("*.state")):
            try:
                self.run_command("stop")
            except subprocess.TimeoutExpired:
                pass
        # Independent fallback: a regression in production recovery must not
        # leave fixture children alive or make teardown wait on their pipes.
        deadline = time.monotonic() + 2
        while owned := self.fixture_processes():
            for pid, birth in owned.items():
                if self.process_birth(pid) == birth:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if time.monotonic() >= deadline:
                self.fail(f"Fixture processes survived teardown: {list(owned)}")
            time.sleep(0.03)
        for process in self.processes:
            if process.stdout is not None and process.stdout.closed:
                process.stdout = None
            process.communicate(timeout=2)


    def test_sourcing_config_is_read_only(self):
        (self.prefix / "drive_c/windows/system32/d3d11.dll").write_bytes(b"drifted")
        before = self.snapshot()
        result = subprocess.run(["bash", "-c", 'source "$1/config/env"', "bash", str(self.root)],
                                env={**self.env, "WAYDAW_ABLETON_RUNNER": "proton-exp"},
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.events.exists())



















    def test_atomic_preferences_update_preserves_hardlinked_source_and_first_backup(self):
        preferences = self.prefix / "drive_c/users/steamuser/AppData/Roaming/Ableton/Live 12/Preferences"
        preferences.mkdir(parents=True)
        original = struct.pack("<iiiii", 3, 0, 0, 1280, 1096) + b"\x01" + b"\0" * 7
        source = self.working / "protected-preferences"
        source.write_bytes(original)
        source.chmod(0o640)
        cfg = preferences / "Preferences.cfg"
        cfg.hardlink_to(source)
        for height in (1026, 1000):
            result = self.run_command(str(cfg), str(height), executable="ableton-proton-normalize-placement")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(struct.unpack_from("<i", cfg.read_bytes(), 16)[0], height)
            self.assertEqual(cfg.stat().st_mode & 0o777, 0o640)
            self.assertEqual((preferences / "Preferences.cfg.bak-normalize").read_bytes(), original)
        self.assertEqual(list(preferences.glob(".Preferences.cfg-*")), [])






























    def gate_launcher(self, name):
        gate = self.home / "launcher-waiting"
        release = self.home / "launcher-release"
        self.script(self.fake / "pw-jack", f'''
if [[ "$1" == */bin/{name} ]]; then
  touch "$TEST_GATE"
  while [[ ! -e "$TEST_RELEASE" ]]; do sleep 0.02; done
fi
exec "$@"
''')
        return gate, release

    def assert_no_launch_after_stop(self, process, release):
        try:
            result = self.run_command("stop")
            self.assertEqual(result.returncode, 0, result.stdout)
        finally:
            release.touch()
        process.communicate(timeout=4)
        time.sleep(0.2)  # Release the hostile fixture after Stop has returned.
        self.assertNotIn("wine:", self.event_text())
        self.assertFalse(Path(self.env["TEST_KWIN"]).exists())
        self.assertIn("session=stopped", self.run_command("status").stdout)

























    def test_cleanup_accepts_an_already_stopped_wineserver(self):
        server = self.root / ".local-runners/kron4ek-proton-exp-11.0/bin/wineserver"
        self.script(server, '[[ "$1" != -k ]] || exit 1\nexit 0')
        result = self.run_command(executable="ableton-proton-cleanup")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("cleanup_exit=0", result.stdout)

    def test_cleanup_reports_unexpected_termination_failure(self):
        server = self.root / ".local-runners/kron4ek-proton-exp-11.0/bin/wineserver"
        self.script(server, '[[ "$1" != -k ]] || exit 2\nexit 0')
        result = self.run_command(executable="ableton-proton-cleanup")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("termination failed with exit 2", result.stdout)

    def test_wineasio_check_uses_selected_runner_for_registry_queries(self):
        self.script(self.fake / "find", "exit 0")
        self.script(self.fake / "wine64", '''
printf 'unexpected-system-wine64\\n' >> "$TEST_EVENTS"
exit 99
''')
        result = self.run_command(
            executable="wineasio-check",
            env={"WAYDAW_ABLETON_RUNNER": "proton-exp"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        runner = self.root / ".local-runners/kron4ek-proton-exp-11.0/bin/wine"
        self.assertIn(f"WINE64={runner}", result.stdout)
        self.assertIn(f"wine:{self.prefix}:reg query", self.event_text())
        self.assertNotIn("unexpected-system-wine64", self.event_text())















if __name__ == "__main__":
    unittest.main()
