# Proton-exp manual hand-resize re-enters the storm (2026-07-07)

Follow-up to `docs/ableton-proton-exp-message-pump-starvation.md`, which fixed
the startup storm (placement clamp) and hardened the runtime
vertical-maximize path (KWin intercept-and-clear guard). That note explicitly
flagged one residual: *"vertical-maximize (or a manual full-height resize) can
still reach the divergent state."* This session captured a **live** session in
which the user manually resized the window by hand — and the residual is real.

**Verdict: the manual hand-resize to (near) full workarea height re-entered the
UI-thread message-pump starvation storm. The KWin guard did NOT fire and did
NOT prevent it, because a plain edge-drag resize never sets `maximizeMode`
vertical / fullscreen — the only conditions the shipped guard intercepts. The
window remained non-interactable (File menu would not open). No fix applied;
this is diagnosis only, with a proposed fix direction below awaiting approval.**

## Live capture (before any perturbation or cleanup)

The user's own session was already running and was captured immediately. It was
a copied Proton-exp prefix session (`ableton12-winebase-protonexp-test`),
Ableton unix PID `266306`, started 14:21:44; launched via the runner path
(controller loaded, `steamuser` `Preferences.cfg` height was already clamped to
`1000` — the startup fix was in effect). Demo mode (unauthorized), **not** the
auth dialog: the editor shell renders with "Saving and exporting are
deactivated"; a "Report a Crash" help panel from a prior cleanup was also
present. No auth dialog, no credential surface touched.

| datum | value |
|---|---|
| window id | `0x09000003` |
| geometry | **165,28 1055×1052** (hand-resized; startup was 832×966) |
| height 1052 | **= full workarea height** (1080 − 28 titlebar) |
| `_NET_WM_STATE` | **empty** — NOT `_MAXIMIZED_VERT`, NOT fullscreen |
| `_NET_FRAME_EXTENTS` | `0,0,28,0` (decorated, controller pin holding) |
| `_MOTIF_WM_HINTS` | `0x3,0x3e,0x7a,0x0,0x0` |
| `WM_NORMAL_HINTS` | program-specified location 169,58; static gravity; no min/max clamp |
| `WM_STATE` | Normal |
| main UI thread CPU | **248–285 ticks/3s (~83–95% of a core)**, ~493/6s — spinning |
| hottest thread | the **main thread** (266306); audio threads sum to ~30% — not the audio engine |
| X-level geometry | **stable** 1055×1052 across 40×100 ms samples (0 ConfigureNotify) |
| controller | `loaded=true` |
| KWin `undo vertical-maximize` events | **0** — the guard never fired |
| KWin `re-pin` events | 1997 over ~8 min (~4/s) — the known decoration-flicker churn |
| placement clamp on launch | in effect (cfg height 1000) — startup fix was NOT the failure |

**Interactability test (demo mode, safe — no auth dialog):** window activated
(`xdotool windowactivate --sync`), then a left click at the File-menu location.
**No dropdown opened** (0 File-menu popup windows; screenshot shows the menu bar
with no menu). During the earlier calm acceptance run the identical click opened
the full File dropdown. So posted input is being starved — the storm's
signature symptom.

**Rendering / white bars:** content fills the window; the known **~18px white
top strip persists** (client `y=0..17` pure white `255`, content `129` from
`y=18`) — it did **not** grow into large bars at the larger size, consistent
with a fixed top inset rather than a proportional swapchain scaling error. No
new large white/black bands appeared. The two window-pixmap captures taken
seconds apart showed different Live layouts (crash panel vs Session view),
i.e. the UI is being actively (and wastefully) re-laid-out under the storm.

## Classification

- **Full-height / vertical-maximized?** Full-height **yes** (1052 = full
  workarea), vertical-maximized (WM sense) **no** (`_NET_WM_STATE` empty,
  `maximizeMode` 0). This is the crux.
- **KWin guard fire?** No (0 events).
- **Guard prevent a storm?** No — it never triggered.
- **Storming anyway?** **Yes** — main thread ~83–95%, X-geometry stable
  (Wine-internal storm, exactly the documented signature: the client rect
  churns while the outer X rect is pinned and emits no ConfigureNotify).
- **Remained interactable?** **No** — File menu would not open.
- **White bars / content mismatch reappear?** Only the pre-existing ~18px top
  strip; no new mismatch.
- **Frame-only, or render surface too?** The X frame geometry is stable; the
  storm is the internal window/client-rect reconciliation loop (same as the
  original diagnosis). Swapchain delta not re-measured (DXVK presenter logging
  off at default verbosity).
- **Different from the prior synthetic `xdotool windowsize … 1052` test?**
  **Yes, materially.** The hardening note recorded that a synthetic
  `xdotool windowsize 1052` (no `maximizeMode`) "goes 1052 but stays calm
  (~5% CPU)". The **real hand-resize** to full height instead **storms**
  (~90%). The synthetic single-shot geometry write did not reproduce what a
  user's interactive edge-drag does — likely because an interactive resize
  delivers a stream of incremental `WM_WINDOWPOSCHANGING`/`WM_SIZING` steps
  that walk the window into the same unsatisfiable full-height client belief
  the startup storm had, whereas one atomic `windowsize` did not. This is why
  the synthetic tests under-reported the risk.

## Root cause (consistent with the original model)

The storm trigger is the window reaching the grantable full height, where
Wine's client-rect belief (~1096) diverges from the actual grant (1052) and
Ableton's `WM_WINDOWPOSCHANGED` handler loops trying to reconcile them. The
startup clamp prevents the window from being *born* there; the KWin guard
prevents *WM-driven vertical-maximize* from taking it there. Neither covers a
**user edge-drag** that walks the frame to full height with `maximizeMode`
never leaving 0 — so that path still reaches the divergent state. The shipped
`guardMaximize()` only checks `maximizeMode & 1` and `fullScreen`; it has no
raw full-height check, so it is blind to this case.

## Proposed fix direction (NOT implemented — needs approval)

The gap is specific and the cause is clear, but the fix is **not** a trivial
one-liner, so it is deferred for design review rather than applied:

1. **Extend the KWin guard with a raw full-height cap (preferred, but needs
   care).** In `config/kwin/waydaw-ableton-decoration.js`, add to the
   `frameGeometryChanged` path a check for `frameGeometry.height >=
   (grantable full height − small margin)` even when `maximizeMode` is 0, and
   cap the height back to a safe sub-screen value. **Risk:** the hardening note
   already found that *restoring geometry after* the window reaches full height
   is harmful (the storm is self-sustaining app-side once formed, and writing
   `frameGeometry` back just fights Ableton at ~3/s). So this must **prevent**,
   i.e. cap the height mid-drag *before* Ableton latches the full-height
   configure — which for an interactive edge-drag means catching the first
   frameGeometryChanged that crosses the threshold and clamping in the same
   synchronous handler. Whether KWin delivers that early enough to prevent
   (rather than merely fight) needs a measured prototype.
2. **Constrain the max height via `WM_NORMAL_HINTS` max-size** so the WM refuses
   to resize the window beyond a safe height. Ableton does not set a max-size
   hint (`WM_NORMAL_HINTS` shows none). A KWin-side or wrapper-side max-height
   would stop the drag at the OS level. `maxSize` is read-only in KWin
   scripting (per the hardening probe), so this would need another mechanism.
3. **App-scoped message shim / recursion breaker** — most invasive; only if
   (1) and (2) fail. Own design review.

No option involves authorization, working-prefix mutation, Wine virtual
desktop, or Ableton binary patching.

## Exact commands run (live capture, read-only until cleanup)

- Detection: `pgrep -af 'protonexp-test|msedgewebview|wineserver|winedevice'`
- Process/thread CPU: `/proc/266306/stat` + per-`task/*/stat` tick deltas over
  3–6 s; `ps -o …`
- Window state: `wmctrl -lG`; `xprop -id 0x09000003 _NET_WM_STATE
  _NET_FRAME_EXTENTS _MOTIF_WM_HINTS WM_NORMAL_HINTS WM_STATE`;
  `xwininfo -id 0x09000003`
- Geometry stability: 40× `xdotool getwindowgeometry` at 100 ms
- Controller: `bin/ableton-kwin-decoration-controller --status`;
  `journalctl --user -b | grep waydaw-ableton-decoration`
- Interactability: `xdotool windowactivate --sync` + single left click at the
  File-menu location; `import -window` screenshots (no package installs)
- Top strip: `import -window 0x09000003 -crop 1055x40+0+0` + PIL pixel probe
- Cleanup (after all evidence saved): `bin/ableton-proton-cleanup`

Raw captures (screenshots, sample logs) live in session scratchpad only.

## Cleanup

After all evidence above was captured, the live session was cleaned with
`bin/ableton-proton-cleanup`: `cleanup_result=clean`, controller
`loaded=false`, zero Proton/Wine/WebView2 processes. No authorization was
attempted; no auth/credential control was clicked (the only click was the
File-menu interactability probe in demo mode). Working prefix never touched;
`kwinrc`/`kwinrulesrc` and working-prefix DXVK hashes verified unchanged.

## Is a fix needed?

**Yes — the interactability fix is incomplete for interactive use.** A user who
hand-resizes the Proton-exp window to (near) full height re-enters the exact
storm the branch set out to eliminate, and the window becomes non-interactable
until killed. The startup clamp and the WM-maximize guard both hold; the open
hole is the **raw full-height edge-drag** path. Recommended next action: build
and measure a prototype of fix direction (1) — a mid-drag full-height cap in
the KWin guard — on a fresh branch, validated the same way as the acceptance
run. Until then, the practical guidance is "do not hand-resize the Proton-exp
window toward full screen height."
