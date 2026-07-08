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

---

# Prototype: KWin manual-height cap (fix/proton-manual-resize-cap, 2026-07-07)

Fix direction (1) was prototyped and measured with a real user hand-resize.

**Verdict: the mechanical hook works, but the design is incomplete and NOT
merge-ready. The cap keeps the window at a safe height, and the first
full-height episode decayed to calm after ~40 s — but Ableton latched a
full-height placement belief in runtime memory anyway, and a later NORMAL
user width resize re-triggered a full-height re-assert fight that ran for
18+ minutes with no decay, main UI thread at ~80 %, File menu dead. This is
diagnosis, not acceptance.**

## Guard design (as prototyped)

Guard 3 in `config/kwin/waydaw-ableton-decoration.js`: on every
`frameGeometryChanged` of the target window (same triple scope guard), if the
window is not vertically maximized and not fullscreen and
`frameGeometry.height > workspace.clientArea(KWin.MaximizeArea, w).height − 80`
(cap = frame 1000 on the 1080-high workarea, just above the calm startup frame
of 994), clamp the height back to the cap in the same synchronous handler,
preserving x/y/width. Logs rate-limited to 1/s; the clamp itself always runs;
re-entrancy no-ops because the re-fired event is at the cap.

Threshold tradeoff: heights up to frame 1000 resize normally; a drag past it
rubber-bands at the cap. Margin 80 chosen so the cap clears the calm startup
geometry by only 6 px yet sits 80 px below the danger zone.

Mechanism was pre-validated in live kwin_x11 6.7.1 against a scratch
`xmessage` window with a scratch script: `KWin.MaximizeArea` resolves,
mutate-and-assign `frameGeometry` write takes in one synchronous clamp
(728 → 480 in the test), and the re-fired signal does not loop.

## Live validation timeline (copied Proton-exp prefix, stock 1096 seed restored)

| time | event |
|---|---|
| 17:41 | launch via `bin/ableton-proton`; clamp `1096→1000` fired; startup 832×966 @169,58; `_NET_WM_STATE` empty; main thread 15 ticks/3 s (~5 %); controller loaded |
| 17:56:26–17:57:06 | **user hand-drag toward full height**: guard fired 166 times (~4/s), every event clamping `840×1080+165+0 → h=1000`; main thread stayed calm (18 ticks/3 s) DURING the fight; window never rested at full height |
| 17:57–18:00 | quiet: zero guard events, 17 ticks/3 s, window 964×972 (user had also widened by hand) — first fight **decayed** |
| ~18:00–18:01 | **user widened the window a little (real resize)** + assistant synthetic move/resize probes; full-height re-asserts resumed: `964×1080+300+0` at ~4–5/s |
| 18:01–18:19+ | sustained fight, **no decay**: ~300 guard events/min, cap-write counter #3260 by 18:13, main thread 479–485 ticks/6 s (~80 %), re-pin churn ~4/s |
| 18:14 | File-menu probe (demo mode, editor rendering): click exactly on File — **no dropdown** (input starved; storm signature) |
| 18:19 | still ~5 events/s, 326 ticks/4 s (~81 %); session cleaned up |

## Where the full-height request comes from (the user's five questions)

1. **`Preferences.cfg` does NOT change after the cap fires.** mtime stayed at
   17:41:21 (the launch clamp write) through the entire session; the
   MainWindowPlacement record still read `840×1000`, bools non-maximized. The
   belief is runtime-only, nothing is persisted mid-session.
2. **The requested size is runtime placement memory, not persisted state and
   not KWin feedback.** Fight 1 requested `840×1080@165,0` — stored x/width
   (cfg says 165/840) combined with FULL workarea height (client 1052, which
   the cfg never contained). Fight 2, after the user's width resize, requested
   `964×1080@300,0` — the CURRENT x/width with the same full height. Width
   tracks live geometry while height stays pinned at full-workarea, so the
   height comes from an in-memory "desired client height ≈ 1052" latched
   during the drag episode. If it were KWin feedback it would request the
   granted 1000; if it were the cfg it would request 1000.
3. **Yes — the cap corrects the frame but not Wine/Ableton's belief.** On X11,
   `frameGeometryChanged` fires after KWin has already applied the geometry,
   so Wine received a momentary full-height configure before the clamp wrote
   it back. That instant was enough to latch. From then on the loop is:
   app requests full height → KWin applies → guard clamps → Wine reports the
   972 client grant → Ableton's WM_WINDOWPOSCHANGED handler re-requests full
   height (~4–5/s). X-level geometry looks stable at 964×972 the whole time.
4. **A safer fix must prevent the first full-height configure from ever being
   applied, and no KWin-script lever can do that for app/drag-initiated
   geometry on X11.** Post-apply clamping (this prototype) is too late.
   `maxSize` is read-only in KWin scripting. An external `WM_NORMAL_HINTS`
   PMaxSize would be honored by KWin pre-apply, but Wine rewrites
   WM_NORMAL_HINTS at runtime (the program-specified location updated
   169,58 → 304,58 during this session), re-creating the two-writer property
   race that made churn worse before. Lowering the cap threshold does not
   help: no cap events fired between 1001 and 1079 during the drag — the
   first over-threshold event was already the app's own 1080 re-assert, so a
   lower threshold intercepts nothing earlier. Correcting the copied-prefix
   placement seed is already done (and confirmed intact); the latch is
   in-memory. Remaining directions: a KWin window RULE with forced maximum
   size (persistent-settings tradeoff — currently out of bounds), or the
   app-scoped message shim (fix direction 3, most invasive).
5. **The app does NOT remain interactable after the second user width resize.**
   There was no quiet period after it — the fight ran 18+ minutes without
   decay, and the File menu did not open (probe at 18:14; screenshots saved in
   session scratchpad). Escape had nothing to close.

## Classification

- **Mechanical hook: works.** The guard fires on the raw-height path that the
  shipped guard 2 is blind to, clamps synchronously, never lets the window
  rest at full height, and its own writes do not loop.
- **Storm becomes bounded/transient in SOME cases.** The initial drag episode
  self-terminated after ~40 s with the main thread calm throughout — strictly
  better than the unguarded permanent storm. But the latched belief survives
  the quiet period, and any later geometry perturbation (including a normal
  width resize) re-enters the fight, which then does NOT decay.
- **Not merge-ready.** Failure criterion "guard fights repeatedly and causes
  high CPU" was hit in fight 2 (the CPU is the app-side storm, but the
  sustained ~5/s clamp fight is real).
- **Design incomplete** until a normal follow-up user resize no longer
  re-triggers the full-height fight — i.e., until the full-height configure
  can be rejected BEFORE application, or the latched belief can be corrected.

Synthetic-resize insufficiency is re-confirmed from the other side: the storm
signature only appeared with real interactive resizing; the mechanism test and
the earlier one-shot `xdotool windowsize` stayed calm.

Not re-tested this session: guard 2 (vertical-maximize intercept) — no
maximize was requested; zero `undo vertical-maximize` events, as expected.

## Session hygiene

No authorization attempted; no credentials; the only clicks were the demo-mode
File-menu probes (the auth dialog — `_NET_WM_WINDOW_TYPE_DIALOG`, excluded
from the guard by `normalWindow` — was never touched). Cleanup:
`cleanup_result=clean`, controller `loaded=false`, zero
Ableton/Wine/Proton/WebView2 processes. Working-prefix DXVK hashes verified
unchanged (sha256 -c OK ×8); `kwinrc`/`kwinrulesrc` hashes byte-identical
before/after. Copied test prefix only; its `Preferences.cfg` was deliberately
re-seeded to the stock bad 1096 before launch (from `.bak-normalize`) so the
launch exercised the clamp.
