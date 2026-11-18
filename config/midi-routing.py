"""Discover ALSA ports and route only to applications in the guarded session."""
import argparse
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys

sys.dont_write_bytecode = True


class RoutingError(ValueError):
    pass


def parse_ports(text):
    ports, links = {}, set()
    client = port = direction = None
    for line in text.splitlines():
        header = re.match(r"^client (\d+): '(.*)' \[([^]]+)\]", line)
        if header:
            pid = re.search(r"\bpid=(\d+)\b", header[3])
            client = {"client": int(header[1]), "client_name": header[2],
                      "pid": int(pid[1]) if pid else None}
            port = direction = None
            continue
        entry = re.match(r"^\s+(\d+)\s+'(.*)'\s*$", line)
        if entry and client:
            port = f"{client['client']}:{int(entry[1])}"
            ports[port] = dict(client, address=port, name=entry[2].strip())
            direction = None
            continue
        if not port:
            continue
        if "Connecting To:" in line:
            direction = "out"
        elif "Connected From:" in line:
            direction = "in"
        elif not re.match(r"^\s+\d+:\d+", line):
            direction = None
        if direction:
            for a, b in re.findall(r"\b(\d+):(\d+)\b", line):
                other = f"{int(a)}:{int(b)}"
                links.add((port, other) if direction == "out" else (other, port))
    return ports, links


def process(pid, proc_root):
    node = proc_root / str(pid)
    if pid <= 1 or node.stat().st_uid != os.getuid():
        raise RoutingError("Session process is not owned by this user")
    fields = (node / "stat").read_text().rsplit(") ", 1)[1].split()
    if fields[0] in {"Z", "X"}:
        raise RoutingError("Session process has exited")
    return int(fields[19]), int(fields[2])


def guarded_application(root, runtime, role="ableton", proc_root=Path("/proc")):
    session_path, receipt = runtime / "session.state", runtime / f"{role}.state"
    session, owner = session_path.read_text().splitlines(), receipt.read_text().splitlines()
    if (len(session) != 5 or session[3] != str(root.resolve())
            or len(owner) != 3 or owner[2] != "process-group-v1"):
        raise RoutingError("Guarded-session ownership does not match this checkout")
    prefix = Path(session[2])
    if not prefix.is_absolute() or str(prefix.resolve()) != str(prefix):
        raise RoutingError("Guarded prefix is not canonical")
    if process(int(session[0]), proc_root)[0] != int(session[1]):
        raise RoutingError("Supervisor PID was reused")
    supervisor_args = (proc_root / session[0] / "cmdline").read_bytes().split(b"\0")
    if os.fsencode(root / "bin/waydaw") not in supervisor_args or b"start" not in supervisor_args:
        raise RoutingError("Supervisor is not the guarded WayDAW launcher")
    group, birth = map(int, owner[:2])
    if process(group, proc_root) != (birth, group):
        raise RoutingError("Application worker identity changed")
    worker_args = (proc_root / owner[0] / "cmdline").read_bytes().split(b"\0")
    expected = [os.fsencode(root / "config/session-worker.py"), b"run", os.fsencode(receipt)]
    if not any(worker_args[i:i + 3] == expected for i in range(len(worker_args))):
        raise RoutingError("Application worker is not the expected session owner")
    if not Path(session[4]).is_absolute() or (Path(session[4]).parent / "cancelled").exists():
        raise RoutingError("Session is stopping")
    names = ({"ableton live 12 suite.exe", "ableton live 12 standard.exe", "ableton live 12 intro.exe"}
             if role == "ableton" else {"miditranslator.exe", "bome midi translator pro.exe"})
    matches = []
    for node in proc_root.iterdir():
        if not node.name.isdecimal():
            continue
        try:
            pid = int(node.name)
            identity = process(pid, proc_root)
            if identity[1] != group:
                continue
            argv = (node / "cmdline").read_bytes().split(b"\0")
            if not argv or PureWindowsPath(os.fsdecode(argv[0])).name.casefold() not in names:
                continue
            env = dict(os.fsdecode(item).split("=", 1) for item in
                       (node / "environ").read_bytes().split(b"\0") if b"=" in item)
            if env.get("WINEPREFIX") == str(prefix):
                matches.append((pid, identity[0]))
        except (OSError, ValueError, IndexError):
            continue
    if len(matches) != 1:
        raise RoutingError(f"Expected one running guarded {role} application")
    if (session_path.read_text().splitlines() != session or receipt.read_text().splitlines() != owner):
        raise RoutingError("Guarded session changed during discovery")
    return {"pid": matches[0][0], "birth": matches[0][1], "session": session, "owner": owner}


def choose(label, candidates, override=None):
    if override:
        candidates = [p for p in candidates if p["address"] == override]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise RoutingError(f"Ambiguous {label} ports; select an explicit WAYDAW_{label.upper()}_PORT")
    return candidates[0]["address"]


def select_ports(ports, application_pid, environment):
    values = list(ports.values())
    return {
        "launchpad": choose("launchpad", [p for p in values if p["client_name"].startswith("Launchpad")
                                          and "MIDI" in p["name"]], environment.get("WAYDAW_LAUNCHPAD_PORT")),
        "bus": choose("midi_bus", [p for p in values if p["client_name"] == "Midi Through"
                                  and p["name"].startswith("Midi Through Port-")
                                  and (environment.get("WAYDAW_MIDI_BUS_PORT") or p["name"] == "Midi Through Port-0")],
                      environment.get("WAYDAW_MIDI_BUS_PORT")),
        "ableton": choose("ableton", [p for p in values if p["pid"] == application_pid
                                      and p["client_name"].casefold() == "wine midi driver"
                                      and p["name"] == "WINE ALSA Input"]),
    }


def bome_ports(ports, application, proc_root=Path("/proc")):
    # ALSA records the creating thread ID, which can be Bome's Java event
    # thread rather than its main PID. Verify its guarded process group.
    group = int(application["owner"][0])
    result = {"inputs": [], "outputs": []}
    for port in ports.values():
        if (port["pid"] is None or port["client_name"].casefold() != "wine midi driver"
                or not (port["name"] == "WINE ALSA Input"
                        or port["name"].startswith("WINE ALSA Output"))):
            continue
        try:
            if process(port["pid"], proc_root)[1] == group:
                direction = "inputs" if port["name"] == "WINE ALSA Input" else "outputs"
                result[direction].append(port["address"])
        except (OSError, ValueError, IndexError):
            continue
    return {name: sorted(addresses) for name, addresses in result.items()}


def project_connections(selected, bome, links):
    return {"input_connected": any((selected["launchpad"], dst) in links for dst in bome["inputs"]),
            "output_connected": any((src, selected["bus"]) in links for src in bome["outputs"])}


def reconnect_input(selected, bome, project):
    # Only resubscribe an existing, owned input. Never create an application
    # port or replace the project's MIDI output selection.
    if project["input_connected"]:
        return []
    if not project["output_connected"] or len(bome["inputs"]) != 1 or not selected["launchpad"]:
        raise RoutingError("Cannot restore Bome input: expected one open input and its MIDI Through output")
    return [("connect", selected["launchpad"], bome["inputs"][0])]


def changes(selected, links, mode, clear=False, bome_outputs=()):
    required = {"ableton"} if clear else {"ableton", "launchpad"}
    if not clear and mode == "bome":
        required.add("bus")
    missing = [name for name in sorted(required) if selected[name] is None]
    if missing:
        raise RoutingError("Required MIDI ports not found: " + ", ".join(missing))
    if clear:
        return [("disconnect", src, selected["ableton"]) for src in
                (selected["launchpad"], selected["bus"])
                if src is not None and (src, selected["ableton"]) in links]
    launchpad = (selected["launchpad"], selected["ableton"])
    translated = (selected["bus"], selected["ableton"])
    desired = {launchpad} if mode == "direct" else {translated}
    remove = ({launchpad, translated} | {(src, selected["ableton"]) for src in bome_outputs}) - desired
    # Establish translated output before removing an existing direct input.
    return [("connect", *pair) for pair in sorted(desired - links)] + [
        ("disconnect", *pair) for pair in sorted(remove & links)]


def snapshot():
    result = subprocess.run(["aconnect", "-l"], capture_output=True, text=True, check=True, timeout=5)
    return parse_ports(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "check", "route", "clear"))
    parser.add_argument("--mode", choices=("direct", "bome"), default="bome")
    parser.add_argument("--apply", action="store_true", help="apply the displayed connections/disconnections")
    parser.add_argument("--reconnect", action="store_true",
                        help="restore a lost Launchpad subscription into Bome's already-open input")
    args = parser.parse_args(argv)
    if args.reconnect and (args.command != "route" or args.mode != "bome"):
        parser.error("--reconnect requires route --mode bome")
    root = Path(__file__).resolve().parents[1]
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("XDG_STATE_HOME")
                   or Path.home() / ".local/state") / "waydaw"
    ports, links = snapshot()
    app = guarded_application(root, runtime)
    selected = select_ports(ports, app["pid"], os.environ)
    bome = None
    bome_addresses = {"inputs": [], "outputs": []}
    needs_bome = args.command in {"check", "route"} and args.mode == "bome"
    if args.command != "clear" and (needs_bome or (runtime / "bome.state").exists()):
        bome = guarded_application(root, runtime, "bome")
        bome_addresses = bome_ports(ports, bome)
    outputs = bome_addresses["outputs"]
    project = project_connections(selected, bome_addresses, links)
    report = {"mode": args.mode, "ports": selected, "ableton_pid": app["pid"],
              "connections": sorted(links), "applied": False,
              "bome_output_ports": outputs,
              "bome_project": project,
              "scope": "ALSA routes only; verify Bome project processing with an actual MIDI signal"}
    if args.command == "inspect":
        report["inventory"] = list(ports.values())
        print(json.dumps(report, indent=2))
        return 0
    plan = changes(selected, links, args.mode, clear=args.command == "clear", bome_outputs=outputs)
    input_plan = reconnect_input(selected, bome_addresses, project) if args.reconnect else []
    plan = input_plan + plan
    report["changes"] = plan
    project_ready = args.mode == "direct" or all(project.values()) or bool(input_plan)
    report["ready"] = not plan and project_ready and args.command != "clear"
    if args.command == "check":
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 1
    if args.apply:
        if args.command != "clear" and not project_ready:
            raise RoutingError("Bome project ports are not connected: route Launchpad input to MIDI Through in Bome first")
        for action, src, dst in plan:
            if guarded_application(root, runtime) != app:
                raise RoutingError("Session changed before MIDI routing")
            if bome is not None and guarded_application(root, runtime, "bome") != bome:
                raise RoutingError("Bome session changed before MIDI routing")
            current_ports, _ = snapshot()
            if select_ports(current_ports, app["pid"], os.environ) != selected:
                raise RoutingError("MIDI ports changed before routing")
            if bome is not None and bome_ports(current_ports, bome) != bome_addresses:
                raise RoutingError("Bome ports changed before routing")
            command = ["aconnect"] + (["-d"] if action == "disconnect" else []) + [src, dst]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode:
                _, current = snapshot()
                if ((src, dst) in current) != (action == "connect"):
                    raise RoutingError(f"Could not {action} MIDI route {src} -> {dst}")
        current_ports, actual = snapshot()
        if select_ports(current_ports, app["pid"], os.environ) != selected:
            raise RoutingError("MIDI ports changed while routing")
        if guarded_application(root, runtime) != app:
            raise RoutingError("Session changed while routing")
        if bome is not None and (guarded_application(root, runtime, "bome") != bome
                                or bome_ports(current_ports, bome) != bome_addresses):
            raise RoutingError("Bome session or ports changed while routing")
        if any(((src, dst) in actual) != (action == "connect") for action, src, dst in plan):
            raise RoutingError("MIDI routing did not reach the requested state")
        report["applied"] = True
        report["connections"] = sorted(actual)
        report["bome_project"] = project_connections(selected, bome_addresses, actual)
        report["ready"] = (not changes(selected, actual, args.mode, bome_outputs=outputs)
                           and (args.mode == "direct" or all(report["bome_project"].values()))) if args.command != "clear" else False
        if args.command != "clear" and not report["ready"]:
            raise RoutingError("MIDI routing changed before verification")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
        print(json.dumps({"ready": False, "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
