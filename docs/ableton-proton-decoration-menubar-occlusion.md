# Proton-exp decoration / menu-bar occlusion on resize (diagnosis, 2026-07-07)

Opened after the sizing-shim branch (`fix/proton-sizing-shim`) solved the
message-pump resize storm but exposed this **separate, pre-existing** blocker.
Diagnosis only — no fix here; explicitly kept out of the sizing-shim validation
session per instruction.

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

## Working hypothesis

On resize, Ableton/Wine re-derives its Motif window hints and drops the
decoration hint to `0x0` (borderless), but the KWin decoration-pin keeps a
28 px titlebar (`_NET_FRAME_EXTENTS=28`). Ableton then lays out its top menu
row assuming **no** titlebar, so KWin's titlebar draws over it and the menu bar
is occluded. This is the **known decoration-churn / white-top-strip family**
(the titlebar-flicker the decoration-pin was written to fight, see
`docs/ableton-proton-custom-presentation-controller.md` and
`docs/ableton-proton-exp-message-pump-starvation.md`), previously invisible
because the height was frozen (cap 1000 → band 966..1000) and the churn was
never entered. A stale `MAXIMIZED_VERT/HORZ` atom pair — set app-side WITHOUT a
KWin maximize, so `maximizeMode` stays 0 and guard 2 is blind — is part of the
same decoration-state confusion and may compound it.

This is **not** the sizing shim's doing (the shim touches only WM sizing
messages, never decorations) and **not** the message-pump storm (UI thread
calm). It is a decoration/presentation-layer bug.

## Open questions for the fix pass (not yet investigated)

1. Is the menu bar truly **occluded under the titlebar**, or is Ableton
   **not rendering** it (client-side responsive hide) at short heights?
   Distinguish by sampling client pixels at negative-vs-positive y against the
   KWin frame origin, and by checking whether the menu bar returns if the
   titlebar is dropped.
2. Why does the Motif decoration hint drop to `0x0` specifically on resize?
   Is it every resize, only shrink, or only crossing a threshold?
3. Can the decoration-pin be made to keep KWin's border **and** Ableton's
   content aligned — e.g. by NOT pinning the border when Wine requests
   borderless (accept borderless + provide move/close another way), or by
   forcing a consistent decorated geometry so the client reserves the 28 px?
   Both directions have prior tradeoffs (borderless loses titlebar; forcing
   fights Wine) — needs measurement.
4. Should the stale `_NET_WM_STATE_MAXIMIZED_*` atoms be cleared, and does
   clearing them restore the menu bar? (guard 2 is blind to app-set atoms with
   `maximizeMode==0`.)

## Constraints (unchanged)

No authorization / credentials / binary patching / working-prefix mutation /
Wine virtual desktop / package installs / KWin persistent-settings mutation.
Copied Proton-exp prefix only; Proton-exp opt-in. Do not merge or push from a
diagnosis branch.
