"""Explicit, bounded RTKit comparison using newly created disposable children."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import selectors
import shutil
import subprocess
import time


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(pid):
    path = Path("/proc", str(pid))
    return (path.stat().st_uid, (path / "stat").read_text().rsplit(") ", 1)[1].split()[19],
            Path(os.readlink(path / "exe")))


def compare(binary, promotion, mode, rt, dbus):
    child = subprocess.Popen([str(binary), mode, promotion], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    owner = None
    rows, grants = [], []
    pending = b""
    error = None
    controller_killed = False
    selector = selectors.DefaultSelector()
    started = time.monotonic()
    try:
        owner = identity(child.pid)
        if owner[0] != os.getuid() or owner[2] != binary:
            raise RuntimeError("Unexpected diagnostic child ownership or executable")
        selector.register(child.stdout, selectors.EVENT_READ)
        os.set_blocking(child.stdout.fileno(), False)
        while True:
            if time.monotonic() - started > 12:
                raise RuntimeError("Disposable comparison exceeded its 12-second bound")
            if not selector.select(.1):
                continue
            chunk = os.read(child.stdout.fileno(), 16384)
            if not chunk:
                break
            pending += chunk
            if len(pending) > 8192:
                raise RuntimeError("Unexpected child output size")
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                line = raw.decode("ascii")
                rows.append({"line": line, "monotonic_ns": time.monotonic_ns()})
                if len(rows) > 32:
                    raise RuntimeError("Unexpected child output count")
                fields = line.split()
                if not fields or fields[0] != "ready":
                    continue
                if child.poll() is not None:
                    continue
                if len(fields) != 5 or int(fields[1]) != len(grants) or len(grants) >= 9:
                    raise RuntimeError("Unexpected child protocol")
                if int(fields[2]) != child.pid or int(fields[3]) != child.pid:
                    raise RuntimeError("Child requested another process/thread")
                if identity(child.pid) != owner:
                    raise RuntimeError("Owned child identity changed")
                at = time.monotonic_ns()
                rt.MakeThreadRealtimeWithPID(dbus.UInt64(child.pid), dbus.UInt64(child.pid),
                                             dbus.UInt32(9), timeout=1)
                grants.append({"cycle": int(fields[1]), "started_monotonic_ns": at,
                               "returned_monotonic_ns": time.monotonic_ns()})
                if promotion == "waiting":
                    child.stdin.write(b"g")
                    child.stdin.flush()
        child.wait(timeout=2)
    except Exception as failure:
        error = str(failure)
    finally:
        selector.close()
        if child.poll() is None:
            controller_killed = True
            child.kill()
        tail, stderr = child.communicate(timeout=3)
    return {"mode": mode, "promotion": promotion, "pid": child.pid, "birth": owner[1] if owner else None,
            "returncode": child.returncode, "error": error, "rows": rows, "grants": grants,
            "controller_killed": controller_killed,
            "remaining_stdout": (pending + tail).decode("ascii", errors="replace"),
            "stderr": stderr.decode(errors="replace"), "elapsed_seconds": time.monotonic() - started,
            "completed_bursts": sum(row["line"].startswith("busy_complete ") for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True,
                        help="explicitly grant RR9 only to this diagnostic's new children")
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--promotion", choices=["running", "waiting"], default="running")
    args = parser.parse_args()
    try:
        import dbus
    except ImportError:
        parser.error("python3-dbus is required for the explicit RTKit comparison")
    binary = args.binary.resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("--binary must name the compiled diagnostic")
    os.umask(0o077)
    args.output.mkdir(mode=0o700)  # Never overwrite a previous attempt.
    provenance = args.output / "provenance"
    provenance.mkdir(mode=0o700)
    for source in [Path(__file__), Path(__file__).with_suffix(".c"), binary]:
        shutil.copy2(source, provenance / source.name)
    proof = {"binary_sha256": digest(binary), "source_sha256": digest(Path(__file__).with_suffix(".c")),
             "runner_sha256": digest(Path(__file__)), "budget_us": 200000, "rr_priority": 9,
             "busy_ms_per_cycle": 35, "sleep_ms_per_cycle": 200, "requested_cycles": 9,
             "normal_profile_changed": False, "audio_acceptance_evaluated": False, "results": []}
    bus = None
    try:
        bus = dbus.SystemBus(private=True)
        # Bind this attempt to the existing daemon, rather than following a replacement.
        service = bus.get_name_owner("org.freedesktop.RealtimeKit1")
        proxy = bus.get_object(service, "/org/freedesktop/RealtimeKit1", introspect=False)
        rt = dbus.Interface(proxy, "org.freedesktop.RealtimeKit1")
        properties = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
        budget = int(properties.Get("org.freedesktop.RealtimeKit1", "RTTimeUSecMax", timeout=1))
        priority = int(properties.Get("org.freedesktop.RealtimeKit1", "MaxRealtimePriority", timeout=1))
        if budget < 200000 or priority < 9:
            raise RuntimeError("Existing RTKit limits do not permit this bounded comparison")
        proof["rtkit_owner"] = str(service)
        for mode in ["rr-block", "ordinary-block"]:
            result = compare(binary, args.promotion, mode, rt, dbus)
            proof["results"].append(result)
            (args.output / (mode + ".json")).write_text(json.dumps(result, indent=2) + "\n")
            print(mode, "exit", result["returncode"], "completed bursts", result["completed_bursts"], flush=True)
            if result["error"]:
                raise RuntimeError(result["error"])
            if result["returncode"] == 0 and result["completed_bursts"] != 9:
                raise RuntimeError("Child exited without completing the requested bursts")
            if mode == "rr-block" and result["returncode"] != 0:
                raise RuntimeError("Control failed; stopping without another grant sequence")
        control, comparison = proof["results"]
        proof["pattern_observed"] = (control["returncode"] == 0 and control["completed_bursts"] == 9
                                     and comparison["returncode"] == -9 and comparison["completed_bursts"] < 9)
        proof["status"] = "pattern_observed" if proof["pattern_observed"] else "not_reproduced"
        if control["returncode"] != 0 or comparison["returncode"] not in [0, -9]:
            raise RuntimeError("Unexpected child outcome; comparison is inconclusive")
    except (Exception, KeyboardInterrupt) as failure:
        proof.update(status="inconclusive", error=str(failure) or type(failure).__name__)
    finally:
        if bus is not None:
            bus.close()
        (args.output / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    print("Evidence:", args.output)
    return 2 if proof["status"] == "inconclusive" else 0


if __name__ == "__main__":
    raise SystemExit(main())
