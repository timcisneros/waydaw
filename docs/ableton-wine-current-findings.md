# Ableton (Wine/DXVK) — current findings

Authoritative project record of the Ableton Live 12 Suite under Wine debugging on
Fedora KDE. The repo + environment + logs are the source of truth; this document
supersedes any agent-memory notes. Update it as findings change.

Last updated: 2026-06-19.

## Environment
- Host: Fedora KDE Plasma 6. Tested in **both** KDE Wayland (Ableton forced to
  XWayland via `env -u WAYLAND_DISPLAY` in `bin/ableton`) and native **X11**.
- Wine: `wine-staging 11.0`. Prefix: `~/WinePrefixes/ableton12`.
- Ableton: `Live 12.4.2 Suite`, 64-bit, launched via `./bin/ableton`.
- DXVK: installed natively in the prefix `system32` (mandatory — see below).

## Findings (deterministic unless marked observation)

### Session: X11 vs Wayland
- X11 vs Wayland A/B run with `bin/ableton-session-probe` (30s churn window,
  logging ON). See `docs/ableton-x11-ab-test.md` for procedure.
- **X11 did not improve flicker, responsiveness, or interactivity.** Logged
  swapchain churn was the same-or-higher on X11 (recreating_swapchain ~179/30s
  vs Wayland ~30–135/30s, state-dependent). Both sessions: app still freezes /
  not interactable / crashes on interaction (user observation).
- The wmctrl coordinate-doubling artifact is XWayland-only (native X11 reports
  true coords e.g. `165,28`). It is a measurement artifact, not a real bounds bug.

### Bounds / interaction (ruled out as the active defect)
- The maximized window fits the screen (xwininfo ground truth: `y=28 + height
  1052 = 1080`). The "28px overshoot" was a wmctrl reporting artifact.
- The window-manager "blocked_by_child_or_modal" is the Ableton start-screen
  dialog, not a window-manager bug.

### Graphics / DXVK
- **DXVK is mandatory** for Ableton to launch in this prefix. Removing the
  prefix `system32` `d3d11.dll`/`dxgi.dll` makes Ableton fail at the loader
  (`d3d11.dll not found`, `c0000135`, exit 53). wine-staging 11.0 here has no
  usable builtin d3d11, so `WAYDAW_ABLETON_GRAPHICS=wined3d` is not viable.
- The installed DXVK is a **19 MB DEBUG/custom DXVK 2.7 build** (verbose
  `Presenter` logging). A DXVK swapchain-recreation loop (`VK_SUBOPTIMAL_KHR ->
  recreating swapchain`, buffer ~840x1096 != window) is present.
- **Official DXVK 2.7.1 release** (4.45 MB d3d11) was A/B tested reversibly:
  logged churn dropped (X11 recreating 179 -> 73) **but usability was unchanged**
  (still freezes, still crashes on interaction). => `not_a_usability_fix`. Lower
  swapchain counts != usable. Originals restored + sha256-verified.
- dxvk.conf knobs (`dxgi.maxFrameLatency=1`, `dxgi.syncInterval=1`,
  `dxvk.tearFree=True`) did not change the loop beyond noise; present mode stays
  `MAILBOX`. `DXVK_LOG_LEVEL=none` only reduces log volume (not a fix).

### Active usability blocker: WebView2 / embedded Edge
- The freeze/crash-on-interaction is a **WebView2 (embedded Microsoft Edge)
  crash**, independent of DXVK. Evidence (Ableton `Log.txt`):
  `warning: WebView2: The GPU process exited unexpectedly` ->
  `error: WebView2: The main browser process exited unexpectedly`, and every
  startup `Default App: Detected a prior crash (KPriorCrash)` = a crash loop
  (the `Preferences/Crash/` folder holds many recovery snapshots).
- The start screen is the WebView2-backed dialog (`0x..09` "Ableton Live 12
  Suite", transient-for-main, owned by the Ableton main PID). The main editor
  ("Untitled - Ableton Live 12 Suite") loads underneath it.

### Bypass tests (reversible rename, no delete)
- **Disabling `Ableton Web Connector.exe` was INEFFECTIVE.** That exe is the
  auto-updater/web-connector (Python `abl.webconnector`), NOT the start-screen
  host. The start screen + `msedgewebview2.exe` still spawned. Restored.
- **Disabling the actual WebView2 runtime WORKED** to stop the crash: renaming
  both `msedgewebview2.exe` copies (runtime version is **143**, not 140) made
  `msedgewebview2` processes = 0 and produced **no WebView2 GPU/browser crash**.
  Ableton **still launches**; the runtime check still reports "Found WebView2
  runtime" (registry/dir-based) then logs a graceful
  `error: WebView2: Failed to create controller: -2147024894` (= `0x80070002`
  FILE_NOT_FOUND) instead of crash-looping. The **empty** start-screen dialog
  frame still appears above the editor (no browser inside).

### User observation result — WebView2-runtime-disabled run (2026-06-16)
Classification: **`webview2_runtime_disable=not_a_usability_fix`**.
Rule fired: disabling WebView2 eliminated the WebView2 process/crash source but
did NOT make the main editor interactable.

- Deterministic: `msedgewebview2_processes_present=no`,
  `webview2_crash_lines_present=no`, main editor window appears=yes, empty
  start-screen frame remains.
- User observation:
  - `main_editor_interactable=no`
  - `flicker=still_present`
  - `mouse_disappears_over_main_ableton_window=yes`
  - `mouse_disappearing_is_not_new=yes` (longstanding, not introduced by this test)
  - `crash_on_interaction=not_confirmed_in_this_observation`
  - `start_screen_state=empty_frame_still_present`

Conclusion: WebView2 is a real crash/start-screen problem but **not the only
blocker**. The **longstanding mouse-disappearance over the main editor** indicates
a deeper Wine/input/cursor/rendering integration issue. Do NOT keep WebView2
disabled as a fix. Next major path = test a **different Wine build** (better
Ableton/WebView2/input handling). Stop: random dxvk.conf knobs, Wayland/X11
re-investigation, WebConnector testing.

## Current reversible state changes (restore commands are authoritative here)

### DXVK (original debug/custom 2.7 — restored and active; no action needed)
- `system32/d3d11.dll` sha256 `557c1f50…1940dd` (19064602 bytes)
- `system32/dxgi.dll`  sha256 `f31cd64b…2b3fd7` (16106011 bytes)
- Backup of the originals remains at
  `~/WinePrefixes/ableton12/_waydaw_dxvk_version_backup_20260616-194020/`.
- Restore command (only needed if originals were ever swapped out again):
  ```bash
  SYS="$HOME/WinePrefixes/ableton12/drive_c/windows/system32"
  B="$HOME/WinePrefixes/ableton12/_waydaw_dxvk_version_backup_20260616-194020"
  cp -f "$B/d3d11.dll" "$SYS/d3d11.dll"; cp -f "$B/dxgi.dll" "$SYS/dxgi.dll"
  ```

### Official DXVK 2.7.1 release test (already restored; outcome recorded)
- Test DLLs (release 2.7.1): `d3d11.dll` sha256 `523da2cd…303405` (4452366 b),
  `dxgi.dll` sha256 `ec02eb37…1c01be` (2953230 b). Source tarball:
  `github.com/doitsujin/dxvk/releases/download/v2.7.1/dxvk-2.7.1.tar.gz`
  (sha256 `d85ce7c7…13ce87`), extracted to `/tmp/waydaw-dxvk-dl/` (ephemeral).
- Outcome: **restored to original debug build, sha256-verified** by
  `bin/ableton-dxvk-version-test`. Re-run that harness to repeat the A/B.

### WebConnector (restored; no action needed)
- `Ableton Web Connector.exe` is back in place at
  `…/Live 12 Suite/Resources/Extensions/WebConnector/`. If it is ever disabled
  again, restore is `mv "<...>/Ableton Web Connector.exe.disabled.<ts>" "<...>/Ableton Web Connector.exe"`.

### WebView2 runtime — RESTORED (2026-06-16, verified)
Both `msedgewebview2.exe` were temporarily renamed `.disabled.20260616-200927`
for the test, then **restored and verified** (both exes present, no leftover
`.disabled` files). The runtime is back to baseline. Restore commands (used; kept
for reference if ever re-disabled):
```bash
mv "$HOME/WinePrefixes/ableton12/drive_c/Program Files (x86)/Microsoft/EdgeWebView/Application/143.0.3650.96/msedgewebview2.exe.disabled.<ts>" \
   "$HOME/WinePrefixes/ableton12/drive_c/Program Files (x86)/Microsoft/EdgeWebView/Application/143.0.3650.96/msedgewebview2.exe"

mv "$HOME/WinePrefixes/ableton12/drive_c/Program Files (x86)/Microsoft/EdgeCore/143.0.3650.96/msedgewebview2.exe.disabled.<ts>" \
   "$HOME/WinePrefixes/ableton12/drive_c/Program Files (x86)/Microsoft/EdgeCore/143.0.3650.96/msedgewebview2.exe"
```

## Current live state (as of 2026-06-16, after the WebView2 test + restore)
- WebConnector: **restored** (active).
- WebView2 runtime: **restored** (both `msedgewebview2.exe` back, verified) — back
  to baseline (Ableton's original crashing config).
- DXVK: **original debug/custom 2.7**, restored and active.
- Ableton: **stopped** (session killed for the clean WebView2 restore).
- Prefix is back to its unmodified baseline. Next: different-Wine-build A/B.

## Explicitly ruled out (NOT the active defect)
- **Bounds / geometry** — window fits the screen (ground truth); the 28px
  "overshoot" was a wmctrl artifact.
- **X11 session** — did not improve flicker, responsiveness, or interactivity
  (churn same-or-higher than Wayland).
- **wined3d in this prefix** — not viable; Ableton can't load without DXVK
  d3d11/dxgi (no usable builtin in wine-staging 11.0).
- **Random dxvk.conf knobs** — maxFrameLatency/syncInterval/tearFree did not
  change the loop beyond noise.
- **Official DXVK 2.7.1 release as a usability fix** — reduced logged churn but
  did NOT fix freeze/crash; `not_a_usability_fix`.
- **`Ableton Web Connector.exe` as the start-screen host** — disabling it was
  ineffective; it is the updater, not the WebView2 start-screen host.

## Resolved by the WebView2-disabled test (2026-06-16)
- Editor interactable with WebView2 disabled? **NO.**
- Empty dialog frame the only blocker? **NO** — a deeper input/cursor issue remains.
- Keep WebView2 disabled as the fix? **NO** (restored to baseline).
- Next major test = different Wine build? **YES** (decided).

## Still open / leading suspect
- **Longstanding mouse-disappearance over the main editor window** + not
  interactable + flicker — points at a **Wine/input/cursor/rendering integration**
  problem in `wine-staging 11.0`, independent of WebView2 and DXVK. This is the
  primary remaining suspect.

## Next test plan — different Wine build A/B (NOT yet run; needs rollback plan + approval)
Goal: see if a Wine build with better Ableton/WebView2/input handling fixes the
mouse-disappearance + non-interactivity.

Hard rule: **do not change the Wine build in the working prefix without a rollback
plan.** Prefer a **copied test prefix** if the candidate Wine build may mutate the
prefix; only reuse the working prefix if the build is launch-only/non-mutating.

Candidate direction: Wine-TKG / Valve / Proton-style Wine with better
Chromium/WebView2 + input/cursor behavior (specific build TBD with user).

For each Wine build, measure (logging ON, no `DXVK_LOG_LEVEL=none`):
- Ableton launches yes/no
- main editor interactable yes/no
- mouse disappears over main window yes/no   ← key signal
- WebView2 / start-screen crash yes/no
- flicker same/better/worse
- DXVK backend active (must stay; DXVK is mandatory)
- swapchain churn (recreating_swapchain / 30s via `bin/ableton-session-probe`)

Constraints: no Wine virtual desktop, no dxvk.conf, no `DXVK_LOG_LEVEL=none`
during measurement, no forced KWin geometry. Keep DXVK as-is (mandatory).

### Acquisition status (2026-06-16) — BLOCKED on download
Requested: wine-tkg `valvexbe` (Valve Exp Bleeding Edge) from Frogging-Family,
copied-prefix A/B. Research result:
- **No dedicated Fedora build exists.** Frogging-Family only ships
  `Exp Bleeding Edge Arch Linux` (Arch-only) and `Exp Bleeding Edge Other distro`
  (built on Ubuntu-latest, "should work on most distros not using years-old packages").
- **Prebuilt binaries are GitHub Actions CI artifacts that require GitHub login**
  ("You must be logged in to GitHub to download Wine/Proton nightly builds").
  Workflow: `github.com/Frogging-Family/wine-tkg-git/actions/workflows/wine-valvexbe.yml`.
- WebFetch can't fetch authenticated URLs; `curl` needs a token; **`gh` CLI is
  not installed** here. The named build `…9.0.174637.20250316…` (Mar 2025) is >1yr
  old → its CI artifact is expired.
- A Fedora Copr `patrickl/wine-tkg` exists but is system-RPM wine+staging 9.21
  (ntsync/hotfix), NOT a standalone valvexbe runner — and it would mutate the
  system, not a `.local-runners/` build.
=> No anonymous Fedora-compatible valvexbe artifact (CI-only, GitHub-login-gated,
named build expired, gh not installed). User chose Proton-GE instead.

### Proton-GE A/B (GE-Proton10-34) — DONE 2026-06-16
- runner_source_url = github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton10-34/GE-Proton10-34.tar.gz
- runner_archive_sha256 = 51c580b66a833c73998fe00f0717eeac57197654040a2f2ed5189e3ee68d773d (sha512 verified OK against release .sha512sum)
- runner_wine_path = `.local-runners/GE-Proton10-34/files/bin/wine`
- runner_wine_version = `wine-11.0 (Staging)`  ← NOTE: same wine base as the system (wine-staging 11.0)
- Standalone smoke test (throwaway HOME prefix): PASSED (`wineboot --init` ok, `wine cmd /c ver` -> Microsoft Windows 10.0.19045). Proton-GE runs outside Steam via raw `files/bin/wine` (no `proton` wrapper).
- Test prefix: `~/WinePrefixes/ableton12-protonge-test` (rsync copy of the working prefix; working prefix NEVER touched, DXVK sha verified unchanged). Launched via PATH override only (no launcher edit; log marker written inline for the probe). Same native DXVK (debug 2.7) kept => isolates the Wine runtime only.
- Deterministic result (`logs/ableton-session-probe-protonge-test.txt`):
  - Ableton launches=yes, window_detected=yes, backend_effective=dxvk
  - recreating_swapchain=177 / VK=177 / Presenter=380 (DXVK loop UNCHANGED vs system X11 ~179 — expected, same DXVK)
  - msedgewebview2 processes spawned then **crashed out** (count 0)
  - **WebView2 STILL crashes** (test-prefix Log.txt): GPU process exited unexpectedly (x6) -> main browser process exited; `KPriorCrash` loop — identical to system wine.
- Interpretation: Proton-GE 10-34 is wine-11.0-Staging-based (same base), so it did NOT change the WebView2 GPU crash or the DXVK loop. PENDING user visual observation of the remaining key signal: mouse-disappearance / main-editor interactivity (Proton input/cursor patches could still differ even though WebView2 didn't).

Consolidated result (recorded):
```
proton_ge_runner=GE-Proton10-34
runner_wine_version=wine-11.0 Staging
prefix=~/WinePrefixes/ableton12-protonge-test
working_prefix_touched=no
ableton_launches=yes
window_detected=yes
backend_effective=dxvk
recreating_swapchain_count=177
WebView2_crash=yes
WebView2_crash_pattern=same GPU process exited / browser process exited / KPriorCrash
DXVK_loop_changed=no
WebView2_fixed_by_Proton_GE=no
```
Pending user visual observation → decision rules:
- cursor/input improves despite WebView2 still crashing =>
  `wine_input_cursor_or_d3d_window_integration_partially_improved`; next: find a
  runner with better WebView2 but preserve the cursor/input clue.
- cursor/input unchanged => `not_fixed_by_protonge`; next: a genuinely DIFFERENT
  Wine base (not another wine-11.0-staging-based runner).
- everything unchanged => test a Wine build with a different base/version, or
  accept Wine virtual desktop as a separate diagnostic branch.
Reason Proton-GE is likely too close: it is also wine-11.0 Staging, near-identical
to the system Wine, so unlikely to be a meaningful WebView2 fix.
NOTE: the Proton-GE live session later exited on its own (WebView2 crash cascade);
the live visual observation was not captured. Leftover test prefix
`~/WinePrefixes/ableton12-protonge-test` (9.5G) can be removed via the harness:
`bin/ableton-runner-test --label protonge --runner .local-runners/GE-Proton10-34 --cleanup-test-prefix`.

## Runner-test harness (next runner comparisons go through this)
Further Wine-runner comparisons are run via `bin/ableton-runner-test` (copied
prefix, never mutates the working prefix). See `docs/ableton-runner-test-harness.md`.
This is comparative test infrastructure, NOT a Wine/DXVK/WebView2 patch.

### Custom compatibility layer V1 — created 2026-06-19, not yet matrix-tested
The next path is no longer random tweaks. It is a small compatibility-layer
harness that can separate WebView2 browser flags from cursor/input integration:

- `bin/ableton-webview2-mode` prints reversible environment exports for
  `default`, `disable-gpu`, `disable-gpu-no-sandbox`, and `isolated-user-data`.
  It also documents `disabled-runtime` as a prior reversible test only; it does
  not rename or delete files.
- `bin/ableton-cursor-guard` is an X11/XWayland probe for pointer entry over the
  Ableton main editor window. Probe-only/dry-run modes are harmless. Optional
  cursor forcing uses a local helper under `tools/` to call `XDefineCursor` only
  on the detected Ableton top-level window, then `XUndefineCursor` on exit.
- Cursor-helper prerequisite is satisfied:
  `libX11-devel=installed`;
  `dependencies_installed=libXau-devel libxcb-devel xorg-x11-proto-devel`;
  `cursor_helper_built=yes`;
  `helper=tools/ableton-x11-cursor-define`.
- `bin/ableton-runner-test` accepts `--webview2-mode` and `--cursor-guard` so the
  approved matrix can be run against a copied prefix. The harness launch path
  must keep DXVK active and must not set `WINEDLLOVERRIDES=dxgi,d3d11=b` or
  `WAYDAW_ABLETON_GRAPHICS=wined3d`.

Matrix status:
- A: `webview2_mode=default`, `cursor_guard=off` — DONE, FAILED
- B: `webview2_mode=disable-gpu`, `cursor_guard=off` — DONE, FAILED
- C: `webview2_mode=default`, `cursor_guard=on` — DONE, FAILED
- D: `webview2_mode=disable-gpu`, `cursor_guard=on`

Cell A result (2026-06-19,
`logs/ableton-runner-tests/20260619-161121-matrix-a-default-off/result.env`):
- Runner: system Wine `wine-11.0 (Staging)`.
- Prefix: copied test prefix
  `~/WinePrefixes/ableton12-matrix-a-default-off-test`.
- `backend_effective=dxvk`; `recreating_swapchain_count=28`;
  `webview2_crash=yes`; `kprior_crash=yes`.
- User observation: `main_editor_interactable=no`,
  `mouse_disappears_over_main_editor=inconclusive/eventually_no`,
  `crash_on_interaction=yes`, `start_screen_webview2_crash=yes`,
  `flicker=same_then_stops_after_minutes`,
  `responsiveness=worse_or_no`.
- Interpretation: Cell A is not a usability improvement. The corrected baseline
  still fails: main editor is not interactable, start screen is frozen, and
  interaction causes a crash. Mouse disappearance is inconclusive for this cell
  because it eventually stops disappearing after several minutes while the app
  remains unusable.

Working prefix touched: no. Runtime changes: copied-prefix only. See
`docs/ableton-custom-compat-layer.md`.

Cell B result (2026-06-19,
`logs/ableton-runner-tests/20260619-162117-matrix-b-disablegpu-off/result.env`):
- Runner: system Wine `wine-11.0 (Staging)`.
- Prefix: copied test prefix
  `~/WinePrefixes/ableton12-matrix-b-disablegpu-off-test`.
- Mode: `webview2_mode=disable-gpu`, `cursor_guard=off`, DXVK active.
- Deterministic fields: `ableton_launched=yes`, `window_detected=yes`,
  `backend_effective=dxvk`, `recreating_swapchain_count=83`,
  `webview2_process_count=0`, `webview2_crash=yes`, `kprior_crash=yes`.
- User observation: `main_editor_interactable=no`,
  `mouse_disappears_over_main_editor=inconclusive/eventually_no`,
  `crash_on_interaction=yes`, `start_screen_webview2_crash=yes`,
  `flicker=same_then_stops_after_minutes`,
  `responsiveness=worse_or_no`.
- Interpretation: Cell B did not improve over Cell A. `disable-gpu` is not a
  usability fix. The app remains non-interactable, the start screen remains
  frozen/crashed, and interaction still crashes. Do not treat
  `webview2_process_count=0` as success.

Cell C result (2026-06-19,
`logs/ableton-runner-tests/20260619-163939-matrix-c-default-cursorguard/result.env`):
- Runner: system Wine `wine-11.0 (Staging)`.
- Prefix: copied test prefix
  `~/WinePrefixes/ableton12-matrix-c-default-cursorguard-test`.
- Mode: `webview2_mode=default`, `cursor_guard=on`, DXVK active.
- Cursor guard was a real helper-backed test:
  `cursor_guard_pid=466958`,
  `cursor_visibility_action=defined_left_ptr_on_ableton_window`, `errors=none`
  in `cursor-guard.txt`.
- Deterministic fields: `ableton_launched=yes`, `window_detected=yes`,
  `backend_effective=dxvk`, `recreating_swapchain_count=26`,
  `webview2_process_count=5`, `webview2_crash=yes`, `kprior_crash=yes`.
- User observation: `main_editor_interactable=no`,
  `mouse_disappears_over_main_editor=inconclusive/not_primary_signal`,
  `crash_on_interaction=yes_or_same_as_A_B`,
  `start_screen_webview2_crash=yes_but_startup_window_resolved_a_little_faster`,
  `flicker=same_or_not_fully_observed`, `responsiveness=worse_or_no`,
  `cursor_visibly_improved=no_functional_improvement`.
- Interpretation: Cell C did not meaningfully improve usability. The cursor
  guard was active and successfully applied
  `defined_left_ptr_on_ableton_window`, but Ableton remained effectively the
  same as Cells A and B. The startup window resolved a little faster, but this
  is not success because the main editor still was not usable.

Matrix conclusion so far: A, B, and C all failed under system Wine 11.0 Staging
with copied prefixes and DXVK active. Neither WebView2 `--disable-gpu` nor the
X11 cursor guard is a meaningful usability fix.

Working conclusion: stop the local shim matrix here unless Cell D is explicitly
requested for formal closure. The failure is deeper than these local shims:
- A: failed — default WebView2, cursor guard off.
- B: failed — WebView2 `--disable-gpu`, cursor guard off.
- C: failed — default WebView2, cursor guard on.

Next direction: use `bin/ableton-runner-test` to compare genuinely different
Wine bases with copied prefixes and DXVK active. Do not patch Wine/DXVK/WebView2
yet, do not keep tuning WebView2 flags, and do not run Cell D unless explicitly
approved. See `docs/ableton-runner-candidate-plan.md`.

### Runner Candidate 1 metadata — Kron4ek Proton Experimental 11.0

Status on 2026-06-19: acquired and prepare-only checked. Ableton was not
launched.

```text
candidate=Kron4ek Proton Experimental 11.0
artifact_filename=wine-proton-exp-11.0-amd64-wow64.tar.xz
source_url=https://github.com/Kron4ek/Wine-Builds/releases/download/proton-exp-11.0/wine-proton-exp-11.0-amd64-wow64.tar.xz
local_path=.local-runners/wine-proton-exp-11.0-amd64-wow64.tar.xz
computed_sha256=0d3bf893abc0ff3bb72564c41a14f9f33bdf0246e080be18205019c81603447b
expected_sha256=0d3bf893abc0ff3bb72564c41a14f9f33bdf0246e080be18205019c81603447b
checksum_verified=yes
extracted=yes
extract_path=.local-runners/kron4ek-proton-exp-11.0/
resolved_wine_paths=.local-runners/kron4ek-proton-exp-11.0/bin/wine .local-runners/kron4ek-proton-exp-11.0/lib/wine/x86_64-unix/wine
runner_path=.local-runners/kron4ek-proton-exp-11.0/bin/wine
runner_bin_dir=.local-runners/kron4ek-proton-exp-11.0/bin
wine_version=wine-11.0-gd0c1d0160f9 (Proton)
system_wine_version=wine-11.0 (Staging)
different_from_system_wine_11_staging=yes_version_string_differs
source_download_method=GitHub release tarball
requires_system_packages=no
prepare_only_label=candidate1-kron4ek-proton-exp-11-prepare
prepare_only_ok=yes
test_prefix=/home/timcis/WinePrefixes/ableton12-candidate1-kron4ek-proton-exp-11-prepare-test
ableton_launched=no
working_prefix_touched=no
ready_for_candidate1_run=yes
```

Expected reversibility: remove `.local-runners/kron4ek-proton-exp-11.0/`,
`.local-runners/wine-proton-exp-11.0-amd64-wow64.tar.xz`, and the copied test
prefix only. Do not remove the working prefix.

Candidate 1 launch audit (2026-06-19): **invalid pending backend fix**.

```text
official_candidate1_result=invalid_pending_backend_fix
backend_effective=wined3d_builtin_likely
dxvk_dlls_present_in_test_prefix=no
ableton_processes_stopped=yes
working_prefix_touched=no
```

Evidence:
- The Candidate 1 run bundle reported
  `backend_effective=wined3d_builtin_likely`.
- Candidate 1 launch segment in `logs/ableton.log` had
  `runner_log_dxvk_lines=0`.
- The Candidate 1 run prefix contained Wine builtin `system32/d3d11.dll` and
  `system32/dxgi.dll`:
  - `d3d11.dll` sha256
    `d943b99b5aacc00b45880e34047263ae424c635d0bed52d911c5f9d6f8d7cd70`
  - `dxgi.dll` sha256
    `2783cc86f506d7daa20ef6de68cdfb5d95bd4f29e4e1d415afa422363247a524`
- The Candidate 1 prepare-only prefix still preserved the working-prefix DXVK
  hashes:
  - `d3d11.dll` sha256
    `557c1f50e7ff73bcd24968a02352519df89d8b3fe037d47580091ffafe1940dd`
  - `dxgi.dll` sha256
    `f31cd64b547c59441956b17e2a013791dcb62abb1e671fb31d49ff4d6c2b3fd7`

Interpretation: the Proton runner's prefix-update path overwrote the copied
prefix's DXVK DLLs at launch time. This violates the runner comparison rule, so
the Candidate 1 run is not an official comparison result.

Recommended fix before rerun: add a controlled DXVK-enforcement launch path for
copied-prefix runner comparisons. After any runner prefix-update step, verify
the copied-prefix `d3d11.dll`/`dxgi.dll` still match the working-prefix DXVK
hashes; if overwritten, restore the same DXVK DLLs into the copied prefix only,
then launch with `WINEDLLOVERRIDES=d3d11,dxgi=n`. Do not use the forbidden
builtin override `WINEDLLOVERRIDES=dxgi,d3d11=b`.

Harness update: `bin/ableton-runner-test --enforce-dxvk` implements this copied-
prefix-only DXVK enforcement path. The original Candidate 1 launch remains
invalid. Rerun requires `--enforce-dxvk`. Runner comparisons are invalid unless
DXVK hashes are verified after runner prefix update.

Implementation note: the working/source prefix has DXVK signatures in
`system32/d3d11.dll` and `system32/dxgi.dll`; `syswow64` contains Wine builtin
DLLs. For this 64-bit Ableton comparison, `--enforce-dxvk` requires system32
DXVK signatures, while syswow64 files are still copied and hash-verified if
present.

Candidate 1 status: **blocked, not failed**.

```text
candidate=Kron4ek Proton Experimental 11.0
status=blocked_backend_loader
official_usability_result=no
reason=without enforcement runner overwrote DXVK with Wine builtin DLLs; with --enforce-dxvk hashes matched source but Ableton failed before launch with d3d11.dll not found / status c0000135
working_prefix_touched=no
```

Candidate 1 DXVK-enforced rerun attempt (2026-06-19): not a valid usability
result. The harness restored and verified `system32` DXVK hashes in the copied
prefix, but Ableton did not launch:

```text
run_dir=logs/ableton-runner-tests/20260619-171522-candidate1-kron4ek-proton-exp-11-dxvk-enforced
dxvk_enforced=yes
dxvk_restored_after_runner_prefix_update=yes
dxvk_hashes_match_source=yes
launch_winedlloverrides=d3d11,dxgi=n
ableton_launched=no
window_detected=no
backend_effective=invalid_builtin_dll_for_dxvk_comparison
loader_error=d3d11.dll not found / status c0000135
working_prefix_touched=no
```

Interpretation: Candidate 1 still needs backend/loader investigation before it
can be used as an official runner comparison. Do not ask for live usability
observation from this run. Do not keep debugging Candidate 1 unless explicitly
requested.

Backend audit file:
`logs/ableton-runner-tests/20260619-170001-candidate1-kron4ek-proton-exp-11-default-off/backend-audit.txt`.

### Runner Candidate 2 metadata — Kron4ek Wine 11.11 staging-tkg

Status on 2026-06-19: acquired and prepare-only checked. Ableton was not
launched.

```text
candidate=Kron4ek Wine 11.11 staging-tkg
artifact_filename=wine-11.11-staging-tkg-amd64-wow64.tar.xz
source_url=https://github.com/Kron4ek/Wine-Builds/releases/download/11.11/wine-11.11-staging-tkg-amd64-wow64.tar.xz
local_path=.local-runners/wine-11.11-staging-tkg-amd64-wow64.tar.xz
computed_sha256=44f5330be22424c51d2b48ddc60dc4e1fca686628cedd9e76cd2b041a4aeb3d9
expected_sha256=44f5330be22424c51d2b48ddc60dc4e1fca686628cedd9e76cd2b041a4aeb3d9
checksum_verified=yes
extracted=yes
extract_path=.local-runners/kron4ek-wine-11.11-staging-tkg/
resolved_wine_paths=.local-runners/kron4ek-wine-11.11-staging-tkg/bin/wine .local-runners/kron4ek-wine-11.11-staging-tkg/lib/wine/x86_64-unix/wine
runner_path=.local-runners/kron4ek-wine-11.11-staging-tkg/bin/wine
runner_bin_dir=.local-runners/kron4ek-wine-11.11-staging-tkg/bin
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
system_wine_version=wine-11.0 (Staging)
different_from_system_wine_11_staging=yes
source_download_method=GitHub release tarball
requires_system_packages=no
prepare_only_label=candidate2-kron4ek-wine-11-11-prepare
prepare_only_ok=yes
test_prefix=/home/timcis/WinePrefixes/ableton12-candidate2-kron4ek-wine-11-11-prepare-test
ableton_launched=no
working_prefix_touched=no
ready_for_candidate2_run=yes
```

Expected reversibility: remove `.local-runners/kron4ek-wine-11.11-staging-tkg/`,
`.local-runners/wine-11.11-staging-tkg-amd64-wow64.tar.xz`, and the copied test
prefix only. Do not remove the working prefix.

Candidate 2 status: **blocked, not failed**.

```text
candidate=Kron4ek Wine 11.11 staging-tkg
status=blocked_backend_loader
official_usability_result=no
reason=with --enforce-dxvk, copied-prefix DXVK hashes matched source but Ableton failed before launch; backend_effective=invalid_builtin_dll_for_dxvk_comparison; ableton_launched=no; window_detected=no
working_prefix_touched=no
```

Runner acquisition/runs are stopped pending DXVK loader audit. See
`docs/ableton-dxvk-loader-audit.md`.

Candidate 2 DXVK-enforced run attempt (2026-06-19): backend/loader failure, not
a usability result.

```text
run_dir=logs/ableton-runner-tests/20260619-172535-candidate2-kron4ek-wine-11-11-dxvk-enforced
dxvk_enforced=yes
dxvk_restored_after_runner_prefix_update=yes
dxvk_hashes_match_source=yes
launch_winedlloverrides=d3d11,dxgi=n
ableton_launched=no
window_detected=no
backend_effective=invalid_builtin_dll_for_dxvk_comparison
working_prefix_touched=no
```

The copied prefix's `system32/d3d11.dll` and `system32/dxgi.dll` hashes matched
the source DXVK hashes, but Ableton did not launch and no window was detected.
No live usability observation was requested.

Loader-only follow-up for Candidate 2 (2026-06-19): `bin/ableton-dxvk-loader-probe`
compared native-only and native-then-builtin loader behavior without launching
Ableton.

```text
run_root=logs/ableton-dxvk-loader-probes/20260619-173904-candidate2-kron4ek-wine-11-11-*
runner=.local-runners/kron4ek-wine-11.11-staging-tkg
wine_version=wine-11.11.r0.g4d000a90 ( TkG Staging NTsync )
native_only_override=d3d11,dxgi=n
native_only_hashes_match_source=yes
native_only_loader_result=d3d11.dll and dxgi.dll fail with status=c0000135
native_then_builtin_override=d3d11,dxgi=n,b
native_then_builtin_hashes_match_source=yes
native_then_builtin_loader_result=copied d3d11/dxgi DLLs are mapped, but builtin wined3d.dll is loaded
ableton_launched=no
working_prefix_touched=no
```

Conclusion: do not continue runner usability tests from this state. Candidate 2
remains `blocked_backend_loader`; `n,b` is not a clean DXVK enforcement policy
because it allows builtin/wined3d involvement.

System Wine loader-control and DXVK import audit (2026-06-19):

```text
run_root=logs/ableton-dxvk-loader-probes/20260619-212030-system-wine-11-staging-control-*
runner=/usr
wine_version=wine-11.0 (Staging)
system_control_native_only_result=d3d11.dll and dxgi.dll fail with status=c0000135
system_control_native_then_builtin_result=copied d3d11/dxgi DLLs are mapped; no wined3d.dll load observed
candidate2_native_only_result=c0000135
candidate2_native_then_builtin_result=mapped copied DLLs but loaded builtin wined3d.dll
ableton_launched=no
working_prefix_touched=no
```

Interpretation: the `rundll32.exe d3d11.dll,DllRegisterServer` native-only probe
is not a valid clean DXVK-load control, because system Wine fails it too. The
useful control signal is `n,b`: system Wine maps the copied source-prefix DXVK
DLLs without `wined3d.dll`, while Candidate 2 maps them and then loads builtin
`wined3d.dll`.

DXVK import/dependency inspection found no obvious missing external dependency:

```text
d3d11_imports=ADVAPI32.dll, dxgi.dll, GDI32.dll, KERNEL32.dll, msvcrt.dll, SETUPAPI.dll, USER32.dll
dxgi_imports=ADVAPI32.dll, KERNEL32.dll, msvcrt.dll, SETUPAPI.dll, USER32.dll
suspected_missing_dependency=none obvious from PE imports; no direct vulkan-1.dll, msvcp*, or vcruntime* import listed
runner_resolution_difference=Candidate 2 has its own x86_64/i386 d3d11.dll, dxgi.dll, wined3d.dll, and vulkan-1.dll under lib/wine/*-windows; n,b resolution pulls wined3d for Candidate 2 but not system Wine control
recommended_next_action=inspect runner PE/builtin resolution and wined3d involvement before any further Ableton launch
```

Minimal PE loader-control probe status (2026-06-19):

```text
tools/dxvk-load-probe.c=added
bin/ableton-dxvk-pe-loader-probe=added
pe_loader_probe_build_available=no
missing_compilers=x86_64-w64-mingw32-gcc clang
rpm_mingw64_gcc=not_installed
installed_mingw_support_packages=yes
installed_compiler_package=no
pe_loader_probe_executable_built=no
pe_loader_probe_runs_started=no
ableton_launched=no
working_prefix_touched=no
```

The PE probe is designed to call `LoadLibraryW` for `dxgi.dll` and `d3d11.dll`,
then resolve `CreateDXGIFactory1` and `D3D11CreateDevice` without creating a D3D
device. It could not be built with currently installed tools. Do not infer a
Wine/DXVK result from this blocked build step.

Second verification after reported compiler install:

```text
rpm_mingw64_gcc=not_installed
command_x86_64_w64_mingw32_gcc=not_found
usr_bin_mingw_gcc_binaries=none
installed_mingw_support_packages=yes
installed_compiler_package=no
pe_loader_probe_executable_built=no
pe_loader_probe_runs_started=no
ableton_launched=no
working_prefix_touched=no
```

Final PE loader-control probe result (2026-06-19):

```text
compiler_installed=yes
compiler_path=/usr/bin/x86_64-w64-mingw32-gcc
compiler_version=x86_64-w64-mingw32-gcc (GCC) 16.1.1 20260501 (Fedora MinGW 16.1.1-1.fc44)
pe_loader_probe_build_available=yes
pe_loader_probe_executable_built=yes
pe_loader_probe=.local-tools/dxvk-load-probe.exe
run_root=logs/ableton-dxvk-pe-loader-probes/20260619-213942-*
ableton_launched=no
working_prefix_touched=no
```

PE probe results:

```text
system_wine_native_only=failed LoadLibraryW dxgi/d3d11 error=126
system_wine_native_then_builtin=succeeded; copied d3d11/dxgi mapped; wined3d_loaded=no
candidate2_native_only=failed LoadLibraryW dxgi/d3d11 error=126
candidate2_native_then_builtin=succeeded; copied d3d11/dxgi mapped; wined3d_loaded=yes
```

Interpretation: `WINEDLLOVERRIDES=d3d11,dxgi=n` is too strict as a standalone
loader-control mode for both system Wine and Candidate 2. `n,b` is sufficient
for minimal PE `LoadLibraryW`/`GetProcAddress`, but Candidate 2 still diverges
from system Wine because it loads `wined3d.dll`. Candidate 2 remains
`blocked_backend_loader` for official Ableton comparison until that runner
resolution difference is explained or avoided.

PE loader-sequence audit from existing logs (2026-06-19):

```text
system_sequence_summary=under d3d11,dxgi=n,b, system Wine maps C:\windows\system32\dxgi.dll, completes dxgi attach, maps C:\windows\system32\d3d11.dll, reuses dxgi, and never loads wined3d.dll
candidate2_sequence_summary=under d3d11,dxgi=n,b, Candidate 2 maps C:\windows\system32\dxgi.dll, then loads C:\windows\system32\wined3d.dll during dxgi load/attach before d3d11.dll is loaded; d3d11 then reuses existing dxgi and wined3d
candidate2_wined3d_trigger=during Candidate 2 dxgi.dll load/attach path, after dxgi map and before dxgi process_attach completes
candidate2_uses_runner_builtin_d3d11_or_dxgi=unknown; logs map C:\windows\system32 copied paths but label them builtin
candidate2_maps_copied_dxvk_before_wined3d=yes for dxgi; d3d11 maps after wined3d is already loaded
candidate2_falls_back_after_native_failure=no_observed_native_failure_before_wined3d
runner_builtin_files_summary=Candidate 2 ships Wine builtin x86_64-windows d3d11.dll, dxgi.dll, wined3d.dll, and vulkan-1.dll; wined3d contains WineD3D_OpenGL strings
recommended_next_action=abandon Candidate 2 for official runner comparison unless explicitly investigating runner PE/builtin resolution
ableton_launched=no
working_prefix_touched=no
```

Candidate 2 final decision:

```text
Candidate 2 final status=abandoned_for_official_comparison
official_usability_result=no
reason=PE loader sequence shows Candidate 2 maps dxgi.dll, then loads wined3d.dll during DXGI load/attach before d3d11.dll; system Wine does not load wined3d in the same PE n,b control path
working_prefix_touched=no
```

Candidate 3 acquisition/preflight status:

```text
Candidate 3 status=acquisition_blocked
candidate=Frogging-Family Wine-TKG Valve Exp Bleeding Edge
source_workflow=https://github.com/Frogging-Family/wine-tkg-git/actions/workflows/wine-valvexbe.yml
latest_successful_run_id=27850814211
artifact_id=7759513604
artifact_name=wine-tkg-build
artifact_expired=false
downloaded=no
download_result=blocked_http_401_auth_required
reason=GitHub Actions artifact metadata visible, but artifact archive download returned HTTP 401 authentication required; no local artifact, no SHA256, no extraction, no prepare-only, no PE gate
sha256=not_available
extracted=no
runner_path=not_resolved
wine_version=not_available
prepare_only_ok=no_not_run
candidate3_pe_gate_result=not_run
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Candidate 3 public workflow/artifact metadata is available, but
the GitHub Actions artifact archive requires authentication to download. Do not
run Candidate 3, build locally, or use another acquisition source without
explicit approval.

Candidate 4 acquisition/preflight status:

```text
candidate4_selected=Lutris Wine 7.2-2
source_url=https://github.com/lutris/wine/releases/download/lutris-wine-7.2-2/wine-lutris-7.2-2-x86_64.tar.xz
local_artifact=.local-runners/wine-lutris-7.2-2-x86_64.tar.xz
sha256=3a1428358f52c055f7b8f4368291746e9fd9d1db85ae63d5145157f9ed1a8a12
extracted=yes
extract_path=.local-runners/lutris-wine-7.2-2/
runner_path=.local-runners/lutris-wine-7.2-2-wine64-shim
wine_version=wine-7.2-1-g1f8837bdccd (Staging)
prepare_only_ok=yes
candidate4_dxvk_hashes_match_source=yes
candidate4_native_only=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4_native_then_builtin=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4_n_b_probe_exit_code=1
candidate4_n_b_maps_d3d11=no
candidate4_n_b_maps_dxgi=no
candidate4_n_b_loads_wined3d=no
candidate4_pe_gate_result=fail
status=blocked_pe_loader_preflight
official_usability_result=no
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Candidate 4 Lutris Wine 7.2-2 is acquired and prepare-only
checked, but blocked before any Ableton launch because the required PE loader
gate fails before copied DXVK DLLs are mapped. Do not launch this runner unless
explicitly approved after resolving the `/lib/ld-linux.so.2` runtime issue.

Candidate 4B acquisition/preflight status:

```text
candidate4b_selected=Bottles Soda 9.0-1
component_metadata_url=https://raw.githubusercontent.com/bottlesdevs/components/main/runners/wine/soda-9.0-1.yml
component_file_name=soda-9.0-1-x86_64.tar.xz
component_url=https://github.com/bottlesdevs/wine/releases/download/soda-9.0-1/soda-9.0-1-x86_64.tar.xz
component_file_checksum=8806df3e294dd37cf461ed3432d65318
component_file_checksum_type=md5
component_file_size=61960416
local_artifact=.local-runners/soda-9.0-1-x86_64.tar.xz
local_file_size=64564696
local_file_size_matches_component=no
md5_verified=yes
sha256=c38fe0ad3c12a49b61ec1fcaea5c5d8da4a3d1afc5991befe2af6b125f014c28
extracted=yes
runner_path=.local-runners/bottles-soda-9.0-1-wine64-shim
wine_version=wine-experimental.bleeding.edge.9.0.93696.20240429 ( TkG Plain )
prepare_only_ok=yes
candidate4b_dxvk_hashes_match_source=yes
candidate4b_native_only=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4b_native_then_builtin=failed_before_dll_mapping_/lib/ld-linux.so.2_could_not_open
candidate4b_n_b_probe_exit_code=1
candidate4b_n_b_maps_d3d11=no
candidate4b_n_b_maps_dxgi=no
candidate4b_n_b_loads_wined3d=no
candidate4b_pe_gate_result=fail
status=blocked_pe_loader_preflight
official_usability_result=no
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Candidate 4B Bottles Soda 9.0-1 is acquired and prepare-only
checked, but blocked before any Ableton launch because the PE loader gate fails
before copied DXVK DLLs are mapped. Do not launch this runner unless explicitly
approved after resolving the `/lib/ld-linux.so.2` runtime issue.

Candidate 4 i686 loader retest:

```text
ld_linux_so_2_present=yes
glibc_i686_installed=glibc-2.43-6.fc44.i686
candidate4a_wine_runs=no_exit_159
candidate4a_pe_gate_result=fail_no_valid_native_then_builtin_gate_result
candidate4a_native_only_dxvk_hashes_match_source=yes
candidate4a_native_only_probe_exit_code=1
candidate4a_native_only_maps_d3d11=no
candidate4a_native_only_maps_dxgi=no
candidate4a_native_only_loads_wined3d=no
candidate4a_native_only_error=run_wineboot_boot_event_wait_timed_out_then_c0000135_for_dxgi_and_d3d11
candidate4a_native_then_builtin_result=not_completed_no_result_env
candidate4b_wine_runs=no_exit_159
candidate4b_pe_gate_result=fail_no_valid_native_then_builtin_gate_result
candidate4b_native_only_result=not_completed_no_result_env
candidate4b_native_then_builtin_result=not_run_no_result_env
ableton_launched=no
working_prefix_touched=no
```

Interpretation: The i686 loader package is installed and `/lib/ld-linux.so.2`
exists, but Candidate 4A and 4B still do not pass the PE loader-control gate.
This remains a runner/preflight block, not an Ableton usability result. Do not
launch Ableton with Candidate 4A or 4B until a clean `d3d11,dxgi=n,b` PE gate
maps copied DXVK and avoids `wined3d.dll`.

Candidate 4 shim-entrypoint retest:

```text
shim_wineboot_replaced_with_wine64_wrapper=yes
candidate4a_wine_version=wine-7.2-1-g1f8837bdccd (Staging)
candidate4a_pe_gate_result=fail_timeout_before_candidate_native_then_builtin_gate
candidate4a_native_only_result=not_completed_no_result_env
candidate4a_n_b_maps_d3d11=not_run_no_result_env
candidate4a_n_b_maps_dxgi=not_run_no_result_env
candidate4a_n_b_loads_wined3d=not_run_no_result_env
candidate4b_wine_version=wine-experimental.bleeding.edge.9.0.93696.20240429 ( TkG Plain )
candidate4b_native_only_dxvk_hashes_match_source=yes
candidate4b_native_only_probe_exit_code=1
candidate4b_native_only_maps_d3d11=no
candidate4b_native_only_maps_dxgi=no
candidate4b_native_only_loads_wined3d=no
candidate4b_pe_gate_result=fail_timeout_before_candidate_native_then_builtin_result
candidate4b_n_b_maps_d3d11=not_completed_no_result_env
candidate4b_n_b_maps_dxgi=not_completed_no_result_env
candidate4b_n_b_loads_wined3d=not_completed_no_result_env
ableton_launched=no
working_prefix_touched=no
```

Interpretation: Replacing only the local Candidate 4 shim entrypoints with
explicit `wine64` wrappers corrected the shim `wine --version` path but did not
produce a valid PE loader gate. Candidate 4A timed out before a candidate result.
Candidate 4B failed native-only without mapping copied DXVK and timed out before
the candidate `n,b` gate completed. Candidate 4 remains blocked at loader
preflight.

Matrix validity rule: DXVK must remain active from the copied prefix. The matrix
is invalid if builtin `d3d11`/`dxgi` is forced; this is not a `wined3d` test.

## Diagnostic tooling (in `bin/`)
- `bin/ableton-session-probe` — read-only session snapshot (geometry, interaction,
  backend, 30s swapchain churn). Refuses to run if `DXVK_LOG_LEVEL=none`.
- `bin/diagnose-ableton-graphics-backend` — read-only DXVK/DLL/log inspector.
- `bin/diagnose-ableton-interaction` — read-only stacking/activation interaction probe.
- `bin/ableton-graphics-wined3d-cleantest` — reversible wined3d test (auto-restore).
- `bin/ableton-dxvk-version-test <dir> [label]` — reversible DXVK-version A/B (auto-restore).
- `bin/fix-ableton-window-bounds` — dormant ground-truth bounds checker (bounds not a defect).
- `bin/ableton-webview2-mode` — environment-only WebView2 launch-mode printer.
- `bin/ableton-cursor-guard` — X11/XWayland cursor/input probe and optional
  scoped cursor definition for Ableton's detected top-level window.
- `bin/ableton-dxvk-loader-probe` — loader-only copied-prefix DXVK DLL probe;
  does not launch Ableton.
- `bin/ableton-dxvk-pe-loader-probe` — PE LoadLibrary/GetProcAddress loader
  probe; does not launch Ableton.
- `docs/ableton-custom-compat-layer.md` — compatibility-layer V1 procedure.
- `docs/ableton-x11-ab-test.md` — X11/Wayland A/B procedure.

### Diagnostic determinism caveats (do not be misled by these)
- `wmctrl -lxG` reports window x,y at ~2x the true root coords under XWayland
  (size is correct) — use `xwininfo`/`xdotool` absolute coords for geometry.
- `bin/diagnose-ableton-windowing` aggregator can be masked by a trailing benign
  1x1 candidate window (last `derived_issue` wins) — read the per-window blocks.
- `logs/ableton.log` is append-only across runs; segment at the most recent
  `effective environment before Ableton launch` marker before counting DXVK/
  VK_SUBOPTIMAL/Presenter lines, or counts are contaminated by old runs.
- For the swapchain-churn proxy to be observable, DXVK logging must stay ON
  (never `DXVK_LOG_LEVEL=none` during measurement).

## Hard constraints in effect for this investigation
No Wine-build change, no DXVK version change beyond reversible A/B, no launcher
changes, no `dxvk.conf`, no `DXVK_LOG_LEVEL=none`, no Wine virtual desktop, no
forced KWin geometry, no file deletes (reversible renames only).

## Runner Candidate Conclusion

```text
RUNNER_CANDIDATE_CONCLUSION:
system_wine_11_staging=only known runner that launches Ableton
candidate1_status=blocked_backend_loader
candidate2_status=abandoned_for_official_comparison
candidate3_status=acquisition_blocked
candidate4a_status=blocked_pe_loader_preflight
candidate4b_status=blocked_pe_loader_preflight
candidate_runner_path_result=no alternate runner is currently eligible for Ableton usability testing
recommended_next_action=return to system Wine baseline and investigate the actual launch/usability failure surfaces
ableton_launched=no
working_prefix_touched=no
```

Runner-candidate exploration is stopped. Do not acquire more runners or run
Candidate 1, Candidate 2, Candidate 3, Candidate 4A, or Candidate 4B. The next
diagnostics should use system Wine 11.0 Staging and focus on the actual
launch/usability failure surfaces rather than runner replacement.

## System Wine Baseline WebView/Input Diagnostic

Run: `system-wine-baseline-webview-input-1` (2026-06-22)

```text
SYSTEM_WINE_BASELINE_WEBVIEW_INPUT_1:
run_dir=logs/ableton-runner-tests/20260622-222004-system-wine-baseline-webview-input-1
runner=/usr
wine_version=wine-11.0 (Staging)
prefix=/home/timcis/WinePrefixes/ableton12-system-wine-baseline-webview-input-1-test
webview2_mode=default
cursor_guard=off
backend_effective=dxvk
dxvk_hashes_match_source=not_checked_but_test_hashes_equal_source_hashes_in_result_env
ableton_launched=yes
window_detected=yes
main_window_interactable=needs_user_observation
start_screen_seen=likely_child_window_and_webview2_present
webview2_process_count=6
webview2_crash=yes
webview2_gpu_or_browser_exit_lines=229
kprior_crash=yes
recreating_swapchain_count=17
blocked_by_child_or_modal=yes
child_or_modal_evidence=second Ableton window 512x479 plus session_probe interaction_state=blocked_by_child_or_modal
user_visible_result=needs_user_observation
ableton_process_left_running=no_current_matching_process_after_collection
ableton_launched_from_working_prefix=no
working_prefix_touched=no
```

Interpretation: The corrected system-Wine copied-prefix baseline still reaches
the same failure surface family: Ableton launches under DXVK, WebView2 starts,
WebView2 GPU crash markers appear, and a child/modal-like Ableton window is
present during probe collection. The session probe classified interaction as
`blocked_by_child_or_modal`. This run should not be repeated as-is. The next
targeted branch should isolate WebView2/start-screen behavior first, while
preserving system Wine and copied-prefix discipline.

Run: `system-wine-webview2-isolated-user-data-1` (2026-06-22)

```text
SYSTEM_WINE_WEBVIEW2_ISOLATED_USER_DATA_1:
run_dir=logs/ableton-runner-tests/20260622-222439-system-wine-webview2-isolated-user-data-1
runner=/usr
wine_version=wine-11.0 (Staging)
prefix=/home/timcis/WinePrefixes/ableton12-system-wine-webview2-isolated-user-data-1-test
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
webview2_gpu_or_browser_exit_lines=230
kprior_crash=yes
recreating_swapchain_count=19
blocked_by_child_or_modal=yes
child_or_modal_evidence=second Ableton window 512x479 plus session_probe interaction_state=blocked_by_child_or_modal
user_visible_result=needs_user_observation
ableton_process_left_running=no_current_matching_process_after_collection
ableton_launched_from_working_prefix=no
working_prefix_touched=no
```

Interpretation: The isolated WebView2 user-data folder was used, but it did not
remove the WebView2 GPU crash markers or the child/modal input block. This makes
stale/corrupt WebView2 profile state unlikely as the main cause. Do not repeat
this launch unchanged. The next branch should either disable/bypass the
start-screen/WebView2 surface or move to input/window ownership diagnostics if
WebView2 can be ruled out.

Run: `system-wine-window-ownership-1` (2026-06-22)

```text
SYSTEM_WINE_WINDOW_OWNERSHIP_1:
run_dir=logs/ableton-runner-tests/20260622-223230-system-wine-window-ownership-1
runner=/usr
wine_version=wine-11.0 (Staging)
prefix=/home/timcis/WinePrefixes/ableton12-system-wine-window-ownership-1-test
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
user_visible_result=needs_user_observation
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Interpretation: The 512x479 blocker is an Ableton-owned dialog window, transient
for the main Ableton window, with the same Ableton process PID. It is not a
WebView2 window and is not a KPriorCrash/crashpad window. WebView2 still starts
and logs GPU crash markers, but the input-blocking surface identified by X11
ownership is the Ableton child dialog. The next branch should focus on
Ableton-owned dialog/start-screen window ownership or a targeted start-screen
bypass, not WebView2 profile state.

## Ableton-Owned Dialog Identification / Bypass Audit

Audit source: `logs/ableton-runner-tests/20260622-223230-system-wine-window-ownership-1`
and copied prefix
`/home/timcis/WinePrefixes/ableton12-system-wine-window-ownership-1-test`.
No Ableton launch was performed for this audit.

Read-only findings:

- The blocker remains classified as an Ableton-owned dialog:
  `blocker_window_id=0x09000008`, `blocker_geometry=333,322 512x479`,
  `_NET_WM_WINDOW_TYPE_DIALOG`, transient for main window `0x09000003`, same
  Ableton PID as the main process.
- The ownership probe rules out WebView2 and crashpad/KPriorCrash as the
  blocking window owner: `blocker_is_webview2=no`,
  `blocker_is_kprior_crash=no`, `blocker_is_ableton_child=yes`.
- The run bundle still records WebView2 GPU exits and
  `Default App: Detected a prior crash`; that remains a failure surface, but it
  does not own the blocking dialog window.
- Latest Ableton `Preferences/Log.txt` reaches
  `Default App: Checking whether to restore the document`, then loads
  `DefaultLiveSet.als`.
- Active crash-recovery metadata exists in the copied prefix:
  `Preferences/CrashRecoveryInfo.cfg` and
  `Preferences/Crash/2026_06_22__22_32_13_CrashRecoveryInfo.cfg`. Both reference
  `C:/ProgramData/Ableton/Live 12 Suite/Resources/Builtin/Templates/DefaultLiveSet.als`.
- Existing `.als` files are present in the copied prefix, including
  `Resources/Builtin/Templates/DefaultLiveSet.als`, but
  `bin/ableton-runner-test` does not currently support launching Ableton with a
  file argument.

Working interpretation:
`likely_dialog_identity=prior_crash_or_crash_recovery_startup_dialog` (not
visually confirmed). The best next bypass candidate is `C`: target the
crash/recovery startup path in a copied prefix. Any approved mutation must be
copied-prefix-only and reversible, with restore commands printed before changes.
Do not repeat WebView2 profile tests or unchanged system-Wine baselines.

## System Wine Crash-Recovery Bypass Diagnostic

Run: `system-wine-crash-recovery-bypass-1` (2026-06-22)

The harness now supports `--crash-recovery-bypass`, which prepares a copied test
prefix, then moves only copied-prefix Ableton crash/recovery startup metadata
into a copied-prefix-local backup directory before launch. Restore commands are
printed before every rename and recorded in the run bundle.

```text
SYSTEM_WINE_CRASH_RECOVERY_BYPASS_1:
run_dir=logs/ableton-runner-tests/20260622-224403-system-wine-crash-recovery-bypass-1
runner=/usr
wine_version=wine-11.0 (Staging)
prefix=/home/timcis/WinePrefixes/ableton12-system-wine-crash-recovery-bypass-1-test
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
webview2_gpu_or_browser_exit_lines=234
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
user_visible_result=needs_user_observation
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Interpretation: The crash/recovery metadata bypass did not remove the same
Ableton-owned 512x479 dialog. The copied-prefix latest log segment still loads
`DefaultLiveSet.als`, then WebView2 GPU/browser exits occur. Crash-recovery
metadata alone is not a sufficient bypass. Next branch: visually identify the
dialog, or patch the harness to test an explicit `.als` file launch in a copied
prefix. Do not repeat this crash-recovery bypass unchanged.

## System Wine Explicit ALS Launch Diagnostic

Run: `system-wine-explicit-als-default-template-1` (2026-06-22)

The harness now supports `--launch-file-relative`, which resolves a file under
the copied test prefix only, refuses paths outside the test prefix, verifies the
file exists, and launches Ableton with the resolved file path as an explicit
argument. This test passed the copied-prefix default template `.als` file.

```text
SYSTEM_WINE_EXPLICIT_ALS_DEFAULT_TEMPLATE_1:
run_dir=logs/ableton-runner-tests/20260622-225030-system-wine-explicit-als-default-template-1
runner=/usr
wine_version=wine-11.0 (Staging)
prefix=/home/timcis/WinePrefixes/ableton12-system-wine-explicit-als-default-template-1-test
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
webview2_gpu_or_browser_exit_lines=230
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
user_visible_result=deterministic_same_512x479_ableton_owned_dialog_blocker
ableton_process_left_running=no_current_matching_process_after_collection
working_prefix_touched=no
```

Interpretation: Explicitly launching the built-in default `.als` template did
not bypass the 512x479 Ableton-owned dialog. The process command line confirms
the explicit file argument was passed, but `blocked_by_child_or_modal` and the
same dialog geometry/window ownership remain. Next diagnostic: one targeted
visual capture of the 512x479 dialog only, then decide whether the target is a
startup/welcome/licensing/update prompt or a Wine dialog-ownership/input issue.

## System Wine Dialog Visual Capture

Run: `system-wine-dialog-visual-capture-1` (2026-06-25)

The harness now supports `--dialog-visual-capture`. After the ownership probe
identifies the blocker, it captures only that X11 window with ImageMagick
`import -window`; it does not focus, move, resize, click, or close the window.

```text
run_dir=logs/ableton-runner-tests/20260625-154611-system-wine-dialog-visual-capture-1
runner=/usr
wine_version=wine-11.0 (Staging)
ableton_launched=yes
window_detected=yes
backend_effective=dxvk
blocked_by_child_or_modal=yes
blocker_window_id=0x07800008
blocker_geometry=333,322 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07800003
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
capture_tool=import
capture_file=logs/ableton-runner-tests/20260625-154611-system-wine-dialog-visual-capture-1/blocker-window.png
capture_success=yes
webview2_process_count=6
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=109
ableton_process_left_running=no
working_prefix_touched=no
```

Visual identification: the 512x479 window contains a severely zoomed/cropped
promotional image from the Ableton start-screen content surface. Only fragments
of large display lettering are visible, with no visible dialog message,
buttons, license controls, recovery controls, or error text. This rules out the
working assumption that the blocker is a conventional crash-recovery prompt.
The ownership remains Ableton-side at X11 level, but the visible content is
consistent with the embedded start-screen/media surface. The next diagnostic
should target the start-screen host viewport/scale and child-window integration,
not WebView2 profile state, crash-recovery metadata, licensing bypass, or more
runner changes.

## Start-Screen Viewport and Scale Audit

Audit source:
`logs/ableton-runner-tests/20260625-154611-system-wine-dialog-visual-capture-1`
and copied prefix
`/home/timcis/WinePrefixes/ableton12-system-wine-dialog-visual-capture-1-test`.
No Ableton launch or prefix mutation was performed for this audit.

Read-only findings:

- The captured blocker is exactly `512x479`, matching its X11 client geometry.
- The same X11 tree contains an unnamed `msedgewebview2.exe` surface sized
  `1432x776`, while the visible Ableton-owned dialog remains `512x479`.
- WebView2 starts with `--embedded-browser-webview-dpi-awareness=2`; its renderer
  reports `--device-scale-factor=1`. No explicit
  `--force-device-scale-factor` is present.
- Wine stores `LogPixels=0x60` (96 DPI). Ableton logs
  `Screen at +0+0: 1920x1080, scale 1`.
- The host X server reports 1920x1080, 96 DPI, identity transform, and KDE
  output scale 1. No `GDK_SCALE`, `QT_SCALE_FACTOR`, or equivalent process scale
  override is present.
- Ableton reports `Effective process DPI awareness: 0` while its ALF layer
  reports `pm-aware v2`. This inconsistency may affect child-window integration,
  but there is no numeric host/Wine DPI mismatch.
- `Preferences.cfg` contains generic second-window keys including
  `SecondWindowGuiScalingPercentUnlinked`, `SecondWindowPlacement`, and
  `SecondWindowIsOpen`. Read-only string inspection did not expose reliable
  values or a start-screen/welcome suppression key.
- Existing WebView2 modes are `default`, `disable-gpu`,
  `disable-gpu-no-sandbox`, and `isolated-user-data`; none controls viewport or
  device scale.

Conclusion: global DPI is consistently 96/scale 1. The evidence instead points
to a WebView2/start-screen surface whose content bounds are substantially larger
than the Ableton-owned dialog viewport. The safest next single launch candidate
is a copied-prefix, environment-only WebView2 mode that adds
`--force-device-scale-factor=0.5`. This is a diagnostic, not a proposed permanent
setting. It should retain the visual-capture probe so the resulting viewport can
be compared directly. Do not launch it without explicit approval.

## WebView2 Device Scale 0.5 Visual Comparison

Run: `system-wine-webview2-force-scale-0-5-1` (2026-06-25)

The WebView2 helper and harness gained the dedicated environment-only mode
`force-device-scale-0-5`, which sets only:

```text
WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--force-device-scale-factor=0.5
```

It did not change Wine DPI, KDE scale, KWin geometry, DXVK, WebView2 user data,
or the working prefix.

```text
run_dir=logs/ableton-runner-tests/20260625-155514-system-wine-webview2-force-scale-0-5-1
runner=/usr
wine_version=wine-11.0 (Staging)
webview2_mode=force-device-scale-0-5
ableton_launched=yes
window_detected=yes
backend_effective=dxvk
blocked_by_child_or_modal=yes
blocker_window_id=0x07800008
blocker_geometry=333,322 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07800003
blocker_is_webview2_corrected=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
capture_tool=import
capture_file=logs/ableton-runner-tests/20260625-155514-system-wine-webview2-force-scale-0-5-1/blocker-window.png
capture_success=yes
webview2_process_count=6
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=13
ableton_process_left_running=no
working_prefix_touched=no
```

The WebView2 process tree confirms the flag propagated: the main process and
renderer contain `--force-device-scale-factor=0.5`, and the renderer reports
`--device-scale-factor=0.5`.

Visual difference: the previous oversized promotional image disappeared. The
same `512x479` modal surface instead captured a scaled/cropped portion of
Ableton's mixer/editor, including track routing, send, arm, and solo controls.
This is a real rendering change, but it is not a usable start screen: the same
Ableton-owned modal child remains, the session remains
`blocked_by_child_or_modal`, and the separate WebView2 X11 surface remains
`1432x776`.

The raw ownership result reported `blocker_is_webview2=yes` only because its
classifier searched the full Ableton process command line, whose copied-prefix
label contains `webview2-force-scale`. The window PID and WM_CLASS remain
Ableton's; the corrected interpretation is `blocker_is_webview2=no`.

Conclusion: device scale affects what is painted into the blocker but does not
fix the host viewport or modal child ownership. Do not repeat scale `0.5`
unchanged. The next branch should inspect copied-prefix Ableton second-window
state and the host sizing relationship between the `1432x776` WebView2 surface
and the fixed `512x479` Ableton dialog.

## Second-Window State and Ownership Classifier Audit

No-launch audit completed on 2026-06-25 using only these copied prefixes:

- `/home/timcis/WinePrefixes/ableton12-system-wine-dialog-visual-capture-1-test`
- `/home/timcis/WinePrefixes/ableton12-system-wine-webview2-force-scale-0-5-1-test`

The ownership probe classifier was corrected. `blocker_is_webview2=yes` now
requires a WebView/MS Edge signal in `WM_CLASS`, `WM_NAME`, or `_NET_WM_NAME`,
or an exact process `argv[0]` basename of `msedgewebview2.exe`. Full command
lines, copied-prefix paths, and test labels are no longer WebView ownership
evidence.

Both copied `Preferences.cfg` files are byte-for-byte identical:

```text
size=29871
sha256=a8d2edf51e126dce792c536f584b62249f277b99e97da1df3c0e5b7948d0e164
```

Binary key context:

```text
SecondWindowGuiScalingPercentUnlinked: present at offset 778
SecondWindowPlacement: present at offset 1872
SecondWindowIsOpen: present at offset 1935
OpenSecondWindowOnStartup: absent
base_vs_scale_context_differs=no
```

The nearby bytes identify Ableton's serialized field/type schema, including
`UserFloat`, `WindowPlacement`, and `RemoteableBool`, but do not expose a
reliably decodable value adjacent to the key. Therefore this audit cannot safely
infer whether the second window is open, its placement, or its scale. Individual
binary-byte edits are not justified.

`OpenSecondWindowOnStartup` appears in `Log.txt` as a startup hook that runs in
zero milliseconds, not as a key in `Preferences.cfg`. `WebConnector.txt` only
records normal Web Connector process startup and contains no useful second
window, viewport, DPI, or scaling state.

Host geometry is invariant between the default visual run and scale-0.5 run:

```text
main_window=848x1052 at 165,28
blocker=512x479 at 333,322
webview2_surface=1432x776 at 4,30
```

Changing Chromium device scale changed the pixels rendered in the blocker but
did not change any host-window dimensions. This confirms that more Chromium
scale flags are not the next step.

Best next single launch candidate: add a copied-prefix-only reversible option
that prints a restore command, renames `Preferences.cfg` to a label-specific
backup after prefix preparation, then launches system Wine with default WebView2
mode and dialog capture. This tests stale Ableton second-window/preference state
without guessing at the binary format. If the same geometry remains with a
fresh generated preference file, close the preference-state branch and focus on
Wine/Ableton/WebView child-window host sizing. Do not run without explicit
approval.

## Preferences.cfg Reset Diagnostic

Run: `system-wine-preferences-cfg-reset-1` (2026-06-25)

The harness now supports `--preferences-cfg-reset`. It operates only after the
test prefix is copied, validates that both paths remain under the test prefix,
prints the exact restore command before renaming, and stores a manifest in the
label-specific copied-prefix backup directory and run bundle.

```text
run_dir=logs/ableton-runner-tests/20260625-160546-system-wine-preferences-cfg-reset-1
runner=/usr
wine_version=wine-11.0 (Staging)
preferences_cfg_reset_enabled=yes
preferences_cfg_moved=yes
preferences_cfg_backup_path=/home/timcis/WinePrefixes/ableton12-system-wine-preferences-cfg-reset-1-test/drive_c/users/timcis/AppData/Roaming/Ableton/Live 12.4.2/Preferences/.waydaw-preferences-cfg-reset-backup-system-wine-preferences-cfg-reset-1/Preferences.cfg
preferences_cfg_restore_command_recorded=yes
preferences_cfg_original_sha256=a8d2edf51e126dce792c536f584b62249f277b99e97da1df3c0e5b7948d0e164
preferences_cfg_generated_after_launch=no
preferences_cfg_generated_sha256=missing
ableton_launched=yes
window_detected=yes
blocked_by_child_or_modal=yes
blocker_window_id=0x07800009
blocker_geometry=704,314 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07800003
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
capture_tool=import
capture_file=logs/ableton-runner-tests/20260625-160546-system-wine-preferences-cfg-reset-1/blocker-window.png
capture_success=yes
webview2_process_count=5
webview2_crash=yes
kprior_crash=yes
recreating_swapchain_count=0
ableton_process_left_running=no
working_prefix_touched=no
```

The visual capture conclusively identifies the `512x479` dialog as Ableton's
software authorization welcome screen. It presents legitimate online,
offline/no-internet, and defer-authorization choices. No button was clicked and
no attempt was made to bypass licensing.

Interpretation:

- Removing copied `Preferences.cfg` did not remove the fixed modal host.
- It changed the content from malformed/cropped surfaces to a coherent
  first-run authorization dialog.
- Ableton did not generate a replacement `Preferences.cfg` during this run.
- At collection time, the original copied preference file remained intact at
  the recorded backup path with the expected SHA256 and restore command.
- The session probe reported no swapchain recreation activity while the
  authorization dialog was displayed; its `wined3d_builtin_likely` inference is
  not sufficient backend evidence for this run and does not override the
  verified copied DXVK DLL hashes.

The stale second-window preference hypothesis is not established as the root
cause. Further automated bypass work must stop at the authorization boundary.
The copied prefix can be restored using the recorded manifest. Any future
launch should occur only after the user chooses a legitimate authorization path
or explicitly requests a no-launch host-sizing investigation.

## Authorization Boundary Closeout

Closeout completed on 2026-06-25 without launching Ableton.

```text
AUTHORIZATION_BOUNDARY_CLOSEOUT:
preferences_cfg_reset_prefix_restored=yes
restored_preferences_cfg_path=/home/timcis/WinePrefixes/ableton12-system-wine-preferences-cfg-reset-1-test/drive_c/users/timcis/AppData/Roaming/Ableton/Live 12.4.2/Preferences/Preferences.cfg
restored_preferences_sha256=a8d2edf51e126dce792c536f584b62249f277b99e97da1df3c0e5b7948d0e164
automated_bypass_diagnostics_stopped=yes
working_prefix_touched=no
recommended_next_action=user must choose a legitimate Ableton authorization path before further launch testing
```

The exact restore command recorded in
`logs/ableton-runner-tests/20260625-160546-system-wine-preferences-cfg-reset-1/preferences-cfg-reset.txt`
was executed against only the copied test prefix. The restored file exists and
matches the original recorded SHA256. No authorization control was activated.

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

Read-only diagnostic completed on 2026-06-25 after the user's
`./bin/ableton` launch had already ended. Evidence bundle:
`logs/working-prefix-live-auth-input-diagnostic/`.

No new Ableton instance was launched. The existing launcher was not reused
because it mutates the working prefix's Wine window registry and defaults to:

```text
WAYDAW_ABLETON_GRAPHICS=wined3d
WINEDLLOVERRIDES=dxgi,d3d11=b
```

That launch policy conflicts with the established requirement to keep DXVK
active and with this diagnostic's no-working-prefix-mutation constraint.

Recorded state for the user's launch:

```text
launch_start=2026-06-25 16:16:36
launcher_exit=2026-06-25 16:17:28
launcher_exit_code=58
ableton_executable_process_after_exit=no
visible_ableton_or_webview_window_after_exit=no
residual_wineserver=yes
residual_webview2_gpu_process=yes
active_and_focused_window=waydaw_terminal
live_authorization_focus_evidence=unavailable
working_prefix_mutated_by_diagnostic=no
authorization_control_activated=no
```

Ableton's log confirms:

- Suite startup found no valid loaded Suite license.
- The existing unlock data described a Standard product and reported
  `IsUnlocked?=false`.
- Ableton completed application initialization and opened its second/start
  window path.
- WebView2 GPU processes exited repeatedly, followed by the main WebView2
  browser process exiting unexpectedly.
- A second Ableton initialization began shortly after the launcher reported
  exit code 58.

The Wine output also reports unavailable Windows Web Authentication activation
classes. This is relevant to a future legitimate authorization flow, but no
authorization control was clicked, so it is not yet evidence that button
activation itself fails.

Conclusion: the captured post-failure state is not a live dialog with focus
elsewhere. The Ableton parent and windows are gone, while a WebView2 GPU process
and wineserver remain orphaned. The apparent frozen authorization window is
most consistent with process/WebView lifecycle failure during the observed
session; a pure X11 focus or pointer-routing failure cannot be confirmed from
the ended session.

Before another live input diagnostic, the normal working-prefix launcher must
be brought back into alignment with the documented DXVK baseline and made
non-mutating for evidence collection. That is tooling work and requires
explicit approval. Do not click or automate authorization controls.

## Non-Mutating DXVK Diagnostic Launcher Mode

Tooling-only change completed on 2026-06-25. Ableton was not launched and the
working prefix was not mutated.

`bin/ableton` now supports an explicit opt-in diagnostic policy:

```bash
WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY=1 \
WAYDAW_ABLETON_GRAPHICS=dxvk \
WAYDAW_ABLETON_DRY_RUN=1 \
./bin/ableton
```

Diagnostic mode behavior:

- Requires `WAYDAW_ABLETON_GRAPHICS=dxvk`.
- Skips all `Managed` and `Decorated` registry writes.
- Skips all virtual-desktop registry deletion or modification.
- Does not invoke `winecfg`.
- Ignores and unsets inherited `WINEDLLOVERRIDES`, preventing builtin
  `d3d11/dxgi` overrides from leaking into the launch.
- Leaves existing prefix DXVK DLLs in place.
- Prints the effective launch policy and command before any future launch.
- `WAYDAW_ABLETON_DRY_RUN=1` exits before registry setup and before any Wine or
  Ableton command.

Verified dry-run fields:

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

The existing normal launcher default remains unchanged: absent the diagnostic
environment variables, it retains the legacy window-registry setup and
`wined3d` default. This is deliberate compatibility preservation, not a
recommendation to use that legacy path for Ableton diagnostics.

No live launch is authorized by this change. The next approved step may use the
new diagnostic mode for one working-prefix launch and passive focus/input
collection while the legitimate authorization dialog is visible.

## Working-Prefix DXVK Authorization Live Input Diagnostic

Run: `working-prefix-dxvk-auth-live-input-1` (2026-06-25)

The final dry-run verified DXVK mode, an empty DLL override, and disabled
registry/virtual-desktop mutation. One live working-prefix launch then ran
through the corrected diagnostic path. No authorization control was activated.

```text
diagnostic_bundle=logs/working-prefix-dxvk-auth-live-input-1
dry_run_verified=yes
live_launch_started=yes
registry_mutation_enabled=no
virtual_desktop_mutation_enabled=no
graphics_mode=dxvk
winedlloverrides=
authorization_control_activated=no
blocker_window_id=0x07000008
blocker_geometry=333,322 512x479
blocker_wm_name=Ableton Live 12 Suite
blocker_wm_class=ableton live 12 suite.exe
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07000003
blocker_pid=939932
blocker_is_webview2=no
blocker_is_kprior_crash=no
blocker_is_ableton_child=yes
capture_success=yes
visible_window_identity=Ableton software authorization welcome dialog
focus_window=waydaw terminal
focus_pid=22821
active_window=0x4e00004
ableton_process_alive_after_collection=yes
webview2_processes_alive_after_collection=yes
new_session_webview2_browser_alive_after_collection=no
working_prefix_mutated_by_diagnostic=no
```

The dialog was mapped, viewable, topmost among the Ableton windows, and
transient for the main Ableton window. It did not have `_NET_WM_STATE_FOCUSED`.
Both initial and follow-up snapshots reported the terminal as
`_NET_ACTIVE_WINDOW` and X input focus owner. No click or focus-changing command
was sent, so this proves failure to acquire/retain focus automatically but does
not yet prove that mouse events would be discarded after explicit activation.

The current launch's WebView2 GPU processes repeatedly exited and its main
browser process exited. The only WebView2 process remaining after collection
predated this launch and had no mapped window. Ableton and its native
authorization dialog remained alive despite those WebView failures.

Conclusion: the next branch is a narrow focus/activation diagnostic around the
native Ableton-owned authorization dialog, not authorization bypass and not
WebView2 input embedding. It should inspect focus protocols and, only with
explicit approval, activate the dialog without clicking any authorization
control, then re-check focus and passive pointer state.

## Working-Prefix Authorization Focus Activation Diagnostic

Run: `working-prefix-auth-focus-activation-1` (2026-06-25)

The existing live Ableton session was reused. No new Ableton instance was
launched, no authorization control was activated, and no keyboard or pointer
input was sent to Ableton.

Pre-activation X11 evidence:

```text
blocker_window_id=0x07000008
parent_window_id=0x07000003
blocker_window_type=_NET_WM_WINDOW_TYPE_DIALOG
blocker_transient_for=0x07000003
blocker_map_state=IsViewable
blocker_accepts_focus_hint=no
blocker_wm_protocols=WM_DELETE_WINDOW,_NET_WM_PING,WM_TAKE_FOCUS
blocker_state=_NET_WM_STATE_SKIP_TASKBAR
active_window=0x4e00004
focus_window=waydaw terminal
focus_pid=22821
```

The dialog and parent both set the ICCCM input hint to false and advertise
`WM_TAKE_FOCUS`. This means the window manager should request focus through the
client protocol instead of directly assigning X input focus.

Exactly one activation request was issued:

```text
wmctrl -ia 0x07000008
```

Result:

```text
active_window_after_1s=0x4e00004
focus_window_after_1s=waydaw terminal
active_window_after_5s=0x4e00004
focus_window_after_5s=waydaw terminal
blocker_focused_after_activation=no
focus_remained_stable=no
ableton_process_alive_after=yes
capture_after_activation=yes
working_prefix_mutated=no
authorization_control_activated=no
```

The dialog remained visible and visually unchanged, and Ableton remained alive.
KWin did not make it active and Wine/Ableton did not take focus in response to
the activation request. This is stronger evidence for a focus activation or
`WM_TAKE_FOCUS` delivery failure than for mouse click delivery failure. The
remaining WebView2 process is a pre-existing GPU process with no mapped WebView
window, so WebView embedding does not own this focus failure.

Next diagnostic: inspect KWin focus-stealing prevention state and X11 client
messages around `_NET_ACTIVE_WINDOW`/`WM_TAKE_FOCUS`. Do not click or automate
authorization controls.

## KWin and Wine WM_TAKE_FOCUS Audit

Run: `working-prefix-kwin-wm-take-focus-audit-1` (2026-06-25)

The existing live session was reused. No launch, click, keyboard input, registry
write, KWin change, or authorization action occurred.

KWin read-only policy:

```text
focusPolicy=ClickToFocus
focusStealingPreventionLevel=1
separateScreenFocus=true
nextFocusPrefersMouse=false
```

One KWin rule matches the Ableton main window. It contains only
`noborderrule=3`; it has no focus, activation, or focus-stealing override.

Both Ableton windows use the same focus model:

```text
blocker_accepts_focus_hint=no
parent_accepts_focus_hint=no
blocker_wm_protocols=WM_DELETE_WINDOW,_NET_WM_PING,WM_TAKE_FOCUS
parent_wm_protocols=WM_DELETE_WINDOW,_NET_WM_PING,WM_TAKE_FOCUS
```

The dialog allows move, minimize, shade, fullscreen, desktop change, and close.
The parent allows move, resize, minimize, maximize, fullscreen, and desktop
change. Neither window advertises direct input focus acceptance.

Exactly one parent activation request was issued:

```text
wmctrl -ia 0x07000003
```

Result:

```text
active_window_before=0x4e00004
focus_window_before=waydaw terminal
active_window_after_parent_1s=0x4e00004
focus_window_after_parent_1s=waydaw terminal
active_window_after_parent_5s=0x4e00004
focus_window_after_parent_5s=waydaw terminal
parent_focused_after_activation=no
blocker_focused_after_activation=no
ableton_process_alive_after=yes
capture_after_parent_activation=yes
authorization_control_activated=no
working_prefix_mutated=no
```

The dialog remained visible and unchanged. Global KWin focus prevention is low,
and the matching Ableton rule does not control focus. Both direct dialog
activation and parent activation have now failed identically. The remaining
focus-specific failure surface is the `_NET_ACTIVE_WINDOW` to Wine
`WM_TAKE_FOCUS` client-message path, not an obvious configured KWin exception.

Next diagnostic should trace X11 focus/client-message events for one activation
request or inspect Wine's X11 focus handling. Do not change KWin policy yet and
do not interact with authorization controls.

## UI-Thread Liveness Diagnostic — ROOT CAUSE CANDIDATE FOUND (2026-07-03/04)

Run: `bin/ableton-auth-liveness-probe`
(`logs/ableton-auth-liveness-probe/20260703-231014/`). Read-only; working
prefix launched via the diagnostic launcher mode; no clicks, no mutation.
Full analysis: `docs/ableton-authorization-interaction-rethink.md`
("Diagnostic result" section).

```text
UI_THREAD_LIVENESS_1:
notepad_control=same input=False + WM_TAKE_FOCUS hints as Ableton (standard Wine)
notepad_wmctrl_activation=no  -> wmctrl activation unreliable session-wide
prior_focus_activation_failures=measurement artifact, not Ableton/Wine defect
kwin_activated_ableton_dialog_on_map_and_fallback=yes
main_thread_startup_phase=nested WINPROC re-entrancy spin, ~94% CPU, timeGetTime polling
main_thread_end_state=RtlAcquireSRWLockExclusive(0xB34E90) from d3d11 (DXVK debug 2.7)
end_state_persistence=identical across 10 samples over ~6h; thread CPU now 0
srw_lock_word=owners=0x0003 exclusive_waiters=0x0001 (leaked shared owners)
collateral=thread 0188 wedged in SendMessageW to the dead UI thread
webview2_alive_this_session=yes (deadlock is WebView2-independent)
verdict=UI thread permanently deadlocked in d3d11/DXVK SRW lock under wine-staging 11.0
retired_as_blockers=KWin focus, Wine WM_TAKE_FOCUS, WebView2 ownership, geometry, virtual desktop
next=reversible DXVK-version A/B (official 2.7.1) WITH thread-stack capture
working_prefix_touched=no (probe); Ableton left running deadlocked, pid 176090
```
