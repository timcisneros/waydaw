# waydaw

Linux Wayland/Wine session harness for Ableton Live 12, Max for Live,
Bome MIDI Translator Pro, and Windows VST2/VST3 plugins.

[Portfolio case study](https://timcis.com/projects/waydaw)

WayDAW provides a guarded Proton/XWayland launch path for KDE Plasma Wayland,
explicit dependency checks, session logs, and recovery scoped to one copied
Wine prefix. The sizing shim preserves Ableton's menu row; a runtime KWin
controller protects the KDE frame and translates maximize into safe-fit.

The launcher infrastructure has automated regression tests. A production
release still requires the recording, authorization, MIDI, and recovery
acceptance checks in [the readiness plan](docs/production-readiness.md).

## Start here

Run commands from the repository root:

```sh
./bin/waydaw check
./bin/waydaw start
```

The launcher applies `pw-jack` itself. For a full session with Bome:

```sh
./bin/waydaw check --with-bome
./bin/waydaw start --with-bome
```

Bome and Ableton use the same copied prefix and Proton runner. The supervisor
starts an optional ALSA-to-JACK bridge if none exists. Each launcher has a
recorded process-group owner. Cleanup cancels and terminates these groups
before shutting down the copied-prefix wineserver and unloading the runtime
KWin controller. It checks owner identity before signalling a group, allows
two seconds for SIGTERM, then uses SIGKILL with a two-second exit deadline.
An existing bridge is preserved. Close Ableton normally after saving both
applications.

After startup, a Bome failure marks `status` as `session=degraded`, with
`bome=failed` and its exit code. The supervisor logs the failure and sends one
critical desktop notification when `notify-send` is available. Ableton stays
open so you can save before closing and restarting the full session. If Ableton
later exits successfully, the session returns Bome's failure code; an Ableton
error keeps its own exit code. A normal Bome quit reports `bome=stopped` without
an error alert and lets Ableton continue.
Status is read-only. If the supervisor cannot publish its Bome health record,
status falls back to this session's worker result and verifies the worker's
PID, birth time, and process group. Missing or invalid ownership for a
participating Bome worker reports degraded health instead of assuming success,
including when the session log directory is unreadable.

Inspect the command without launching or changing files:

```sh
./bin/waydaw start --dry-run
./bin/waydaw status
./bin/waydaw stop --dry-run
```

`check` queries the host services and reads files; it does not launch Wine,
repair DLLs, edit preferences, install the shim, or load a KWin script.
`start --dry-run` only describes the selected command; use `check` for a full
host preflight. `--print-launch-config` is also read-only.

## Desktop launcher

```sh
./bin/install-waydaw-desktop --print
./bin/install-waydaw-desktop
```

Select **WayDAW** in KDE's application menu. Its default action starts Ableton;
additional actions start with Bome, check the environment, or stop the session.
Menu launches open Ableton without a terminal window. The `bin/waydaw-desktop`
frontend calls the same `bin/waydaw` supervisor as the terminal workflow,
records startup output under `~/.local/state/waydaw/desktop/`, and shows a
dialog if startup or the session fails, including cleanup errors from that
session's own log. The environment-check action displays
its results in a dialog. Detailed session logs remain under
`~/.local/state/waydaw/logs/`.

If the Wine-generated **Ableton Live 12 Suite** shortcut exists, the installer
also routes it through WayDAW while preserving its menu identity and icon.
It saves the first original shortcut and installation record in
`~/.local/state/waydaw/desktop-install.json`. Run the installer again after
moving the checkout or if Wine regenerates its shortcut.
`./bin/install-waydaw-desktop --uninstall` removes the WayDAW entry and restores
the original Ableton shortcut. Independently edited entries are preserved;
the saved original remains available across uninstall/reinstall cycles.

## Runtime and prefixes

The supported runtime is recorded in `config/validated-runtime.sh`:

- Kron4ek Proton Experimental 11.0 standalone runner, pinned archive checksum.
- Upstream DXVK 2.7.1, with its archive and native D3D10/11 DLL hashes pinned.
- Repository sizing shim, built from `compat/ableton-sizing-shim`.
- KDE Plasma Wayland with XWayland, PipeWire JACK compatibility, and WineASIO
  registered in the copied prefix. Audio settings require host validation.

The runtime runner lives at:

```text
.local-runners/kron4ek-proton-exp-11.0/bin/
```

The supported session uses:

```text
~/WinePrefixes/ableton12-winebase-protonexp-test
```

An existing validated copy may be selected with
`WAYDAW_ABLETON_RUNNER_PREFIX=/absolute/path/to/copy`. Use the same selection
for Start, Check, and Stop. Launch and recovery resolve symlink aliases and
refuse paths overlapping the legacy working prefix:

```text
~/WinePrefixes/ableton12
```

The working prefix is a read-only fallback source for restoring the exact
pinned `d3d11.dll`, `dxgi.dll`, and `d3d10core.dll` in the copied prefix.
Wine builtin markers are rejected even when a recorded hash matches; those
files can fall back to Wine's renderer under Proton. If neither location has
the verified native DLLs, startup fails. The guarded process forces native
loading for all three DLLs without modifying the registry. Prefix preparation runs at real launch under the
session lock. It seeds missing copied `steamuser` preferences from the current
Linux user's copied profile and normalizes saved placement with a backup.
Normalization replaces the preferences atomically, preserves the first backup,
and rejects backup symlinks before changing the preferences.
Bome startup uses the built `wait-bome.exe` helper to acknowledge Windows GUI
initialization with `WaitForInputIdle`; an elapsed delay alone is insufficient.
Preflight and launch share executable discovery and reject Bome executables
outside the copied prefix. In guarded Proton sessions Bome uses the same
XWayland display path as Ableton.
Discovery accepts `MIDITranslator.exe` and `Bome MIDI Translator Pro.exe`;
setup programs and executable backups do not qualify. Standard installation
locations take priority; multiple fallback application matches are rejected.
The host allows 45 seconds for the complete startup, including Wine bootstrap;
the helper allows 30 seconds for GUI initialization. This acknowledgement does
not validate a loaded Bome project or MIDI routing. Ableton verifies the pinned
DXVK DLL hashes after this acknowledgement, immediately before launch.
If Bome's Wine startup changes the DLLs, the
session aborts and cleans up; it does not repair DLLs while Bome is running.
The harness does not install or authorize Ableton, Bome, plugins, WineASIO,
or system packages. See the readiness plan for reproducible host setup.

For settings specific to this machine, the guarded launcher reads optional
PipeWire property data from `~/.config/waydaw/pipewire.properties`. It also uses
`~/.config/waydaw/pipewire/` as `PIPEWIRE_CONFIG_DIR` when that directory contains
`jack.conf`. Explicit environment values take precedence. These files affect
WayDAW's child processes; they do not change the desktop audio service.
Preflight and session logs report the selected values. A full JACK configuration
can control data-thread scheduling, which `rt.prio` in JACK properties alone
does not disable.

## Session controls and compatibility commands

```sh
./bin/waydaw status
./bin/waydaw stop
```

`stop` is emergency recovery: it terminates the copied-prefix Wine session,
so unsaved work may be lost. Prefer saving and closing Ableton normally.
Stop validates the supervisor PID and birth time before signalling it.
Without a supervisor, it waits up to five seconds for pending worker setup to
release the same lock before recovering the copied prefix through its matching
wineserver. A lock timeout preserves the recovery record. It terminates recorded launcher groups
first, preventing a delayed wrapper from starting Wine after a successful Stop.
It never kills by a process-name regex. Stop waits up to 45 seconds for cleanup.

If a supervisor crashes or cleanup fails, `status` reports
`session=recovery-required`. A new Start refuses to prepare or launch that
session until `stop` succeeds. Use the checkout and prefix recorded by Status
to recover it. Stop also recovers recorded launcher groups and a bridge owned
by the failed session. Do not delete ownership or session records to bypass
recovery. If an owner disappears while its descendants remain, recovery fails
and preserves the record for inspection rather than signalling an unknown group.

Only one supervised WayDAW session runs per user. A second Start fails before
changing the prefix. Long-lived children do not retain the session lock; worker
setup retains it until ownership is recorded and cancellation is checked. Cleanup errors
return a failure status and are recorded in the session log.

Existing commands route to the supervisor:

| Command | Behavior |
| --- | --- |
| `./bin/ableton-wayland` | Guarded Start |
| `./bin/session` | Guarded Start with Bome |
| `./bin/check` | Guarded preflight |
| `./bin/kill-session` | Guarded emergency Stop |
| `./bin/verify-proton-runner-mode` | Isolated regression suite |

`bin/ableton` remains an explicit system-Wine diagnostic path by default.
`bin/ableton-proton` remains a lower-level Proton diagnostic launcher; it does
not provide the supervisor's session lifecycle. Use neither for normal sessions.
`bin/check-system` and `bin/kill-system-session` explicitly target the older
system-Wine setup. `bin/ableton-native-wayland` is experimental. Do not run
these diagnostic launchers concurrently with a supervised session.

## Audio and MIDI

The production audio path is PipeWire JACK compatibility plus WineASIO. Use a
consistent sample rate and buffer size in PipeWire and Ableton. Preflight checks
PipeWire service availability; it does not prove WineASIO registration, actual
routing, latency, or recording quality.

For diagnostics against the supported copied prefix:

```sh
WAYDAW_ABLETON_RUNNER=proton-exp ./bin/wineasio-check
WAYDAW_ABLETON_RUNNER=proton-exp ./bin/audio-check
WAYDAW_ABLETON_RUNNER=proton-exp ./bin/bome-midi-check
./bin/session-status
```

Bome's Windows BMIDI kernel driver is not the Linux routing foundation.
Use ALSA sequencer MIDI, VirMIDI, and PipeWire/JACK graph routing. The working
manual topology is Launchpad S directly to Wine/Ableton, plus Bome output
through VirMIDI to Ableton. Device IDs and temporary routes can change on reboot
or reconnect. Once Ableton has created its Wine MIDI ports, inspect and apply:

```sh
./bin/midi-route-inspect
./bin/apply-live-routes
./bin/midi-route-inspect
```

`./bin/clear-live-routes` removes those temporary routes. The supervisor does not
load kernel modules, create persistent routing, or change PipeWire settings.

## Updates and recovery

Keep Ableton's in-app updater disabled. A `.Live 12 Suite_updated` swap marker
blocks startup. `_autoupdates` alone produces a warning. The historical failure
was `Swapper: rename_1 stage failed: Sharing violation.`

After saving and stopping the session, inspect/update-disable the selected copy:

```sh
WAYDAW_ABLETON_RUNNER=proton-exp ./bin/disable-ableton-updates
./bin/waydaw check
```

This maintenance command renames known updater paths to timestamped backups.
It does not delete them. Back up the entire stopped prefix before manually
installing any Ableton update. Validate updates in a separate copied prefix
before using them for daily work.

## Logs and verification

Each supervised session prints a unique log path under:

```text
${XDG_STATE_HOME:-~/.local/state}/waydaw/logs/<timestamp>-<id>/session.log
```

The session log includes the effective runner, prefix, graphics overrides,
application output, and cleanup result. The logging relay continues when its
stdout reader disconnects. Cleanup writes directly to the session log, so it
can finish even if the relay exits; inspect that log for shutdown diagnostics.
New sessions record their exact log path for Stop, so the desktop action can
display cleanup errors even when the session started in a terminal. Older
session records remain supported but do not contain that path.
Existing diagnostic commands also keep
logs under the checkout's `logs/` directory. Logs may include user and project
paths; review them before sharing. Session logs are retained until you remove
them deliberately.

```sh
./bin/verify-proton-runner-mode
node tests/test_kwin_controller.cjs
```

Tests use disposable homes, copied scripts, fake Wine/KWin/PipeWire services,
and fixture DLLs. They never touch real prefixes or the desktop. The Node.js
check covers KWin windows with and without optional decoration signals,
decoration protection, window scoping, and removal of closed-window state. CI verifies
shell syntax, ShellCheck for session scripts, desktop entries, launcher behavior,
and reproducible MinGW builds of the sizing shim and Bome readiness helper.

Read [the production-readiness plan](docs/production-readiness.md) for the
implementation milestones, first-machine setup, release gates, and rollback.
