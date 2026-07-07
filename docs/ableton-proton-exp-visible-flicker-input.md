# Proton-exp reopened: visible flicker + non-interactability (2026-07-07)

The previous closeout (flicker "solved", interactability "not a WM-level
issue") was **incomplete**. User-observed reality on the Proton-exp path:

- flicker is **gone** (controller works — user-confirmed),
- but the window is **not interactable and cannot be closed**, and
- a **new geometry defect**: white bars inside the window frame; the
  content does not fill the window's content area.

This note captures the missing data with a live reproduction, a real
input-delivery test (not just focus), pixel-level geometry measurement, and
a controller on/off (A/B) comparison. Branch:
`diagnosis/proton-exp-visible-flicker-input` from `main @ 8e35b12`. Copied
prefix only; no authorization; no auth/license buttons clicked; no text
entered. Working prefix, `kwinrc`, `kwinrulesrc`, and working-prefix DXVK
hashes all verified unchanged before/after.

## Session facts

- X11 session, `kwin_x11 6.7.1`, compositor active.
- Screen `2560x1080` @ 59.98 Hz, workarea `0,0 2560,1080` (ultrawide).
- A **live Proton-exp session was already running** at investigation start
  (the user's own "tried again with proton-exp" run, copied prefix) — used
  directly as the reproduction. A separate controller-off run (B) followed.

## Finding 1 — Flicker on Proton-exp: RESOLVED (confirmed)

User confirms no flicker with the integrated controller. In the live
session the frame was a stable 28px decorated titlebar; controller
`loaded=true`. With the controller **off** (B) the bursty frameless state
(`_NET_FRAME_EXTENTS=0`, `_MOTIF_WM_HINTS=0x0`) reappears intermittently.
Flicker is a solved, controller-dependent item. Not the remaining problem.

## Finding 2 — Non-interactability / cannot close: REAL BUG, controller-independent

The prior diagnosis tested only focus/activation. This time, **real pointer
input and a real close request** were exercised.

WM-level input **works** (both windows, controller on and off):

- Real-pointer titlebar drag moved the main window `37,74 → 237,74`.
- Real-pointer titlebar drag moved the auth dialog `249,339 → 449,339`.
- Activation/focus land correctly; the auth dialog holds `_NET_WM_STATE_FOCUSED`.

App-level input and close are **ignored**:

- `wmctrl -c` (WM_DELETE_WINDOW) on the main window was **ignored for 90+
  seconds** — window stays mapped, PID alive — in **both** the live session
  (controller on) and run B (controller off).

Why (root cause), from `bin/ableton-thread-endstate-capture` in both runs:

```
main_thread_forward_progress = executing        (top frames change across samples)
main_thread_in_srw_exclusive = no               (NOT the old wine-staging deadlock)
threads_in_sendmessage       = (none)
main_thread_in_message_wait   = no      <-- KEY
main_thread_cpu_ticks_per_3s ≈ 350–370  (~117–123% of one core)  <-- KEY
top frames: win32u / ableton live 12 suite (x3)
```

The UI thread is **alive and busy-looping, but not sitting in a message
wait** — i.e. it is **not pumping the Windows message queue**. A Win32 app
that does not call GetMessage/DispatchMessage cannot process content clicks,
menu opens, or WM_DELETE_WINDOW; those events queue and are never
dispatched. Titlebar drag still works because KWin performs it
compositor-side without the app. This is precisely the "alive, focused, and
still practically unusable" case the reopen brief warned against — the
earlier "liveness healthy → fine" conclusion conflated *executing* with
*pumping messages*.

The busy-loop is the **same unauthorized-state loop** documented as the
flicker driver (~115% CPU, constant re-management while unauthorized). It is
persistent, not intermittent (close ignored across 90 s continuous).

**Controller is NOT implicated:** identical non-interactability with the
controller off (B). The KWin controller only flips `noBorder`; it has no
path to the app's message pump.

Classification (non-interactability): **stale/unresponsive UI despite
liveness — the app does not service its message queue while in the
unauthorized busy-loop.** Not a modal-block-only situation (WM_DELETE to the
top-level is also dropped), not a WM/focus/pointer problem, not a controller
regression, not the old SRW deadlock.

Caveat / missing data: whether the auth **dialog** itself ever accepts a
real click was NOT tested (no auth/license clicks allowed). The 2026-07-04
note claimed the dialog accepted clicks; that may have been during an early
pump window before the tight loop, or optimistic. Given the same thread
owns the dialog and is not pumping, the dialog's own responsiveness is in
doubt and must be verified (see next steps).

## Finding 3 — White bars / content not filling frame: REAL BUG, controller-independent

Hard measurement, live session (controller on), window `0x08c00003`:

- Window client area: **1153 × 1052** (grew from the seed during the session).
- DXVK swapchain buffer: **848 × 1096** (from the DXVK presenter log).
- Captured window pixmap: **1153 × 1006** (46 px shorter than client height).
- Pixel scan of the client area:
  - **top edge**: pure white `srgb(255,255,255)` for `y = 0..~12`, content
    (grey `165`) from `y≈20`.
  - **right edge**: content to `x≈1140`, then white `255` for `x≈1145..1150`,
    window border black at `x=1152`.

Run B (controller off): window client **848 × 1052**, swapchain **848 ×
1096** — width now matches (848=848), height still mismatched (1096 vs 1052).

Interpretation: the **DXVK/Ableton presentation surface is a fixed 848×1096
that does not track the X window client size.** When Ableton's window equals
848 wide the width fills; when the window is a different size (1153 wide in
the live session) the surface no longer covers the frame, leaving unpainted
white margins (top ~12 px, right ~10 px) and a ~44 px height mismatch
throughout. The window size itself drifts between runs (848 vs 1153) because
Ableton rewrites the seeded `steamuser` `Preferences.cfg` placement on exit.

Classification (flicker/geometry): **graphics/DXVK presentation flicker →
here, a swapchain-vs-window-rect size mismatch (unpainted margins)**, not
frame-extents/Motif churn, not window recreation, not compositor redraw.
Controller-independent (present with controller off).

## A/B result summary

| dimension | A: controller on (live) | B: controller off |
|---|---|---|
| flicker / decoration | stable 28px titlebar | bursty frameless returns |
| titlebar drag (real pointer) | moves | moves |
| WM_DELETE / close | **ignored 90+ s** | **ignored 90+ s** |
| UI thread | executing, `message_wait=no`, ~123% CPU | executing, `message_wait=no`, ~117% CPU |
| swapchain vs window | 848×1096 vs 1153×1052 (mismatch, white bars) | 848×1096 vs 848×1052 (height mismatch) |

A "C" run (manual pre-load of the controller) was **not** run: it targets
flicker *timing*, and flicker is already resolved and confirmed
controller-dependent; the two remaining defects are both controller-
independent, so C adds nothing to this assessment.

## Acceptance decision

**Current `main` is NOT acceptable for the presentation/interactability
phase.** Two real, controller-independent defects remain:

1. The window is not interactable and will not close while unauthorized
   (message queue not pumped).
2. The rendered content does not fill the window frame (swapchain/window
   size mismatch → white margins).

Flicker is resolved; the KWin controller stands and is not implicated in
either remaining defect. Do **not** mark the phase complete on liveness +
focus + flicker alone.

## A fix is needed — proposed next steps (diagnosis only; NOT implemented)

No fix implemented. Proposed next diagnostics, in priority order (user
prioritized interactability):

1. **Interactability (priority).** Establish *what* the UI thread spins on:
   a full winedbg backtrace of the busy TID (not just top 4 frames) across
   several samples, and correlate with WebView2 activity (the auth dialog is
   the WebView2 "Authorize with ableton.com" surface — a spinning/ retrying
   WebView2 is a prime suspect for pegging the UI thread and starving the
   pump). Then a **user-assisted, non-authorizing** responsiveness test:
   with the harness recording, the user attempts one benign dialog
   interaction (e.g. hover/drag within the dialog, or press Esc) to
   determine whether the dialog's own message loop is alive while the main
   window's is starved. Decision fork: if even the dialog is dead → the
   unauthorized loop must be tamed (investigate the WebView2/auth spin); if
   only the main window is blocked (dialog live) → it is app-modal and the
   real ask is reliable dialog discoverability, not a code fix.

2. **White bars.** Determine why the DXVK swapchain is pinned at 848×1096
   and does not recreate on window resize (VK_PRESENT_MODE_IMMEDIATE +
   Wine/Proton window-resize → swapchain-recreate path). Test whether
   constraining the window to the swapchain size (fixed non-resizable
   placement matching the render surface) or forcing swapchain recreation
   removes the margins. Likely a Proton/DXVK-under-Wine surface-sync issue,
   copied-prefix or runner-scoped; no working-prefix or virtual-desktop
   involvement.

Both are design/diagnosis directions only — do not implement without
explicit approval, per the reopen constraints.

## Hygiene

Ableton was launched/observed (one pre-existing live session + one B run),
copied prefix only. No authorization attempted; no Authorize/"Authorize
later"/license buttons clicked; no credentials entered. Real pointer input
limited to: titlebar drags of the main window and auth dialog (both moved
back to no lasting effect via cleanup), and WM_DELETE_WINDOW close requests
(ignored by the app). Both sessions cleaned (`cleanup_result=clean`,
controller `loaded=false`, zero processes). Working prefix untouched;
`kwinrc`/`kwinrulesrc`/working-prefix DXVK hashes verified unchanged.
Stale working-prefix Wine skeleton from an unrelated earlier default-
launcher run was terminated with user authorization (no Ableton.exe was in
it).
