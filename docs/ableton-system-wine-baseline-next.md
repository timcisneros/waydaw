# Ableton System Wine Baseline Next Phase

## 1. Current baseline

- Runner: system Wine 11.0 Staging
- Status: launches Ableton, but editor/start-screen usability remains broken
- DXVK: active in copied-prefix tests and current working prefix
- Geometry/KWin/X11 branch: not root cause
- Alternate runners: not eligible after preflight

## 2. Known failed branches

- WebView2 `--disable-gpu` did not improve usability.
- X11 cursor guard did not produce functional improvement.
- X11 versus Wayland did not resolve flicker, responsiveness, or interaction.
- Bounds/geometry and KWin geometry changes are not the root cause.
- `wined3d` / builtin `d3d11` is not viable for this prefix; DXVK must remain active.
- Alternate runner candidates are blocked or abandoned before official usability testing.

## 3. Remaining failure surfaces

1. WebView2 / embedded Edge / start-screen crash path
2. Input/window interaction path
3. DXVK presentation/flicker path, only after usability is solved

## 4. Next diagnostic order

1. Use system Wine only.
2. Use copied prefixes first where possible.
3. Do not change the working prefix until a copied-prefix result proves value.
4. Prefer targeted WebView2/start-screen isolation over more runner changes.
5. Do not test graphics tweaks until the app is interactable.

## 5. Launch approval boundary

No Ableton launch should happen from this planning step. A later step may
explicitly approve a single system-Wine copied-prefix launch for
WebView2/start-screen diagnostics.

## Baseline Run 1 Result

Run: `system-wine-baseline-webview-input-1` (2026-06-22)

```text
run_dir=logs/ableton-runner-tests/20260622-222004-system-wine-baseline-webview-input-1
runner=/usr
wine_version=wine-11.0 (Staging)
test_prefix=/home/timcis/WinePrefixes/ableton12-system-wine-baseline-webview-input-1-test
webview2_mode=default
cursor_guard=off
backend_effective=dxvk
ableton_launched=yes
window_detected=yes
main_window_interactable=needs_user_observation
start_screen_seen=likely_child_window_and_webview2_present
webview2_process_count=6
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=17
blocked_by_child_or_modal=yes
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Decision: Do not repeat this baseline launch unchanged. The evidence points to
the WebView2/start-screen and child/modal/input ownership surfaces, not runner
replacement. The next approved launch should be a single targeted
WebView2/start-screen isolation test in a copied prefix under system Wine.

## WebView2 Isolated User Data Result

Run: `system-wine-webview2-isolated-user-data-1` (2026-06-22)

```text
run_dir=logs/ableton-runner-tests/20260622-222439-system-wine-webview2-isolated-user-data-1
runner=/usr
wine_version=wine-11.0 (Staging)
test_prefix=/home/timcis/WinePrefixes/ableton12-system-wine-webview2-isolated-user-data-1-test
webview2_mode=isolated-user-data
isolated_user_data_folder=C:\ProgramData\Ableton\Live 12 Suite\Program\run\user\1000\waydaw-ableton-webview2-user-data-timcis-system-wine-webview2-isolated-user-data-1
cursor_guard=off
backend_effective=dxvk
ableton_launched=yes
window_detected=yes
main_window_interactable=needs_user_observation
start_screen_seen=likely_child_window_and_webview2_present
webview2_process_count=6
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=19
blocked_by_child_or_modal=yes
child_or_modal_evidence=second_ableton_window_512x479_and_session_probe_interaction_state_blocked_by_child_or_modal
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Decision: WebView2 isolated user data did not improve the deterministic failure
markers. WebView2 still started, GPU crash markers remained, and the same
512x479 Ableton child window/modal block appeared. Stale WebView2 profile state
is not the primary cause. The next approved branch should be targeted
start-screen/WebView2 bypass or input/window ownership diagnostics; do not
repeat isolated-user-data unchanged.

## Window Ownership Result

Run: `system-wine-window-ownership-1` (2026-06-22)

```text
run_dir=logs/ableton-runner-tests/20260622-223230-system-wine-window-ownership-1
runner=/usr
wine_version=wine-11.0 (Staging)
test_prefix=/home/timcis/WinePrefixes/ableton12-system-wine-window-ownership-1-test
webview2_mode=default
cursor_guard=off
backend_effective=dxvk
ableton_launched=yes
window_detected=yes
webview2_process_count=6
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=29
blocked_by_child_or_modal=yes
blocker_window_id=0x09000008
blocker_geometry=333,322 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x09000003
blocker_pid=459243
blocker_process_cmdline=/home/timcis/WinePrefixes/ableton12-system-wine-window-ownership-1-test/drive_c/ProgramData/Ableton/Live 12 Suite/Program/Ableton Live 12 Suite.exe
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
main_window_id=0x09000003
main_window_pid=459243
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Decision: The blocker is an Ableton-owned dialog transient for the main window,
not WebView2 and not KPriorCrash. The next approved branch should identify or
bypass that Ableton child/start-screen dialog, or diagnose Wine input/window
ownership around that dialog. Do not repeat the default baseline unchanged.

## Ableton Dialog Bypass Audit

Audit source: `logs/ableton-runner-tests/20260622-223230-system-wine-window-ownership-1`
and copied prefix
`/home/timcis/WinePrefixes/ableton12-system-wine-window-ownership-1-test`.

Read-only evidence:

- `result.env` and `window-ownership.txt` identify the blocker as window
  `0x09000008`, `512x479`, `_NET_WM_WINDOW_TYPE_DIALOG`, transient for the main
  Ableton window, owned by the same Ableton process PID.
- `window-ownership.txt` classifies the blocker as
  `blocker_is_webview2=no`, `blocker_is_kprior_crash=no`,
  `blocker_is_ableton_child=yes`.
- `webview2-summary.txt` still shows WebView2 GPU exits and
  `Default App: Detected a prior crash`, but the blocking X11 window is not a
  WebView2 or crashpad window.
- `Preferences/Log.txt` for the latest run reaches
  `Default App: Checking whether to restore the document`, then loads
  `C:\ProgramData\Ableton\Live 12 Suite\Resources\Builtin\Templates\DefaultLiveSet.als`.
- `Preferences/CrashRecoveryInfo.cfg` and
  `Preferences/Crash/2026_06_22__22_32_13_CrashRecoveryInfo.cfg` are active
  crash-recovery metadata and reference `DefaultLiveSet.als`.
- Existing `.als` files are present in the copied prefix, including
  `Resources/Builtin/Templates/DefaultLiveSet.als`, but
  `bin/ableton-runner-test` currently launches only `wine "$exe"` and has no
  file-argument mode.

Likely dialog identity:
`prior_crash_or_crash_recovery_startup_dialog`, not visually confirmed.

Best next bypass candidate:
`C` — target the crash/recovery startup path in a copied prefix. The next
approved diagnostic should be a single copied-prefix-only test that suppresses
or moves aside crash-recovery metadata with restore commands printed before the
mutation. A secondary option is to patch the harness to pass an explicit `.als`
file argument, but current evidence points first at crash recovery rather than
missing template/file selection.

No Ableton launch was performed for this audit, and the working prefix was not
touched.

## Crash Recovery Bypass Result

Run: `system-wine-crash-recovery-bypass-1` (2026-06-22)

The harness was extended with `--crash-recovery-bypass`, a copied-prefix-only
diagnostic that runs after prefix preparation and before launch. It moves
Ableton crash/recovery startup metadata aside inside the test prefix only and
records restore commands in `crash-recovery-bypass.txt`.

```text
run_dir=logs/ableton-runner-tests/20260622-224403-system-wine-crash-recovery-bypass-1
runner=/usr
wine_version=wine-11.0 (Staging)
test_prefix=/home/timcis/WinePrefixes/ableton12-system-wine-crash-recovery-bypass-1-test
webview2_mode=default
cursor_guard=off
backend_effective=dxvk
crash_recovery_bypass_enabled=yes
bypass_backup_dir=/home/timcis/WinePrefixes/ableton12-system-wine-crash-recovery-bypass-1-test/drive_c/users/timcis/AppData/Roaming/Ableton/Live 12.4.2/Preferences/.waydaw-crash-recovery-bypass-backup-system-wine-crash-recovery-bypass-1
moved_files_count=41
restore_commands_recorded=yes
ableton_launched=yes
window_detected=yes
webview2_process_count=0
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=47
blocked_by_child_or_modal=yes
blocker_window_id=0x09000008
blocker_geometry=333,322 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x09000003
blocker_pid=462724
blocker_is_webview2=no
blocker_is_kprior_crash=yes
blocker_is_ableton_child=yes
main_window_interactable=needs_user_observation
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Interpretation: Moving aside active crash/recovery metadata in the copied prefix
did not remove the 512x479 Ableton-owned dialog or the
`blocked_by_child_or_modal` state. The latest Ableton log segment after the
bypass still reaches default-template loading and then WebView2 GPU/browser
failure lines. The crash-recovery metadata branch is therefore not sufficient as
a bypass. The next branch should visually identify the 512x479 dialog or patch
the harness to launch an explicit `.als` file argument in a copied prefix.

## Explicit ALS Launch Result

Run: `system-wine-explicit-als-default-template-1` (2026-06-22)

The harness was extended with `--launch-file-relative`, which resolves an
explicit file argument under the copied test prefix, refuses absolute paths or
paths outside the test prefix, verifies the file exists, and launches Ableton as
`wine "$ableton_exe" "$resolved_launch_file"`.

```text
run_dir=logs/ableton-runner-tests/20260622-225030-system-wine-explicit-als-default-template-1
runner=/usr
wine_version=wine-11.0 (Staging)
test_prefix=/home/timcis/WinePrefixes/ableton12-system-wine-explicit-als-default-template-1-test
webview2_mode=default
cursor_guard=off
backend_effective=dxvk
launch_file_enabled=yes
launch_file_relative=drive_c/ProgramData/Ableton/Live 12 Suite/Resources/Builtin/Templates/DefaultLiveSet.als
launch_file_resolved=/home/timcis/WinePrefixes/ableton12-system-wine-explicit-als-default-template-1-test/drive_c/ProgramData/Ableton/Live 12 Suite/Resources/Builtin/Templates/DefaultLiveSet.als
launch_file_exists=yes
ableton_launched=yes
window_detected=yes
webview2_process_count=0
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=59
blocked_by_child_or_modal=yes
blocker_window_id=0x09000009
blocker_geometry=333,322 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x09000003
blocker_pid=465293
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
main_window_interactable=needs_user_observation
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Interpretation: Passing the built-in default `.als` file explicitly did not
bypass the generic 512x479 Ableton-owned dialog. The blocker remains an
Ableton-owned dialog transient for the main window and the process command line
confirms the `.als` argument was passed. Do not repeat explicit default-template
launch unchanged. The next diagnostic should visually identify the 512x479
dialog with a targeted capture of that dialog only.

## Dialog Visual Capture Result

Run: `system-wine-dialog-visual-capture-1` (2026-06-25)

```text
run_dir=logs/ableton-runner-tests/20260625-154611-system-wine-dialog-visual-capture-1
runner=/usr
wine_version=wine-11.0 (Staging)
backend_effective=dxvk
ableton_launched=yes
window_detected=yes
blocked_by_child_or_modal=yes
blocker_window_id=0x07800008
blocker_geometry=333,322 512x479
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07800003
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
capture_tool=import
capture_file=logs/ableton-runner-tests/20260625-154611-system-wine-dialog-visual-capture-1/blocker-window.png
capture_success=yes
ableton_process_left_running=no
working_prefix_touched=no
```

The captured window is a severely zoomed/cropped promotional start-screen image,
not a conventional crash, recovery, license, authorization, trial, or missing
dependency dialog. No controls or error message are visible in the captured
viewport. This changes the primary interpretation from an unidentified startup
prompt to a mis-sized embedded start-screen content surface hosted by an
Ableton-owned child/dialog window.

Next diagnostic order:

1. Keep system Wine and copied prefixes.
2. Inspect start-screen host viewport, DPI/scale, and child-window integration
   without changing KWin geometry or global desktop scaling.
3. Treat WebView2 process crashes as correlated secondary evidence, while
   preserving the fact that the X11 blocker is owned by the Ableton process.
4. Do not repeat profile isolation, crash-recovery bypass, or explicit `.als`
   launch unchanged.
5. Require explicit approval before another Ableton launch.

## Start-Screen Viewport and Scale Audit

No-launch audit completed on 2026-06-25 using the visual-capture run and its
copied prefix.

```text
capture_dimensions=512x479
blocker_geometry=333,322 512x479
webview2_surface_geometry=1432x776
wine_logpixels=96
ableton_reported_screen_scale=1
webview2_renderer_device_scale_factor=1
host_xft_dpi=96
host_xdpyinfo_dpi=96x96
kde_output_scale=1
xrandr_transform=identity
global_scale_mismatch=no
start_screen_suppression_preference_found=no
working_prefix_touched=no
ableton_launched=no
```

The mismatch is between the large WebView2 surface/content bounds and the
`512x479` Ableton-owned dialog viewport, not between host, Wine, and Chromium
DPI values. Ableton also reports process DPI awareness `0` while its ALF layer
reports per-monitor-aware v2, so child-window DPI integration remains relevant.

Best next single launch candidate:

```text
runner=/usr
copied_prefix=yes
webview2_additional_browser_arguments=--force-device-scale-factor=0.5
dialog_visual_capture=yes
```

Rationale: this is the narrowest reversible environment-only test that can show
whether reducing Chromium content scale exposes the missing start-screen
controls inside the fixed dialog viewport. It must not change Wine DPI, KDE
scale, KWin geometry, DXVK, or the working prefix. Add a dedicated named
WebView2 mode and run it only after explicit approval.

## WebView2 Device Scale 0.5 Result

Run: `system-wine-webview2-force-scale-0-5-1` (2026-06-25)

```text
run_dir=logs/ableton-runner-tests/20260625-155514-system-wine-webview2-force-scale-0-5-1
webview2_mode=force-device-scale-0-5
webview2_additional_browser_arguments=--force-device-scale-factor=0.5
renderer_device_scale_factor=0.5
ableton_launched=yes
window_detected=yes
blocked_by_child_or_modal=yes
blocker_geometry=333,322 512x479
capture_success=yes
webview2_process_count=6
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=13
ableton_process_left_running=no
working_prefix_touched=no
```

The visual output changed from oversized promotional start-screen media to a
scaled/cropped view of Ableton's mixer/editor controls inside the same
`512x479` modal child. The modal blocker did not disappear and interaction
remains blocked. The WebView2 X11 surface also remains `1432x776`.

The ownership probe's raw `blocker_is_webview2=yes` is a false positive caused
by the test prefix label containing the word `webview2`; WM_CLASS, PID, and
transient ownership still identify the window as Ableton-owned.

Decision: `--force-device-scale-factor=0.5` proves that Chromium device scale
changes the pixels painted into the child surface, but it is not sufficient to
correct host sizing or usability. Do not repeat it unchanged. The next
no-launch branch should inspect the binary `SecondWindowIsOpen`,
`SecondWindowPlacement`, and `SecondWindowGuiScalingPercentUnlinked` preference
values with a structure-aware parser or compare them against a clean copied
preference file before considering another launch.

## Second-Window State Audit

No Ableton launch was performed. The base and scale-0.5 copied-prefix
`Preferences.cfg` files are identical, including binary context around:

```text
SecondWindowGuiScalingPercentUnlinked offset=778
SecondWindowPlacement offset=1872
SecondWindowIsOpen offset=1935
OpenSecondWindowOnStartup absent
```

The serialized schema names are visible, but the corresponding values cannot be
decoded reliably from local byte context. No individual preference value should
be patched.

The ownership classifier now ignores the full process command line and test
prefix label when deciding WebView ownership. It uses only window class/name
signals or an exact `msedgewebview2.exe` process basename.

Geometry comparison:

```text
base_main_window=848x1052
scale_main_window=848x1052
base_blocker=512x479
scale_blocker=512x479
base_webview2_surface=1432x776
scale_webview2_surface=1432x776
```

Best next single launch candidate:

1. Prepare a new copied prefix under system Wine.
2. Print the exact restore command.
3. Rename only the copied `Preferences.cfg` to a label-specific backup.
4. Launch with default WebView2 mode and dialog visual capture.
5. Compare generated preferences, blocker geometry, WebView host geometry, and
   captured content.

This test separates stale Ableton preference/second-window state from persistent
Wine child-window host sizing. It requires explicit launch approval.

## Preferences.cfg Reset Result

Run: `system-wine-preferences-cfg-reset-1` (2026-06-25)

```text
preferences_cfg_reset_enabled=yes
preferences_cfg_moved=yes
preferences_cfg_restore_command_recorded=yes
preferences_cfg_original_sha256=a8d2edf51e126dce792c536f584b62249f277b99e97da1df3c0e5b7948d0e164
preferences_cfg_generated_after_launch=no
blocker_geometry=704,314 512x479
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
capture_success=yes
working_prefix_touched=no
```

The reset exposed a coherent Ableton software authorization welcome dialog in
the same fixed `512x479` modal host. No authorization control was activated.
At collection time, the original copied `Preferences.cfg` remained available at
the manifest's backup path; no replacement file was generated during collection.

Decision:

1. Stop automated bypass diagnostics at the licensing boundary.
2. Do not infer that stale second-window state caused the modal host.
3. Restore the copied preference file before reusing this test prefix.
4. Continue only through a user-selected legitimate authorization path, or use
   no-launch diagnostics for Wine/Ableton/WebView host sizing.
5. Do not run another Ableton launch without explicit approval.

## Authorization Boundary Closeout

```text
AUTHORIZATION_BOUNDARY_CLOSEOUT:
preferences_cfg_reset_prefix_restored=yes
restored_preferences_sha256=a8d2edf51e126dce792c536f584b62249f277b99e97da1df3c0e5b7948d0e164
automated_bypass_diagnostics_stopped=yes
working_prefix_touched=no
recommended_next_action=user must choose a legitimate Ableton authorization path before further launch testing
```

The exact manifest restore command was applied only to the copied
`system-wine-preferences-cfg-reset-1` test prefix. The restored file exists and
matches its original SHA256. Ableton was not launched and no authorization
control was activated during closeout.

## Final Current Status

```text
FINAL_CURRENT_STATUS:
system_wine_launches_ableton=yes
working_prefix_touched=no
automated_bypass_diagnostics_stopped=yes
blocked_at_legitimate_authorization_boundary=yes
next_user_decision_required=yes
```

Allowed next paths:

1. User performs legitimate Ableton authorization manually, then testing can resume.
2. User requests no-launch host-sizing/documentation cleanup only.
3. User requests tooling cleanup/commit preparation only.

No further runtime action is authorized until the user explicitly selects one
of these paths.

## Working-Prefix Authorization Input Diagnostic

The user's `./bin/ableton` session was no longer live when evidence collection
began. No new instance was launched because the current launcher writes Wine
windowing registry values in the working prefix and requests builtin
`dxgi,d3d11`, contrary to the established DXVK baseline.

```text
diagnostic_bundle=logs/working-prefix-live-auth-input-diagnostic
ableton_already_running=no
launched_new_instance=no
latest_launcher_exit_code=58
ableton_window_after_exit=no
residual_webview2_gpu_process=yes
residual_wineserver=yes
focus_window=waydaw terminal
live_authorization_focus_evidence=unavailable
working_prefix_mutated_by_diagnostic=no
authorization_control_activated=no
```

The ended launch showed repeated WebView2 GPU exits, a main browser-process
exit, and then another Ableton initialization. The remaining WebView2 process
has no mapped window and the ownership probe finds no blocker. Therefore the
current evidence indicates parent/browser lifecycle failure rather than a
currently focused but input-dead authorization dialog.

Next action requires explicit tooling approval: correct the normal launcher so
it preserves DXVK and offers a read-only/no-registry-mutation diagnostic launch
path. Only then can a live focus/input-routing capture distinguish X11 focus
failure from Wine input delivery while the legitimate authorization dialog is
actually present.

## Corrected Diagnostic Launcher Policy

`bin/ableton` now has an opt-in, non-mutating DXVK diagnostic mode:

```text
WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY=1
WAYDAW_ABLETON_GRAPHICS=dxvk
WAYDAW_ABLETON_DRY_RUN=1
```

The verified dry-run reports:

```text
wine_binary=/usr/bin/wine
wineprefix=/home/timcis/WinePrefixes/ableton12
graphics_mode=dxvk
winedlloverrides=
registry_mutation_enabled=no
virtual_desktop_mutation_enabled=no
dxvk_expected_active=yes
would_launch_command=env -u WAYLAND_DISPLAY -u WINEDLLOVERRIDES WINEPREFIX=/home/timcis/WinePrefixes/ableton12 wine .../Ableton Live 12 Suite.exe
```

Dry-run exits before all Wine commands and registry setup. A future real
diagnostic launch in this mode also skips registry/virtual-desktop mutation and
unsets inherited DLL overrides so the existing prefix DXVK remains active.

Normal mode was not behaviorally changed. No Ableton launch occurred. A live
diagnostic remains blocked pending explicit user approval.

## Working-Prefix DXVK Authorization Live Input Result

One approved launch used the corrected no-registry DXVK mode.

```text
run_bundle=logs/working-prefix-dxvk-auth-live-input-1
dry_run_verified=yes
graphics_mode=dxvk
winedlloverrides=
registry_mutation_enabled=no
virtual_desktop_mutation_enabled=no
authorization_control_activated=no
blocker_window_id=0x07000008
blocker_geometry=333,322 512x479
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07000003
blocker_is_webview2=no
blocker_is_ableton_child=yes
capture_success=yes
focus_window=waydaw terminal
active_window=0x4e00004
ableton_process_alive_after_collection=yes
new_session_webview2_browser_alive_after_collection=no
working_prefix_mutated_by_diagnostic=no
```

The legitimate authorization dialog remained visible and owned by Ableton, but
the terminal stayed active and focused across repeated passive snapshots. The
dialog lacked `_NET_WM_STATE_FOCUSED`. No click was attempted, so input delivery
after explicit activation remains untested.

Next diagnostic: inspect `WM_PROTOCOLS`/`WM_HINTS` and focus model for the dialog
and parent. With separate explicit approval, activate only the dialog window
without clicking controls, then verify whether focus transfers and remains
stable. Do not automate or click authorization actions.

## Authorization Focus Activation Result

The existing dialog was activated once with `wmctrl -ia 0x07000008`. No click
or keyboard input was sent.

```text
blocker_accepts_focus_hint=no
blocker_wm_protocols=WM_DELETE_WINDOW,_NET_WM_PING,WM_TAKE_FOCUS
active_window_before=0x4e00004
focus_window_before=waydaw terminal
active_window_after_1s=0x4e00004
focus_window_after_1s=waydaw terminal
active_window_after_5s=0x4e00004
focus_window_after_5s=waydaw terminal
blocker_focused_after_activation=no
ableton_process_alive_after=yes
authorization_control_activated=no
working_prefix_mutated=no
```

The dialog stayed mapped and Ableton stayed alive, but activation did not
transfer active-window status or X input focus. The focus model depends on
`WM_TAKE_FOCUS`, so the next no-click branch should inspect KWin
focus-prevention and Wine client-message handling rather than WebView input
embedding or authorization logic.

## KWin WM_TAKE_FOCUS Audit Result

```text
kwin_focus_policy=ClickToFocus
kwin_focus_stealing_prevention=1
kwin_matching_rule=border_only
blocker_accepts_focus_hint=no
parent_accepts_focus_hint=no
blocker_wm_protocols=WM_DELETE_WINDOW,_NET_WM_PING,WM_TAKE_FOCUS
parent_wm_protocols=WM_DELETE_WINDOW,_NET_WM_PING,WM_TAKE_FOCUS
parent_activation_command=wmctrl -ia 0x07000003
parent_focused_after_activation=no
blocker_focused_after_activation=no
ableton_process_alive_after=yes
authorization_control_activated=no
working_prefix_mutated=no
```

KWin's global prevention level is low and its Ableton rule does not alter focus.
Activating the parent failed exactly like activating the transient dialog:
active-window status and X input focus remained on the terminal for five
seconds.

Next no-click branch: trace `_NET_ACTIVE_WINDOW`, `WM_TAKE_FOCUS`, FocusIn, and
FocusOut events during one activation request, or inspect Wine X11 focus
handling. Do not change KWin settings based on the current evidence.
