# Ableton authorization-dialog interaction — first-principles rethink

Date: 2026-07-03. Analysis-only note; no runtime behavior, prefix, KWin, DXVK,
or launcher change is made by this document. Companion to
`docs/ableton-wine-current-findings.md` (evidence source of record).

## Problem statement

Ableton Live 12 Suite launches under system Wine 11.0 Staging (DXVK active,
forced XWayland via `env -u WAYLAND_DISPLAY`). The visible blocker is the
native Ableton **software authorization welcome dialog** (512x479, identified
visually on 2026-06-25). It is mapped, viewable, on-screen, and topmost among
the Ableton windows — but it cannot be interacted with, and explicit
activation requests do not make it focused.

This note deliberately re-derives the failure model instead of extending the
previous one.

## 1. Evidence ledger

### What we know (observed, deterministic unless noted)

- **The blocker is Ableton's own authorization dialog, not a ghost.** X11
  ownership probe: `_NET_WM_WINDOW_TYPE_DIALOG`, transient for the main
  window, same Ableton PID, `blocker_is_webview2=no`,
  `blocker_is_kprior_crash=no`. Visual capture shows legitimate
  online / offline / defer authorization choices. The license state explains
  it: `Log.txt` reports no valid Suite license, `IsUnlocked?=false`. The
  dialog is *expected* first-run behavior, not a stuck artifact.
- **Geometry is ruled out.** Dialog at `333,322 512x479` on 1920x1080; main
  window fits the screen (xwininfo ground truth). The earlier "28px
  overshoot" was a wmctrl XWayland reporting artifact.
- **Both Ableton windows use the ICCCM "Globally Active" input model.**
  `WM_HINTS input = False` plus `WM_TAKE_FOCUS` in `WM_PROTOCOLS`, on both
  the dialog and the parent. Under this model the window manager never
  assigns X input focus directly — not on activation requests and not on
  clicks. The *client* must call `XSetInputFocus` itself when it receives the
  `WM_TAKE_FOCUS` client message. Focus success is therefore contingent on a
  live, responsive client event loop.
- **Two explicit activation requests both failed identically.**
  `wmctrl -ia <dialog>` and `wmctrl -ia <parent>`: `_NET_ACTIVE_WINDOW`
  remained the terminal at +1s and +5s, no `_NET_WM_STATE_FOCUSED`, dialog
  visually unchanged, Ableton process alive.
- **KWin configuration is permissive and unexceptional.**
  `focusPolicy=ClickToFocus`, `focusStealingPreventionLevel=1` (low),
  the only matching KWin rule is `noborderrule=3` (no focus/activation
  override).
- **A native X11 session did not help.** The earlier X11 vs Wayland A/B
  showed the same non-interactivity/freeze family, so the general failure is
  not specific to Wayland/XWayland focus mediation. (Caveat: the *specific*
  authorization-dialog activation test has only been run under the Wayland
  session.)
- **WebView2 crash-loops in every run** (GPU process exits → browser process
  exits → `KPriorCrash`), but the corrected ownership classifier proves
  WebView2 does **not** own the blocking window, and Ableton plus its native
  authorization dialog stay alive through the WebView2 crashes.
- **Disabling the WebView2 runtime stopped the crashes but did not restore
  interactivity** (2026-06-16 test, restored afterward). So WebView2 is a
  real failure surface but eliminating its *processes* is not sufficient.
- **State-reset bypasses do not remove the dialog:** crash-recovery metadata
  bypass, explicit `.als` launch, isolated WebView2 user data, device-scale
  changes, and `Preferences.cfg` reset all left the same 512x479 modal host.
  (Expected in hindsight: an unauthorized install must show this dialog.)
- **Longstanding cursor disappearance over the main editor window** (user
  observation, predates all tests).
- **Earlier sessions crashed *on interaction*** — meaning at some point input
  events did reach the process and triggered activity.
- Wine logs report unavailable Windows Web Authentication activation classes
  (relevant to the *online* authorization path once the dialog is usable).

### What we do not know

- **Whether Ableton's window-owning thread is pumping messages at all** while
  the dialog is visible. Never measured. Every observed symptom is
  compatible with a blocked UI thread.
- **Whether KWin actually sends `WM_TAKE_FOCUS`** in response to the
  activation request, and whether Wine's event handling receives it. No
  client-message trace has been captured.
- **Whether a real pointer click on the dialog delivers press events** into
  the Wine process. Automation has never clicked (authorization boundary);
  the user reports the dialog is not interactable, but we have no event-level
  trace of a click.
- **Whether `input=False` is normal for Wine windows on this system** or a
  signal that the Win32 windows are in a special state (e.g. disabled). We
  have no control comparison against a known-good Wine app (notepad/winecfg)
  in the same session.
- **Whether the dialog is Win32-disabled** (`WS_DISABLED` via a modal loop
  whose owner window died — e.g. a crashed WebView2 start-screen host),
  which would make Wine discard input regardless of X focus.

### Prior assumptions that may be wrong

1. *"This is a focus/window-manager problem."* Under the Globally Active
   model, a WM cannot focus a client whose event loop is dead. KWin refusing
   to mark the window active is exactly what a *correct* WM does when the
   client never responds to `WM_TAKE_FOCUS`. The observed "focus failure"
   may be a symptom, not the defect.
2. *"WebView2 is ruled out."* It is ruled out as the **owner of the blocking
   window**, not as the thing that blocks/disables the UI thread that owns
   the dialog (e.g. a synchronous wait on WebView2 controller creation, or a
   modal chain left disabled by the crashed start-screen host).
3. *"Interaction fails."* We have actually only proven **activation fails**.
   Click delivery has never been traced. These have different causes and
   different fixes.
4. *"No virtual desktop is a neutral constraint."* Wine's virtual desktop
   replaces the KWin↔client focus contract with Wine-internal activation
   (one InputHint=True top-level; Wine routes Win32 activation itself). If
   the defect is in the `_NET_ACTIVE_WINDOW`→`WM_TAKE_FOCUS`→client path, a
   virtual desktop bypasses it entirely — which makes it a *discriminating
   diagnostic*, not merely an unwanted hack. If the defect is a dead UI
   thread, a virtual desktop changes nothing. The constraint is reasonable as
   a product decision but should not forbid a one-shot copied-prefix
   diagnostic if step-1 evidence points at focus protocol.
5. *"The dialog blocks the app."* Causality may be inverted: the app-wide
   input problem (freeze, cursor loss, crash-on-interaction) predates and
   accompanies the dialog. The dialog is just the first surface the user
   must click.

## 2. Competing hypotheses

Ranked by how much observed evidence each one explains.

**H1 — Blocked/starved client event loop (leading).** Ableton's
window-owning thread is not pumping (or pumps intermittently), plausibly
stuck in or throttled by the WebView2 start-screen/controller path that is
simultaneously crash-looping. Explains: activation ignored twice (no
`WM_TAKE_FOCUS` response possible), clicks dead (no `WM_LBUTTONDOWN`
processing), cursor disappearing over the window (no `WM_SETCURSOR`
processing → stale/null cursor), "freeze", and why KWin/X11-session/geometry
changes never mattered. Tension to resolve: the dialog painted coherently at
capture time (rendering may be on another thread or already committed), and
the WebView2-runtime-disabled test still wasn't interactable (so the block
must also occur on the graceful-failure path, or have a second cause).

**H2 — Win32 modal/disabled window chain.** The dialog (and parent) are
`EnableWindow(FALSE)`-disabled because some other Win32 modal loop — e.g. a
WebView2 host window whose browser process died — never re-enabled them.
Wine would then discard delivered input at the Win32 layer. Consistent with
`input=False` on *both* windows and with the dialog looking alive but eating
clicks. Discriminated by the same probe as H1 (thread stacks + Win32 window
enumeration via winedbg).

**H3 — Wine `WM_TAKE_FOCUS`/foreground logic defect.** The event thread
receives `WM_TAKE_FOCUS` but Wine declines to set foreground (e.g. it thinks
another window is modal or foreground-locked). Middle ground between H1/H2;
distinguishable only with an event-level trace or debugger.

**H4 — KWin focus-stealing / XWayland activation mediation.** KWin never
sends `WM_TAKE_FOCUS` (or mishandles XWayland activation). Weakened by:
permissive KWin config, no focus-related rules, and the same
non-interactivity in a native X11 session. Not fully dead because the
dialog-specific activation test only ran under Wayland. Cheap to
kill/confirm with a control app in the same session.

**H5 — Bad geometry / offscreen input region.** Ruled out by ground truth
(window on-screen; capture works). Only a shaped-input-region defect would
revive it; nothing points there.

**H6 — WebView2 child-window ownership of the blocker.** Ruled out as
*ownership* (corrected classifier). Survives only inside H1/H2 as the thing
that wedges the UI thread / modal chain.

**H7 — Ableton-specific authorization startup behavior under Wine.** The
auth dialog may run a custom message loop that behaves differently from the
main loop. Not separately testable from the outside; the H1 probe (thread
stacks) reveals it if true.

**H8 — The "no virtual desktop" constraint itself.** Not a root cause, but
possibly an over-constraint: it removes the one configuration that bypasses
the entire WM↔client focus contract. Re-admit it *as a copied-prefix
diagnostic only* if evidence lands on H3/H4.

## 3. Ideal solution criteria

The correct end state, regardless of which hypothesis wins:

1. **Stable launch** from `./bin/ableton` on Fedora KDE Wayland (XWayland),
   system Wine, DXVK active — no manual steps.
2. **Correct visible bounds** (already true; must not regress).
3. **Authorization dialog fully interactable** so the user can complete a
   *legitimate* authorization once (online or offline). After that the
   dialog should never gate startup again — the fix must also leave the
   main editor interactable, since the evidence says the input problem is
   app-wide, not dialog-specific.
4. **No flicker, or tolerable flicker** (secondary; explicitly deferred
   until interactivity works).
5. **No session/desktop mutation**: no KWin policy changes, no global DPI or
   scale changes, nothing that affects non-Ableton windows.
6. **Minimal WayDAW-specific hacks**: prefer fixing/configuring the actual
   defect layer (Wine focus handling, WebView2 startup, Ableton prefs) over
   compensating layers (KWin rules, cursor guards, geometry forcing) — the
   compensating-layer attempts have all failed anyway.
7. **Repeatable from script** with deterministic probes (the existing
   runner-test/ownership/capture harness stays the measurement instrument).

## 4. Decision matrix

Scales: evidence support (does current evidence say this addresses the
blocker?), risk, reversibility, likelihood of fixing the actual blocker,
constraint violation.

| Path | Evidence support | Risk | Reversibility | Likelihood | Violates constraints? |
|---|---|---|---|---|---|
| **A. Continue native XWayland WM + client-side diagnosis first** (thread stacks, control app, event trace) | **High** — every surviving hypothesis (H1–H4) is discriminated by it | Low (read-only) | Full | n/a (diagnostic, not fix — but selects the fix) | No |
| **B. Temporary Wine virtual desktop, authorization only** (copied prefix, one session) | Medium — fixes the blocker iff H3/H4; useless for H1/H2 | Low-medium (registry keys in a *copied* prefix; never the working prefix) | High (copied prefix discarded) | Medium | Yes (needs explicit approval; justified only after A points at H3/H4) |
| **C. Permanent Wine virtual desktop** | Low — nothing yet shows the WM contract is the defect; contradicts criteria 5–6 | Medium (permanent behavior change, alt-tab/fullscreen quirks) | Medium | Low-medium | Yes |
| **D. KWin rule / focus-policy adjustment** | **Low** — KWin config already permissive; X11 session failed the same way; no rule currently touches focus | Low | High | Low | Yes (KWin settings frozen during analysis) |
| **E. WebView2 / start-screen suppression** | Low as a *standalone* fix — runtime-disable already tested: crashes stopped, interactivity did not return | Low (reversible renames/env) | High | Low alone; medium *as part of* an H1 fix (unblock UI thread) | Borderline (prefix file renames) |
| **F. Different Wine version / prefix strategy** | Low short-term — five runner candidates ended blocked/abandoned; system Wine is the only runner that launches Ableton | High effort | High (copied prefixes) | Unknown, expensive to learn | No, but explicitly stopped by prior decision |
| **G. Separate authorization bootstrap mode** (dedicated one-time flow to get authorized, then normal launches) | Medium — matches the fact that the dialog is legitimate and one-time; but still requires *some* interactable path once (possibly via B) | Low-medium | High | Medium-high *for the dialog*; does not by itself fix app-wide input if H1 holds | Depends on mechanism chosen |

Reading of the matrix: **A dominates** — it is cheap, constraint-compliant,
and converts every other row from a guess into a decision. B and G are the
most plausible *fix shapes* afterward (B if focus-protocol, G as the product
packaging of whatever works), E re-enters only as an H1 remedy, D and C are
close to falsified, F stays stopped.

## 5. Recommended next move (one move)

**One read-only live diagnostic session that tests client-side liveness,
with a same-session control app.** Working prefix via the existing
non-mutating diagnostic launcher mode (`WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY=1
WAYDAW_ABLETON_GRAPHICS=dxvk`), no authorization control clicked, no prefix /
KWin / DXVK / launcher changes. While the authorization dialog is visible:

1. **Control:** launch `wine notepad` (same prefix, same
   `env -u WAYLAND_DISPLAY` session). Record whether it can be focused and
   typed into, and capture its `WM_HINTS.input` + `WM_PROTOCOLS` for
   comparison with Ableton's `input=False`.
2. **Core datum:** attach non-interactively to the Ableton process and dump
   all thread backtraces (`winedbg` is installed: e.g.
   `winedbg --command "info process"` then per-thread `bt`, detach). The
   question answered: *is the thread that owns windows `0x…03`/`0x…08`
   parked in a normal message wait (`MsgWaitForMultipleObjectsEx`/
   `NtUserMsgWaitForMultipleObjectsEx`), or blocked in something else
   (WebView2 wait, loader lock, modal loop on a dead window)?*
3. **Passive corroboration (no extra launch):** one `wmctrl -ia` activation
   while watching `_NET_ACTIVE_WINDOW`/`_NET_WM_STATE` with `xprop -spy`, to
   timestamp whether anything at all changes client-side.

Why this is the smallest sufficient step: it splits the hypothesis tree at
the root. A blocked thread stack confirms H1/H2 and instantly retires
KWin/virtual-desktop/focus work; a cleanly pumping thread plus a focusable
notepad confirms H3 (Wine focus logic) and makes the copied-prefix
virtual-desktop test (path B) the justified follow-up; an *unfocusable
notepad* revives H4 (session/WM integration) and redirects everything.
It uses only installed tools, launches nothing new besides notepad, mutates
nothing, and respects the authorization boundary.

The fix is **not** implemented now: current evidence cannot yet distinguish
H1/H2 from H3, and those demand different fixes.

## 6. Stop conditions (what forces a pivot)

- **Control app cannot be focused either** → the defect is session-level
  (XWayland/KWin activation), not Ableton/Wine-app-level. Stop all
  client-side work; pivot to H4 with an event-level trace; KWin/Wayland
  becomes the primary surface despite the earlier X11 A/B.
- **Ableton UI thread is provably pumping normally AND `WM_TAKE_FOCUS`
  arrives but focus never moves** → H1/H2 are dead; pivot to Wine focus
  logic (H3): copied-prefix temporary virtual-desktop test (path B) and/or
  Wine `+event,+win` channel trace. Continuing "activation attempts" would
  be wrong.
- **UI thread is blocked in a WebView2/start-screen wait** → focus work is
  dead; pivot to start-screen/WebView2 unblocking (path E as remedy, path G
  as packaging). A virtual desktop would be provably useless — decline it.
- **Thread stacks normal + notepad fine + a (user-performed, legitimate)
  click on the dialog produces Win32 input in a trace but no UI response**
  → H2 confirmed: hunt the disabling modal owner via Win32 window
  enumeration, not X11 tools.
- **Meta stop-rule:** any proposed step that mutates more than one layer at
  a time, or repeats a launch without a new discriminating measurement,
  is evidence we are guessing again — stop and re-open this note.

## Diagnostic result (2026-07-03/04) — recommended next move EXECUTED

The section-5 diagnostic ran via the new read-only probe
`bin/ableton-auth-liveness-probe` (run bundle:
`logs/ableton-auth-liveness-probe/20260703-231014/`, plus manual follow-up
captures in the same directory). Working prefix launched through the
non-mutating diagnostic launcher mode; no prefix/KWin/DXVK mutation, no click
or keystroke into Ableton, authorization boundary preserved. Ableton was left
running afterward (unix pid 176090).

### Control result — notepad

`wine notepad` (same prefix, same `env -u WAYLAND_DISPLAY` session) mapped
fine and showed the **same** `WM_HINTS input=False` + `WM_TAKE_FOCUS` profile
as Ableton's windows — that hinting is standard Wine, **not** a
disabled-window signal (kills H2's main clue). Notepad was **not** activated
on map and `wmctrl -ia` did **not** activate it either. Meanwhile KWin
activated Ableton's dialog on map and again on focus-fallback after notepad
was killed. Conclusion: `wmctrl`-style external X-client activation requests
are unreliable session-wide under this KWin/Wayland session (focus-stealing
heuristics for script-launched X clients), so **the 2026-06-25 activation
failures were a measurement artifact and implicate neither Ableton nor Wine
focus handling**. H3 and H4 are retired as blocker candidates; H4 survives
only as a benign measurement caveat.

### Ableton client-liveness result — H1 confirmed, refined

The one clean activation attempt against the real authorization dialog
(`0x0aa00009`, 512x479) reproduced the June result exactly
(`_NET_ACTIVE_WINDOW` unchanged at +1 s/+5 s) — now explained by the above.

Thread evidence (winedbg attach/detach + `/proc` sampling, ptrace_scope=0):

1. **Startup phase:** the main/UI thread ran at ~94% CPU with ~76 k context
   switches per 3 s, three `WINPROC_wrapper` levels deep in re-entrant
   sent-message handling (msgs `0x401`/`0x406`), innermost app code polling
   `timeGetTime` — a nested pump spin, not a healthy message wait.
2. **End state (persistent across 23:17 → 05:02, ten identical samples):**
   the main thread is parked in `RtlAcquireSRWLockExclusive(0xB34E90)` called
   from `d3d11` (the prefix's DXVK debug 2.7 build), reached from *inside* a
   winproc that is itself handling a synchronous cross-thread message.
   CPU is now **0**; total lifetime CPU ~65 s over a 6 h process. The thread
   never ran again.
3. **The lock word reads `owners=0x0003, exclusive_waiters=0x0001`** — the
   SRW lock is genuinely held by three shared owners that never released it;
   the sole exclusive waiter is the UI thread. No living thread shows a
   d3d11 frame holding it (all DXVK workers idle in
   `SleepConditionVariableSRW`, which releases their locks) — the shared
   ownership is leaked/orphaned.
4. **Collateral:** Ableton helper thread `0188` is wedged in a synchronous
   `SendMessageW` to the dead UI thread. Every input, focus
   (`WM_TAKE_FOCUS`), cursor (`WM_SETCURSOR`) and close/ping message for both
   Ableton windows queues behind a thread that will never resume.
5. WebView2 was fully alive this session (browser/GPU-SwiftShader/renderer/
   network processes present, no crash-out during the probe) — the deadlock
   happened anyway, further detaching the blocker from WebView2.

### Verdict

**H1 confirmed with a specific mechanism: the UI thread first spins in
Ableton's nested sent-message pump, then deadlocks permanently on a leaked
shared-mode SRW lock inside the d3d11 (DXVK) layer under wine-staging 11.0.**
Every user-visible symptom (visible-but-dead authorization dialog, no focus
response, vanishing cursor, freeze, crash-on-interaction, X11-vs-Wayland
invariance, WebView2 independence) is downstream of this. Focus/KWin work,
virtual-desktop trials, and WebView2 suppression are all dead ends for this
blocker.

### Single next recommended move

Rerun the **existing reversible DXVK-version A/B**
(`bin/ableton-dxvk-version-test`, official 2.7.1 vs the installed 19 MB debug
2.7 build) **with thread-stack capture added** (the probe's winedbg sequence)
and compare end-state main-thread stacks. The earlier A/B judged only
user-visible usability; it never established whether the official build
reaches the *same* lock deadlock. Outcome decides the layer:
same deadlock under official DXVK → Wine 11.0 SRW/base problem (pursue newer
system Wine); no deadlock under official DXVK → the custom debug DXVK build
is the culprit (replace it). This uses an already-approved reversible
procedure and one launch.

## Relationship to existing constraints

This note changes no constraint. It flags one for conditional review: the
"no Wine virtual desktop" rule should be interpreted as "no *permanent*
virtual desktop," while a single copied-prefix virtual-desktop session
remains available as a *diagnostic* if and only if the recommended next move
lands on H3/H4. All other constraints (system Wine only, DXVK mandatory,
copied-prefix discipline, authorization boundary, no KWin/DPI mutation)
are reaffirmed by the evidence above.
