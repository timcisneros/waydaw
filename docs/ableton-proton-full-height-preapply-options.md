# Preventing the full-height configure pre-apply: design options (2026-07-07)

Design-only follow-up to `docs/ableton-proton-manual-resize.md`. The KWin
post-apply cap prototype (`fix/proton-manual-resize-cap @ d3954b6`) proved the
hook mechanically works but is architecturally too late; the branch is kept as
evidence and is NOT merged. This note evaluates the remaining fix directions
and recommends one. **Nothing here is implemented.** No session was launched
for this note; every probe below was read-only against the copied prefix, the
running KWin, and the repository.

## Why the KWin post-apply cap is insufficient

On X11, a KWin script's `frameGeometryChanged` fires **after** KWin has
already applied the geometry (the `XConfigureWindow` has happened). Wine
therefore receives the full-height configure for an instant before the clamp
writes it back, and that instant is enough for Ableton to latch a
"desired client height = full workarea (1052)" belief in runtime memory.
Measured consequences (2026-07-07 session): the belief survives quiet
periods, is not persisted (`Preferences.cfg` mtime and content unchanged all
session), and any later geometry perturbation — including a **normal user
width resize** — re-enters a clamp/re-assert fight (~5/s) that ran 18+
minutes without decay, main UI thread ~80 %, File menu dead. Post-apply
clamping bounds the *geometry* but cannot bound the *belief*.

## Why lowering the cap threshold does not solve it

During the real hand-drag, **no cap events fired between frame 1001 and
1079**. The first over-threshold event was already `840×1080` — the app's own
re-assert of stored x/width with full workarea height. There is no incremental
walk through the 1001–1079 band for a lower threshold to catch earlier; the
first dangerous configure arrives *at* full height, and any script-side
threshold still acts post-apply. Lowering the threshold changes where the
rubber-band sits, not when the app first sees full height.

## Option 1 — KWin forced maximum-size rule

**Mechanism.** KWin exposes no runtime rule interface: `busctl introspect
org.kde.KWin /KWin` shows no RuleBook methods (probed on kwin_x11 6.7.1), so a
rule means writing `~/.config/kwinrulesrc` and calling
`org.kde.KWin.reconfigure`. Unlike scripting (`maxSize` read-only), a rule's
forced maximum size enters KWin's `constrainFrameSize()` path, which is
consulted **before** geometry is applied for both interactive resizes and X11
`ConfigureRequest` handling — i.e., genuinely pre-apply: the WM never grants
above the max, so Wine never sees full height, so the belief never latches.
(This enforcement path is from KWin source reading and must be confirmed live
as validation step 1.)

**App-scoping: yes, with precedent.** `kwinrulesrc` on this machine *already
contains* a WayDAW rule from an earlier phase — `[waydaw-ableton-proton-decoration]`
forcing `noborder=false` with `wmclass=steam_proton` + `titlematch` substring
`Ableton Live 12 Suite`, `types=1` (normal windows only). A max-size rule
would use the identical match triple, so it cannot affect other Proton/Steam
windows or Ableton's auth dialog. The rule value would be
`maxsize=<large-width>,1000` (frame units) with a *force* policy;
`ForceTemporarily` is the better policy for a lifecycle-managed rule — KWin
discards it when the window closes, so even a crashed cleanup leaves no
behavioral residue for future windows.

**Lifecycle management: possible, honest tradeoff.** The runner would: back up
`kwinrulesrc` byte-for-byte → add the rule (`kwriteconfig6`, prior art in the
untracked `bin/install-ableton-kwin-rule`) → `reconfigure` → launch → on
cleanup remove the rule → `reconfigure` → verify the restored file hash. The
residual risk is a hard crash between add and cleanup leaving the rule in the
file; with `ForceTemporarily` the leftover is inert (it only ever matched the
Ableton Proton window and self-expires per-window), and the next cleanup run
can sweep it. But strictly: **this transiently mutates a persistent KWin
settings file, which the current project constraint forbids.** It cannot be
done without explicitly relaxing that constraint to "transient, backed-up,
hash-verified restore, app-scoped".

**Limit.** A rule prevents the *grant*, exactly like the shipped clamp
prevents the *rest state* — but if a belief has already latched (e.g. the rule
is added mid-session after a storm), it cannot unlatch it. Prevention must be
in place from process start. Since the belief is proven non-persistent, a
fresh launch under the rule starts clean.

## Option 2 — external `WM_NORMAL_HINTS` / `PMaxSize`

**Rejected as a standalone external write.** The race is structural, not
incidental: Wine rewrites the *entire* `WM_NORMAL_HINTS` property
(`XSetWMNormalHints` replaces the struct wholesale) whenever it updates window
state — observed this session as the program-specified location changing
`169,58 → 304,58` mid-run. An externally-set `PMaxSize` survives only until
Wine's next rewrite, and the rewrites are driven by exactly the app
`SetWindowPos` activity that precedes the storm — the hint would be gone at
the moment it is needed. There is no stable lifecycle point: hints would need
re-asserting after every Wine write, which is the two-writer property fight
that was already measured to make churn worse (the abandoned xprop guard).

**But note where `PMaxSize` legitimately comes from:** Wine itself publishes
`PMaxSize` when the window has a maximum track size — which Wine obtains from
the app via `WM_GETMINMAXINFO`. If the *app's answer* to `WM_GETMINMAXINFO` is
clamped (option 3), Wine becomes the sole writer of a correct `PMaxSize`, and
option 2's pre-apply WM enforcement happens for free, race-free. Option 3
subsumes option 2.

## Option 3 — app-scoped Wine/Proton message shim

**Exact hook point: `WM_GETMINMAXINFO`, with `WM_WINDOWPOSCHANGING` as
belt-and-braces. Not `WM_WINDOWPOSCHANGED`, not `WM_NCCALCSIZE`.**

Reasoning over the candidate boundaries:

- `WM_GETMINMAXINFO` — the root lever. Windows sizing semantics funnel
  through `MINMAXINFO.ptMaxTrackSize` for thick-frame windows: the
  interactive sizing loop clamps to it, `DefWindowProc`'s
  `WM_WINDOWPOSCHANGING` handling clamps `SetWindowPos` requests to it, and
  Wine's winex11 driver derives the X11 `PMaxSize` hint from it. Answering
  `WM_GETMINMAXINFO` with `ptMaxTrackSize.y = safe height (≈1000)` therefore
  clamps **every** path — app-initiated `SetWindowPos`, drag-driven sizing,
  and the WM's own grants (via the now-correct `PMaxSize`) — *before* any
  full-height rectangle exists anywhere. This is documented Windows behavior,
  no Wine internals involved.
- `WM_WINDOWPOSCHANGING` — valid secondary clamp (`wp->cy = min(wp->cy,
  cap)`) for any path that skips minmax (e.g. `SWP_NOSENDCHANGING`); cheap to
  include in the same subclass procedure.
- `WM_WINDOWPOSCHANGED` — **wrong**: fires after the rectangle is applied;
  same post-fact position as the KWin cap, and it is precisely the handler
  Ableton loops in.
- `WM_NCCALCSIZE` — **wrong layer**: computes the client area for a given
  frame; it cannot reject the frame size, and lying in it recreates the exact
  client/frame divergence that drives the storm.
- `SetWindowPos` (API hot-patch) — unnecessary given the above and strictly
  worse: import-table or inline patching is binary-adjacent and misses
  WM-initiated paths.

**Injection vehicle: proxy `VERSION.dll` in the copied prefix, runner-only.**
Probed read-only with `objdump -x` on the copied-prefix exe: Ableton imports
`VERSION.dll` (also `dbghelp.dll`, `SHLWAPI.dll` — alternates if needed).
The classic vector: a small PE DLL named `version.dll` placed next to the exe
in the copied prefix's `Program` dir, forwarding the handful of real version
exports and, on `DLL_PROCESS_ATTACH`, installing a `WH_CBT` hook; on
`HCBT_CREATEWND` for the main window class it subclasses via
`SetWindowLongPtrW(GWLP_WNDPROC)` and clamps `WM_GETMINMAXINFO` /
`WM_WINDOWPOSCHANGING` in the subclass proc. Loading is gated by
`WINEDLLOVERRIDES="version=n,b"` — an environment variable the runner already
manages, set **only** in the Proton-exp runner path. Toolchain:
`x86_64-w64-mingw32-gcc` is already installed (verified; no package installs
needed).

**Constraint audit for option 3:** no Ableton binary is modified (one *new*
file is added beside the exe, inside the disposable copied prefix — flagged
for explicit sign-off since it lives in the app's directory); working prefix
untouched; no registry writes (env-var override only); no virtual desktop; no
packages; no KWin settings; opt-in (runner path only); reversible by deleting
the file and dropping the override. The main honest cons: it is in-process
code in a proprietary app (a shim bug crashes Ableton), it must be carefully
scoped to the main window so the auth dialog and WebView2 surfaces are
untouched, and it is the most engineering of the three options.

## Correcting an already-latched belief

Not needed if prevention holds from process start: the belief is proven
runtime-only (nothing persisted mid-session), so a clean relaunch under
either option 1 or option 3 starts unlatched. No in-session unlatch mechanism
is proposed — the measured record (guard 2 hardening + this prototype) says
post-hoc correction fights and loses.

## Recommendation

**Prototype option 3 first (WM_GETMINMAXINFO shim via proxy `VERSION.dll`,
runner-scoped), with option 1 as the fallback.** Option 3 is the only
direction that (a) prevents the full-height rectangle from ever existing on
the Windows side — the actual latch site, (b) makes Wine publish a race-free
`PMaxSize` so the WM also refuses pre-apply (subsuming option 2), and (c)
violates **no current project constraint** — whereas option 1, though much
smaller, cannot be built without relaxing the KWin persistent-settings
constraint. If the shim prototype misses (e.g. Ableton sizes via a path that
ignores minmax, or the CBT subclass proves fragile), fall back to option 1
and ask for an explicit, scoped relaxation: transient rule, `ForceTemporarily`
policy, byte-identical backup/restore, hash-verified — precedent already
exists in the shipped `waydaw-ableton-proton-decoration` rule.

## Validation required before any merge

1. Real user hand-drag to full height (primary proof — synthetic
   `xdotool`/`wmctrl` resize is demonstrably insufficient and may be used only
   as secondary comparison), from a stock-1096-seed launch.
2. Follow-up **normal width and height resizes plus moves after the drag**,
   then a quiet period — this is the exact sequence that broke the cap
   prototype; it must not re-trigger any full-height re-assert.
3. Observation that the full-height configure never appears: keep the KWin
   guard-3 cap loaded as a *sentinel* — a correct pre-apply fix means it
   fires **zero** times.
4. `WM_NORMAL_HINTS` shows a `PMaxSize` (option 3) and survives moves/resizes
   (Wine as sole writer); `xprop` sampled across the session.
5. Main UI thread stays calm (≤ ~10 % of a core) during and after all
   resize attempts; File menu opens and Escape closes it afterwards.
6. Vertical-maximize and fullscreen behavior re-tested (guard 2 events or
   clean clamped maximize; no regression to the maximize storm).
7. Auth dialog and WebView2 windows unaffected (no shim subclass on them);
   no authorization surfaces touched.
8. Cleanup: controller unloaded, zero processes, working-prefix DXVK hashes
   and `kwinrc`/`kwinrulesrc` byte-identical (for option 1: restored
   byte-identical after rule removal).
9. Crash-resilience check for whichever option ships: kill -9 the session
   mid-flight and verify the leftover state (rule residue / DLL file) is
   inert and swept by the next cleanup.

## Constraint check of the recommendation

Option 3 as specified violates none of: no authorization, no credentials, no
binary patching (new file only — flagged), working prefix untouched, copied
prefix only, no virtual desktop, no package installs (mingw already present),
no registry mutation, Proton-exp stays opt-in, KWin persistent settings
unchanged, no geometry-fighting loop, real-manual-resize validation required.
Option 1 violates exactly one: KWin persistent settings — and is therefore
gated on the user relaxing it, not on engineering.

---

# Implementation + validation: option 3 sizing shim (fix/proton-sizing-shim, 2026-07-07)

Option 3 was implemented and validated with a real user hand-resize.

**Verdict: the sizing shim mechanically SOLVES the message-pump resize storm.**
Startup stayed calm, the stock 1096 seed was still corrected, a real manual
edge-drag toward full height did NOT storm, and — the exact path that broke the
KWin post-apply cap — a normal width resize AFTER a height change did not
re-trigger the full-height fight. The main UI thread stayed calm (~5–15 % of a
core) throughout; no 80 % runaway ever appeared. **But the branch is NOT
merge-ready:** resizing the window shorter exposes a separate decoration /
menu-bar occlusion bug (below) that can make the UI awkward or unusable. That
bug is pre-existing (decoration churn), not caused by the shim, and out of
scope for the sizing-shim acceptance — tracked separately.

## What was implemented

- `compat/ableton-sizing-shim/version-shim.c` (+ `version.def`, `build.sh`):
  a proxy `version.dll` (six forwarded version.dll exports; the real DLL is
  loaded by explicit `System32\version.dll` path to avoid self-recursion). On
  `DLL_PROCESS_ATTACH` it installs a **thread-local** `WH_CBT` hook on the main
  thread; on `HCBT_CREATEWND` for top-level `WS_THICKFRAME` (non-`WS_CHILD`)
  windows it subclasses the wndproc and clamps, in the same synchronous
  message handling:
  - `WM_GETMINMAXINFO`: `ptMaxTrackSize.y` and `ptMaxSize.y` → cap.
  - `WM_WINDOWPOSCHANGING`: `wp->cy` → cap (belt-and-braces).
  Built with the already-installed `x86_64-w64-mingw32-gcc`; artifact lives in
  untracked `.local-tools/ableton-sizing-shim/version.dll`.
- Runner wiring (`config/ableton-runner.sh`, `bin/ableton`): the proton-exp
  runner flags the shim (`WAYDAW_ABLETON_SIZING_SHIM=1`, opt-out `=0`);
  `bin/ableton` installs the DLL beside the Ableton exe **in the copied prefix
  only** (hard refusal for the working prefix) at real launch, and gates
  loading with `WINEDLLOVERRIDES=version=n,b`. Dry-run discloses
  source/target/cap and mutates nothing. Default `bin/ableton` (system Wine,
  working prefix) is entirely unchanged.
- `bin/verify-proton-runner-mode` extended to 58 checks (shim disclosure,
  no-dry-run-mutation, opt-out, cap override, default-path-clean,
  working-prefix-has-no-shim).

## Cap tuning: 1000 was too cramped; 1040 made height usable

The cap is the Win32 window-height ceiling the shim enforces
(`WAYDAW_SIZING_SHIM_MAX_H`, decoupled from the conservative startup placement
clamp `WAYDAW_ABLETON_MAX_WINDOW_HEIGHT=1000`; override via
`WAYDAW_ABLETON_SIZING_CAP_H`).

- **Cap 1000 (first try): storm solved, but height unusable.** The window's
  legal height band was only ~966 (Ableton's content-minimum) … 1000 — about
  34 px — so height "wouldn't resize" and snapped back, while width was free
  (it stuck at ~90 distinct values from 498 to 2560). Measured: during a
  synthetic shrink to 800 the window snapped to 966 with **zero** shim
  `WM_WINDOWPOSCHANGING` clamps — i.e. the snap-back is the window bouncing
  inside the narrow band, not the shim rewriting the drag. Maximize was capped
  at 1000 (`ptMaxSize.y`) so it "didn't fill the screen" and took several
  clicks. Main thread calm (~5 %) throughout; storm absent.
- **Cap 1040 (chosen): height resizing became usable.** The KWin guard-3
  margin was loosened to 20 (backstop clamp ~1060) so it no longer fights the
  shim's band. Re-launched from the stock 1096 seed (clamped 1096→1000);
  startup 832×966, calm (~4 %). Real hand-resize: the window now settled
  freely at many heights (566, 675, 849, 937, 977, up to ~1006 client at the
  1040 cap) instead of snapping to 966 — height axis unstuck. Width resize
  after a height change: **no full-height re-assert**, main thread stayed
  ~14 % during active drags and calm at idle; the KWin sentinel stayed
  near-silent (only a lone guard-2 maximize-undo on a maximize attempt). Storm
  did not return.

Maximize remains intentionally odd: `ptMaxSize.y` caps the maximized height
and guard 2 undoes vertical-maximize, so maximize does not fill the screen and
can take multiple clicks. Accepted tradeoff of capping height to avoid the
storm — not a regression to fix here.

## New blocker: decoration / menu-bar occlusion when resizing smaller

Resizing the window **shorter** makes Ableton's top **File/Edit menu bar
disappear** behind the KWin titlebar, with a flicker during the drag. Captured
failure state (window hand-resized to 1709×331):

| datum | value |
|---|---|
| geometry | 1709×331 @19,213 |
| `_MOTIF_WM_HINTS` | `0x3,0x3e,0x0,0x0,0x0` — **decorations 0x0 (borderless)**; startup was `0x7a` |
| `_NET_FRAME_EXTENTS` | `0,0,28,0` — KWin **still drawing a 28 px titlebar** (decoration-pin holding) |
| `_NET_WM_STATE` | `_MAXIMIZED_VERT,_MAXIMIZED_HORZ` — **stale** (window is 331 px tall, not maximized) |
| main UI thread | ~14 % of a core — **calm, NOT storming** |
| guard events (90 s) | undo-vmax 0, cap-height 0, re-pin 0 — guards quiet |
| menu bar | client top row (y=0) renders the grey control bar (129); the File/Edit row is **not in the client render** — occluded/absent |

**Mechanism:** on resize, Ableton/Wine re-derives its Motif window hints and
drops the decoration hint to `0x0` (borderless), but the KWin decoration-pin
keeps a 28 px titlebar (`_NET_FRAME_EXTENTS=28`). Ableton then lays out its top
menu row assuming no titlebar, and KWin's titlebar draws over it. This is the
**known decoration-churn / white-top-strip family** the decoration-pin guard
was written to fight (see
`docs/ableton-proton-custom-presentation-controller.md`), now visible only
because height resizing finally works (at cap 1000 the height was frozen at
966, so the churn was never entered). A stale `MAXIMIZED_VERT/HORZ` atom pair
(set app-side without a KWin maximize, so guard 2 stays blind) is part of the
same decoration-state confusion. **The sizing shim does not touch decorations
and neither causes nor fixes this.**

## Classification

- **Storm fix: promising / mechanically successful.** The shim clamps the
  sizing pipeline pre-apply; the full-height latch never forms; the
  width-after-height failure path is fixed; the app stays responsive with a
  calm UI thread across height and width resizing.
- **Product readiness: NOT merge-ready.** Resizing shorter can occlude the top
  menu bar behind the titlebar (decoration bug), making the UI awkward or
  unusable at some sizes. This must be resolved (separate decoration
  investigation) before the Proton-exp resize experience is acceptable.

## Session hygiene

Ableton was launched twice via `./bin/ableton-proton` (cap 1000 then 1040),
each from the stock 1096 seed restored from `.bak-normalize`. No authorization
attempted; no credentials; the only clicks were demo-mode File-menu
interactability probes (a "Welcome to Ableton" panel appeared, confirming
posted input is processed — the storm's dead-input signature is gone). The
auth dialog (`_NET_WM_WINDOW_TYPE_DIALOG`, excluded by `normalWindow` and by
the shim's `WS_THICKFRAME`/`!WS_CHILD` gate) was never touched. Cleanup after
each session: `cleanup_result=clean`, controller `loaded=false`, zero
Proton/Wine/WebView2 processes, working-prefix DXVK hashes verified unchanged
(sha256 -c OK ×8), `kwinrc`/`kwinrulesrc` byte-identical. The shim DLL lives
only in the disposable copied prefix.

---

# Addendum (2026-07-07): min-height floor added to the shim

The recommended `WM_GETMINMAXINFO` shim gained a **min floor**
(`ptMinTrackSize.y`, default 820 via `WAYDAW_ABLETON_SIZING_MIN_H`) to keep
Ableton out of its menu-less compact/borderless mode (see
docs/ableton-proton-decoration-menubar-occlusion.md, which documents the fix,
two KWin-side backstops — floor guard 4 and post-resize renegotiation nudge
guard 5 — and the real-resize validation). The max cap and its rationale
above are unchanged (`WAYDAW_ABLETON_SIZING_CAP_H`, default 1040).

One correction to the analysis above: Wine did **not** publish the minmax
constraints as X `PMin/PMaxSize` hints on this Proton build
(`WM_NORMAL_HINTS` carried only location/gravity), so the WM does not refuse
over/under-band drags pre-apply; the constraint holds Windows-side only, and
WM-imposed geometry needs the KWin-side backstops.
