"""Keep a verifiable process-group owner alive until session cleanup finishes.

The owner survives its command's exit and SIGTERM. This preserves the identity
needed to terminate descendants, including wrappers that have not reached Wine.
Cleanup releases an idle owner only after its descendants exit, or escalates
to SIGKILL for the whole group after the shutdown deadline.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def process(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        if fields[0] in ("Z", "X"):
            return None
        return int(fields[19]), int(fields[2])  # birth time, process group
    except (OSError, IndexError, ValueError):
        return None


def publish(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".worker-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(value)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run(receipt, result, cancelled, parent, birth, *command):
    stopping = False

    def cancel(_signal, _frame):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, cancel)
    os.setsid()
    pid = os.getpid()
    own_birth = process(pid)[0]
    publish(receipt, f"{pid}\n{own_birth}\nprocess-group-v1\n")
    # FD 9 holds the session lock through receipt publication. If cleanup ran
    # before publication, its permanent cancellation marker blocks any exec.
    parent_state = process(int(parent))
    if stopping or cancelled.exists() or not parent_state or parent_state[0] != int(birth):
        receipt.unlink(missing_ok=True)
        return 1
    os.close(9)
    try:
        status = 143 if stopping else subprocess.Popen(command).wait()
        status = status if status >= 0 else 128 - status
    except OSError as error:
        print(f"ERROR: could not launch {command[0]}: {error}", file=sys.stderr, flush=True)
        status = 1
    # Install graceful release only after wait(), so cleanup cannot release an
    # owner still about to exec. Publish the result before advertising release
    # readiness: status must not mistake a normal quit for a missing result,
    # and cleanup must not release this owner before its result is published.
    signal.signal(signal.SIGUSR1, lambda _sig, _frame: sys.exit(0))
    publish(result, f"{status}\n")
    publish(receipt, f"{pid}\n{own_birth}\nprocess-group-v1\nwaiting\n")
    # Do not relinquish the group identity when the launcher exits: Wine or a
    # wrapper may still have descendants. Cleanup removes the complete group.
    while True:
        signal.pause()


def group_members(group):
    return [int(entry.name) for entry in Path("/proc").iterdir()
            if entry.name.isdecimal()
            and (state := process(int(entry.name))) and state[1] == group]


def wait_until(predicate, seconds):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.03)
    return True


def stop(receipt, label):
    if not receipt.exists():
        return 0
    try:
        owner = receipt.read_text().splitlines()
    except FileNotFoundError:
        return 0  # A cancelled worker can withdraw its receipt before exec.
    if (len(owner) not in (3, 4) or not owner[0].isdecimal() or not owner[1].isdecimal()
            or owner[2] != "process-group-v1" or int(owner[0]) <= 1
            or (len(owner) == 4 and owner[3] != "waiting")):
        raise ValueError(f"invalid {label} ownership record")
    pid, birth = map(int, owner[:2])
    state = process(pid)
    if state != (birth, pid):
        # Never signal a reused PID. If an anchor died unexpectedly while its
        # group survives, retain the record and require recovery investigation.
        if group_members(pid):
            raise ValueError(f"{label} owner lost while descendants remain")
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Cancellation before exec may already have finished.
        def ready_to_release():
            if set(group_members(pid)) - {pid}:
                return False
            if process(pid) != (birth, pid):
                return True
            try:
                return receipt.read_text().splitlines() == [*owner[:3], "waiting"]
            except FileNotFoundError:
                return False

        graceful = wait_until(ready_to_release, 2)
        if process(pid) != (birth, pid):
            if group_members(pid):
                raise ValueError(f"{label} owner disappeared during cleanup")
        elif graceful:
            os.kill(pid, signal.SIGUSR1)
        else:
            os.killpg(pid, signal.SIGKILL)
            print(f"{label}_stop=forced", flush=True)
        if not wait_until(lambda: not group_members(pid), 2):
            raise ValueError(f"{label} descendants did not exit")
    receipt.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    try:
        if sys.argv[1] == "run":
            sys.exit(run(*(Path(value) for value in sys.argv[2:5]), *sys.argv[5:]))
        if sys.argv[1] == "stop":
            sys.exit(stop(Path(sys.argv[2]), sys.argv[3]))
        raise ValueError("expected run or stop")
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}; recovery required.", file=sys.stderr, flush=True)
        sys.exit(1)
