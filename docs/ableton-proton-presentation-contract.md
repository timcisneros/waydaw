# Design note: the Ableton presentation contract (Proton-exp)

Status: DESIGN ONLY (2026-07-08). No implementation in this note's commit.
Base: `main @ f67f619` (startup placement clamp, KWin controller guards 1–5,
sizing shim cap 1040 / floor 820 all landed and validated).

## Why this note exists

Maximize on the Proton-exp Ableton window is awkward: it takes several
clicks and never fills the screen. The question posed: is that a bug to fix,
or a symptom of a missing abstraction?

**Finding: symptom.** Every landed fix — placement clamp, decoration pin,
maximize guard, manual cap, sizing shim cap, sizing shim floor, floor
backstop, renegotiation nudge — is an independently discovered patch
enforcing pieces of one unstated rule set. The rule set was never written
down as a single contract, so the pieces disagree in small ways (see
"contract wrinkles") and user-facing intents like "maximize" fall into the
gaps between layers: guard 2 *cancels* maximize instead of *translating* it,
so the user's click does nothing and they click again. The awkwardness is
the contract gap made visible.

## The contract (current, as actually enforced)

Heights are Win32 window units on the shim side; X frame heights differ by
the 28 px KWin titlebar (win32 ≈ X client on this build; frame = client + 28).

| # | Invariant | Why |
|---|-----------|-----|
| C1 | Ableton must never believe a height above the cap (1040) | full-height belief latches the WM_WINDOWPOSCHANGED storm |
| C2 | Ableton must never believe a height below the floor (820) | short belief flips the app into menu-less compact mode (`_MOTIF 0x0`, flip ~740–750, hysteresis to ~1000) |
| C3 | The WM must never *settle* the window outside the band | WM-imposed geometry bypasses Win32 messages (raw adoption); a settled out-of-band window is a stuck sliver or a dead black bar |
| C4 | The window is born inside the band | startup seed 1096 > screen coerces vertical-maximize → storm |
| C5 | Decoration stays on (`_MOTIF 0x7a`); menu row visible; File opens; Esc closes | the point of the whole exercise |
| C6 | Vertical maximize / fullscreen / full-height must never be granted | same as C1 but via the WM path |
| C7 | Width is free (measured calm at ≥1841 px); only height is dangerous | all storms and mode switches are height-driven |
| C8 | Environment: working prefix untouched, Proton-exp opt-in, no persistent KWin settings, copied prefix only | project safety policy |

Numbers today: floor 820 / cap 1040 (`WAYDAW_ABLETON_SIZING_MIN_H` /
`_CAP_H`), startup seed clamp 1000 (`WAYDAW_ABLETON_MAX_WINDOW_HEIGHT`),
KWin guard constants 800/848 (floor) and workarea−20 (cap sentinel).

### Contract wrinkles (evidence the abstraction is missing)

- **The band top is unreachable.** Shim allows client 1040, but guard 3 caps
  the frame at workarea−20 = 1060 → client 1032. Effective top is
  min(cap, workarea−20−titlebar) and nothing states that anywhere.
- **Constants are duplicated in incompatible units.** Launcher env (win32:
  820/1040/1000) vs controller JS literals (frame: 800/848/−20). KWin
  scripts cannot read env vars, so the controller values are re-derived by
  hand and drift is silent.
- **"Maximize" has no defined meaning.** Guard 2 defines it as "error to be
  cancelled." The user defines it as "make it big." Nobody wins.

## Which layer owns what (design answer, Q1)

Three authorities, one contract — this split is correct and should be kept;
what must change is that the *numbers* come from one place:

| Layer | Owns | Why it must be this layer |
|-------|------|---------------------------|
| **Sizing shim** (Win32) | what Ableton may *believe* (C1, C2) | the mode switch and the storm are driven by the app's belief, not X geometry — proven when `_MOTIF` stayed `0x7a` at a 28 px X grant |
| **KWin controller** (WM) | what the WM may *grant/settle* (C3, C5-pin, C6) | Wine raw-adopts WM configures with no Win32 message; the shim is provably blind there (WM_WINDOWPOSCHANGING floor count = 0 while the window sat at 861×41) |
| **Launcher/runner** (env) | initial state (C4), wiring, lifecycle, and **the constants** | already the single source for the shim's numbers; the natural contract home |

Recommended primitive: a single `config/ableton-presentation-contract`
definition (env-var defaults in `config/ableton-runner.sh`, as today) from
which *every* consumer derives: the shim (env, already done), the dry-run
disclosure (done), the verifier (done), and — the missing piece — the KWin
script, which should be **templated at load time** by
`bin/ableton-kwin-decoration-controller` (substitute the frame-unit
constants into a temp copy before `loadScript`; runtime-only, no persistent
settings, same lifecycle).

## What "maximize" should mean in WayDAW (Q2, Q3, Q4)

**Reframe maximize as safe-fit. Yes.**

- *Real vertical maximize is intentionally unsupported* — not a bug, a
  declared property of the compat layer. It is exactly C6; a window granted
  full workarea height storms (measured repeatedly, root-caused, docs
  `ableton-proton-exp-message-pump-starvation.md`).
- **Safe-fit** := `width = workarea.width` (C7 says free),
  `height = bandTopFrame = min(capFrame, workarea.height − CAP_MARGIN)`,
  positioned at the workarea top-left. Today that is 2560?×1060 frame /
  client ×1032 on this machine — computed from workarea at apply time, never
  hardcoded.
- **Interception is feasible and the mechanism is already proven.** Guard 2
  runs synchronously on the maximize transition and successfully prevents
  it. Change its *response*: instead of only `setMaximize(false, false)`
  (which also throws away the safe horizontal half — this is precisely why
  maximize "does nothing" and takes several clicks), do
  `setMaximize(false, false)` **then apply the safe-fit rect**. The user's
  intent ("big") is honored; the unsafe part (full height) is translated,
  not refused. KWin `maximizeMode` semantics support the split: bit 1 =
  vertical (blocked/translated), bit 2 = horizontal (safe — guard 2 already
  ignores horizontal-only today, so horizontal maximize *is currently
  allowed* and can remain so).
- **Stale maximize atoms (Q5):** translation avoids them by construction —
  the window never ends in a maximized state, so `_NET_WM_STATE` stays
  empty (measured throughout the floor validation). No external atom
  clearing (xprop writers made churn worse; two-writer race). The residue
  case in the diagnosis docs predates guard 2's current behavior and was
  already downgraded to "residue, not causal."

## Guard necessity today (Q6, Q7)

| Guard | Verdict | Rationale |
|-------|---------|-----------|
| 1 decoration pin | **keep** | auth-phase Motif churn is not height-driven; independent of shim |
| 2 vertical-max guard | **keep, becomes the safe-fit translator** | only synchronous interception point for WM maximize; shim blind to it |
| 3 manual height cap | **backstop (sentinel)** | shim holds interactive sizing pre-apply; guard 3 catches only WM-imposed near-full-height escapes; expected zero-fire; keep with a fire-counter alarm |
| 4 floor backstop | **necessary, not a backstop** | the raw-adoption stuck-sliver path is real and shim-invisible; guard 4 is the only settle-time floor |
| 5 renegotiation nudge | **necessary until the hints experiment lands** | heals the lost-counter-configure black bar; no other component can detect "granted > painted" |

Simplification path (later, one experiment): if Wine can be made to publish
`PMinSize`/`PMaxSize` in `WM_NORMAL_HINTS` (it currently publishes neither
on this build — measured), KWin itself would refuse out-of-band drags
pre-apply. Then guards 3–5 all decay to sentinels and during-drag
sliver/black-strip visuals disappear. Risk: Wine owns `WM_NORMAL_HINTS`
(two-writer race) — so the safe route is a *shim-side* experiment (make the
minmax answer flow into Wine's own hint publication, e.g. verify why Wine
skips PMin/PMaxSize here), **not** an external X writer. Explicitly out of
scope for the safe-fit work.

## Startup geometry (Q8) and the fit command (Q9)

- **Q8 — start near safe-fit? Not yet.** Current startup (clamp to 1000,
  observed born ~832×966–1006 depending on saved width) is *proven calm
  across many sessions*. Moving the seed to band-top (1032) is plausible but
  changes the most-validated moment of the whole flow for a cosmetic gain.
  Sequence it: land the safe-fit primitive first; if `ableton-proton-fit`
  proves the rect is calm at startup-adjacent times, then raise
  `WAYDAW_ABLETON_MAX_WINDOW_HEIGHT` (or better: seed width too) in a
  separate validated pass.
- **Q9 — `bin/ableton-proton-fit`: yes, and it comes first.** Command
  before controller behavior, because a command is deterministic, testable
  in isolation, and cannot loop. It computes the safe-fit rect from the
  live workarea and applies it to the current Ableton window (external
  resize request — the same mechanism as the validated recovery kick, which
  triggers a full Wine/app renegotiation). Guard 2's translation then
  *reuses the identical rect computation* (single implementation, exposed
  via the controller template or a shared helper), giving: maximize click →
  safe-fit; explicit command → safe-fit; two intents, one primitive.

## Invariants that prove the contract (Q10)

Machine-checkable after any interaction (the acceptance harness for a
safe-fit prototype and for regressions):

- **I1 (belief band):** shim minmax answers always in [floor, cap]; floor ≤ cap.
- **I2 (settle band):** ≤ 1 s after any interaction ends, X frame height ∈
  [floorFrame, bandTopFrame]. No permanent out-of-band settle.
- **I3 (mode):** `_MOTIF_WM_HINTS` decorations byte = `0x7a` whenever mapped.
- **I4 (menu):** File/Edit row present in the client render; File opens;
  Esc closes.
- **I5 (no war):** controller writes per interaction ≤ 3 (measured failure
  mode: 3858/12 s).
- **I6 (calm):** main UI thread below ~30 % sustained; no storm signature.
- **I7 (painted = granted):** no dead strip — bottom/side pixel rows of the
  window are non-black after settle (screenshot row-mean check, as used to
  find the 26 px bar).
- **I8 (maximize semantics):** any maximize request settles at the safe-fit
  rect within 1 s, `maximizeMode == 0`, `_NET_WM_STATE` empty, and is
  idempotent (second click: no geometry change, no writes).
- **I9 (environment):** working-prefix hashes stable; no shim DLL in the
  working prefix; `kwinrc`/`kwinrulesrc` byte-identical; controller
  unloaded and zero Wine/Proton/WebView2 processes after cleanup.

## Validation plan for a safe-fit prototype

1. Dry-run: disclose the computed safe-fit rect and contract constants;
   mutate nothing (verifier checks, as with cap/floor).
2. Launch `./bin/ableton-proton` (copied prefix only); baseline I1–I7.
3. Synthetic: `bin/ableton-proton-fit` twice → I2, I7, I8 (idempotence).
4. Real user pass (synthetic is never sufficient — project rule):
   maximize button once → safe-fit, menu visible; click again → no churn;
   unmaximize/restore behavior sane; then full regression of the landed
   suite (hard shrink, tall drag, width-after-height, File/Esc, idle).
5. Capture I1–I9; cleanup; hashes.

## Answers in one line each

1. **Authority:** shim = app belief; controller = WM settle; launcher = birth
   + constants. Keep the split; unify the numbers.
2. **Real maximize:** drop it; expose safe-fit.
3. **Intercept-and-translate:** yes — guard 2 is already the interception
   point; change cancel → cancel-then-apply-safe-fit.
4. **Horizontal maximize:** already allowed (guard 2 checks only the
   vertical bit); keep allowing it.
5. **Stale atoms:** avoided by translation (never end maximized); never
   write atoms externally.
6. **Simplify guards:** later, via the shim-side size-hints experiment; not
   during safe-fit.
7. **Guards 3–5:** 3 is a sentinel; 4 and 5 are load-bearing today.
8. **Start at safe-fit:** not yet — sequence after the fit primitive is
   validated.
9. **`bin/ableton-proton-fit`:** yes, first deliverable; controller
   translation second, sharing one rect computation.
10. **Proof:** invariants I1–I9 above.

## Recommended next step

Implement **`bin/ableton-proton-fit`** (one rect computation + external
apply, reusing the validated renegotiation mechanism), then rewire guard 2
to translate maximize into the same rect. Both are small, both reuse proven
levers, and together they turn "maximize is awkward" into "maximize means
safe-fit" — the contract made user-visible. Constant unification
(controller templating from the launcher env) can ride along with the
guard-2 change since the controller file is being touched anyway.

---

# UX note (2026-07-08): the native-feel boundary

User feedback after live safe-fit validation: *"the window overall just
doesn't have a native feel."* This section treats that as product feedback
about the whole presentation layer, not as a bug, and answers one question:
**should WayDAW keep chasing native feel, or define an intentionally
non-native but stable "WayDAW window mode"?**

## 1. What now works reliably (proven, most of it user-validated)

- Launch: calm startup on the copied Proton-exp prefix, placement clamp,
  shim + controller lifecycle, cleanup leaves zero residue.
- Interaction: File menu opens, Escape closes, input stays alive, UI thread
  calm (5–20%), no message-pump storm in any tested scenario.
- Resize-storm prevention: cap band held through hard shrink drags, tall
  drags, width-after-height, maximize attempts, and synthetic abuse.
- Menu preservation: `_MOTIF` stayed decorated through every shrink attempt
  (granted X heights down to 28 px); the File/Edit row never disappeared.
- Full-width fit: one maximize click → real horizontal maximize, full width,
  painted edge-to-edge; `bin/ableton-proton-fit` does the same on demand.
- Restore/toggle: second maximize click restores the previous size
  (synthetic-validated; user confirmed "maximize does go back").
- Manual height: drags move the height freely inside the band and reach the
  band top (observed live at 2560×1032).

## 2. What still feels non-native

- Maximize semantics: maximize means safe-fit (full width, kept height),
  not KDE fill-the-screen; the titlebar button state never shows
  "maximized".
- Height is bounded: cap ~1040 and floor 820 — a native window would do
  neither.
- During-drag artifacts: transient sliver on shrink, transient black strip
  on tall drags, rubber-banding on release.
- File-menu double-click-after-Esc quirk (Wine menu capture).
- KDE-titlebar expectations (button states, drag-anywhere maximize
  gestures, quick-tile) don't map cleanly onto what Wine/Ableton tolerate.
- Stale `_NET_WM_STATE` maximize atoms can linger (Wine-side residue;
  cosmetic, KWin behavior unaffected).

## 3. Non-native by design — inherent safety tradeoffs (do not "fix")

- No true vertical maximize: full workarea height is the measured storm
  trigger. This is the load-bearing wall of the whole compat layer.
- The height cap: same reason.
- The height floor: below it Ableton itself deletes its menu row.
- Safe-fit instead of real maximize: the only maximize semantics compatible
  with the two constraints above.

## 4. Possibly polishable later (ordered by value/risk)

1. During-drag artifacts — the `WM_NORMAL_HINTS`/PMinSize-PMaxSize
   experiment (shim-side, making Wine publish the band so KWin refuses
   out-of-band drags pre-apply) would remove sliver/strip/rubber-banding in
   one stroke. Highest polish value; needs its own careful branch.
- 2. Launcher messaging — print the window-mode rules at launch (one line:
   "window mode: safe-fit maximize, height band 820–1040") so behavior
   reads as designed, not broken.
3. Fit ergonomics — a keybinding or tray affordance for
   `bin/ableton-proton-fit`; possibly a `--restore` counterpart.
4. A dedicated WayDAW window-control overlay — only if the mode sticks
   long-term; heavyweight.

## 5. Explicitly not chased now (destabilization risk)

- True full-height maximize (the storm).
- KWin persistent rules (policy: runtime scripting only).
- External writers of Wine-owned X properties (measured two-writer churn).
- Auto height completion through Wine's opaque win32↔X mapping: three
  mechanisms were prototyped live (KWin-write + heal, message/timer-based
  shim completion, watcher-thread shim completion); instrumentation showed
  the app's Win32 belief already at band top while Wine presented 66 px
  less — the discrepancy lives inside Wine's NC/mapping accounting, varies
  by decoration state, and touching it means modifying the storm-critical
  clamps on guesswork. All three prototypes were REVERTED; the shim on this
  branch is byte-identical to the merged, validated one.

## 6. Recommendation

**Proceed as "stable WayDAW window mode" — merge after validation.** The
native-feel gap is real but the alternative (chasing indistinguishability
from a native KDE app) runs through exactly the mechanisms that caused
weeks of storms: full-height geometry, Wine property races, and NC-mapping
internals. The honest product definition:

- `./bin/ableton-proton` runs Ableton in a constrained, stable
  presentation mode.
- Maximize means safe-fit (full width, height kept), toggled by a second
  click. It is not native maximize and does not claim to be.
- Height is bounded for safety: ~820 to ~1040.
- Known limitations: during-drag visual artifacts, the menu double-click
  quirk, lingering maximize atoms.
- Stability and recoverability beat perfect native feel.

Ship that, say it clearly (launcher line + README), and revisit native
feel only through the one experiment with real leverage
(`WM_NORMAL_HINTS`) when there is appetite for a new investigation branch.
