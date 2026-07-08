# Proton-exp decoration / menu-bar occlusion on resize (diagnosis, 2026-07-07)

Opened after the sizing-shim branch (`fix/proton-sizing-shim`) solved the
message-pump resize storm but exposed this **separate, pre-existing** blocker.
Diagnosis only — no fix here; explicitly kept out of the sizing-shim validation
session per instruction.

> **Note on the name:** the file is named "occlusion" from the first hypothesis
> (titlebar-over-menu). That hypothesis is **disproven** below — the menu loss
> is an app-side decoration-mode switch, not a KWin occlusion. Kept the
> filename for continuity; read the root cause, not the title.

## Symptom

With the sizing shim active (storm gone, height freely resizable), resizing the
Ableton main window **shorter** produces a flicker during the drag and
**eventually makes the top File/Edit menu bar disappear**. The app is otherwise
responsive (no storm) but the missing menu bar makes it awkward-to-unusable.

## Captured failure state (window hand-resized to 1709×331)

| datum | value |
|---|---|
| geometry | 1709×331 @19,213 |
| `_MOTIF_WM_HINTS` | `0x3,0x3e,0x0,0x0,0x0` — **decorations field 0x0 (borderless)**; startup value was `0x7a` |
| `_NET_FRAME_EXTENTS` | `0,0,28,0` — KWin **still drawing a 28 px titlebar** |
| `_NET_WM_STATE` | `_MAXIMIZED_VERT,_MAXIMIZED_HORZ` — **stale** (331 px tall, not maximized) |
| main UI thread | ~14 % of a core — **calm, NOT storming** |
| guard events (90 s) | undo-vmax 0, cap-height 0, re-pin 0 — all guards quiet |
| client top row (y=0) | grey control bar (129); the File/Edit menu row is **not in the client render** |

Evidence artifacts (session scratchpad only): `decoration-occlusion-evidence.txt`,
`decoration-occlusion-full.png`, `decoration-occlusion-topstrip.png`,
`menubar-state.png`.

## Original hypothesis — DISPROVEN

The initial guess was "the KWin titlebar draws over Ableton's menu row" (a pure
occlusion). The read-only reproduction below **disproves** that: with the pin
OFF and KWin's titlebar fully removed (`_NET_FRAME_EXTENTS = 0,0,0,0`), the
File/Edit menu is **still gone**. The menu loss is **app-side**, not a titlebar
occlusion.

## Reproduction (read-only, 2026-07-07, sizing shim active)

Launched `./bin/ableton-proton` (copied prefix, shim cap 1040), loaded the real
controller **plus** a read-only KWin observer script
(`waydaw-deco-observer`, logs `noBorder`/`maximizeMode`/`fullScreen`/geometry;
mutates nothing). Drove geometry with `xdotool windowsize` and sampled
`xprop` + `import` screenshots. No clicks into auth surfaces.

**Finding 1 — Ableton flips its own decoration mode by height.** A synthetic
height sweep at fixed width:

| frame height | `_MOTIF_WM_HINTS` decorations | menu row |
|---|---|---|
| 966 (startup), 900, 800, 780, 760 | `0x7a` (decorated) | **present** |
| 740, 730, 720, 700, 500, 400 | `0x0` (borderless) | **absent** |

The flip is crisp between **760 and 740** px on the way down. It is Ableton
(via Wine) rewriting its own `_MOTIF_WM_HINTS`, driven purely by window height
— not by the pin, not by maximize, not by width/aspect, not by the welcome
panel.

**Finding 2 — there is hysteresis.** Once borderless, the window stays
borderless well above the shrink threshold (observed borderless at 956 px), and
only re-decorates (`0x7a`) when grown back to ~1000+ px. So mode depends on
history, not just current height. Startup is decorated at 966; it only enters
borderless if height is dragged below ~750.

**Finding 3 — the menu absence is app-side, proven by removing the pin.**
Holding the window short (spam-`windowsize`, since a one-shot resize is bounced
back by Ableton's content-min):
- **Pin ON:** `_MOTIF=0x0`, `_NET_FRAME_EXTENTS=28` (titlebar kept), `re-pin`
  fires ~4/s (the pin fighting KWin's attempts to honor borderless). Titlebar
  drawn over Ableton's control bar; File/Edit menu absent. (Matches the user's
  live report exactly.)
- **Pin OFF:** `_MOTIF=0x0`, `_NET_FRAME_EXTENTS=0,0,0,0` (KWin drops the
  titlebar). No titlebar over anything — and the File/Edit menu is **still
  absent**; the client's top row (y=0) is the transport/control bar in both
  cases. Growing back tall re-decorates and the full
  `File Edit Create Playback View Navigate Options Help` row returns.

So Ableton, in its borderless/compact chrome mode (under Wine), does **not**
render the File/Edit menu bar at all. The KWin titlebar is a cosmetic overlay
on top of that, not the cause.

**Finding 4 — the stale maximized atoms are residue, not causal.** Throughout
the synthetic reproduction `maximizeMode` stayed `0` and no
`_NET_WM_STATE_MAXIMIZED_*` appeared; the menu still vanished on the height
flip. The maximized atoms seen in the user session came from their maximize
attempts and are unrelated to the menu loss. (They remain a minor separate
oddity: app-set atoms with `maximizeMode==0` that guard 2 is blind to.)

**Finding 5 — CPU stayed calm** (~5–15 % of a core) across every state; this is
purely a presentation-mode issue, never the message-pump storm.

## Root cause

Ableton Live switches between a **decorated** window mode (Motif `0x7a`,
File/Edit menu rendered in the client) and a **borderless/compact** mode (Motif
`0x0`, menu not rendered) based on window height, with hysteresis (down at
~750 px, back up at ~1000 px). Under Wine, the borderless mode simply omits the
menu bar. The KWin decoration-pin — added earlier to stop titlebar flicker and
keep a movable/closable titlebar during the auth/startup phase — keeps a 28 px
titlebar in the borderless state, which looks like occlusion and adds flicker
(re-pin fighting), but is **not** why the menu disappears.

## Is the pin now counterproductive? (goal 5)

Partly. In the borderless state the pin produces a cosmetic titlebar-over-
content mismatch and ~4/s re-pin churn as it fights KWin honoring `0x0`.
But dropping the pin does **not** restore the menu (Finding 3), so changing the
pin alone does not fix the blocker. The pin's original job (calm decorated
titlebar during auth/startup) is still valid there.

## Proposed fix (NOT implemented; needs its own validated pass)

**Floor the window height in the sizing shim so Ableton never enters the
menu-less borderless mode.** The shim already clamps `ptMaxTrackSize.y` to the
max cap (1040); add a `ptMinTrackSize.y` floor safely above the decoration
flip (e.g. ~820, comfortably above the ~750 down-flip) in the same
`WM_GETMINMAXINFO` handler. The legal height band becomes roughly
`[~820, 1040]` — always decorated, menu always visible, storm still prevented,
and no KWin decoration change needed. This keeps the fix **app-scoped in the
shim** (where the diagnosis proves it belongs, since the trigger is
height-driven app behavior), not in the KWin controller, and touches no
persistent KWin settings.

- **Tradeoff:** the user can no longer make the window shorter than ~820 px —
  acceptable, since a shorter Ableton window has no menu bar and is not useful.
- **Why not fix the pin instead:** proven insufficient (menu is app-side).
- **Why not clear the maximized atoms:** they are residue, not the cause.
- **Validation required (real user drag, synthetic is insufficient):** confirm
  the floor holds during an interactive edge-drag; menu stays visible at the
  floor; storm still absent; width resize after height still calm; File menu
  opens + Escape closes; auth/demo path intact; cleanup clean; working-prefix
  and KWin hashes unchanged. Confirm the exact floor value against the measured
  flip threshold (shim logs the Win32 heights).

## Does the sizing shim branch remain blocked?

**Yes.** `fix/proton-sizing-shim` stays not-merge-ready: with only the max cap,
a user can still drag the window into the menu-less borderless mode. The
proposed min-height floor is the smallest fix and lives in the same shim, so it
should be prototyped on a shim fix branch (not this diagnosis branch) and
validated with a real hand-resize before the Proton-exp resize experience is
acceptable.

## Constraints honored this session

No authorization; no credentials; auth dialog never touched (only synthetic
`windowsize` on the main window + read-only `xprop`/`import`). Working prefix
untouched (copied Proton-exp prefix only). No Wine virtual desktop; no package
installs. KWin persistent settings unchanged (`kwinrc`/`kwinrulesrc` hashes
byte-identical before/after); the observer and controller are runtime scripting
only, both unloaded at cleanup. `cleanup_result=clean`, zero
Ableton/Wine/Proton/WebView2 processes, working-prefix DXVK hashes unchanged.
No fix implemented. Do not merge or push from a diagnosis branch.

---

# Fix implemented: min-height floor (2026-07-07, `fix/proton-sizing-shim-minheight`)

The proposed floor was prototyped and validated with real user hand-resize.
It took **three layers** to make the short-resize path safe — the shim floor
alone was necessary but not sufficient.

## Layer 1 — Windows-side floor in the sizing shim (primary)

`compat/ableton-sizing-shim/version-shim.c`: the existing `WM_GETMINMAXINFO`
handler now also raises `ptMinTrackSize.y` to a floor (observed startup value:
app asks 34 early, 677 later → floored to 820). Belt-and-braces: a guarded
`WM_WINDOWPOSCHANGING` upward clamp (`cy >= 200 && cy < floor && !IsIconic`)
for message-carrying paths that skip minmax; minimize rects are left alone.
The floor is clamped to never exceed the cap (empty-band guard).

- `WAYDAW_ABLETON_SIZING_MIN_H` (launcher) → `WAYDAW_SIZING_SHIM_MIN_H`
  (DLL), **default 820**; cap unchanged: `WAYDAW_ABLETON_SIZING_CAP_H` →
  `WAYDAW_SIZING_SHIM_MAX_H`, **default 1040**. Legal band: `[820, 1040]`.
- **Why 820:** the decorated→borderless flip is at frame ~740–750; 820 leaves
  ~70 px of margin (interactive drags overshoot the constraint transiently by
  ~25–55 px before Wine re-asserts, measured), while keeping ~220 px of usable
  shrink range below the 1040 cap.
- Dry-run now discloses the floor (`sizing_shim_min_h=820`) alongside cap,
  source DLL, target, and no-mutation; `bin/verify-proton-runner-mode` gained
  6 checks (floor disclosed, default 820, overridable, cap still 1040 and
  independent) — **62/62 PASS**.

**Result:** the app-side mode switch is fully prevented. Across every shrink
attempt (interactive and synthetic, granted X heights as low as 28 px),
`_MOTIF_WM_HINTS` stayed `0x7a` and the File/Edit row never disappeared. The
app's height *belief* never goes below the floor, so the compact mode cannot
latch. This confirms the diagnosis: the switch is driven by the Win32-side
height, not by the X geometry.

## Layer 2 — KWin floor backstop (guard 4 in the decoration controller)

Real hand-resize exposed a gap the shim cannot cover: **Wine adopts
WM-imposed configures through a raw path that sends no sizing messages**
(the shim's `WM_WINDOWPOSCHANGING` floor counter stayed 0 throughout). A hard
interactive shrink left the X window **stuck at 861×41** — a sliver — while
the app still believed it was tall (`_MOTIF` still `0x7a`, CPU calm, menu
intact but unusable at 41 px).

`config/kwin/waydaw-ableton-decoration.js` gained guard 4: any granted frame
height `< 800` is raised to `848` (the WM-frame equivalent of the shim band
bottom; win32 ≈ X client here, +28 px titlebar).

**Hard-won lesson (measured):** the first version clamped unconditionally
inside `frameGeometryChanged` and degenerated into a compositor-level
geometry war during held shrink drags — **3858 writes in ~12 s**, making ALL
interactive resizing sluggish with repaint bars. The fixed guard (a) stands
down entirely while `w.resize === true` (mid-drag slivers are harmless — the
shim protects the app's belief), (b) corrects once on
`interactiveMoveResizeFinished` / next settle, (c) rate-limits writes to one
per 400 ms per window, like guard 2. After the fix: exactly one floor write
per release (releases at 110/66/56 px → one write each → settled ≥ floor).

## Layer 3 — post-resize renegotiation nudge (guard 5)

Tall drags exposed the mirror-image gap: when an interactive resize ends,
the app's counter-configure can be lost (KWin ignores client configure
requests during the drag), leaving the X window **taller than the app
paints** — measured X client 1032 vs painted 1006, a permanent 26 px black
bar at the window bottom (screenshot row means: 0.0 below y≈1007). A 1 px
external resize forced renegotiation and healed it instantly (app's
preferred size won, bar repainted).

Guard 5 automates exactly that: when an interactive resize on the target
window finishes, shrink the frame height by 1 px once. If the app adopted
the dragged size the pixel is imperceptible; if the counter-configure was
swallowed, the renegotiation replays and the mismatch heals. Cannot loop
(the per-resize flag is consumed before the write).

## Validation (real manual resize; copied prefix reseeded to stock bad 1096)

- Startup: placement clamp `1096→1000`; shim loaded
  (`cap_h=1040, min_h=820`); controller loaded; decorated `0x7a`; menu
  visible; `_NET_WM_STATE` empty (no stale maximized atoms); UI thread calm.
- Hard shrink drags (repeated, to granted heights 28–139 px): window
  rubber-bands or pops back on release; **never settles below the floor;
  menu row visible throughout; Motif never left `0x7a`**.
- Tall drag: during-drag black strip (inherent paint lag), **heals on
  release** via guard 5.
- Width after height: normal feel (the sluggishness seen mid-session was the
  guard-4 war, fixed above).
- File menu opens; Escape closes it. UI thread ~5–15%; no storm at any
  point; `WM_GETMINMAXINFO` polling is ordinary DefWindowProc traffic.
- Working-prefix DXVK and `kwinrc`/`kwinrulesrc` hashes byte-identical
  before/after; working prefix has no shim DLL; no auth interaction.

## Remaining limitations

- **During-drag visuals:** shrink drags show a transient sliver, tall drags a
  transient black strip, until release. Root fix would be publishing
  `PMinSize`/`PMaxSize` in `WM_NORMAL_HINTS` so KWin constrains the drag
  itself, but Wine owns that property and external X-property writers made
  churn measurably worse before — deferred as a future experiment.
- **File-menu double-click after Esc:** after Escape closes the menu, the
  next File click dismisses immediately and needs a second click. Wine
  menu-capture quirk; shim cannot plausibly cause it (menus are popups,
  never subclassed; no input messages handled). Pre-existing; cosmetic.
- Floor/restore constants in the KWin script (`800`/`848`) are fixed (KWin
  scripts cannot read env vars); the shim-side floor is the configurable one.

## Merge readiness

With this branch, the short-resize blocker recorded above is **fixed**: the
window cannot settle in the menu-less compact/borderless mode, and the
File/Edit row survived every shrink attempt in real hand-resize testing.
The sizing-shim line (`fix/proton-sizing-shim` + this branch) is now
functionally complete for the Proton-exp resize experience and ready for
closeout audit; merge remains held per project policy (nothing merged,
nothing pushed).
