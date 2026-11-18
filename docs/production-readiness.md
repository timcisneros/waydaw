# Production-readiness plan

The first release target is the measured KDE Plasma Wayland/XWayland setup,
with the pinned Proton/DXVK path, PipeWire JACK compatibility, and WineASIO.
The completed launcher work does not certify recording performance or broaden
support to other compositors, display layouts, or Wine builds.

## Implementation sequence

1. Unify terminal, desktop, and full-session startup behind `bin/waydaw`.
   Keep Bome and Ableton in the copied prefix and reject duplicate sessions.
2. Separate read-only runner selection and inspection from real preparation.
   Refuse working-prefix aliases/overlaps and unsafe directory symlinks.
   Publish preference backups exclusively, reject backup symlinks, and replace
   updated preferences atomically while preserving the original backup.
3. Make missing fixes fail before Wine launches; supervise exit, interruption,
   emergency Stop, and cleanup using the matching prefix-scoped wineserver.
   Preserve incomplete-session records until Stop succeeds. Verify DXVK again
   after Bome's explicit GUI-initialization acknowledgement. Bound startup and
   group termination, retaining a verifiable process-group owner for each
   launcher. Cancel and terminate groups before Wine shutdown, including during
   crash recovery and when a wrapper has not yet started Wine. Wait briefly for
   pending workers to release the lock after supervisor death. Keep cleanup
   independent of stdout readers and the logging relay.
4. Verify behavior in isolated fixtures and CI; make the shim and readiness
   helper builds reproducible with the same compiler/toolchain.
5. Document installation, runtime identity, acceptance evidence, and rollback.

These software changes are implemented. The initially missing prefixes were
recreated from the Ableton 12.4.2 installer on 2026-11-16. That reconstruction
verified the editor, normal exit, the native DXVK renderer on Intel
Iris Xe, and WineASIO initialization through PipeWire JACK. Subsequent local
validation used authorized Live 12.4.16 and confirmed a real 48 kHz recording,
Max for Live signal processing, native save/reopen/export, and seven physical
Launchpad pad pairs forwarded unchanged through Bome. Later reboot/reconnect recovery checks and isolated source/project restoration
are recorded in [reliability validation](reliability-validation-20261118.md).
Sustained testing exposed audio gaps with ordinary scheduling at both 1024 and
2048 samples. A scoped realtime 2048-sample trial also stopped after about two
hours and six minutes on a signal/clock discontinuity; the measurement client's
contribution remains under investigation. The production plugin set and
sustained workload acceptance remain release gates;
a release tag remains pending.

The reconstruction uses pinned upstream DXVK 2.7.1. The historical debug DLLs
carried Wine builtin markers and fell back to a renderer that Ableton
blacklisted on this host. Hash verification alone did not establish an active
DXVK backend. Preflight and launch now also reject that marker, and require
`d3d10core.dll` alongside `d3d11.dll` and `dxgi.dll` for Live's D3D10 consumers.

The restored installation also needed genuine Microsoft C++ runtime DLLs.
Successful redistributable installation alone was insufficient: verify the
installed architecture and files rather than accepting Wine builtin stubs.
The installation evidence records the extracted Microsoft payload hashes.

Realtime ASIO streaming caused exit 137 on this host. Limiting only JACK's
`rt.prio` did not disable PipeWire's realtime data thread. The machine-specific
fallback uses a separate JACK configuration under
`~/.config/waydaw/pipewire/jack.conf` with ordinary thread scheduling.
`bin/waydaw` passes that directory only to its own processes. This fallback
requires recording and dropout acceptance before production use; do not infer
realtime stability from successful driver initialization.

## First-machine setup

1. Start with KDE Plasma Wayland and working XWayland. Install host dependencies
   through the distribution's package manager: Bash, coreutils (`realpath`,
   `sha256sum`, `timeout`), util-linux (`flock`), systemd user tools (`busctl`,
   `systemctl`), Python 3, and PipeWire JACK compatibility (`pw-jack`). MinGW's
   `x86_64-w64-mingw32-gcc` is needed to build the shim and Bome readiness
   helper. Optional diagnostics use `jack_lsp`, `aconnect`, `pw-link`, and
   `qpwgraph`. `a2jmidid` is optional;
   the supervisor starts one bridge only when no existing bridge is found.
   Node.js is required for the isolated KWin compatibility check, not for launch.
2. Check out the intended WayDAW commit in a writable location. Record its full
   SHA (`git rev-parse HEAD`). Do not update that checkout during a session.
3. Acquire the runner archive named in `config/validated-runtime.sh` from its
   recorded URL. Verify its SHA-256 before extracting it. These commands only
   read the runtime manifest and create the runner directory:

   ```sh
   source ./config/validated-runtime.sh
   mkdir -p .local-runners
   curl --fail --location "$WAYDAW_RUNNER_URL" -o ".local-runners/$WAYDAW_RUNNER_ARTIFACT"
   printf '%s  %s\n' "$WAYDAW_RUNNER_SHA256" ".local-runners/$WAYDAW_RUNNER_ARTIFACT" | sha256sum --check
   tar -tf ".local-runners/$WAYDAW_RUNNER_ARTIFACT" | head
   mkdir -p .local-runners/kron4ek-proton-exp-11.0
   tar -xf ".local-runners/$WAYDAW_RUNNER_ARTIFACT" \
     -C .local-runners/kron4ek-proton-exp-11.0 --strip-components=1
   ```

   Extract the verified archive so the executables end up at
   `.local-runners/kron4ek-proton-exp-11.0/bin/wine` and `bin/wineserver`.
   Account for the archive's top-level directory; do not extract into `/usr`.
   The manifest pins the archive, not arbitrary files later edited in an
   extracted runner. Restore from the verified archive when runner integrity
   is uncertain.
4. Restore your own stopped, licensed Ableton/Bome prefix into
   `~/WinePrefixes/ableton12-winebase-protonexp-test`. Preserve the legacy
   `~/WinePrefixes/ableton12` as a separate backup/reference. A filesystem copy
   with copy-on-write reflinks is suitable; do not use hard-link farms or
   symlink application/system directories into the working prefix. A blank
   prefix will not work: this project does not redistribute or install the
   proprietary applications, activations, plugins, or WineASIO.
5. Acquire the upstream DXVK archive recorded in the manifest and verify it:

   ```sh
   source ./config/validated-runtime.sh
   curl --fail --location "$WAYDAW_DXVK_URL" -o ".local-runners/$WAYDAW_DXVK_ARTIFACT"
   printf '%s  %s\n' "$WAYDAW_DXVK_SHA256" ".local-runners/$WAYDAW_DXVK_ARTIFACT" | sha256sum --check
   mkdir -p .local-runners/dxvk-2.7.1
   tar -xf ".local-runners/$WAYDAW_DXVK_ARTIFACT" \
     -C .local-runners/dxvk-2.7.1 --strip-components=1
   ```

   Finish Wine bootstrap, WineASIO registration, and the native DLL overrides
   for `d3d11`, `dxgi`, and `d3d10core` using the selected runner before
   installing the graphics files. Stop that prefix's Wine server, then copy
   the archive's `x64/d3d11.dll`, `x64/dxgi.dll`, and `x64/d3d10core.dll` into
   copied-prefix `drive_c/windows/system32`, replacing destination symlinks
   rather than following them. Verify all three manifest hashes. The launcher
   can repair them only when the stopped working-prefix reference has the
   exact same files. Other DXVK builds require a separate compatibility check.
6. Build the shim with `./compat/ableton-sizing-shim/build.sh` and the Bome
   readiness helper with `./compat/waydaw-launch/build.sh`. The helper is
   required for `--with-bome`; preflight rejects a missing build. These builds
   do not execute Wine or modify a prefix. The tracked
   shim is available, but a reproducible source build should be recorded for a
   release. Rebuilding changes the local artifact; review its hash before use.
7. Run `./bin/waydaw check --with-bome` (or omit Bome), then
   `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/wineasio-check`. Set up audio and MIDI
   in the selected prefix. `check` only proves prerequisite availability.
   For Bome's bundled Windows Java runtime, install and register Arial,
   Courier New, Times New Roman, and Tahoma in the copied prefix during stopped
   maintenance. Verify readable menus and dialogs after a cold launch. Missing
   Windows fonts can make Java select an unrelated host font; this machine
   selected the TeX `drmit10` math font until the standard fonts were installed.
   Preserve the font installers, checksums, and registration data with recovery
   artifacts. Keep Bome's Windows virtual-MIDI driver disabled under Wine and
   configure native Linux MIDI ports and project aliases separately. Follow
   [MIDI routing setup](midi-routing.md) to load a Bome project automatically and
   opt into guarded route maintenance using the existing MIDI Through port.
8. Install the desktop entry with `./bin/install-waydaw-desktop`. It creates
   `com.timcis.WayDAW.desktop` under the user's XDG applications directory.
   Menu launches use `bin/waydaw-desktop` with `Terminal=false`; successful
   startup is silent. That frontend records early startup output and displays
   failures, including session cleanup errors, in a dialog while keeping the
   same guarded supervisor. If Wine's `Ableton Live 12 Suite.desktop` exists,
   the installer redirects it too, preserving its menu identity and icon and
   saving the first original in `waydaw/desktop-install.json` under the XDG state
   directory. Both entries use the checkout's absolute path; rerun the installer
   after moving it or after Wine regenerates its shortcut.

## Release evidence

Create one release record identifying the WayDAW commit, runner archive and
checksum, built shim/helper hashes and compiler version, DXVK hashes, Ableton/Bome/plugin
versions, distro/kernel, Plasma/KWin/XWayland, GPU/driver, monitor resolution
and scaling, PipeWire/WirePlumber, WineASIO, audio interface, sample rate, and
buffer size. The manifest records only the established software baseline;
host-specific fields must come from the acceptance machine.

All items below must pass on that recorded environment before a release tag:

- Legitimate authorization completes in the copied prefix and survives closing,
  relaunching, and rebooting. Do not infer this from an interactive dialog.
  Browser `ableton://authorize` callbacks and offline `.auz` files must return to
  the running guarded instance without starting the legacy installation. Stop
  must cancel a pending delivery before Wine shutdown. No callback URL or token
  may appear in WayDAW's logs. Delivery acknowledgement alone does not establish
  successful authorization; check the application and a cold relaunch.
- Terminal and KDE menu launches produce the same runner, prefix, and guards.
- Bome GUI initialization acknowledges before Ableton launches, including on a
  cold Wine start. A stalled or early-exiting Bome blocks Ableton. Confirm Bome
  project loading and MIDI routing separately; `WaitForInputIdle` does not
  establish application-specific readiness.
  After startup, test a failed Bome exit and loss of its process-group owner:
  status must report `session=degraded` and a desktop notification must warn
  when `notify-send` is available, while Ableton stays open for saving. A normal
  Bome quit reports `bome=stopped` without an error alert. Confirm Stop still
  succeeds if notification delivery fails or stalls. Simulate failure to publish
  the Bome health record: Status must use the session's worker result or verify
  its PID, birth time, and process group, and report degraded health when those
  records cannot verify Bome. Pause normal-exit result publication: status must
  remain healthy, then report Bome stopped after publication. Stop during the
  result-to-waiting transition must complete without forcing the Bome owner.
  Status queries must not write records, signal processes, or send notifications.
  Only application executable
  names qualify for Bome discovery; an installer alone must fail preflight.
  Test both Ableton-only and Bome sessions. Verify File/Edit menus, plugin
  windows, resize, safe-fit maximize, restore, and normal close.
- Record audio and MIDI into a representative project, save it, quit, reopen,
  and export. Confirm recorded files and export content, not merely UI activity.
- Exercise the actual VST2/VST3 set and Max for Live devices used in production.
  Confirm plugin state persists when reopening the project.
- Validate Launchpad/Bome/MIDI Through routes after reboot and device reconnect.
  No stuck notes, duplicate notes, or unexpected feedback loops.
- Run the representative project for at least four hours at the intended sample
  rate/buffer. Record xruns/dropouts and CPU behavior, separating startup events
  from steady playback/recording. Require zero unexplained steady-state dropouts
  for the tested workload; record actual latency measurements if latency matters.
- Test duplicate Start, a failed launch, terminal closure, normal exit, and
  emergency Stop. Test supervisor death and cleanup failure: Start must remain
  blocked until explicit recovery succeeds with the recorded checkout/prefix.
  Confirm Bome-induced graphics DLL changes block Ableton launch. Test delayed
  launchers, cancellation during startup, and bounded group termination using
  isolated fixtures rather than disrupting live
  MIDI services. After cleanup, the copied-prefix wineserver is stopped, the
  WayDAW KWin script is unloaded, and any bridge started by WayDAW is stopped.
  A pre-existing bridge and unrelated Wine prefixes remain running.
- Isolated regressions must also cover backup symlinks, atomic preference
  updates, disconnected stdout, a terminated logging relay, and recovery while
  a pending worker still holds the inherited session lock. Failed tests must
  reap their own fixture processes before deleting the temporary prefix.
- Verify a backup restore and a rollback to the previous known-good commit and
  prefix. Re-run the core recording/save/reopen/export checks after restoration.
- Run `./bin/verify-proton-runner-mode`, `node tests/test_kwin_controller.cjs`,
  and CI. Keep the acceptance record and
  relevant session log paths with the release. Do not mark unchecked items as
  passing because automated fixture tests pass.

The current sizing band is designed around the measured desktop. Fractional
scaling, smaller displays, monitor changes, and other GPU drivers need their own
acceptance record. Preflight does not currently certify those combinations.

## Updates and rollback

Save Ableton and Bome work and close the session normally before maintenance.
Confirm `./bin/waydaw status` is stopped. If the session is hung,
`./bin/waydaw stop` is emergency termination and may lose unsaved work.

If Status reports `session=recovery-required`, use its `recorded_checkout` and
`recorded_prefix` values to run Stop from that checkout with the same
`WAYDAW_ABLETON_RUNNER_PREFIX`. Recovery keeps the marker when any shutdown
step fails, and subsequent Start remains blocked. Stop verifies the matching
wineserver has exited before unloading the KWin controller. If Wine exit cannot
be confirmed, it retains the controller and reports failure. Do not remove the
records by hand to force a restart; resolve the reported error and retry Stop.
After supervisor death, recovery waits up to five seconds for workers still
publishing ownership to release the lock. If that deadline expires, Stop reports
the contention and leaves the recovery record intact without beginning cleanup.

Cleanup diagnostics go directly to the session log. Disconnecting stdout leaves
file logging active; if the logging relay itself exits, shutdown still records
its result directly in the log and session completion record.

The supervisor records process-group owner PIDs and start times in
`$XDG_RUNTIME_DIR/waydaw/{ableton,bome,bridge}.state` (or the state-directory
fallback when `XDG_RUNTIME_DIR` is absent). Each owner remains alive after its
command exits, so cleanup can still identify and terminate descendants. Stop
checks owner identity before sending SIGTERM, escalates after two seconds, and
verifies exit within another two seconds, before shutting down Wine. It leaves
pre-existing bridges and reused PIDs untouched. A missing owner with remaining
group members causes recovery to fail and preserve its record for inspection.
Legacy PID-only bridge records are also supported for recovery.

Bome's readiness helper uses Microsoft's
[WaitForInputIdle](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-waitforinputidle)
initialization barrier. A successful acknowledgement establishes GUI
initialization; project loading and MIDI routing still require acceptance checks.

Back up the complete stopped copied prefix, projects, and any external sample
or plugin content it references. Record the current commit and runtime manifest.
Test runner, DXVK, Ableton, plugin, desktop, and audio updates in a separate
prefix selected by `WAYDAW_ABLETON_RUNNER_PREFIX`; change one component at a
time. Do not promote an update until the relevant acceptance checks pass.

For rollback, stop the session; restore the matching prefix snapshot and known-
good checkout/runtime artifacts; reinstall the desktop entry from that checkout;
then run preflight and the recording/save/reopen/export checks. Never restore a
prefix while its Wine processes are running.
Before switching to a checkout older than authorization-handler support, run
the current `bin/install-waydaw-desktop --uninstall` so its managed handlers are
restored before the older installer reads the installation record.

To remove menu integration, run `./bin/install-waydaw-desktop --uninstall`.
It restores the saved original Ableton shortcut when the installed entry is
unchanged. It preserves independently edited entries and retains the first
original in the installation record across uninstall/reinstall cycles for recovery.
Session logs remain under `${XDG_STATE_HOME:-~/.local/state}/waydaw/logs`.
Prefixes, activations, samples, project files, and installed host packages are
not removed by uninstalling the desktop entry.
