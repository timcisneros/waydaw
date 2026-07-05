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

## DXVK-version A/B with end-state thread capture (2026-07-04) — EXECUTED

Mechanism: `bin/ableton-dxvk-version-test` (reversible swap, sha256-verified
restore) with a new opt-in end-state block (`WAYDAW_DXVK_AB_ENDSTATE=1`,
480 s dwell) that calls `bin/ableton-thread-endstate-capture` — the winedbg
capture logic factored out of `bin/ableton-auth-liveness-probe`. Launches ran
through the non-mutating diagnostic launcher env
(`WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY=1 WAYDAW_ABLETON_GRAPHICS=dxvk`).

### Arm results

| | custom/debug DXVK 2.7 (19 MB) | official DXVK 2.7.1 (release) |
|---|---|---|
| End-state evidence | run `20260703-231014` (previous night, same launch path) | run `logs/ableton-dxvk-endstate-ab/20260704-122125-official271b` |
| Auth dialog appears | yes | yes (`0x0a600009`, transient for `0xa600003`) |
| Main thread end state | `RtlAcquireSRWLockExclusive(0xB34E90)` from **d3d11**, inside nested winprocs | `RtlAcquireSRWLockExclusive(0x12B4ADD0)` from **dxgi**, same nesting |
| Main thread CPU at end | 0 ticks/3 s | 0 ticks/3 s (state S, 2331 lifetime ticks) |
| SRW lock word | `owners=0x0003 exclusive_waiters=0x0001` | `owners=0x0003 exclusive_waiters=0x0001` |
| Thread stuck in `SendMessageW` to UI thread | yes (`0188`) | yes (`0190`) |
| WebView2 at capture | alive (full tree) | absent (count 0) |
| Ableton caller frames into the lock | `+0x311af7f +0x30b5d5a +0x30ae8a9 +0x31211bd +0x312e725` | identical offsets |
| UI interactable | no; user click while deadlocked → fatal SEH on thread 0024: `Exception frame is not in stack limits` (2026-07-04 launch log) | no (untested by click; hands-off run) |

Both today's arm-1 dwell (user click-crash destroyed the session mid-run) and
an aborted first official run (`official271`, SIGTERM ~80 s in) produced no
end state; the table's custom-arm column therefore cites the prior night's
full capture, which used the same launcher path and persisted 6 h. DXVK
restore was sha256-verified after every run; prefix DXVK is the original
debug build again.

### Verdict

**The custom/debug DXVK build is NOT the cause.** The identical deadlock —
same Ableton call path, same lock-word signature (three leaked shared owners,
one exclusive waiter), same `SendMessageW` collateral — occurs under the
official DXVK 2.7.1, merely surfacing in `dxgi` instead of `d3d11`. The
recurring exact `owners=0x0003` across different DXVK builds and different
lock objects points at the layer both builds share: **wine-staging 11.0's SRW
lock / wait-on-address implementation** (or its interaction with Ableton's
re-entrant nested message pumps). WebView2 presence/absence is again
irrelevant.

The user-click fatal exception on the deadlocked thread also explains the
historical `crash_on_interaction` observations.

### Next move after this A/B

Test a **genuinely different Wine base** — but unlike the abandoned runner
exploration, the target is now precise and falsifiable: does the UI thread
still park in `RtlAcquireSRWLockExclusive` with `owners=3/waiters=1`? The
cheapest constraint-compliant candidate is plain (non-staging) Wine or a
newer Wine release, checked with the same end-state capture. This narrow
question also makes an upstream WineHQ bug search / report actionable for
the first time ("SRW shared owners leak under re-entrant sent-message
pumping, wine-staging 11.0, DXVK client").

## Wine-base A/B with end-state thread capture (2026-07-04) — EXECUTED

One question: does the UI thread still deadlock in
`RtlAcquireSRWLockExclusive` with `owners=3 / exclusive_waiters=1` under a
genuinely different Wine base? Method: copy the working prefix, boot it with
the comparator runner, restore the debug DXVK DLLs into the copy after the
runner's prefix-update overwrote them (sha256-verified), launch Ableton
directly (no forced `WINEDLLOVERRIDES`, no virtual desktop), dwell 480 s, then
`bin/ableton-thread-endstate-capture`. Working prefix never touched; nothing
installed.

**Bases compared** — both Wine **11.0**, same DXVK (debug 2.7), same prefix
contents:
- Baseline: system `wine-11.0 (Staging)`.
- Comparator: `.local-runners/kron4ek-proton-exp-11.0`,
  `wine-11.0-gd0c1d0160f9 (Proton)` — non-staging, already cached from the
  June runner exploration. (The June runs were blocked only on a DXVK-loader
  technicality that is irrelevant to today's thread-end-state question.)

### Result

| | baseline: wine-staging 11.0 | comparator: Proton-exp 11.0 (non-staging) |
|---|---|---|
| Evidence | `logs/ableton-dxvk-endstate-ab/…official271b` + 6 h liveness capture | `logs/ableton-winebase-ab/20260704-162604-protonexp-confirm` |
| Ableton launches | yes | yes (10 s) |
| Auth dialog reached | yes (512x479) | yes (512x479, `0x0b00000e` transient) |
| WebView2 | present | present (2 procs) |
| UI thread innermost | `RtlAcquireSRWLockExclusive` via d3d11/dxgi | Ableton code (frames 0–7), **no** d3d11/dxgi/SRW |
| Thread in `RtlAcquireSRWLockExclusive` | yes (the UI thread) | **none** (0 of 52 threads) |
| SRW lock word | `owners=0x0003 waiters=0x0001` | n/a — no SRW wait |
| Thread wedged in `SendMessageW` | yes | **none** |
| UI-thread CPU at capture | **0** ticks/3 s (kernel futex wait) | **38** ticks/3 s (~12% core; ~62 s total) |
| Same Ableton message-pump lower frames | yes | yes (identical offsets) |

The comparator reaches the identical Ableton nested message-pump/winproc code
path as the baseline, but instead of descending into d3d11/dxgi and blocking
forever on the SRW lock, its UI thread stays in Ableton code and keeps
consuming CPU. **The `owners=3 / waiters=1` SRW deadlock signature does not
reproduce under the different Wine base.**

Honesty caveats (do not overclaim): (a) this run's built-in forward-progress
sub-check returned empty samples because the per-thread `bt` filter keyed on
winedbg's `=>0` marker, which only tags the active thread — its "frozen"
label is a filter artifact and is disregarded; the script's sampler is now
fixed. The verdict rests on the `bt all` capture (no SRW / no SendMessageW)
plus the non-zero CPU delta, which together exclude the staging futex
deadlock. (b) The auth dialog was **not** interacted with, so Ableton is not
shown to be *usable* under Proton — only that its UI thread is not in the
staging deadlock. Whether the CPU-active state is healthy progress or a
different busy state is the next thing to confirm with the fixed sampler.

### Verdict

**Not a general Wine 11.0 / SRW-layer defect. The deadlock is
build-specific:** a different Wine 11.0 build (Proton-exp, non-staging), with
the same DXVK and prefix, does not reproduce the `RtlAcquireSRWLockExclusive`
`owners=3/waiters=1` signature and keeps the UI thread executing. wine-staging
11.0's patchset (or a build difference it carries — SRW/WaitOnAddress/ntsync)
is the prime suspect; this single comparator does not isolate the exact patch,
so "staging-specific" is likely but not proven versus "Proton-carries-a-fix."

### Single next recommended move

One Proton-exp confirmation run with the **fixed** forward-progress sampler and
a longer post-dialog observation, to establish whether the CPU-active UI
thread is making real progress (→ Proton-exp is a viable Wine-base
replacement; pivot to standing it up as the WayDAW runner) or busy-spinning
(→ Ableton fails differently under Proton; report the exact difference rather
than adopt it). This needs no new download and no working-prefix mutation.
Only after that should an upstream WineHQ report be framed — and it would now
be a *staging-specific* SRW report, not "Wine 11.0."

## Proton-exp forward-progress confirmation (2026-07-04) — EXECUTED

Question: after Ableton reaches the auth dialog under Proton-exp, is the UI
thread making real forward progress, or busy-spinning in one small stack
region? Method: relaunch the copied Proton prefix (debug DXVK verified
pre/post), wait for the 512x479 auth dialog, dwell **720 s**, then
`bin/ableton-thread-endstate-capture` with the **fixed** forward-progress
sampler (each sample now takes a full `bt all` and extracts the main thread's
innermost frames by TID — the previous run's `=>0`-only filter that produced
empty samples is corrected).
Run: `logs/ableton-winebase-ab/20260704-173436-protonexp-progress`.

### Result

- Auth dialog reached in ~12 s (`0x0b20000f`, transient for `0xb200003`),
  69-thread UI process, WebView2 present.
- **Forward-progress sampler: 6/6 samples non-empty, 3 distinct signatures.**
  Samples 1–4 caught the thread in a win32u message-wait region; sample 5 in a
  message-dispatch path (user32/ntdll); sample 6 deep in Ableton code
  (`+0x2e870d3 ← +0x36e94b9 ← …`). `forward_progress=executing`.
- Contrast: staging's UI thread was byte-identical across 10 samples over 6 h.
  Proton's visits ≥3 stack regions in ~30 s → a live message pump, not a
  pinned spin.
- **No thread in `RtlAcquireSRWLockExclusive` (0 hits), none in
  `SendMessageW` (0 hits)** across all 69 threads. `srw_lock_addr=none`,
  `main_thread_in_d3d11=no`.
- CPU: `35` ticks/3 s (~12 % core; total ~82 s) — periodic work, not a
  100 %-pegged busy loop.
- DXVK debug build unchanged pre/post; working prefix untouched; processes
  cleaned up.

The stable-looking full-capture snapshot (`main_thread_top_frames` all in
Ableton, `message_wait=no`) is just the single instant of the `bt all` grab;
the time-series sampler shows the thread cycling through wait → dispatch →
app-code, i.e. a normal Win32 UI loop **gated at the unauthorized auth
dialog** — the expected healthy state for an un-activated install.

### Verdict

**Proton-exp 11.0 is the leading WayDAW runner candidate.** Under it the UI
thread makes genuine forward progress, the `owners=3/waiters=1` SRW deadlock
does not reappear, and no `SendMessageW` wedge forms — while system
wine-staging 11.0 hard-deadlocks at the same point. This corroborates the
build-specific (staging-implicated) conclusion.

Not yet proven: full end-to-end usability. The auth dialog was **not**
interacted with (authorization boundary preserved), so "the app is usable
under Proton" is unconfirmed — but the thread state is healthy and correctly
gated, which is the most that can be shown without a real authorization.

### Single next recommended move

Stand up Proton-exp behind an **explicit, opt-in WayDAW runner mode** (e.g. a
`WAYDAW_ABLETON_RUNNER=proton-exp` path in `bin/ableton` that prepends the
runner bin dir, keeps `env -u WAYLAND_DISPLAY`, keeps DXVK, and — because
Proton's prefix-update overwrites the DXVK DLLs — re-asserts+verifies the
debug DXVK hashes after any wineboot). Run it once against the **copied**
prefix for a user-driven authorization attempt; only after a successful,
legitimate authorization + confirmed editor interactivity should it be
considered for the working prefix. Do not change the default launcher until
then.

## Relationship to existing constraints

This note changes no constraint. It flags one for conditional review: the
"no Wine virtual desktop" rule should be interpreted as "no *permanent*
virtual desktop," while a single copied-prefix virtual-desktop session
remains available as a *diagnostic* if and only if the recommended next move
lands on H3/H4. All other constraints (system Wine only, DXVK mandatory,
copied-prefix discipline, authorization boundary, no KWin/DPI mutation)
are reaffirmed by the evidence above.
