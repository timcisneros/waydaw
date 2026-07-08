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
