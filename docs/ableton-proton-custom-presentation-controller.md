# Custom WayDAW presentation controller — design (2026-07-06)

Design note for eliminating/neutralizing the **unauthorized-state titlebar
flicker** of Ableton under the opt-in Proton-exp runner, **without** Wine
virtual desktop, **without** authorization, and **without** working-prefix
mutation. Design only — no prototype implemented in this commit; the
recommended prototype (§6) is fully specified and awaits explicit approval.

Branch context: `fix/proton-exp-window-presentation` (held, local-only), on
top of the completed pre-authorization runner phase (`origin/main @ 95ef251`).
Prior evidence: `docs/ableton-proton-window-presentation.md`.

## 1. Current evidence summary

Structural presentation is fixed (steamuser `Preferences.cfg` seed in
`config/ableton-runner.sh`): the window opens as a normal decorated
maximized-vertical 848×1052 window; no fullscreen, no bottom black bar.

Residual defect, measured by `bin/observe-ableton-proton-flicker`
(300 ms sampling, 100 s, copied prefix, unauthorized):

- window id `0x07a00003` and PID stable for the whole run — **no recreation**
- `_NET_WM_STATE = MAXIMIZED_VERT + DEMANDS_ATTENTION`, constant — **no
  maximize/fullscreen churn**
- `_MOTIF_WM_HINTS` decorations field toggles `0x7a ↔ 0x0`
  (87% / 13% of samples); `_NET_FRAME_EXTENTS` top follows `28 ↔ 0` in
  lock-step — **Wine flips the hint, KWin faithfully follows**
- 28 frame transitions / 100 s, in bursts; stable-decorated between bursts
- zero DXVK presentation lines, zero d3d11/dxgi errors, WebView2 count
  uncorrelated — **not a rendering problem**
- UI thread ~115% of a core while unauthorized (busy re-init loop) — the hint
  churn is a side effect of Ableton's unauthorized window re-management

Classification: **Wine Motif decoration-hint churn**. The client (Wine)
re-derives `_MOTIF_WM_HINTS` from Ableton's Windows-side style activity and
re-emits it; each `0x0` burst makes KWin drop the frame, each return to
`0x7a` restores it.

## 2. Ruled-out approaches (do not retry)

**Wine virtual desktop — REJECTED as a product direction (user decision).**
It would technically hide the churn (Ableton would render inside one stable
managed desktop window), but it is not the product WayDAW wants: it changes
the user-facing window model. Rejected, not deferred.

**KWin rule policy — FAILED.** `noborderrule=3` (Apply/initial): 87%
decorated, 28 transitions/100 s. Switching to `noborderrule=2` (Force): 75%
decorated, 32 transitions — no better. KWin honors the client's run-time
`_MOTIF_WM_HINTS` changes regardless of rule policy in this Plasma 6.7
(caveat: the Force test ran after a mid-session `reconfigure`, which this
Plasma applies unreliably — see §7 missing data). Rule mutation is stopped;
the committed rule stays as-is.

**xprop property-removal guard — FAILED, made it worse (59% decorated, 71
transitions).** It deleted/rewrote the client-owned `_MOTIF_WM_HINTS` X
property from outside, so Wine re-asserted it and KWin processed *both*
parties' writes — roughly doubling the churn. Removed; do not reintroduce.
Its failure mode (racing on a **client-owned X property**) is the key design
constraint below.

**Authorization — not available as a fix.** Authorization happens only after
WayDAW is fully complete; it is not a validation step and no design below may
depend on it.

## 3. Design principle

The failed guard raced Wine on Wine's own X property. The controller must
therefore act **on the WM side of the boundary**: let Wine write whatever
hints it wants, and correct **KWin's internal decoration state** after the
hint lands. KWin's `noBorder` state is not an X property Wine reads or owns —
correcting it does not feed anything back to Wine, so there is no two-writer
loop on shared data. Wine's resting state is decorated (`0x7a`, 87%), so the
controller only has to hold the frame through the `0x0` bursts.

## 4. Candidate layers, in evaluated order

### 4.1 KWin-native script (RECOMMENDED — API verified locally)

A tiny KWin script, loaded at runtime through KWin's D-Bus Scripting
interface, that watches for the one matching window and pins
`window.noBorder = false` whenever KWin flips it to `true`.

API verification (this machine, X11 session, `kwin_x11 6.7.1` active WM,
PID-verified owner of `org.kde.KWin`):

- D-Bus: `org.kde.KWin /Scripting org.kde.kwin.Scripting` exposes
  `loadScript(path, pluginName)`, `start()`, `isScriptLoaded(name)`,
  `unloadScript(name)` (introspected via `busctl`). Runtime load/unload —
  **no kwinrc change, no KWin settings change, survives nothing** (gone on
  KWin restart), which is exactly the reversibility we want.
- Scripting API symbols present in the **active** `libkwin-x11.so.6.7.1`:
  `windowAdded`, `windowList`, `normalWindow`, `resourceClass`, `caption`,
  `captionChanged`, `noBorder`, `noBorderChanged`, `setNoBorder`,
  `maximizeMode`, `fullScreen`. Usage idiom confirmed against the stock
  Plasma 6.7 script `/usr/share/kwin/scripts/virtualdesktopsonlyonprimary/`
  (`workspace.windowAdded.connect`, `window.<signal>.connect`,
  `workspace.windowList()`, `window.normalWindow`).

Scope guard (all three required, same predicate as the committed KWin rule):
`resourceClass === "steam_proton"` AND caption contains
`"Ableton Live 12 Suite"` AND `normalWindow` — no other Proton/Steam window
is touched; the auth Dialog is excluded by `normalWindow`.

Why this is structurally less racy than the xprop guard:

- It never writes any X property. Wine's `_MOTIF_WM_HINTS` stays exactly as
  Wine wrote it; Wine sees no external interference to fight.
- It reacts to KWin's **internal** `noBorderChanged` signal inside KWin's own
  event loop — no X round-trips, no polling, no separate process racing the
  property stream.
- Worst case is Wine's own burst frequency (the script adds no extra
  hint-writes for Wine or KWin to re-process), vs. the xprop guard which
  doubled it.

Open risk (the thing the prototype must measure): a repaint may still slip
in between KWin honoring a `0x0` hint and the script's `noBorder = false`
landing — i.e. flicker reduced-but-visible instead of eliminated. Also
possible: KWin coalesces the change before the next frame and the flicker is
fully gone. Only a probe run answers this.

Diagnostic side benefit: the script logs every `noBorderChanged` to the
journal, giving ground truth on whether the frame drops are really
`noBorder` flips or decoration re-creation with `noBorder` never changing —
which disambiguates the confounded Force-rule result (§7).

### 4.2 WayDAW-side D-Bus controller (COLLAPSES INTO 4.1)

Introspected `org.kde.KWin /KWin` on the live WM: it exposes only queries and
desktop-level actions (`getWindowInfo`, `queryWindowInfo`, `killWindow`,
`reconfigure`, …). **KWin exposes no D-Bus API to set per-window decoration
state directly.** Therefore a "pure D-Bus controller" cannot exist; the
supported D-Bus role is the *delivery mechanism* — a WayDAW helper script
that `loadScript`s / `unloadScript`s the 4.1 script around the Ableton
session. That pairing (runner loads controller at launch, cleanup unloads
it) is the proposed shape.

### 4.3 Runner-side Wine/Proton adjustment (WEAK — verified, no decoration lever)

Inspected the actual runner driver
(`.local-runners/kron4ek-proton-exp-11.0/lib/wine/x86_64-unix/winex11.so`,
strings, read-only). Findings:

- Env vars present: `WINE_USE_KWIN_HACKS`, `WINE_DISABLE_FULLSCREEN_HACK`,
  `WINE_DISABLE_VULKAN_OPWR`, `SteamAppId`/`SteamGameId`.
- `WINE_USE_KWIN_HACKS` gates request sequencing for **maximize/fullscreen
  `_NET_WM_STATE`** changes ("temporarily restoring (KWin hack)", "delaying
  request (KWin hack)"). Our churn is in the Motif **decorations** field with
  `_NET_WM_STATE` constant — different mechanism; unlikely to help, cheap to
  A/B later if 4.1 underperforms.
- `SteamAppId=<n>` would change `WM_CLASS` to `steam_app_<n>`. Useless here:
  the rule already *matches* (`steam_proton` + title) and matching is not the
  problem. Risk: unknown side effects on Proton steam-integration paths. Not
  recommended.
- **No env var or registry lever exists to pin/stabilize the Motif
  decorations field.** Wine re-derives it from Windows window styles; only a
  code change (4.4) alters that.

### 4.4 Minimal Wine/Proton patch (DESIGN-ONLY FALLBACK)

If 4.1 measurably fails, the minimal patch is in winex11's Motif-hint
emission (the driver already serializes these — "requesting _MOTIF_WM_HINTS
%s serial %lu"): gate on a WayDAW-private env var (set only by the opt-in
runner, e.g. `WAYDAW_PIN_DECORATIONS=1`) and, when set, **clamp the
decorations field to decorated** for managed, non-fullscreen top-level
windows — i.e. suppress only the `0x7a → 0x0` transitions that occur while
the window is mapped and not fullscreen. Properties: app/runner-scoped (env
set only in Proton-exp mode), no prefix mutation, default path untouched.
Cost: maintaining a runner rebuild — significant; that is why it is last
among the active options. **Not to be implemented without explicit
approval.**

### 4.5 Accept known limitation (LAST RESORT)

The branch already improves presentation structurally (no fullscreen, no
black bar, decorated 87% of the time). Since authorization is deferred to
project completion, the flicker would be user-visible for the entire
remaining project lifetime — acceptance is therefore **not** the
recommendation while 4.1 is untried.

## 5. Risks and reversibility

| Layer | Risk | Reversal |
|---|---|---|
| 4.1 KWin script | visible residual flicker; (theoretical) mis-scope — mitigated by 3-way predicate | `unloadScript` via D-Bus; also auto-gone on KWin restart; zero files outside repo |
| 4.2 helper | same as 4.1 (it only loads/unloads 4.1) | same |
| 4.3 env A/B | Proton behavior shifts (KWin hacks path) | unset env; runner-scoped |
| 4.4 patch | runner rebuild burden; Wine behavior drift | revert to stock runner tarball |

Nothing in any layer touches: the working prefix, the copied prefix's
contents, KWin settings/rules files, the default launcher, or packages.

## 6. Recommended next prototype (needs explicit approval)

**`bin/ableton-kwin-decoration-controller`** — a repo-tracked helper that:

1. writes the KWin script below to the scratchpad (or `share/` in-repo),
2. loads it: `busctl --user call org.kde.KWin /Scripting
   org.kde.kwin.Scripting loadScript ss <path> waydaw-ableton-decoration`
   then `… start` (no args), and
3. unloads it on `--stop` / session cleanup:
   `… unloadScript s waydaw-ableton-decoration`.

(`busctl` and `gdbus` are both installed; no qdbus on this system.)

Proposed script (complete):

```js
// waydaw-ableton-decoration: pin KWin-side decoration for the Proton
// Ableton main window against Wine's unauthorized-state Motif hint churn.
// Never touches X properties; only corrects KWin's internal noBorder state.
function isTarget(w) {
    return w.normalWindow
        && w.resourceClass === "steam_proton"
        && w.caption.includes("Ableton Live 12 Suite");
}
function pin(w) {
    if (isTarget(w) && w.noBorder) {
        console.info("waydaw-ableton-decoration: re-pinning noBorder=false on " + w.internalId);
        w.noBorder = false;
    }
}
function manage(w) {
    // caption arrives late on Proton windows; evaluate on every change
    w.captionChanged.connect(() => pin(w));
    w.noBorderChanged.connect(() => pin(w));
    pin(w);
}
workspace.windowList().forEach(manage);
workspace.windowAdded.connect(manage);
```

Validation plan (one launch, copied prefix, no authorization): load script →
`WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton` →
`bin/observe-ableton-proton-flicker` (same 100 s protocol) → compare against
the 87%/28-transition baseline → `bin/ableton-proton-cleanup` + unload.
Journal (`journalctl --user -b | grep waydaw-ableton-decoration`) gives the
KWin-side event count.

Success: transitions ≈ 0 and 100% decorated, or transitions reduced to
sub-perceptual (< 3/100 s with no multi-second frameless dwell).

## 7. Exact data still missing

1. Whether a script-side `noBorder = false` re-pin lands before the next
   compositor repaint (i.e. flicker eliminated vs. shortened) — only the §6
   prototype run answers this.
2. Whether the frame drops are `noBorder` flips at all, or decoration
   re-creation without a `noBorder` change — the script's journal log
   answers this in the same run.
3. Whether the earlier Force-rule failure was real or a casualty of Plasma
   6.7's unreliable mid-session `reconfigure` (rule values took many
   reconfigures to load in prior sessions). §6's log resolves this
   indirectly; no further rule mutation to find out.
4. (Only if §6 underperforms) whether `WINE_USE_KWIN_HACKS=1` changes the
   hint/request sequencing observably for this window.

## 8. Stop conditions

- Probe shows transitions **not reduced** (≥ baseline 28/100 s) or any
  metric worse → unload script, stop, fall back to evaluating 4.4 on paper.
- Any effect on a non-target window (any window without all three predicate
  matches) → unload immediately, fix predicate before any retry.
- Any liveness regression (SRW/`SendMessageW` wedge, forward-progress loss)
  → unload, `bin/ableton-proton-cleanup`, stop.
- KWin instability (crash/restart) after load → do not reload; stop and
  reassess (script auto-unloads on restart).
- Two failed prototype iterations → stop iterating; escalate to the 4.4
  design decision rather than tuning the script indefinitely.

## 9. Status

Design note only (2026-07-06 first commit). The §6 prototype was then
explicitly approved and implemented — results in §10. Branch remains
**held**.

## 10. Prototype result (2026-07-06) — FLICKER ELIMINATED, VIABLE

The §6 prototype was approved and implemented:

- `bin/ableton-kwin-decoration-controller` — `--load/--install`,
  `--unload/--uninstall`, `--status`, `--dry-run`. Talks only to
  `org.kde.KWin /Scripting org.kde.kwin.Scripting` via `busctl`; changes no
  KWin settings/files; nothing persists a KWin restart.
- `config/kwin/waydaw-ableton-decoration.js` — the tracked KWin script
  source. Scope predicate exactly as designed:
  `normalWindow && resourceClass === "steam_proton" && caption.includes("Ableton Live 12 Suite")`.

### Iteration 1 finding — `noBorderChanged` never fires (missing-data #2 resolved)

The as-designed script (pin on `noBorderChanged` + `captionChanged`) matched
the target window but logged **zero** re-pins across a full churn run
(92% decorated / 28 transitions — baseline noise). Ground truth from the
journal: **KWin's X11 Motif-hint handler drops the decoration and sets its
internal no-border flag WITHOUT emitting `noBorderChanged`.** The signal
path the design assumed simply never runs for hint-driven drops. (This also
plausibly explains the earlier rule-policy failures beyond the reconfigure
confound — the hint path is special-cased inside KWin.)

### Iteration 2 — trigger on `frameGeometryChanged` (works)

Every decoration drop changes the frame geometry (client reclaims the 28px
titlebar), and `frameGeometryChanged` **does** fire on that path. The script
now additionally connects it; the handler reads `w.noBorder` (which does
reflect the silently-set internal flag — confirmed `true` at churn moments)
and re-pins `noBorder = false`. Re-entrancy-safe: the restore fires one more
geometry change, after which `noBorder` reads false and the handler no-ops.

### Measurements (same probe/protocol as baseline: 300 ms × 100 s, copied prefix, unauthorized)

| metric | baseline (no controller) | iteration 1 | **iteration 2** |
|---|---|---|---|
| decorated (frame_top=28) | 87% | 92% | **100%** |
| frame transitions / 100 s | 28 | 28 | **0** |
| `_MOTIF_WM_HINTS` toggling | yes (0x7a↔0x0) | yes | **yes — untouched, by design** |
| `_NET_FRAME_EXTENTS` top | 28↔0 | 28↔0 | **constant 28** |
| window id / maximize state | stable / MAX_VERT | stable | **stable / MAX_VERT only** |
| geometry | 848x1052↔848x1080 | toggling | **constant 848x1052** |

- Wine still churns the Motif hint underneath (914 journal re-pins over the
  ~5.5 min session); KWin now absorbs every drop internally before the probe
  (300 ms) can ever observe a frameless sample. The correction runs
  synchronously inside KWin's own event dispatch — no X property is ever
  written by us, no external process races Wine.
- Scope verified: journal shows exactly **one** window ever matched
  (`steam_proton` / "Untitled - Ableton Live 12 Suite"); the authorization
  Dialog and all other windows untouched. No authorization attempted.
- Screenshot: decorated titlebar, full UI incl. bottom status bar, no black
  bar, no fullscreen.
- Liveness healthy end-state: `main_thread_in_srw_exclusive=no`,
  `threads_in_sendmessage=` (none), `forward_progress=executing`, app alive
  after capture. UI thread still ~115% of a core — the unauthorized busy
  loop continues; only its presentation symptom is neutralized.
- Cleanup: `bin/ableton-proton-cleanup` → `cleanup_result=clean`; controller
  unloaded (`--status` → `loaded=false`). Working prefix never touched.

### Install / uninstall (manual — still available alongside the lifecycle)

```bash
bin/ableton-kwin-decoration-controller --load     # before/while Ableton runs
bin/ableton-kwin-decoration-controller --status
bin/ableton-kwin-decoration-controller --unload   # full reversal
```

Runtime-only: a KWin restart also removes it. No kwinrc/kwinrulesrc edits.

### Verdict

**Viable — this is the custom WayDAW solution.** Residual caveat: the probe
bounds any frameless dwell to <300 ms; the correction is event-driven inside
the compositor, and none of 242 samples caught a frameless frame, but a
sub-sample blink cannot be strictly disproven by this probe.

## 11. Runner lifecycle integration (2026-07-06, approved) — DONE

The controller is now **lifecycle-managed by the opt-in Proton-exp runner**;
manual `--load/--unload/--status` remains available and unchanged.

How it is wired:

- `config/ableton-runner.sh` (proton-exp branch only) exports
  `WAYDAW_ABLETON_KWIN_CONTROLLER=1` — a **flag only**; sourcing config/env
  never loads anything. Opt out per-run with
  `WAYDAW_ABLETON_KWIN_CONTROLLER=0`.
- `bin/ableton` loads the controller **only at real launch** (after the
  dry-run and `--print-launch-config` exits), only when the flag is 1. The
  default system-Wine path never sets the flag, so `./bin/ableton` is
  unchanged. Load is idempotent (already-loaded is a no-op). If the load
  fails, the launch continues but prints a LOUD warning that flicker
  protection is NOT active — it never silently pretends.
- `bin/ableton-proton-cleanup` unloads the controller after session cleanup
  (`kwin_controller_unload=ok|FAILED` in its output; dry-run lists the
  unload in `[would_run]`). Unload targets ONLY the
  `waydaw-ableton-decoration` plugin name — no other KWin script is touched.
- Dry-run reporting: `WAYDAW_ABLETON_DRY_RUN=1` prints
  `kwin_decoration_controller=would_load` (proton-exp) / `no`
  (default or opted out) **without loading anything** — verified by test.
- `bin/verify-proton-runner-mode` grew a controller-lifecycle section
  (dry-run-does-not-load, load, status, idempotent second load, cleanup
  unload, status-after, safe double-unload): suite now passes **33/33**.

Scope predicate (unchanged): `resourceClass === "steam_proton"` AND caption
contains `Ableton Live 12 Suite` AND normal window only. No KWin config
persistence: the script exists only in the running compositor and disappears
on cleanup unload or any KWin restart.

Integrated validation (copied prefix, unauthorized, no authorization
attempted): controller auto-loaded at launch; probe from launch: 99%
decorated, 4 transitions (two ≤300 ms dips, one during Ableton's startup
double-init); settled-session probe: 99% decorated, 2 transitions (one
≤300 ms dip); vs baseline 87% / 28 transitions with multi-second frameless
dwells. Same mechanism as the §10 prototype (592 pins absorbed this
session); the occasional single-sample dip is the probe catching a
correction in flight. Maximize state stable (`MAXIMIZED_VERT` only),
geometry constant 848x1052, window id stable, liveness healthy (no SRW, no
`SendMessageW` wedge, executing). Cleanup: `cleanup_result=clean`,
`kwin_controller_unload=ok`, controller `loaded=false`, zero processes left.

Authorization remains a later, user-owned step and is **not** required for
presentation stability — the controller neutralizes the unauthorized-state
churn as long as it runs. Branch stays **held**; merge is a user decision.
