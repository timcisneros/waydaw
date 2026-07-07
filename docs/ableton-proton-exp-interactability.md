# Proton-exp interactability diagnosis (2026-07-06)

User report: with the lifecycle-integrated KWin decoration controller, the
Proton-exp Ableton window "may not be interactable". Interactability is a
separate acceptance gate from liveness and decoration stability; this note
records a controller-enabled vs controller-disabled A/B diagnosis.

Branch: `diagnosis/proton-exp-interactability` from `main @ 0ca7d51`.
Copied prefix only; no authorization; no clicks or typing anywhere; safe
focus/activation (`wmctrl -ia`) only. Working prefix and KWin settings
hash-verified unchanged before/after.

## Method

Two identical launches, full cleanup between:

- **A:** `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`
  (controller auto-loaded, verified `loaded=true`)
- **B:** `WAYDAW_ABLETON_RUNNER=proton-exp WAYDAW_ABLETON_KWIN_CONTROLLER=0 ./bin/ableton`
  (controller verified `loaded=false`, zero controller log lines)

Per launch: window/property census (`wmctrl -lpG -x`, `xprop` on main +
dialog: `WM_HINTS`, `WM_PROTOCOLS`, `_NET_WM_STATE`,
`_NET_WM_ALLOWED_ACTIONS`, `WM_TRANSIENT_FOR`, `_MOTIF_WM_HINTS`,
`_NET_FRAME_EXTENTS`, stacking), activation of main then dialog via
`wmctrl -ia`, 18 s focus-stability sampling
(`_NET_ACTIVE_WINDOW`/`xdotool getwindowfocus`), and
`bin/ableton-thread-endstate-capture`.

## Results — A and B are IDENTICAL in every measured dimension

| observation | A (controller on) | B (controller off) |
|---|---|---|
| main window | `0x09200003` normal, `MAXIMIZED_VERT`, decorated | same |
| auth dialog | `0x09200091` 512x479 Dialog, `WM_TRANSIENT_FOR=main`, `SKIP_TASKBAR` | same |
| input model (both windows) | `WM_HINTS input=False` + `WM_TAKE_FOCUS` protocol | same |
| `wmctrl -ia <main>` | focus lands on the **dialog** (`_NET_ACTIVE_WINDOW=0x9200091`, dialog `FOCUSED`, raised) | same |
| `wmctrl -ia <dialog>` | dialog `FOCUSED`, stable for 18 s, no drops | same |
| liveness | no SRW, no `SendMessageW` wedge, executing, ~350 ticks/3 s | same (~346) |

Key mechanics confirmed working in BOTH runs:

1. **The `WM_TAKE_FOCUS` path works under Proton-exp.** Both windows use the
   ICCCM "globally active" input model (`input=False` + `WM_TAKE_FOCUS`):
   KWin sends `WM_TAKE_FOCUS` and the *client* (Wine) must claim focus
   itself. It does — the dialog becomes `_NET_WM_STATE_FOCUSED` and
   `xdotool getwindowfocus` confirms real X input focus on it. (Under the
   old system wine-staging SRW deadlock, exactly this path was dead.)
2. **Activation of the main window is redirected to the dialog.** That is
   Wine faithfully forwarding Ableton's application-modal relationship: the
   auth dialog is modal over the editor. Wine re-raises the dialog and
   focuses it; the editor also briefly flags `DEMANDS_ATTENTION` during
   startup (seen in flicker probes) — the standard "you must deal with the
   modal dialog first" pattern.

## Interpretation

- **The KWin decoration controller is NOT implicated.** With the controller
  fully absent (B), focus, stacking, modality, and liveness behave
  identically. The controller also has no mechanism to affect input: it
  flips only KWin's internal `noBorder` flag and never touches input focus,
  the input model, or any X property.
- **While unauthorized, the ONLY intended interactable surface is the
  authorization dialog.** The main editor window is deliberately blocked by
  the app's own modal dialog. Clicks on the editor doing nothing is
  *expected Ableton behavior in this state*, not a defect.
- The WM-level evidence says the dialog *can* receive input (it holds real
  X focus stably), and phase-completion evidence (2026-07-04, controller
  not yet existing) already validated that this dialog **accepts user
  clicks** under Proton-exp. This diagnosis could not re-verify actual
  click delivery without violating the no-click constraint.
- **Most plausible explanation for the user report** (manual-observation
  mismatch): clicking the *editor* while the auth dialog is open — possibly
  with the dialog ended up *behind* the maximized editor and invisible
  (it is `SKIP_TASKBAR`, so it has no taskbar entry to find it by; during
  startup churn its stacking can vary). The session then looks like "a
  window that ignores input" even though the app is healthy and the dialog
  is interactable.

## Manual safe test (user-owned, no authorization)

1. Launch `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`.
2. If no dialog is visible, press Alt+Tab (the dialog is not in the
   taskbar) or run `wmctrl -ia $(wmctrl -l | awk '/^0x/ && $NF=="Suite" {print $1}')`.
3. Drag the auth dialog by its titlebar — it should move.
4. Optionally click **Authorize later** (this does NOT authorize; Live runs
   in demo mode) and check the editor becomes interactable (menus, track
   clicks). Authorization itself remains deferred to project completion.

If step 3 or 4 fails with the dialog visibly focused, THAT is a real input
bug — report back and this diagnosis reopens (next probe would be
XInput/event-delivery level, not window-manager level).

## Verdict

- Issue does **not** reproduce at the window-manager level: activation and
  focus work identically with and without the controller.
- The controller is **not implicated**; no controller change is needed.
- **Presentation phase is not blocked** by this finding: the unauthorized
  state exposes exactly one interactable surface (the modal auth dialog),
  which holds focus correctly; the editor unblocks only when the dialog is
  dismissed (demo mode) or after eventual authorization.
- No fix implemented (nothing to fix at this layer). If the manual safe
  test fails, reopen with an input-event-level probe.

Hygiene: both sessions cleaned (`cleanup_result=clean`), controller
`loaded=false` at end, zero Ableton/Wine/WebView2 processes, working-prefix
DXVK hashes and `kwinrulesrc`/`kwinrc` hash-verified unchanged. Ableton was
launched twice (copied prefix), no authorization attempted, no auth buttons
clicked, no text entered.
