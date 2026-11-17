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
if [[ "${TEST_AUTH_RECEIVER:-0}" == 1 && "$1" == *'Ableton Live 12'* ]]; then
  if [[ $# == 1 ]]; then
    export WINELOADERNOEXEC=1 WINESERVERSOCKET=123 WINEPRELOADRESERVE=fixture
  fi
  application="$1"
  shift
  export PYTHONHOME=/usr
  exec -a "$application" /usr/bin/python3 "$TEST_AUTH_RECEIVER_SCRIPT" "$application" "$@"
fi
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

    def authorization_receiver(self):
        receiver = self.fake / "authorization-receiver.py"
        receiver.write_text('''import json, os, sys, time
from pathlib import Path
events = Path(os.environ["TEST_EVENTS"])
if sys.argv[2:]:
    gate = os.environ.get("TEST_AUTH_GATE")
    if gate:
        Path(gate).touch()
        while not Path(os.environ["TEST_AUTH_RELEASE"]).exists():
            time.sleep(0.02)
    with events.open("a") as output:
        output.write("authorization_received:" + json.dumps({
            "arguments": sys.argv[2:], "prefix": os.environ["WINEPREFIX"],
            "overrides": os.environ.get("WINEDLLOVERRIDES"),
            "wayland": os.environ.get("WAYLAND_DISPLAY"),
            "wine_internal": {key: os.environ.get(key) for key in ["WINELOADERNOEXEC", "WINESERVERSOCKET", "WINEPRELOADRESERVE"]},
        }) + "\\n")
    raise SystemExit(int(os.environ.get("TEST_AUTH_EXIT", "0")))
with events.open("a") as output:
    output.write("authorization_receiver_ready\\n")
while not Path(os.environ["TEST_STOP"]).exists():
    time.sleep(0.03)
''')
        return {"TEST_AUTH_RECEIVER": "1", "TEST_AUTH_RECEIVER_SCRIPT": str(receiver)}

    def test_authorization_callback_uses_running_guarded_instance_and_keeps_tokens_out_of_logs(self):
        process = self.launch("--with-bome", **self.authorization_receiver())
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        owners = {name: (runtime / (name + ".state")).read_bytes() for name in ("ableton", "bome")}
        before = self.snapshot()
        marker = self.home / "must-not-execute"
        uri = f"ableton://authorize?license_id=fixture&session_id=private-fixture-$(touch {marker})"
        result = self.run_command("authorize", uri, executable="waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.wait_for(lambda: not (runtime / "authorization.state").exists(), process)
        event = next(line.removeprefix("authorization_received:") for line in self.event_text().splitlines()
                     if line.startswith("authorization_received:"))
        received = json.loads(event)
        self.assertEqual(received["arguments"], [uri])
        self.assertEqual(received["prefix"], str(self.prefix))
        self.assertIn("d3d11,dxgi,d3d10core=n", received["overrides"])
        self.assertIn("version=n,b", received["overrides"])
        self.assertIsNone(received["wayland"])
        self.assertTrue(all(value is None for value in received["wine_internal"].values()))
        self.assertFalse(marker.exists())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({name: (runtime / (name + ".state")).read_bytes() for name in owners}, owners)
        self.assertEqual(self.event_text().count("authorization_receiver_ready"), 1)
        self.assertIsNone(process.poll())
        self.assertNotIn(uri, result.stdout + self.session_log_text())
        for log in (Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop").glob("*.log"):
            self.assertNotIn(uri, log.read_text())
        queue = Path((runtime / "session.state").read_text().splitlines()[4]).parent / "authorization"
        self.assertEqual(list(queue.iterdir()), [])
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_authorization_file_uri_reaches_guarded_ableton_without_preparation(self):
        path = self.home / "Downloads/official authorization.auz"
        path.parent.mkdir()
        path.write_bytes(b"fixture authorization file")
        process = self.launch(**self.authorization_receiver())
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        before = self.snapshot()
        result = self.run_command("authorize", path.as_uri())
        self.assertEqual(result.returncode, 0, result.stdout)
        event = next(line.removeprefix("authorization_received:") for line in self.event_text().splitlines()
                     if line.startswith("authorization_received:"))
        self.assertEqual(json.loads(event)["arguments"], [str(path)])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.event_text().count("authorization_receiver_ready"), 1)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_authorization_follows_the_live_custom_prefix_without_browser_environment(self):
        custom = self.prefix.with_name("selected copied prefix")
        self.prefix.rename(custom)
        self.prefix = custom
        process = self.launch(**self.authorization_receiver(), WAYDAW_ABLETON_RUNNER_PREFIX=str(custom))
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        result = self.run_command("authorize", "ableton://authorize?session_id=fixture-custom")
        self.assertEqual(result.returncode, 0, result.stdout)
        event = next(line.removeprefix("authorization_received:") for line in self.event_text().splitlines()
                     if line.startswith("authorization_received:"))
        self.assertEqual(json.loads(event)["prefix"], str(custom))
        self.assertIsNone(process.poll())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_authorization_does_not_start_wine_without_a_session(self):
        before = self.snapshot()
        result = self.run_command("authorize", "ableton://authorize?session_id=private-fixture")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Open WayDAW Ableton", result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.event_text(), "")
        self.assertFalse(Path(self.env["XDG_RUNTIME_DIR"]).exists())

    def test_authorization_rejects_unrelated_requests_and_dry_run_without_delivery(self):
        process = self.launch(**self.authorization_receiver())
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        for value in ["https://example.invalid/authorize?private-fixture", "ableton://open?file=x",
                      "file://remote/Unlock.auz", "ableton://private-fixture\u2100/authorize?token=x"]:
            with self.subTest(value=value):
                result = self.run_command("authorize", value)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn(value, result.stdout)
        result = self.run_command("authorize", "--dry-run", "ableton://authorize?session_id=private-fixture")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("authorization_received:", self.event_text())
        self.assertIsNone(process.poll())
        self.stop.touch()
        process.communicate(timeout=8)

    def test_authorization_failure_keeps_ableton_open_and_does_not_log_the_callback(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        process = self.launch(**self.authorization_receiver(), TEST_AUTH_EXIT="17")
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        uri = "ableton://authorize?session_id=private-fixture-failure"
        result = self.run_command("authorize", uri, executable="waydaw-desktop")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(uri, result.stdout + self.session_log_text())
        self.assertIn("session=running", self.run_command("status").stdout)
        self.assertIsNone(process.poll())
        self.assertNotIn("wineserver:", self.event_text())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_authorization_requires_a_callback_capable_session(self):
        process = self.launch(**self.authorization_receiver())
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        queue = Path((runtime / "session.state").read_text().splitlines()[4]).parent / "authorization"
        queue.rmdir()
        result = self.run_command("authorize", "ableton://authorize?session_id=fixture")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Restart", result.stdout)
        self.assertNotIn("authorization_received:", self.event_text())
        self.stop.touch()
        process.communicate(timeout=8)

    def test_authorization_never_bootstraps_a_missing_ableton_process(self):
        helper = self.root / "config/ableton-authorization.py"
        helper.write_text(helper.read_text().replace("time.monotonic() + 10", "time.monotonic() + 0.2"))
        process = self.launch(TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        before = self.event_text().count("wine:")
        result = self.run_command("authorize", "ableton://authorize?session_id=fixture")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.event_text().count("wine:"), before)
        self.assertIsNone(process.poll())
        self.stop.touch()
        process.communicate(timeout=8)

    def test_stop_cancels_authorization_delivery_and_clears_private_requests(self):
        gate, release = self.home / "authorization-gate", self.home / "authorization-release"
        self.releases.add(release)
        process = self.launch(**self.authorization_receiver(), TEST_AUTH_GATE=str(gate), TEST_AUTH_RELEASE=str(release))
        self.wait_for(lambda: "authorization_receiver_ready" in self.event_text(), process)
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        queue = Path((runtime / "session.state").read_text().splitlines()[4]).parent / "authorization"
        callback = self.start_command("authorize", "ableton://authorize?session_id=private-fixture-stop")
        self.wait_for(gate.exists, process)
        queued = self.start_command("authorize", "ableton://authorize?session_id=private-fixture-queued")
        self.wait_for(lambda: len(list(queue.glob("*.request"))) == 1, process)
        stopped = self.run_command("stop")
        self.assertEqual(stopped.returncode, 0, stopped.stdout)
        output = callback.communicate(timeout=8)[0]
        self.assertNotEqual(callback.returncode, 0, output)
        output = queued.communicate(timeout=8)[0]
        self.assertNotEqual(queued.returncode, 0, output)
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 143)
        release.touch()
        self.assertNotIn("authorization_received:", self.event_text())
        self.assertEqual(list(queue.glob("*.request")), [])
        self.assertFalse((runtime / "authorization.state").exists())
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_desktop_authorization_handlers_are_redirected_and_restored(self):
        applications = Path(self.env["XDG_DATA_HOME"]) / "applications"
        applications.mkdir(parents=True)
        originals = {}
        for name, mime, field in [("wine-protocol-ableton.desktop", "x-scheme-handler/ableton", "%u"),
                                  ("wine-extension-auz.desktop", "application/x-wine-extension-auz", "%f")]:
            original = f"[Desktop Entry]\nType=Application\nName=Ableton\nMimeType={mime};\nExec=env WINEPREFIX=legacy wine start {field}\nNoDisplay=true\n"
            (applications / name).write_text(original)
            originals[name] = original
        for _ in range(2):
            result = self.run_command(executable="install-waydaw-desktop")
            self.assertEqual(result.returncode, 0, result.stdout)
        for name, original in originals.items():
            installed = (applications / name).read_text()
            self.assertIn('waydaw-desktop" authorize ', installed)
            self.assertNotIn("WINEPREFIX=legacy", installed)
            self.assertIn("MimeType=", installed)
            if shutil.which("desktop-file-validate"):
                validated = subprocess.run(["desktop-file-validate", str(applications / name)], capture_output=True, text=True)
                self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)
        handler = applications / "com.timcis.WayDAW.Authorization.desktop"
        self.assertIn("authorize %u", handler.read_text())
        self.assertIn("NoDisplay=true", handler.read_text())
        record = json.loads((Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop-install.json").read_text())
        self.assertEqual(record["original_authorization"], originals)
        for name, original in originals.items():
            (applications / name).write_text(original.replace("legacy", "regenerated"))
        self.assertEqual(self.run_command(executable="install-waydaw-desktop").returncode, 0)
        self.assertEqual(self.run_command("--uninstall", executable="install-waydaw-desktop").returncode, 0)
        self.assertFalse(handler.exists())
        for name, original in originals.items():
            self.assertEqual((applications / name).read_text(), original)

    def test_desktop_authorization_migrates_old_records_and_preserves_independent_edits(self):
        applications = Path(self.env["XDG_DATA_HOME"]) / "applications"
        applications.mkdir(parents=True)
        path = applications / "wine-protocol-ableton.desktop"
        original = '[Desktop Entry]\nType=Application\nName=Ableton\nMimeType=x-scheme-handler/ableton;\nExec=wine start %u\n'
        path.write_text(original)
        state = Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop-install.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"version": 1, "applications": str(applications),
                                     "original_ableton": None, "installed": {}}))
        self.assertEqual(self.run_command(executable="install-waydaw-desktop").returncode, 0)
        edited = path.read_text() + 'X-User-Setting=keep\n'
        path.write_text(edited)
        result = self.run_command("--uninstall", executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(path.read_text(), edited)
        self.assertEqual(self.run_command(executable="install-waydaw-desktop").returncode, 0)
        self.assertEqual(json.loads(state.read_text())["original_authorization"][path.name], original)
        self.assertEqual(self.run_command("--uninstall", executable="install-waydaw-desktop").returncode, 0)
        self.assertEqual(path.read_text(), original)

    def test_dry_run_and_print_do_not_mutate_or_invoke_services(self):
        (self.prefix / "drive_c/windows/system32/d3d11.dll").write_bytes(b"drifted")
        seed = self.prefix / "drive_c/users/fixture/AppData/Roaming/Ableton/Live 12/Preferences/Preferences.cfg"
        seed.parent.mkdir(parents=True)
        seed.write_bytes(b"seed")
        (self.prefix / "drive_c/users/steamuser/AppData/Roaming/Ableton/Live 12/Preferences").mkdir(parents=True)
        before = self.snapshot()
        for command in (("start", "--dry-run"), ("start", "--print-launch-config")):
            result = self.run_command(*command)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("sizing_shim=would_enable", result.stdout)
        result = self.run_command("--print-launch-config", executable="ableton-proton")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.events.exists())
        self.assertFalse((self.root / "logs").exists())

    def test_sourcing_config_is_read_only(self):
        (self.prefix / "drive_c/windows/system32/d3d11.dll").write_bytes(b"drifted")
        before = self.snapshot()
        result = subprocess.run(["bash", "-c", 'source "$1/config/env"', "bash", str(self.root)],
                                env={**self.env, "WAYDAW_ABLETON_RUNNER": "proton-exp"},
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.events.exists())

    def test_preflight_does_not_repair_drift_or_start_wine(self):
        (self.prefix / "drive_c/windows/system32/d3d11.dll").write_bytes(b"drifted")
        before = self.snapshot()
        result = self.run_command("check", "--with-bome")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preflight=passed", result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("wine:", self.event_text())
        self.assertNotIn("loadScript", self.event_text())

    def test_working_prefix_aliases_and_overlaps_are_rejected(self):
        alias = self.home / "alias"
        alias.symlink_to(self.working, target_is_directory=True)
        for path in (self.working, alias, self.working / "nested", self.working.parent):
            for command in ("start", "stop"):
                result = self.run_command(command, "--dry-run", env={"WAYDAW_ABLETON_RUNNER_PREFIX": str(path)})
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("overlapping", result.stdout)
        self.assertFalse(self.events.exists())

    def test_symlinked_system_directory_is_rejected(self):
        system = self.prefix / "drive_c/windows/system32"
        shutil.rmtree(system)
        system.symlink_to(self.working / "drive_c/windows/system32", target_is_directory=True)
        result = self.run_command("start", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("escapes", result.stdout)

    def test_missing_dependencies_and_unsafe_settings_block_launch(self):
        cases = [
            ({"DISPLAY": ""}, "XWayland"),
            ({"TEST_PIPEWIRE_FAIL": "1"}, "PipeWire"),
            ({"WAYDAW_ABLETON_KWIN_CONTROLLER": "0"}, "must be 1"),
            ({"WAYDAW_ABLETON_SIZING_SHIM": "0"}, "must be 1"),
            ({"WAYDAW_ABLETON_GRAPHICS": "wined3d"}, "requires DXVK"),
        ]
        for env, message in cases:
            result = self.run_command("start", env=env)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(message, result.stdout)
        self.assertNotIn("wine:", self.event_text())

    def test_missing_dlls_and_update_marker_block_launch(self):
        dll = self.prefix / "drive_c/windows/system32/d3d11.dll"
        dll.write_bytes(b"drift")
        (self.working / "drive_c/windows/system32/d3d11.dll").write_bytes(b"drift")
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no verified restore source", result.stdout)
        dll.write_bytes(b"fixture d3d11")
        (self.prefix / "drive_c/ProgramData/Ableton/.Live 12 Suite_updated").touch()
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("swap marker", result.stdout)
        self.assertNotIn("wine:", self.event_text())

    def test_missing_shim_and_runner_block_launch(self):
        shim = self.root / ".local-tools/ableton-sizing-shim/version.dll"
        shim.unlink()
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shim missing", result.stdout)
        (self.runner / "wine").unlink()
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wine not found", result.stdout)

    def test_bome_requires_readiness_helper_and_winepath(self):
        helper = self.root / ".local-tools/waydaw-launch/wait-bome.exe"
        helper.unlink()
        result = self.run_command("check", "--with-bome")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("readiness helper missing", result.stdout)
        helper.write_bytes(b"MZfixture helper")
        (self.runner / "winepath").unlink()
        result = self.run_command("check", "--with-bome")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("winepath is missing", result.stdout)
        self.assertNotIn("wine:", self.event_text())

    def test_controller_failure_blocks_wine_and_cleans_up(self):
        result = self.run_command("start", env={"TEST_CONTROLLER_FAIL": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("launch blocked", result.stdout)
        self.assertNotIn("wine:", self.event_text())
        self.assertIn("wineserver:" + str(self.prefix) + ":-k", self.event_text())

    def test_normal_exit_repairs_only_copy_and_propagates_status(self):
        before = {p.name: p.read_bytes() for p in (self.working / "drive_c/windows/system32").iterdir()}
        dll = self.prefix / "drive_c/windows/system32/d3d11.dll"
        dll.unlink()
        dll.symlink_to(self.working / "drive_c/windows/system32/d3d11.dll")
        # A correct symlink should also be safe: no write through the link.
        result = self.run_command("start", "--", "project with spaces.als", env={"TEST_WINE_EXIT": "7"})
        self.assertEqual(result.returncode, 7, result.stdout)
        self.assertIn("project with spaces.als", self.event_text())
        self.assertIn("overrides=d3d11,dxgi,d3d10core=n;version=n,b:wayland=unset", self.event_text())
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.working / "drive_c/windows/system32").iterdir()})
        self.assertFalse(Path(self.env["TEST_KWIN"]).exists())
        self.assertFalse((Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state").exists())

    def test_wine_exit_is_reported_when_a_descendant_keeps_stdout_open(self):
        self.script(self.runner / "wine", '''
bash -c 'trap "" TERM; while :; do sleep 0.05; done' &
exit 23
''')
        result = self.run_command("start")
        self.assertEqual(result.returncode, 23, result.stdout)
        self.assertIn("session_exit=23 cleanup_exit=0", self.session_log_text())
        self.assertFalse((Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state").exists())

    def test_local_pipewire_properties_are_data_and_reach_the_child(self):
        self.env.pop("PIPEWIRE_PROPS", None)
        profile = Path(self.env["XDG_CONFIG_HOME"]) / "waydaw/pipewire.properties"
        profile.parent.mkdir(parents=True)
        marker = self.home / "must-not-be-created"
        value = f'{{ rt.prio=0 custom.value="$(touch {marker})" }}'
        profile.write_text(value + "\n")
        self.script(self.fake / "pw-jack", '''
printf 'props:%s\\n' "${PIPEWIRE_PROPS:-}" >> "$TEST_EVENTS"
exec "$@"
''')
        result = self.run_command("start")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("props:" + value, self.event_text())
        self.assertFalse(marker.exists())

    def test_explicit_pipewire_properties_override_the_local_profile(self):
        profile = Path(self.env["XDG_CONFIG_HOME"]) / "waydaw/pipewire.properties"
        profile.parent.mkdir(parents=True)
        profile.write_text("{ rt.prio=0 }\n")
        result = self.run_command("check", env={"PIPEWIRE_PROPS": "{ rt.prio=12 }"})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("pipewire_properties={ rt.prio=12 }", result.stdout)

    def test_local_pipewire_configuration_reaches_the_child(self):
        self.env.pop("PIPEWIRE_CONFIG_DIR", None)
        profile = Path(self.env["XDG_CONFIG_HOME"]) / "waydaw/pipewire"
        profile.mkdir(parents=True)
        (profile / "jack.conf").write_text("context.properties = { loop.rt-prio = 0 }\n")
        self.script(self.fake / "pw-jack", '''
printf 'config-dir:%s\\n' "${PIPEWIRE_CONFIG_DIR:-}" >> "$TEST_EVENTS"
exec "$@"
''')
        result = self.run_command("start")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("config-dir:" + str(profile), self.event_text())
        explicit = self.run_command("check", env={"PIPEWIRE_CONFIG_DIR": "/explicit/config"})
        self.assertEqual(explicit.returncode, 0, explicit.stdout)
        self.assertIn("pipewire_config_dir=/explicit/config", explicit.stdout)

    def test_duplicate_launch_status_stop_and_restart(self):
        process = self.launch(relative=True, TEST_WINE_HOLD="1")
        self.wait_for(lambda: "wine:" in self.event_text(), process)
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already", result.stdout)
        self.assertIn("session=running", self.run_command("status").stdout)
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        output = process.communicate(timeout=8)[0]
        self.assertEqual(process.returncode, 143, output)
        self.assertIn("session=stopped", self.run_command("status").stdout)
        self.assertFalse(Path(self.env["TEST_BRIDGE"]).exists())
        self.stop.unlink()
        self.assertEqual(self.run_command("start").returncode, 0)

    def test_real_start_restores_drifted_dll_without_changing_source(self):
        target = self.prefix / "drive_c/windows/system32/d3d11.dll"
        source = self.working / "drive_c/windows/system32/d3d11.dll"
        target.write_bytes(b"drifted")
        before = source.read_bytes()
        result = self.run_command("start")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(target.read_bytes(), b"fixture d3d11")
        self.assertEqual(source.read_bytes(), before)

    def test_real_start_seeds_and_normalizes_only_copied_preferences(self):
        seed = self.prefix / "drive_c/users/fixture/AppData/Roaming/Ableton/Live 12/Preferences/Preferences.cfg"
        seed.parent.mkdir(parents=True)
        original = struct.pack("<iiiii", 3, 0, 0, 1280, 1096) + b"\x01" + b"\0" * 7
        seed.write_bytes(original)
        preferences = self.prefix / "drive_c/users/steamuser/AppData/Roaming/Ableton/Live 12/Preferences"
        preferences.mkdir(parents=True)
        result = self.run_command("start")
        self.assertEqual(result.returncode, 0, result.stdout)
        normalized = (preferences / "Preferences.cfg").read_bytes()
        self.assertEqual(struct.unpack_from("<iiiii", normalized), (1, 0, 0, 1280, 1026))
        self.assertEqual(normalized[20], 0)
        self.assertEqual(seed.read_bytes(), original)
        self.assertEqual((preferences / "Preferences.cfg.bak-normalize").read_bytes(), original)

    def test_escaping_preferences_symlink_is_rejected_before_write(self):
        outside = self.home / "outside-preferences"
        outside.write_bytes(b"unchanged")
        preferences = self.prefix / "drive_c/users/steamuser/AppData/Roaming/Ableton/Live 12/Preferences"
        preferences.mkdir(parents=True)
        (preferences / "Preferences.cfg").symlink_to(outside)
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Preferences.cfg escapes", result.stdout)
        self.assertEqual(outside.read_bytes(), b"unchanged")
        self.assertNotIn("wine:", self.event_text())

    def test_regression_backup_symlinks_are_rejected_without_writes(self):
        preferences = self.prefix / "drive_c/users/steamuser/AppData/Roaming/Ableton/Live 12/Preferences"
        preferences.mkdir(parents=True)
        original = struct.pack("<iiiii", 3, 0, 0, 1280, 1096) + b"\x01" + b"\0" * 7
        cfg = preferences / "Preferences.cfg"
        cfg.write_bytes(original)
        backup = preferences / "Preferences.cfg.bak-normalize"
        for existing in (False, True):
            with self.subTest(existing_target=existing):
                cfg.write_bytes(original)
                outside = self.working / f"backup-target-{existing}"
                if existing:
                    outside.write_bytes(b"untouched")
                backup.symlink_to(outside)
                try:
                    result = self.run_command("start")
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("backup must be a regular file", result.stdout)
                    self.assertEqual(cfg.read_bytes(), original)
                    self.assertTrue(backup.is_symlink())
                    self.assertEqual(outside.read_bytes() if outside.exists() else None,
                                     b"untouched" if existing else None)
                    self.assertNotIn("wine:", self.event_text())
                finally:
                    backup.unlink()

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

    def test_regression_stop_survives_disconnected_stdout(self):
        process = self.launch(TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        process.stdout.close()
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        process.wait(timeout=6)
        self.assertEqual(process.returncode, 143)
        self.assertIn("session=stopped", self.run_command("status").stdout)
        self.assertFalse(Path(self.env["TEST_KWIN"]).exists())
        logs = Path(self.env["XDG_STATE_HOME"]) / "waydaw/logs"
        output = next(logs.glob("*/session.log")).read_text()
        self.assertIn("session_exit=143 cleanup_exit=0", output)

    def test_regression_stop_survives_logger_exit(self):
        logger = self.home / "logger-pid"
        self.script(self.fake / "tee", '''
if [[ "$*" == *session.log* ]]; then printf '%s' "$$" > "$TEST_LOGGER"; fi
exec /usr/bin/tee "$@"
''')
        process = self.launch(TEST_WINE_HOLD="1", TEST_LOGGER=str(logger))
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        os.kill(int(logger.read_text()), signal.SIGTERM)
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        process.communicate(timeout=6)
        self.assertIn("session=stopped", self.run_command("status").stdout)
        self.assertFalse(Path(self.env["TEST_KWIN"]).exists())

    def test_logger_exit_during_startup_triggers_complete_cleanup(self):
        gate, release = self.home / "bome-starting", self.home / "bome-release"
        logger = self.home / "logger-pid"
        self.script(self.fake / "tee", '''
if [[ "$*" == *session.log* ]]; then printf '%s' "$$" > "$TEST_LOGGER"; fi
exec /usr/bin/tee "$@"
''')
        process = self.launch("--with-bome", TEST_BOME_INITIALIZING=str(gate),
                              TEST_BOME_RELEASE=str(release), TEST_LOGGER=str(logger))
        self.wait_for(gate.exists, process)
        logger_pid = int(logger.read_text())
        os.kill(logger_pid, signal.SIGTERM)
        self.wait_for(lambda: self.process_birth(logger_pid) is None)
        release.touch()
        process.communicate(timeout=6)
        self.assertEqual(process.returncode, 141)
        self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())
        self.assertIn("session_exit=141 cleanup_exit=0", self.session_log_text())
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_bome_uses_same_prefix_and_is_stopped(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.assertIn("wine:" + str(self.prefix) + ":" + str(self.prefix / "drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe"), self.event_text())
        bome_event = next(line for line in self.event_text().splitlines()
                          if line.startswith("wine:") and "MIDITranslator.exe" in line)
        self.assertIn("wayland=unset", bome_event)
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        process.communicate(timeout=8)

    def test_bome_preflight_and_launcher_accept_same_alternate_filename(self):
        directory = self.prefix / "drive_c/Program Files/Bome MIDI Translator Pro"
        executable = directory / "Bome MIDI Translator Pro.exe"
        (directory / "MIDITranslator.exe").rename(executable)
        before = self.snapshot()
        checked = self.run_command("check", "--with-bome")
        self.assertEqual(checked.returncode, 0, checked.stdout)
        self.assertEqual(self.snapshot(), before)
        launched = self.run_command(executable="bome", env={"WAYDAW_ABLETON_RUNNER": "proton-exp"})
        self.assertEqual(launched.returncode, 0, launched.stdout)
        self.assertIn("wine:" + str(self.prefix) + ":" + str(executable), self.event_text())

    def test_bome_preflight_rejects_executable_symlink_outside_prefix(self):
        executable = self.prefix / "drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe"
        outside = self.home / "outside-bome.exe"
        outside.touch()
        executable.unlink()
        executable.symlink_to(outside)
        checked = self.run_command("check", "--with-bome")
        self.assertNotEqual(checked.returncode, 0, checked.stdout)
        self.assertIn("Bome executable escapes", checked.stdout)
        self.assertNotIn("wine:", self.event_text())

    def test_bome_discovery_rejects_installers_and_backup_executables(self):
        (self.prefix / "drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe").unlink()
        directory = self.prefix / "drive_c/users/fixture/Downloads"
        directory.mkdir(parents=True)
        for name in ("MIDITranslatorPro1.9.2_Full_Windows.exe", "Bome MIDI Translator Pro Setup.exe", "MIDITranslator.backup.exe"):
            with self.subTest(name=name):
                candidate = directory / name
                candidate.touch()
                checked = self.run_command("check", "--with-bome")
                self.assertNotEqual(checked.returncode, 0, checked.stdout)
                launched = self.run_command(executable="bome", env={"WAYDAW_ABLETON_RUNNER": "proton-exp"})
                self.assertNotEqual(launched.returncode, 0, launched.stdout)
                self.assertNotIn("wine:", self.event_text())
                candidate.unlink()

    def test_bome_discovery_rejects_ambiguous_nonstandard_installations(self):
        (self.prefix / "drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe").unlink()
        for folder in ("Custom Bome", "Old Bome"):
            candidate = self.prefix / "drive_c" / folder / "MIDITranslator.exe"
            candidate.parent.mkdir()
            candidate.touch()
        result = self.run_command("check", "--with-bome")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Multiple Bome executables", result.stdout)
        self.assertNotIn("wine:", self.event_text())

    def test_bome_runtime_failure_warns_once_and_preserves_ableton(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="23")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        self.wait_for(lambda: "session=degraded" in self.run_command("status").stdout, process)
        self.wait_for(lambda: "notification:" in self.event_text(), process)
        status = self.run_command("status").stdout
        self.assertIn("bome=failed", status)
        self.assertIn("bome_exit=23", status)
        self.assertIsNone(process.poll())
        self.assertNotIn("wineserver:", self.event_text())
        self.assertIn("Ableton remains open", self.session_log_text())
        for _ in range(3):
            self.assertIn("session=degraded", self.run_command("status").stdout)
        self.assertEqual(self.event_text().count("notification:"), 1)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 23)
        self.assertIn("session_exit=23 cleanup_exit=0", self.session_log_text())
        self.assertIn("session=stopped", self.run_command("status").stdout)
        self.stop.unlink()
        self.assertEqual(self.run_command("start").returncode, 0)

    def test_bome_normal_quit_keeps_ableton_open_without_error_alert(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="0")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        self.wait_for(lambda: "bome=stopped" in self.run_command("status").stdout, process)
        self.assertIn("session=running", self.run_command("status").stdout)
        self.assertIsNone(process.poll())
        self.assertNotIn("notification:", self.event_text())
        self.assertNotIn("wineserver:", self.event_text())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_bome_runtime_failure_preserves_ableton_error_code(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_WINE_FINAL_EXIT="17", TEST_BOME_RUNTIME_EXIT="23")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        self.wait_for(lambda: "session=degraded" in self.run_command("status").stdout, process)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 17)

    def test_bome_runtime_alert_failure_does_not_close_ableton(self):
        self.script(self.fake / "notify-send", 'printf "notification-failed\\n" >> "$TEST_EVENTS"; exit 7')
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="23")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        self.wait_for(lambda: "notification-failed" in self.event_text(), process)
        self.assertIsNone(process.poll())
        self.assertIn("session=degraded", self.run_command("status").stdout)
        self.assertNotIn("wineserver:", self.event_text())
        stopped = self.run_command("stop")
        self.assertEqual(stopped.returncode, 0, stopped.stdout)
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 143)

    def test_bome_runtime_owner_loss_is_reported_without_closing_ableton(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="0")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        state = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/bome.state"
        owner = int(state.read_text().splitlines()[0])
        children = [int(pid) for pid in Path(f"/proc/{owner}/task/{owner}/children").read_text().split()]
        os.kill(owner, signal.SIGKILL)
        self.wait_for(lambda: "session=degraded" in self.run_command("status").stdout, process)
        self.assertIn("bome_exit=1", self.run_command("status").stdout)
        self.wait_for(lambda: "process owner exited without a result" in self.session_log_text(), process)
        self.assertIn("process owner exited without a result", self.session_log_text())
        self.assertIsNone(process.poll())
        self.assertNotIn("wineserver:", self.event_text())
        self.bome_stop.touch()
        self.wait_for(lambda: all(self.process_birth(pid) is None for pid in children), process)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 1)

    def test_bome_invalid_runtime_result_is_a_reported_failure(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        state = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state"
        log_dir = Path(state.read_text().splitlines()[4]).parent
        (log_dir / "bome.result").write_text("invalid exit status\n")
        self.wait_for(lambda: "session=degraded" in self.run_command("status").stdout, process)
        self.wait_for(lambda: "notification:" in self.event_text(), process)
        self.assertIn("bome_exit=1", self.run_command("status").stdout)
        self.assertIsNone(process.poll())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 1)

    def test_bome_status_falls_back_when_health_publication_fails(self):
        self.script(self.fake / "mv", '''
[[ "${@: -1}" != */bome.exit ]] || exit 1
exec /usr/bin/mv "$@"
''')
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="23")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        state = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state"
        log_dir = Path(state.read_text().splitlines()[4]).parent
        self.bome_stop.touch()
        self.wait_for(lambda: "notification:" in self.event_text(), process)
        self.assertFalse((log_dir / "bome.exit").exists())
        self.assertEqual((log_dir / "bome.result").read_text().strip(), "23")
        before_prefix = self.snapshot()
        before_events = self.event_text()
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        before_records = {str(path): path.read_bytes() for directory in (runtime, log_dir)
                          for path in directory.iterdir() if path.is_file()}
        result = self.run_command("status")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("session=degraded", result.stdout)
        self.assertIn("bome=failed", result.stdout)
        self.assertIn("bome_exit=23", result.stdout)
        self.assertEqual(self.snapshot(), before_prefix)
        self.assertEqual(self.event_text(), before_events)
        self.assertEqual({str(path): path.read_bytes() for directory in (runtime, log_dir)
                          for path in directory.iterdir() if path.is_file()}, before_records)
        self.assertIsNone(process.poll())
        self.assertNotIn("wineserver:", self.event_text())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 23)

    def test_bome_status_reports_normal_quit_without_health_record(self):
        self.script(self.fake / "mv", '''
[[ "${@: -1}" != */bome.exit ]] || exit 1
exec /usr/bin/mv "$@"
''')
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="0")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        self.wait_for(lambda: "Bome closed normally" in self.session_log_text(), process)
        status = self.run_command("status").stdout
        self.assertIn("session=running", status)
        self.assertIn("bome=stopped", status)
        self.assertIn("bome_exit=0", status)
        self.assertNotIn("notification:", self.event_text())
        self.assertIsNone(process.poll())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_bome_normal_exit_publication_keeps_status_healthy_and_stop_safe(self):
        pending = self.home / "result-pending"
        publish_release = self.home / "publish-release"
        published = self.home / "result-published"
        waiting_release = self.home / "waiting-release"
        signalled = self.home / "bome-signalled"
        self.releases.update((publish_release, waiting_release))
        worker = self.root / "config/session-worker.py"
        # Pause the real worker on both sides of its atomic result publication.
        # Neither pause changes the ordering of its completion records.
        worker.write_text(worker.read_text().replace(
            "def publish(path, value):\n",
            "def publish(path, value):\n"
            "    if path.name == 'bome.result':\n"
            "        Path(os.environ['TEST_RESULT_PENDING']).touch()\n"
            "        while not Path(os.environ['TEST_PUBLISH_RELEASE']).exists(): time.sleep(0.02)\n"
        ).replace(
            "        os.replace(temporary, path)",
            "        os.replace(temporary, path)\n"
            "        if path.name == 'bome.result':\n"
            "            Path(os.environ['TEST_RESULT_PUBLISHED']).touch()\n"
            "            while not Path(os.environ['TEST_WAITING_RELEASE']).exists(): time.sleep(0.02)"
        ).replace(
            "        stopping = True",
            "        stopping = True\n"
            "        if receipt.name == 'bome.state': Path(os.environ['TEST_BOME_SIGNALLED']).touch()"
        ))
        process = self.launch(
            "--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="0",
            TEST_RESULT_PENDING=str(pending), TEST_PUBLISH_RELEASE=str(publish_release),
            TEST_RESULT_PUBLISHED=str(published), TEST_WAITING_RELEASE=str(waiting_release),
            TEST_BOME_SIGNALLED=str(signalled),
        )
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        try:
            self.wait_for(pending.exists, process)
            status = self.run_command("status")
            self.assertEqual(status.returncode, 0, status.stdout)
            self.assertIn("session=running", status.stdout)
            self.assertNotIn("bome=failed", status.stdout)
            self.assertNotIn("notification:", self.event_text())
            self.assertIsNone(process.poll())
            self.assertNotIn("wineserver:", self.event_text())
            publish_release.touch()
            self.wait_for(published.exists, process)
            status = self.run_command("status")
            self.assertEqual(status.returncode, 0, status.stdout)
            self.assertIn("session=running", status.stdout)
            self.assertIn("bome=stopped", status.stdout)
            self.assertIn("bome_exit=0", status.stdout)
            self.assertNotIn("notification:", self.event_text())
            stop = self.start_command("stop")
            self.wait_for(signalled.exists)
            self.assertIsNone(stop.poll())
        finally:
            publish_release.touch()
            waiting_release.touch()
        output = stop.communicate(timeout=8)[0]
        self.assertEqual(stop.returncode, 0, output)
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 143)
        self.assertNotIn("bome_stop=forced", self.session_log_text())
        self.assertIn("cleanup_exit=0", self.session_log_text())
        self.assertIn("session=stopped", self.run_command("status").stdout)

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory read permissions")
    def test_bome_status_uses_ownership_when_session_log_directory_is_unreadable(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="0")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        log_dir = Path((runtime / "session.state").read_text().splitlines()[4]).parent
        owner = int((runtime / "bome.state").read_text().splitlines()[0])
        children = [int(pid) for pid in Path(f"/proc/{owner}/task/{owner}/children").read_text().split()]
        mode = log_dir.stat().st_mode & 0o777
        try:
            log_dir.chmod(0)
            os.kill(owner, signal.SIGKILL)
            self.wait_for(lambda: "notification:" in self.event_text(), process)
            result = self.run_command("status")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("session=degraded", result.stdout)
            self.assertIn("bome_exit=1", result.stdout)
            self.assertIsNone(process.poll())
            self.assertNotIn("wineserver:", self.event_text())
        finally:
            log_dir.chmod(mode)
        self.bome_stop.touch()
        self.wait_for(lambda: all(self.process_birth(pid) is None for pid in children), process)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 1)

    def test_bome_status_reports_lost_owner_when_health_record_cannot_be_created(self):
        self.script(self.fake / "mktemp", '''
[[ "$*" != *'/.bome-exit-'* ]] || exit 1
exec /usr/bin/mktemp "$@"
''')
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="0")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        log_dir = Path((runtime / "session.state").read_text().splitlines()[4]).parent
        owner = int((runtime / "bome.state").read_text().splitlines()[0])
        children = [int(pid) for pid in Path(f"/proc/{owner}/task/{owner}/children").read_text().split()]
        os.kill(owner, signal.SIGKILL)
        self.wait_for(lambda: "notification:" in self.event_text(), process)
        self.assertFalse((log_dir / "bome.exit").exists())
        self.assertFalse((log_dir / "bome.result").exists())
        status = self.run_command("status").stdout
        self.assertIn("session=degraded", status)
        self.assertIn("bome_exit=1", status)
        self.assertIsNone(process.poll())
        self.assertNotIn("wineserver:", self.event_text())
        self.bome_stop.touch()
        self.wait_for(lambda: all(self.process_birth(pid) is None for pid in children), process)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 1)

    def test_bome_status_does_not_treat_unverified_ownership_as_healthy(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        runtime = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        receipt = runtime / "bome.state"
        original = receipt.read_bytes()
        unrelated = subprocess.Popen(["sleep", "30"])
        cases = [None, b"invalid ownership\n", f"{os.getpid()}\n0\nprocess-group-v1\n".encode(),
                 f"{unrelated.pid}\n{self.process_birth(unrelated.pid)}\nprocess-group-v1\n".encode(),
                 original + b"waiting\n"]
        try:
            for record in cases:
                with self.subTest(record=record):
                    if record is None:
                        receipt.unlink(missing_ok=True)
                    else:
                        receipt.write_bytes(record)
                    status = self.run_command("status").stdout
                    self.assertIn("session=degraded", status)
                    self.assertIn("bome_exit=1", status)
                    self.assertNotIn("notification:", self.event_text())
                    self.assertIsNone(process.poll())
        finally:
            receipt.write_bytes(original)
            self.assertIsNone(unrelated.poll())
            unrelated.terminate()
            unrelated.wait(timeout=2)
        self.assertIn("session=running", self.run_command("status").stdout)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_bome_status_rejects_nonregular_health_records_without_blocking(self):
        process = self.launch("--with-bome", TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        state = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state"
        record = Path(state.read_text().splitlines()[4]).parent / "bome.exit"
        try:
            record.mkdir()
            self.assertIn("session=degraded", self.run_command("status").stdout)
            record.rmdir()
            os.mkfifo(record)
            self.assertIn("session=degraded", self.run_command("status").stdout)
        finally:
            if record.is_dir():
                record.rmdir()
            else:
                record.unlink(missing_ok=True)
        self.assertNotIn("notification:", self.event_text())
        self.assertIn("session=running", self.run_command("status").stdout)
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_bome_status_ignores_other_session_failure_records(self):
        stale = Path(self.env["XDG_STATE_HOME"]) / "waydaw/logs/other-session"
        stale.mkdir(parents=True)
        (stale / "bome.exit").write_text("23\n")
        (stale / "bome.result").write_text("23\n")
        (stale / "bome.ready").write_text("ready\n")
        process = self.launch("--with-bome", TEST_WINE_HOLD="1")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        status = self.run_command("status").stdout
        self.assertIn("session=running", status)
        self.assertNotIn("bome=failed", status)
        self.assertNotIn("notification:", self.event_text())
        self.stop.touch()
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0)

    def test_bome_stalled_notification_does_not_hold_stop_lock(self):
        self.script(self.fake / "notify-send", 'printf "notification-started\\n" >> "$TEST_EVENTS"\nsleep 30')
        process = self.launch("--with-bome", TEST_WINE_HOLD="1", TEST_BOME_RUNTIME_EXIT="23")
        self.wait_for(lambda: "Ableton Live 12 Suite.exe:" in self.event_text(), process)
        self.bome_stop.touch()
        self.wait_for(lambda: "notification-started" in self.event_text(), process)
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        process.communicate(timeout=8)
        self.assertEqual(process.returncode, 143)
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_bome_default_system_mode_keeps_its_prefix_and_display(self):
        executable = self.working / "drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe"
        executable.parent.mkdir(parents=True)
        executable.touch()
        shutil.copy2(self.runner / "wine", self.fake / "wine")
        result = self.run_command(executable="bome", env={"TEST_BOME_EXIT": "0"})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("wine:" + str(self.working) + ":" + str(executable), self.event_text())
        self.assertIn("wayland=wayland-fixture", self.event_text())

    def test_bome_clean_early_exit_is_failure(self):
        result = self.run_command("start", "--with-bome", env={"TEST_BOME_EXIT": "0"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Bome exited during startup", result.stdout)
        self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())

    def test_cleanup_failure_is_reported(self):
        result = self.run_command("start", env={"TEST_CLEANUP_FAIL": "1"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("cleanup_exit=1", self.session_log_text())

    def test_crashed_supervisor_blocks_start_until_explicit_recovery(self):
        process = self.launch(TEST_WINE_HOLD="1")
        try:
            self.wait_for(lambda: "wine:" in self.event_text(), process)
            self.wait_for(lambda: Path(self.env["TEST_BRIDGE"]).is_file(), process)
            process.kill()
            process.wait(timeout=2)
            before = self.snapshot()
            result = self.run_command("start")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("recovery required", result.stdout.lower())
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.event_text().count("wine:"), 1)
            self.assertIn("session=recovery-required", self.run_command("status").stdout)
            events_before_stop = self.event_text()
            wrong_scope = self.run_command("stop", env={"WAYDAW_ABLETON_RUNNER_PREFIX": str(self.home / "other-copy")})
            self.assertNotEqual(wrong_scope.returncode, 0, wrong_scope.stdout)
            self.assertIn("Recorded session belongs", wrong_scope.stdout)
            self.assertEqual(self.event_text(), events_before_stop)
            result = self.run_command("stop")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertFalse(Path(self.env["TEST_BRIDGE"]).exists())
            process.communicate(timeout=3)
            self.assertIn("session=stopped", self.run_command("status").stdout)
            self.stop.unlink()
            self.assertEqual(self.run_command("start").returncode, 0)
        finally:
            self.stop.touch()
            bridge = Path(self.env["TEST_BRIDGE"])
            if bridge.is_file():
                try:
                    os.kill(int(bridge.read_text()), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass

    def test_failed_cleanup_preserves_recovery_marker_and_blocks_start(self):
        result = self.run_command("start", env={"TEST_CLEANUP_FAIL": "1"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        before = self.event_text()
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("recovery required", result.stdout.lower())
        self.assertEqual(self.event_text(), before)
        self.assertIn("session=recovery-required", self.run_command("status").stdout)
        failed_stop = self.run_command("stop", env={"TEST_CLEANUP_FAIL": "1"})
        self.assertNotEqual(failed_stop.returncode, 0, failed_stop.stdout)
        self.assertIn("session=recovery-required", self.run_command("status").stdout)
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_bome_dll_update_blocks_ableton_launch(self):
        source = self.working / "drive_c/windows/system32/d3d11.dll"
        before = source.read_bytes()
        result = self.run_command("start", "--with-bome", env={"TEST_BOME_DRIFT": "1"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("DXVK verification failed", result.stdout)
        self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())
        self.assertEqual(source.read_bytes(), before)
        self.assertIn("wineserver:" + str(self.prefix) + ":-k", self.event_text())

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

    def test_stop_cancels_delayed_ableton_wrapper_before_wine_cleanup(self):
        gate, release = self.gate_launcher("ableton")
        process = self.launch(TEST_GATE=str(gate), TEST_RELEASE=str(release))
        self.wait_for(gate.exists, process)
        self.assert_no_launch_after_stop(process, release)

    def test_stop_cancels_delayed_bome_wrapper_before_wine_cleanup(self):
        gate, release = self.gate_launcher("bome")
        process = self.launch("--with-bome", TEST_GATE=str(gate), TEST_RELEASE=str(release))
        self.wait_for(gate.exists, process)
        self.assert_no_launch_after_stop(process, release)

    def test_exited_launcher_descendants_are_cancelled(self):
        release = self.home / "descendant-release"
        self.script(self.fake / "pw-jack", '''
if [[ "$1" == */bin/ableton ]]; then
  (
    while [[ ! -e "$TEST_RELEASE" ]]; do sleep 0.02; done
    exec "$@"
  ) &
  exit 0
fi
exec "$@"
''')
        try:
            result = self.run_command("start", env={"TEST_RELEASE": str(release)})
            self.assertEqual(result.returncode, 0, result.stdout)
        finally:
            release.touch()
        time.sleep(0.2)
        self.assertNotIn("wine:", self.event_text())
        self.assertFalse(Path(self.env["TEST_KWIN"]).exists())

    def test_crash_recovery_cancels_delayed_launcher(self):
        gate, release = self.gate_launcher("ableton")
        process = self.launch(TEST_GATE=str(gate), TEST_RELEASE=str(release))
        self.wait_for(gate.exists, process)
        process.kill()
        process.wait(timeout=2)
        self.assert_no_launch_after_stop(process, release)

    def test_regression_recovery_waits_for_pending_worker_publication(self):
        bridge_gate, bridge_release = self.home / "bridge-pending", self.home / "bridge-release"
        gate, release = self.gate_launcher("ableton")
        self.releases.add(bridge_release)
        self.script(self.fake / "python3", '''
if [[ "$1" == */session-worker.py && "$2" == run && "$3" == */bridge.state ]]; then
  touch "$TEST_BRIDGE_GATE"
  while [[ ! -e "$TEST_BRIDGE_RELEASE" ]]; do sleep 0.02; done
fi
exec /usr/bin/python3 "$@"
''')
        process = self.launch(TEST_GATE=str(gate), TEST_RELEASE=str(release),
                              TEST_BRIDGE_GATE=str(bridge_gate), TEST_BRIDGE_RELEASE=str(bridge_release))
        self.wait_for(lambda: bridge_gate.exists() and gate.exists(), process)
        process.kill()
        process.wait(timeout=2)
        stop = self.start_command("stop")
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                stop.communicate(timeout=0.25)
        finally:
            bridge_release.touch()
        output = stop.communicate(timeout=6)[0]
        self.assertEqual(stop.returncode, 0, output)
        release.touch()
        process.communicate(timeout=4)
        self.assertNotIn("wine:", self.event_text())
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_recovery_lock_wait_is_bounded_and_preserves_session(self):
        directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        directory.mkdir(parents=True)
        state = directory / "session.state"
        state.write_text(f"0\n0\n{self.prefix}\n{self.root}\n")
        with (directory / "session.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_command("stop")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("after 5 seconds", result.stdout)
        self.assertTrue(state.exists())
        self.assertEqual(self.event_text(), "")

    def test_fixture_teardown_cleans_failed_recovery_and_preserves_unrelated_process(self):
        fixture = GuardedSessionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        unrelated = subprocess.Popen(["sleep", "30"])
        try:
            process = fixture.launch(TEST_WINE_HOLD="1")
            fixture.wait_for(lambda: "wine:" in fixture.event_text(), process)
            process.kill()
            process.wait(timeout=2)
            directory = Path(fixture.env["XDG_RUNTIME_DIR"]) / "waydaw"
            (directory / "ableton.state").write_text("invalid ownership")
            fixture.doCleanups()
            self.assertEqual(fixture.fixture_processes(), {})
            self.assertIsNotNone(process.poll())
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_stop_before_worker_publishes_ownership_cancels_launch(self):
        gate, release = self.home / "worker-waiting", self.home / "worker-release"
        self.script(self.fake / "python3", '''
if [[ "$1" == */session-worker.py && "$2" == run ]]; then
  touch "$TEST_GATE"
  while [[ ! -e "$TEST_RELEASE" ]]; do sleep 0.02; done
fi
exec /usr/bin/python3 "$@"
''')
        process = self.launch(TEST_GATE=str(gate), TEST_RELEASE=str(release), TEST_BRIDGE_EXISTING="1")
        self.wait_for(gate.exists, process)
        stop = self.start_command("stop")
        try:
            logs = Path(self.env["XDG_STATE_HOME"]) / "waydaw/logs"
            self.wait_for(lambda: bool(list(logs.glob("*/cancelled"))))
            self.assertIsNone(stop.poll())  # Pending worker still holds the lock.
        finally:
            release.touch()
        output = stop.communicate(timeout=6)[0]
        self.assertEqual(stop.returncode, 0, output)
        process.communicate(timeout=4)
        self.assertNotIn("wine:", self.event_text())
        directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        self.assertEqual(list(directory.glob("*.state")), [])

    def test_stop_as_session_record_becomes_visible_runs_cleanup(self):
        gate, release = self.home / "session-published", self.home / "session-release"
        stop_waiting = self.home / "stop-waiting"
        self.script(self.fake / "mv", '''
/usr/bin/mv "$@"
if [[ "${@: -1}" == */session.state ]]; then
  touch "$TEST_GATE"
  while [[ ! -e "$TEST_RELEASE" ]]; do sleep 0.02; done
fi
''')
        self.script(self.fake / "flock", '''
[[ "$1" != -w ]] || touch "$TEST_STOP_WAITING"
exec /usr/bin/flock "$@"
''')
        process = self.launch(TEST_GATE=str(gate), TEST_RELEASE=str(release))
        self.wait_for(gate.exists, process)
        stop = self.start_command("stop", env={"TEST_STOP_WAITING": str(stop_waiting)})
        try:
            self.wait_for(stop_waiting.exists)  # Stop has delivered SIGTERM.
        finally:
            release.touch()
        output = stop.communicate(timeout=6)[0]
        self.assertEqual(stop.returncode, 0, output)
        output = process.communicate(timeout=4)[0]
        self.assertIn("cleanup_exit=0", self.session_log_text())
        self.assertNotIn("wine:", self.event_text())

    def test_stop_while_worker_publishes_ownership_cancels_launch(self):
        gate, release = self.home / "worker-published", self.home / "worker-release"
        signalled = self.home / "worker-signalled"
        worker = self.root / "config/session-worker.py"
        worker.write_text(worker.read_text().replace(
            "        stopping = True", "        stopping = True\n        Path(os.environ['TEST_SIGNALLED']).touch()"
        ).replace(
            "    parent_state = process(int(parent))",
            "    Path(os.environ['TEST_GATE']).touch()\n"
            "    while not Path(os.environ['TEST_RELEASE']).exists(): time.sleep(0.02)\n"
            "    parent_state = process(int(parent))"))
        process = self.launch(TEST_GATE=str(gate), TEST_RELEASE=str(release),
                              TEST_SIGNALLED=str(signalled), TEST_BRIDGE_EXISTING="1")
        self.wait_for(gate.exists, process)
        stop = self.start_command("stop")
        try:
            self.wait_for(signalled.exists)
        finally:
            release.touch()
        output = stop.communicate(timeout=6)[0]
        self.assertEqual(stop.returncode, 0, output)
        process.communicate(timeout=4)
        self.assertNotIn("wine:", self.event_text())
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_bome_readiness_deadline_cleans_up_without_starting_ableton(self):
        launcher = self.root / "bin/waydaw"
        launcher.write_text(launcher.read_text().replace(
            "bome_deadline=$((SECONDS + 45))", "bome_deadline=$((SECONDS + 1))"))
        gate, release = self.home / "bome-initializing", self.home / "bome-release"
        try:
            result = self.run_command("start", "--with-bome", env={
                "TEST_BOME_INITIALIZING": str(gate), "TEST_BOME_RELEASE": str(release)})
        finally:
            release.touch()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Bome readiness timed out", result.stdout)
        self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_delayed_bome_initialization_precedes_dxvk_verification(self):
        gate = self.home / "bome-initializing"
        release = self.home / "bome-release"
        process = self.launch("--with-bome", TEST_BOME_INITIALIZING=str(gate),
                              TEST_BOME_RELEASE=str(release), TEST_BOME_DRIFT="1")
        self.wait_for(gate.exists, process)
        try:
            time.sleep(2.2)  # Longer than the old fixed startup delay.
            self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())
        finally:
            release.touch()
        output = process.communicate(timeout=6)[0]
        self.assertNotEqual(process.returncode, 0, output)
        self.assertIn("DXVK verification failed", output)
        self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())

    def test_stop_during_bome_initialization_blocks_ableton(self):
        gate = self.home / "bome-initializing"
        release = self.home / "bome-release"
        process = self.launch("--with-bome", TEST_BOME_INITIALIZING=str(gate),
                              TEST_BOME_RELEASE=str(release))
        self.wait_for(gate.exists, process)
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        process.communicate(timeout=4)
        release.touch()
        time.sleep(0.2)
        self.assertNotIn("Ableton Live 12 Suite.exe:", self.event_text())

    def test_bridge_ignoring_sigterm_is_killed_within_cleanup_deadline(self):
        self.script(self.fake / "a2jmidid", '''
printf '%s' "$$" > "$TEST_BRIDGE"
trap '' TERM INT
while :; do sleep 0.05; done
''')
        process = self.launch(TEST_WINE_HOLD="1")
        bridge_pid = None
        try:
            self.wait_for(lambda: "wine:" in self.event_text(), process)
            self.wait_for(lambda: Path(self.env["TEST_BRIDGE"]).is_file(), process)
            bridge_pid = int(Path(self.env["TEST_BRIDGE"]).read_text())
            self.stop.touch()  # Ableton closes normally; cleanup must finish.
            output = process.communicate(timeout=6)[0]
            self.assertEqual(process.returncode, 0, output)
            self.assertIn("bridge_stop=forced", self.session_log_text())
            self.assertFalse((Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state").exists())
        finally:
            self.stop.touch()
            if bridge_pid is not None:
                try:
                    os.kill(bridge_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_preexisting_midi_bridge_survives_session_cleanup(self):
        bridge = subprocess.Popen([str(self.fake / "a2jmidid")], env=self.env)
        try:
            self.wait_for(lambda: Path(self.env["TEST_BRIDGE"]).is_file())
            result = self.run_command("start", env={"TEST_BRIDGE_EXISTING": "1"})
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIsNone(bridge.poll())
        finally:
            bridge.terminate()
            bridge.wait(timeout=3)

    def test_stop_reports_supervisor_cleanup_failure(self):
        process = self.launch(TEST_WINE_HOLD="1", TEST_CLEANUP_FAIL="1")
        self.wait_for(lambda: "wine:" in self.event_text(), process)
        result = self.run_command("stop")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Session cleanup failed", result.stdout)
        output = process.communicate(timeout=8)[0]
        session_log = next(line for line in output.splitlines() if line.startswith("session_log="))
        self.assertIn(session_log, result.stdout)

    def test_stop_accepts_legacy_session_record_without_log_path(self):
        process = self.launch(TEST_WINE_HOLD="1")
        self.wait_for(lambda: "wine:" in self.event_text(), process)
        state = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw/session.state"
        state.write_text("\n".join(state.read_text().splitlines()[:4]) + "\n")
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        process.communicate(timeout=8)
        self.assertIn("session=stopped", self.run_command("status").stdout)

    def test_stale_state_does_not_signal_unrelated_process(self):
        directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        directory.mkdir(parents=True)
        # Our own PID but a mismatched birth time: never signal it.
        (directory / "session.state").write_text(f"{os.getpid()}\n0\n{self.prefix}\n{self.root}\n")
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("wineserver:" + str(self.prefix) + ":-k", self.event_text())
        self.assertNotIn("wineserver:" + str(self.working) + ":", self.event_text())

    def test_stale_bridge_identity_does_not_signal_reused_pid(self):
        directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        directory.mkdir(parents=True)
        (directory / "session.state").write_text(f"0\n0\n{self.prefix}\n{self.root}\n")
        (directory / "bridge.state").write_text(f"{os.getpid()}\n0\n")
        result = self.run_command("stop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((directory / "bridge.state").exists())
        self.assertFalse((directory / "session.state").exists())

    def test_reused_group_owner_is_not_signalled_and_preserves_recovery(self):
        unrelated = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
            directory.mkdir(parents=True)
            (directory / "session.state").write_text(f"0\n0\n{self.prefix}\n{self.root}\n")
            receipt = directory / "ableton.state"
            receipt.write_text(f"{unrelated.pid}\n0\nprocess-group-v1\n")
            result = self.run_command("stop")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("owner lost while descendants remain", result.stdout)
            self.assertIsNone(unrelated.poll())
            self.assertTrue(receipt.exists())
            self.assertIn("session=recovery-required", self.run_command("status").stdout)
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_invalid_bridge_record_preserves_recovery_marker(self):
        directory = Path(self.env["XDG_RUNTIME_DIR"]) / "waydaw"
        directory.mkdir(parents=True)
        (directory / "session.state").write_text(f"0\n0\n{self.prefix}\n{self.root}\n")
        (directory / "bridge.state").write_text("")
        result = self.run_command("stop")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("invalid bridge ownership record", result.stdout)
        self.assertTrue((directory / "session.state").exists())
        self.assertTrue((directory / "bridge.state").exists())

    def test_stop_refuses_a_different_active_prefix(self):
        process = self.launch(TEST_WINE_HOLD="1")
        self.wait_for(lambda: "wine:" in self.event_text(), process)
        result = self.run_command("stop", env={"WAYDAW_ABLETON_RUNNER_PREFIX": str(self.home / "other-copy")})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("session belongs", result.stdout)
        self.assertIsNone(process.poll())

    def test_check_rejects_wine_builtin_even_with_matching_hash(self):
        builtin = b"MZ" + bytes(62) + b"Wine builtin DLL\0"
        for prefix in (self.prefix, self.working):
            (prefix / "drive_c/windows/system32/d3d11.dll").write_bytes(builtin)
        manifest = self.root / "config/validated-runtime.sh"
        with manifest.open("a") as output:
            output.write(f"\nWAYDAW_D3D11_SHA256={hashlib.sha256(builtin).hexdigest()}\n")
        before = self.snapshot()
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Wine builtin marker", result.stdout)
        self.assertEqual(before, self.snapshot())
        self.assertNotIn("wine:", self.event_text())

    def test_missing_d3d10core_blocks_launch_before_wine(self):
        for prefix in (self.prefix, self.working):
            (prefix / "drive_c/windows/system32/d3d10core.dll").unlink()
        result = self.run_command("start")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Required DXVK d3d10core.dll missing", result.stdout)
        self.assertNotIn("wine:", self.event_text())

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

    def test_desktop_install_print_and_uninstall(self):
        result = self.run_command("--print", executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f'Exec="{self.root}/bin/waydaw-desktop" start', result.stdout)
        self.assertIn('Terminal=false', result.stdout)
        self.assertFalse(Path(self.env["XDG_DATA_HOME"]).exists())
        self.assertFalse(Path(self.env["XDG_STATE_HOME"]).exists())
        result = self.run_command(executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        desktop = Path(self.env["XDG_DATA_HOME"]) / "applications/com.timcis.WayDAW.desktop"
        self.assertTrue(desktop.exists())
        if shutil.which("desktop-file-validate"):
            checked = subprocess.run(["desktop-file-validate", str(desktop)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        result = self.run_command("--uninstall", executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(desktop.exists())

    def test_desktop_frontend_logs_preflight_failure_and_preserves_status(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        result = self.run_command("start", executable="waydaw-desktop", env={"TEST_PIPEWIRE_FAIL": "1"})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("--detailederror", self.event_text())
        self.assertIn("PipeWire user service is not active", self.event_text())
        logs = list((Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop").glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("PipeWire user service is not active", logs[0].read_text())

    def test_desktop_frontend_displays_actual_cleanup_failure(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        unrelated = Path(self.env["XDG_STATE_HOME"]) / "waydaw/logs/unrelated/session.log"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("UNRELATED SESSION ERROR\n")
        os.utime(unrelated, (time.time() + 3600, time.time() + 3600))
        result = self.run_command("start", executable="waydaw-desktop", env={"TEST_CLEANUP_FAIL": "1"})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("--detailederror", self.event_text())
        self.assertIn("Wine shutdown could not be verified", self.event_text())
        self.assertIn("session recovery required", self.event_text())
        self.assertIn("cleanup_exit=1", self.event_text())
        self.assertNotIn("UNRELATED SESSION ERROR", self.event_text())

    def test_desktop_stop_displays_cleanup_failure_from_terminal_session(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        process = self.launch(TEST_WINE_HOLD="1", TEST_CLEANUP_FAIL="1")
        self.wait_for(lambda: "wine:" in self.event_text(), process)
        result = self.run_command("stop", executable="waydaw-desktop")
        output = process.communicate(timeout=8)[0]
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("--detailederror", self.event_text())
        self.assertIn("Wine shutdown could not be verified", self.event_text())
        self.assertIn("cleanup_exit=1", self.event_text())
        self.assertIn("Session cleanup failed; inspect the session log", self.event_text())
        session_log = next(line.removeprefix("session_log=") for line in output.splitlines()
                           if line.startswith("session_log="))
        self.assertIn(session_log, self.event_text())
        self.assertIn("session=recovery-required", self.run_command("status").stdout)

    def test_desktop_frontend_falls_back_when_session_log_is_unavailable(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        self.script(self.root / "bin/waydaw", '''
printf 'session_log=/missing/session.log\\nERROR: startup failed before logging\\n'
exit 17
''')
        result = self.run_command("start", executable="waydaw-desktop")
        self.assertEqual(result.returncode, 17, result.stdout)
        self.assertIn("startup failed before logging", self.event_text())

    def test_desktop_install_repairs_original_shortcut_and_restores_it(self):
        desktop = Path(self.env["XDG_DATA_HOME"]) / "applications/wine/Programs/Ableton Live 12 Suite.desktop"
        desktop.parent.mkdir(parents=True)
        original = ('[Desktop Entry]\nName=Ableton Live 12 Suite\nExec=wine original.lnk\n'
                    'Type=Application\nIcon=ableton-original\nStartupWMClass=ableton.exe\n'
                    'Path=/original/path\nTerminal=true\n')
        desktop.write_text(original)
        for _ in range(2):
            result = self.run_command(executable="install-waydaw-desktop")
            self.assertEqual(result.returncode, 0, result.stdout)
        installed = desktop.read_text()
        self.assertIn(f'Exec="{self.root}/bin/waydaw-desktop" start\n', installed)
        self.assertIn("Icon=ableton-original\n", installed)
        self.assertIn("StartupWMClass=ableton.exe\n", installed)
        self.assertIn("Terminal=false\n", installed)
        self.assertEqual(installed.count("Exec="), 1)
        self.assertNotIn("Exec=wine", installed)
        record = Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop-install.json"
        self.assertEqual(json.loads(record.read_text())["original_ableton"], original)
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)
        if shutil.which("desktop-file-validate"):
            checked = subprocess.run(["desktop-file-validate", str(desktop)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        result = self.run_command("--uninstall", executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(desktop.read_text(), original)

    def test_desktop_reinstall_repairs_wine_regeneration_without_losing_original(self):
        desktop = Path(self.env["XDG_DATA_HOME"]) / "applications/wine/Programs/Ableton Live 12 Suite.desktop"
        desktop.parent.mkdir(parents=True)
        original = '[Desktop Entry]\nName=Ableton\nType=Application\nExec=wine first.lnk\n'
        desktop.write_text(original)
        self.assertEqual(self.run_command(executable="install-waydaw-desktop").returncode, 0)
        self.root = self.root.rename(self.root.with_name("moved checkout with spaces"))
        result = self.run_command(executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f'Exec="{self.root}/bin/waydaw-desktop" start\n', desktop.read_text())
        desktop.write_text(original.replace("first.lnk", "regenerated.lnk"))
        result = self.run_command(executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("waydaw-desktop", desktop.read_text())
        result = self.run_command("--uninstall", executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(desktop.read_text(), original)

    def test_desktop_uninstall_preserves_independent_edits(self):
        desktop = Path(self.env["XDG_DATA_HOME"]) / "applications/wine/Programs/Ableton Live 12 Suite.desktop"
        desktop.parent.mkdir(parents=True)
        original = '[Desktop Entry]\nName=Ableton\nType=Application\nExec=wine original.lnk\n'
        desktop.write_text(original)
        self.assertEqual(self.run_command(executable="install-waydaw-desktop").returncode, 0)
        changed = desktop.read_text() + "X-User-Setting=keep\n"
        desktop.write_text(changed)
        result = self.run_command("--uninstall", executable="install-waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Preserved independently changed entry", result.stdout)
        self.assertEqual(desktop.read_text(), changed)
        record = Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop-install.json"
        self.assertEqual(json.loads(record.read_text())["original_ableton"], original)

    def test_desktop_reinstall_after_preserved_edit_keeps_original_wine_shortcut(self):
        desktop = Path(self.env["XDG_DATA_HOME"]) / "applications/wine/Programs/Ableton Live 12 Suite.desktop"
        desktop.parent.mkdir(parents=True)
        original = '[Desktop Entry]\nName=Ableton\nType=Application\nExec=wine original.lnk\n'
        desktop.write_text(original)
        self.assertEqual(self.run_command(executable="install-waydaw-desktop").returncode, 0)
        desktop.write_text(desktop.read_text() + "X-User-Setting=keep\n")
        self.assertEqual(self.run_command("--uninstall", executable="install-waydaw-desktop").returncode, 0)
        self.assertIn("X-User-Setting=keep", desktop.read_text())
        record = Path(self.env["XDG_STATE_HOME"]) / "waydaw/desktop-install.json"
        for _ in range(2):
            result = self.run_command(executable="install-waydaw-desktop")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("X-User-Setting=keep", desktop.read_text())
            self.assertEqual(json.loads(record.read_text())["original_ableton"], original)
            result = self.run_command("--uninstall", executable="install-waydaw-desktop")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(desktop.read_text(), original)
            desktop.write_text(desktop.read_text() + "X-User-Setting=keep\n")

    def test_desktop_frontend_keeps_the_session_supervised_without_a_terminal(self):
        self.script(self.fake / "kdialog", 'printf "unexpected-dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        process = subprocess.Popen(
            [str(self.root / "bin/waydaw-desktop"), "start"],
            env={**self.env, "TEST_WINE_HOLD": "1"},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        self.processes.append(process)
        self.wait_for(lambda: "wine:" in self.event_text(), process)
        self.assertIsNone(process.poll())
        self.assertIn("session=running", self.run_command("status").stdout)
        self.stop.touch()
        _, output = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0, output)
        self.assertIn("session_exit=0 cleanup_exit=0", self.session_log_text())
        self.assertNotIn("unexpected-dialog", self.event_text())

    def test_desktop_frontend_displays_environment_check_results(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        result = self.run_command("check", executable="waydaw-desktop")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--textbox", self.event_text())
        self.assertNotIn("--detailederror", self.event_text())

    def test_desktop_frontend_reports_incomplete_cleanup_after_cancellation(self):
        self.script(self.fake / "kdialog", 'printf "dialog:%s\\n" "$*" >> "$TEST_EVENTS"')
        self.script(self.root / "bin/waydaw", '''
if [[ "$1" == status ]]; then printf 'session=%s\\n' "$TEST_SESSION_STATE"; exit 0; fi
exit 143
''')
        result = self.run_command("start", executable="waydaw-desktop", env={"TEST_SESSION_STATE": "stopped"})
        self.assertEqual(result.returncode, 143, result.stdout)
        self.assertNotIn("--detailederror", self.event_text())
        result = self.run_command("start", executable="waydaw-desktop", env={"TEST_SESSION_STATE": "recovery-required"})
        self.assertEqual(result.returncode, 143, result.stdout)
        self.assertIn("--detailederror", self.event_text())

    def test_compatibility_entry_points_use_the_supervisor(self):
        for executable, marker in (("session", "with_bome=1"), ("ableton-wayland", "with_bome=0")):
            result = self.run_command("--dry-run", executable=executable)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn(marker, result.stdout)
        result = self.run_command("--dry-run", executable="kill-session")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("would_stop_prefix=" + str(self.prefix), result.stdout)


if __name__ == "__main__":
    unittest.main()
