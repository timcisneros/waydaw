"""Queue authorization for the guarded session; never bootstrap another prefix."""
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit
import uuid

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("waydaw_worker", Path(__file__).with_name("session-worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class RequestError(ValueError):
    """A public validation message that contains no callback contents."""


def payload(value):
    if not value or len(value) > 32768 or any(char in value for char in "\0\r\n"):
        raise RequestError("Invalid authorization request.")
    url = urlsplit(value)
    if url.scheme.lower() == "ableton":
        if url.netloc.lower() != "authorize" or url.path not in ("", "/") or not url.query or url.fragment:
            raise RequestError("Expected an Ableton authorization URL.")
        return {"kind": "uri", "value": value}
    if url.scheme == "file":
        if url.netloc not in ("", "localhost") or url.query or url.fragment:
            raise RequestError("Expected a local authorization file.")
        value = unquote(url.path)
    elif url.scheme:
        raise RequestError("Expected an Ableton authorization URL or .auz file.")
    path = Path(value)
    if path.suffix.lower() != ".auz" or not path.is_file():
        raise RequestError("Expected an existing .auz authorization file.")
    return {"kind": "file", "value": str(path.resolve(strict=True))}


def same_session(runtime, expected):
    try:
        current = (runtime / "session.state").read_text().splitlines()
        state = worker.process(int(expected[0]))
        return current == expected and state and state[0] == int(expected[1])
    except (OSError, ValueError):
        return False


def submit(root, prefix, runtime, pid, birth, log, value):
    request = payload(value)
    runtime = Path(runtime)
    expected = [pid, birth, prefix, root, log]
    directory = Path(log).parent / "authorization"
    cancelled = directory.parent / "cancelled"
    if not same_session(runtime, expected) or cancelled.exists():
        raise RequestError("Open WayDAW Ableton before authorizing it.")
    if directory.is_symlink() or not directory.is_dir():
        raise RequestError("Restart the WayDAW session to enable authorization callbacks, then retry.")
    path = directory / (uuid.uuid4().hex + ".request")
    reply = path.with_suffix(".reply")
    try:
        worker.publish(path, json.dumps(request))
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if reply.is_file():
                if reply.read_text().strip() != "0":
                    raise RequestError("Authorization delivery failed. Retry from the running WayDAW Ableton window.")
                print("authorization_request=delivered")
                return 0
            if cancelled.exists() or not same_session(runtime, expected):
                raise RequestError("WayDAW closed before authorization could be delivered. Relaunch it and retry.")
            time.sleep(0.05)
        raise RequestError("Authorization delivery timed out. Retry from the running WayDAW Ableton window.")
    finally:
        path.unlink(missing_ok=True)
        reply.unlink(missing_ok=True)


def target(prefix, receipt):
    try:
        owner = receipt.read_text().splitlines()
        if (len(owner) != 3 or owner[2] != "process-group-v1" or int(owner[0]) <= 1
                or worker.process(int(owner[0])) != (int(owner[1]), int(owner[0]))):
            return None
        for pid in worker.group_members(int(owner[0])):
            proc = Path(f"/proc/{pid}")
            try:
                argument = os.fsdecode((proc / "cmdline").read_bytes().split(b"\0")[0])
                windows = PureWindowsPath(argument)
                if windows.name.lower() not in {"ableton live 12 suite.exe", "ableton live 12 standard.exe", "ableton live 12 intro.exe"}:
                    continue
                if windows.drive.lower() == "c:":
                    executable = prefix / "drive_c" / Path(*windows.parts[1:])
                else:
                    executable = Path(argument)
                    if not executable.is_absolute():
                        continue
                executable = executable.resolve(strict=True)
                environment = dict(os.fsdecode(item).split("=", 1) for item in (proc / "environ").read_bytes().split(b"\0") if b"=" in item)
                if (prefix in executable.parents and executable.is_file()
                        and environment.get("WINEPREFIX") == str(prefix)
                        and "WAYLAND_DISPLAY" not in environment):
                    # Wine adds process-internal loader/socket variables after
                    # exec. Reuse only launch settings, not those internal FDs.
                    launch = dict(os.environ)
                    for key in ["WINEDLLOVERRIDES", "LD_LIBRARY_PATH", "PIPEWIRE_CONFIG_DIR", "PIPEWIRE_PROPS",
                                "WAYDAW_SIZING_SHIM_MAX_H", "WAYDAW_SIZING_SHIM_MIN_H"]:
                        if key in environment:
                            launch[key] = environment[key]
                        else:
                            launch.pop(key, None)
                    launch["WINEPREFIX"] = str(prefix)
                    for key in ["WAYLAND_DISPLAY", "WINELOADERNOEXEC", "WINESERVERSOCKET", "WINEPRELOADRESERVE"]:
                        launch.pop(key, None)
                    return executable, launch
            except (OSError, ValueError):
                continue
    except (OSError, ValueError, IndexError):
        pass
    return None


def dispatch(request, root, prefix, receipt):
    request, root, prefix, receipt = Path(request), Path(root), Path(prefix), Path(receipt)
    try:
        if not stat.S_ISREG(request.lstat().st_mode):
            raise RequestError("Invalid authorization request file.")
        data = json.loads(request.read_text())
        checked = payload(data["value"])
        if data != checked:
            raise RequestError("Invalid authorization request.")
    finally:
        request.unlink(missing_ok=True)
    cancelled = request.parent.parent / "cancelled"
    deadline = time.monotonic() + 10
    found = None
    while time.monotonic() < deadline and not cancelled.exists():
        if (request.parent.parent / "ableton.result").exists():
            break
        found = target(prefix, receipt)
        if found:
            break
        time.sleep(0.05)
    if not found or cancelled.exists():
        raise RequestError("No running guarded Ableton instance can receive authorization.")
    executable, environment = found
    runner = root / ".local-runners/kron4ek-proton-exp-11.0/bin"
    argument = data["value"]
    if data["kind"] == "file":
        converted = subprocess.run([str(runner / "winepath"), "-w", argument], env=environment,
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=10, check=True).stdout.splitlines()
        if len(converted) != 1 or not converted[0]:
            raise RequestError("Could not resolve the authorization file.")
        argument = converted[0]
    if cancelled.exists():
        raise RequestError("The WayDAW session is closing.")
    # The application handles its own official authorization protocol. Preserve
    # its environment and forward opaquely; never repair the live prefix here.
    os.execve(str(runner / "wine"), [str(runner / "wine"), str(executable), argument], environment)


def reply(request, result):
    worker.publish(Path(request).with_suffix(".reply"), "0\n" if result == "0" else "1\n")


def cancel(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise RequestError("Invalid authorization queue.")
    if directory.is_dir():
        (directory.parent / "cancelled").touch()
        for request in directory.glob("*.request"):
            request.unlink(missing_ok=True)
            reply(request, "1")


if __name__ == "__main__":
    try:
        mode = sys.argv[1]
        if mode == "submit":
            sys.exit(submit(*sys.argv[2:]))
        elif mode == "dispatch":
            dispatch(*sys.argv[2:])
        elif mode == "reply":
            reply(*sys.argv[2:])
        elif mode == "cancel":
            cancel(*sys.argv[2:])
        else:
            raise RequestError("Unknown authorization operation.")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Callback URLs contain private session values. Only our own validation
        # messages may reach desktop logs; subprocess exceptions can include argv.
        message = str(error) if isinstance(error, RequestError) else "Authorization delivery failed."
        print("ERROR: " + message, file=sys.stderr)
        sys.exit(1)
