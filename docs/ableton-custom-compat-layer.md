# Ableton custom compatibility layer

This document records the first custom compatibility-layer path for Ableton Live
12 Suite under Wine. It is instrumentation and reversible launch control, not a
Wine/DXVK/WebView2 patch.

## Scope
- Keep the working prefix untouched unless a future test explicitly approves a
  copied-prefix launch.
- Keep the prefix DXVK DLLs active. This matrix is invalid if builtin
  `d3d11`/`dxgi` is forced with `WINEDLLOVERRIDES`.
- Keep DXVK logging observable; never set `DXVK_LOG_LEVEL=none` during
  measurement.
- Do not add `dxvk.conf`, use Wine virtual desktop, change KWin geometry, move
  windows, synthesize clicks, or make permanent launcher changes.
- This matrix is not a `wined3d` test. Prior findings already proved builtin
  `d3d11`/`dxgi` is not viable in the current prefix.
- Prefer environment-only WebView2 controls.
- Probe cursor/input behavior before forcing anything.

## WebView2 mode tool

`bin/ableton-webview2-mode` prints exact shell exports for WebView2 launch modes:

```bash
bin/ableton-webview2-mode --print-env default
bin/ableton-webview2-mode --print-env disable-gpu
bin/ableton-webview2-mode --print-env disable-gpu-no-sandbox
bin/ableton-webview2-mode --print-env isolated-user-data
bin/ableton-webview2-mode --explain disable-gpu
bin/ableton-webview2-mode --restore-info
```

Modes:
- `default`: unsets WebView2 env vars for baseline behavior.
- `disable-gpu`: sets `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--disable-gpu'`.
- `disable-gpu-no-sandbox`: adds no-sandbox flags to separate GPU failure from
  process/sandbox integration.
- `isolated-user-data`: sets `WEBVIEW2_USER_DATA_FOLDER` outside the prefix, in
  runtime/tmp storage.
- `disabled-runtime`: documented only. The prior reversible runtime rename test
  is already recorded and restored; this tool does not rename or delete files.

Restore for environment modes:

```bash
unset WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS WEBVIEW2_USER_DATA_FOLDER WEBVIEW2_BROWSER_EXECUTABLE_FOLDER
```

## Cursor guard

`bin/ableton-cursor-guard` is an X11/XWayland probe for the longstanding
disappearing cursor over the Ableton main editor window.

Probe-only commands:

```bash
bin/ableton-cursor-guard --dry-run
bin/ableton-cursor-guard --probe-only
```

Watch mode:

```bash
bin/ableton-cursor-guard --watch --log logs/ableton-cursor-guard.log
```

Optional scoped cursor forcing requires a local helper:

```bash
tools/build-ableton-x11-cursor-define
bin/ableton-cursor-guard --watch --force-visible --log logs/ableton-cursor-guard.log
```

The helper calls `XDefineCursor` only on the detected Ableton top-level window.
On exit, the guard calls `XUndefineCursor` for the same window. It does not
change the desktop cursor theme and does not install anything system-wide.

Cursor-helper prerequisite status:

```text
libX11-devel=installed
dependencies_installed=libXau-devel libxcb-devel xorg-x11-proto-devel
cursor_helper_built=yes
helper=tools/ableton-x11-cursor-define
```

Required output fields:

```text
cursor_guard_active=
ableton_window_id=
pointer_inside_ableton=
cursor_visibility_action=
errors=
```

## Harness integration

`bin/ableton-runner-test` accepts:

```text
--webview2-mode default|disable-gpu|disable-gpu-no-sandbox|isolated-user-data
--cursor-guard off|on
```

Matrix status:

```text
A: webview2_mode=default     cursor_guard=off  DONE_FAILED
B: webview2_mode=disable-gpu cursor_guard=off  DONE_FAILED
C: webview2_mode=default     cursor_guard=on   DONE_FAILED
D: webview2_mode=disable-gpu cursor_guard=on
```

Run the matrix only after explicit approval. Use a copied prefix via the runner
harness. The working prefix remains untouched. DXVK must remain active from the
copied prefix; do not force builtin `d3d11`/`dxgi` and do not set
`WAYDAW_ABLETON_GRAPHICS=wined3d`.

## Cell A result

Run: `logs/ableton-runner-tests/20260619-161121-matrix-a-default-off/result.env`

Cell A used the corrected baseline: system Wine `wine-11.0 (Staging)`, copied
prefix, `webview2_mode=default`, `cursor_guard=off`, and DXVK active.

Deterministic fields: `ableton_launched=yes`, `window_detected=yes`,
`backend_effective=dxvk`, `recreating_swapchain_count=28`,
`webview2_process_count=5`, `webview2_crash=yes`, `kprior_crash=yes`.

User observation: `main_editor_interactable=no`,
`mouse_disappears_over_main_editor=inconclusive/eventually_no`,
`crash_on_interaction=yes`, `start_screen_webview2_crash=yes`,
`flicker=same_then_stops_after_minutes`, `responsiveness=worse_or_no`.

Interpretation: Cell A failed. It is not a usability improvement; the corrected
baseline still leaves the main editor unusable and interaction can crash.

## Cell B result

Run: `logs/ableton-runner-tests/20260619-162117-matrix-b-disablegpu-off/result.env`

Cell B used system Wine `wine-11.0 (Staging)`, copied prefix,
`webview2_mode=disable-gpu`, `cursor_guard=off`, and DXVK active.

Deterministic fields: `ableton_launched=yes`, `window_detected=yes`,
`backend_effective=dxvk`, `recreating_swapchain_count=83`,
`webview2_process_count=0`, `webview2_crash=yes`, `kprior_crash=yes`.

User observation: `main_editor_interactable=no`,
`mouse_disappears_over_main_editor=inconclusive/eventually_no`,
`crash_on_interaction=yes`, `start_screen_webview2_crash=yes`,
`flicker=same_then_stops_after_minutes`, `responsiveness=worse_or_no`.

Interpretation: Cell B failed. `webview2_mode=disable-gpu` is not a usability
fix and did not improve over Cell A. Do not treat `webview2_process_count=0` as
success because the app remained unusable and crash markers persisted.

## Cell C result

Run: `logs/ableton-runner-tests/20260619-163939-matrix-c-default-cursorguard/result.env`

Cell C used system Wine `wine-11.0 (Staging)`, copied prefix,
`webview2_mode=default`, `cursor_guard=on`, and DXVK active.

Cursor guard was active and helper-backed:
`cursor_guard_pid=466958`,
`cursor_visibility_action=defined_left_ptr_on_ableton_window`, `errors=none`.

Deterministic fields: `ableton_launched=yes`, `window_detected=yes`,
`backend_effective=dxvk`, `recreating_swapchain_count=26`,
`webview2_process_count=5`, `webview2_crash=yes`, `kprior_crash=yes`.

User observation: `main_editor_interactable=no`,
`mouse_disappears_over_main_editor=inconclusive/not_primary_signal`,
`crash_on_interaction=yes_or_same_as_A_B`,
`start_screen_webview2_crash=yes_but_startup_window_resolved_a_little_faster`,
`flicker=same_or_not_fully_observed`, `responsiveness=worse_or_no`,
`cursor_visibly_improved=no_functional_improvement`.

Interpretation: Cell C failed. The cursor guard successfully applied a visible
cursor to the Ableton top-level window, but this did not meaningfully improve
usability. The startup window resolved a little faster, but the main editor was
still not usable.

## Matrix status so far

A: failed — default WebView2, cursor guard off.
B: failed — disable-gpu WebView2, cursor guard off.
C: failed — default WebView2, cursor guard on.

Conclusion so far: Neither WebView2 `--disable-gpu` nor the X11 cursor guard is
a meaningful usability fix under system Wine 11.0 Staging with the copied prefix
and DXVK active.

Stop condition: do not continue the local shim matrix unless Cell D is explicitly
requested for formal closure. The working conclusion is that the failure is
deeper than WebView2 `--disable-gpu` and the X11 cursor guard. Next work moves to
runner-base comparison; see `docs/ableton-runner-candidate-plan.md`.
