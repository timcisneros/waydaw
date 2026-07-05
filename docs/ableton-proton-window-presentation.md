# Proton-exp window presentation — diagnosis (2026-07-04)

Proton-exp **liveness is solved** (see `docs/ableton-proton-*`): the UI thread
executes, no SRW deadlock, the authorization dialog accepts clicks. A separate
**window-presentation** defect was then reported under
`WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`: no top bar, frameless window,
a black bar at the bottom, UI looks cut off at the bottom.

This note is diagnosis only. **No fix was applied** — the effective fix is a
KWin-rule change, which this task's constraints forbid without explicit
approval. The working prefix was not touched; no authorization was attempted.

## Evidence (copied prefix, read-only)

Main window `0x0b200003` under Proton-exp:

- `xwininfo`: `0,0 1920x1080` (full physical screen), Map State IsViewable.
- `_NET_FRAME_EXTENTS = 0, 0, 0, 0` (KWin drew **no** frame).
- `_MOTIF_WM_HINTS = 0x3, 0x6, 0x0, 0x0, 0x0` → decorations field **= 0**
  (the client, Wine, requests **no** WM decorations).
- `_NET_WM_STATE = MAXIMIZED_VERT, MAXIMIZED_HORZ`; `WM_CLASS = "steam_proton"`.
- Wine X11 registry in the copied prefix: `Decorated="Y"`, `Managed="Y"`; no
  per-app `Decorated="N"` override; no virtual-desktop keys.
- Thread state: `main_thread_in_srw_exclusive=no`, no `SendMessageW` wedge,
  `forward_progress=executing`, CPU ~44 ticks/3s — healthy, not the deadlock.
- The window **buffer** (captured with `import -window`) shows the **complete**
  1920x1080 Ableton UI including the bottom status bar. The on-screen black
  bottom region is therefore a presentation artifact of the borderless-
  fullscreen surface, not a render/content failure.

Historical staging capture (working prefix, system wine-staging), for contrast:

- Same `_MOTIF_WM_HINTS = 0x3, 0x6, 0x0, 0x0, 0x0` (decorations **= 0**), but
- `_NET_FRAME_EXTENTS = 0, 0, 28, 0` (a **28px titlebar** was drawn).

Existing KWin rule (`~/.config/kwinrulesrc`, read-only), single rule present:

```
Description=Window settings for ableton live 12 suite.exe
noborderrule=3            # Force
title=Untitled - Ableton Live 12 Suite   titlematch=1
wmclass=ableton live 12 suite.exe        wmclassmatch=1 (exact)
types=1
```

Live reversible test (window-scoped, no global/prefix change): un-maximizing
the Proton window to 800x643 and requesting full Motif decorations still left
`_NET_FRAME_EXTENTS=0` — i.e. with no matching KWin rule, KWin honors Wine's
no-decoration request and draws no frame. The window was restored to its
maximized state afterward.

## Root cause

Wine emits `_MOTIF_WM_HINTS decorations=0` for Ableton's main window under
**both** runners. Under **system wine-staging** the window's `WM_CLASS` is
`ableton live 12 suite.exe`, which **matches** the KWin rule; the rule
(`noborderrule=3`, forcing border-on) **re-adds the titlebar** → decorated
(28px top). Under **Proton-exp** the window's `WM_CLASS` is `steam_proton`
(Proton overrides it), so the rule **does not match**, KWin honors Wine's
no-decoration hint, and the window is **frameless full-screen** → no top bar,
frameless, and a borderless-fullscreen surface whose bottom presents as a
black bar / apparent cut-off.

Ruled out: SRW deadlock (thread healthy); DXVK (buffer renders full UI);
`WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY=1` suppressing decoration setup
(`Decorated=Y`/`Managed=Y` are already set in the copied prefix, so the skipped
`configure_ableton_windowing` would be a no-op); prior copied-prefix registry
leak (no `Decorated=N` anywhere). The defect is a **WM_CLASS mismatch** between
Proton (`steam_proton`) and the decoration-restoring KWin rule
(`ableton live 12 suite.exe`).

## Fix (requires explicit approval — a KWin rule change is out of scope here)

Smallest correct fix: make the decoration-restoring KWin rule also cover the
Proton window. Two concrete options, for the user to choose:

1. **Match the Proton window in KWin.** Add/adjust a rule that forces
   border-on for `wmclass=steam_proton` AND title contains "Ableton Live 12
   Suite" (title-scoped so it does not affect other Proton apps). The existing
   `bin/install-ableton-kwin-rule` is the WayDAW-sanctioned tool to manage this
   rule and could be extended to add the Proton match. This is a **global KWin
   change** and must be done with the user's approval.
2. **Make Proton emit the expected `WM_CLASS`.** If the Kron4ek Proton build
   can be made to report `WM_CLASS=ableton live 12 suite.exe` instead of
   `steam_proton` (no standard Wine env for this is known; needs
   investigation), the existing rule would match with **no** KWin change — the
   preferable outcome if achievable, since it keeps the fix runner-scoped.

Not viable: copied-prefix Wine registry keys (`Decorated`/`Managed` are already
correct and cannot override the per-window Motif hint); DXVK/Wine-base changes
(out of scope and not the cause); a launch-time geometry clamp (would fight the
app and not restore the titlebar).

## What remains later (still excludes authorization)

- Choose and apply one of the two fix options above (option 1 needs KWin-rule
  approval; option 2 needs a Proton `WM_CLASS` investigation).
- Re-verify after the fix: top bar present, framed window, no bottom black bar,
  and re-confirm thread health (no SRW deadlock, no `SendMessageW` wedge).
- Authorization remains a separate, user-owned step and is **not** required to
  resolve this presentation issue.
