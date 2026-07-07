# Proton-exp UI-thread spin source: WM_WINDOWPOSCHANGED storm, WebView2 exonerated (2026-07-07)

Follow-up to `docs/ableton-proton-exp-visible-flicker-input.md`, which established
that the entire UI thread stops pumping messages while Ableton is unauthorized
under Proton-exp (even the auth dialog's own "Authorize later" button does not
register). That note named WebView2 the prime suspect. This session captured
full busy-thread backtraces and ran a decisive WebView2-absence test.

**Result: WebView2 is exonerated. The UI thread is starved by a self-sustaining
`WM_NCCALCSIZE`/`WM_WINDOWPOSCHANGED` sent-message storm on the MAIN window —
Ableton's own window re-management re-triggers itself synchronously inside one
never-returning top-level GetMessage call.**

Branch `diagnosis/proton-exp-visible-flicker-input` @ `9a68b3e` (the decisive
"authorize-later ignored" doc update was already committed before this session
started). Copied Proton-exp prefix only (`ableton12-winebase-protonexp-test`);
two launches; no authorization attempted; no dialog buttons clicked (not even
"Authorize later" this time); no credentials; working prefix and KWin settings
hash-verified unchanged before and after (`kwinrc 7f3fe330…`, `kwinrulesrc
116b2b8c…`, working-prefix `d3d11.dll 557c1f50…`, `dxgi.dll f31cd64b…`).

## Run 1 — baseline full backtrace + WebView2 correlation

`WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`, unauthorized, auth dialog up.
Capture: `bin/ableton-thread-endstate-capture` (winedbg `bt all`, 1 full pass +
6 re-samples at 5 s intervals) plus a 3 s-interval process/thread observer for
~120 s (41 samples).

Identity of the busy thread:

- Ableton UI process unix pid `182640` (69 threads), Wine pid `0020`.
- Busy thread = the **main/UI thread**, Wine TID `0024`, unix tid `182640`
  (thread name `MainThread`), state `R`, **350–354 CPU ticks per 3 s (~117%)**;
  every other thread near-idle (AudioCalc threads 3–14%, all Sleeping waits).

Full-stack structure (identical skeleton in all 7 captures, both runs):

```
base   (stable):  ntdll → kernel32 → ableton+0x248872e → +0x26ac419
                  → +0x30bd201 → win32u+0x15294       <- top-level message-loop
                                                          call; NEVER RETURNS
repeating unit (13–22 deep, depth oscillates 167→201+ frames, hits bt cap):
                  ntdll+0x10b77 (KiUserCallbackDispatcher)
                  → user32+0x61a04 → user32+0x702be (winproc dispatch,
                      msg arg 0x47 = WM_WINDOWPOSCHANGED; one 0x83 =
                      WM_NCCALCSIZE; one 0x401 outermost)
                  → ableton+0x311bee2 → +0x31ba965 → +0x30db576 → +0x3121d85
                  → win32u+0x16e34 (syscall re-entry: SetWindowPos-class call
                      that synchronously delivers the next WM_WINDOWPOSCHANGED)
```

- Target HWND of the storm: `0x100b8` = **the main window** ("Untitled -
  Ableton Live 12 Suite", class `Ableton Live Wind`, thread 0024; mapped via
  winedbg `info wnd`). Not the auth dialog (`0x10178`), not the
  `AbletonWebViewHel…` helper window (`0x400f6`).
- Stacks are **moving** (frame addresses/depth differ across all samples;
  `forward_progress=executing`) but the **base never changes**: the thread is
  structurally *inside its message loop* — the loop call keeps servicing an
  endless stream of internally-generated sent messages and never returns to
  dispatch **posted** messages. That is why clicks and WM_CLOSE (from
  WM_DELETE) queue forever: input starvation, not a hang.
- Nothing else implicated in any sample: no `RtlAcquireSRWLockExclusive`, no
  cross-thread `SendMessage`, no d3d11/dxgi/vulkan, no COM/RPC activity frames
  (rpcrt4 threads all parked), no timer/network/auth functions.
  `embeddedbrowserwebview` frames exist only on thread `0140`, a parked
  blocked wait (WebView2 host waiting on browser IPC).

WebView2 correlation during the same run:

- Exactly **2** `msedgewebview2.exe` processes (182832, 182947), parent
  pid 1918 (wine services), **stable across all 41 samples** — no appear/
  disappear/restart churn. CPU 0.3% and 1.9% — essentially idle.
- The browser/crashpad/gpu-process "restart" line clusters in the log tail
  predate this session (cumulative `logs/ableton.log`); the current-session
  slice shows one normal WebView2 startup and no crash/retry loop.
- X-level check: **0 ConfigureNotify events in 6 s** on both the main window
  and the dialog while the storm ran at ~117% — the storm is Wine-internal
  and does not touch the X server in steady state.
- WM_DELETE (`wmctrl -c`) ignored throughout (sent 07:48:09; both windows
  still mapped 3+ min later).

## Perturbations (diagnosis-only, all reversible, no auth surface touched)

**P1 — external X resize (live session).** Hypothesis: storm is internal and
survives external geometry input; also collects the white-bars resize datum.
`xdotool windowsize 1200 900` → Wine/Ableton **re-asserted 848×1052** within
~14 s (second attempt: width 1200 briefly stuck, height snapped back
immediately). Spin unchanged (~83–100%+ of a core). So the app actively pushes
its own rect back when the X size diverges — the re-management is live, not
residual.

**P2 — remove `_NET_WM_STATE_MAXIMIZED_VERT` and grant 848×1096 (the prior
session's swapchain size).** Hypothesis: the storm is an unsatisfiable-height
fight (wants 1096, KWin's maximized-vert caps client at 1052 = 1080 − 28).
Result: state removed, resize requested, window **still snapped back to
848×1052 by the app side**, spin unchanged. The simple "KWin caps the height"
convergence-failure model is insufficient; the re-assertion loop is
Ableton/Wine-internal (consistent with the SWP_FRAMECHANGED/style-churn
signature: WM_NCCALCSIZE + WM_WINDOWPOSCHANGED, and the Motif-hints churn
documented with the controller off).

**P3 (decisive) — run 2 with WebView2 forced to fail cleanly.** Env-only,
runner-scoped, reversible; no licensing bypass — authorization simply becomes
honestly unavailable (the allowed "auth surface fails cleanly" case):
`WEBVIEW2_BROWSER_EXECUTABLE_FOLDER=<empty dir>` (fixed-version lookup fails,
no fallback). Hypothesis stated in advance: if WebView2 is causal the storm
disappears; if not, it is identical.

Result: **zero msedgewebview2 processes** the whole run; the auth dialog still
appears (without embedded browser content); and the storm is **identical** —
main TID 0024, state `R`, 354 ticks/3 s, `message_wait=no`, 178-frame nested
stack with 15× `0x47`, zero WebView2 frames, WM_DELETE ignored 60+ s, pump
never resumes. Interactivity did not improve under any perturbation.

## Conclusions

1. **Spin source (identified):** Ableton's unauthorized-state window
   re-management on the **main window**. Its `WM_WINDOWPOSCHANGED` handler
   re-invokes a SetWindowPos-class win32u call that synchronously delivers
   another `WM_WINDOWPOSCHANGED` (with `WM_NCCALCSIZE`, i.e. frame-changed
   semantics), recursing 13–22 deep continuously at ~117% of a core. The
   top-level message-loop call never returns, so **posted** input/close
   messages are never dispatched — matching every observed symptom (dead
   dialog buttons, ignored WM_DELETE, WM-drag still working).
2. **WebView2: exonerated.** Not causal and not even correlated: idle stable
   processes in run 1; complete absence in run 2 changes nothing. The prior
   note's "spinning/retrying WebView2 is the prime suspect" is now closed.
3. **Controller/KWin/X: not involved** in the spin (0 ConfigureNotify in
   steady state; controller-independent per the previous session's A/B).
4. **Classification:** UI-thread message-pump starvation via a self-sustaining
   Win32 frame-change feedback loop between Ableton's winproc and Wine's
   synchronous WM_WINDOWPOSCHANGED delivery, active while unauthorized under
   Proton-exp. Not modal-block, not deadlock, not WebView2/COM/GPU, not WM.

## White bars (secondary, data preserved, not fixed)

- This session's windows: main 848×1052 client at 165,28; captured pixmap
  848×1052; `_NET_FRAME_EXTENTS 0,0,28,0`; `_NET_WM_STATE_MAXIMIZED_VERT`
  present (until P2 removed it); Motif hints `0x3,0x6,0x7a,0x0,0x0`.
- No DXVK `Presenter:` lines appeared in the current-session log slice, so the
  swapchain-vs-resize datum could not be re-measured (prior sessions: fixed
  848×1096). External resizes were reverted by the app before any swapchain
  observation was possible — swapchain-recreate-on-resize remains an open
  question, blocked mostly by the same re-assertion loop.
- Note the recurring 1096-vs-1052 (44 px) mismatch: 1096 is exactly the
  workarea height 1080 plus 16, and 1052 = 1080 − 28 (titlebar). The storm and
  the swapchain pin plausibly share the same wrong-size belief inside Ableton;
  resolving the loop will likely move this bug too.
- Next white-bars diagnostic (after interactability): run with DXVK presenter
  logging confirmed on (e.g. `DXVK_LOG_LEVEL=info` runner-scoped) and capture
  swapchain properties across a WM-side resize.

## WINEDEBUG capture (2026-07-07, follow-up session): exact cycle recorded

The proposed `WINEDEBUG=+message,+win` capture was approved and executed.

**Capture setup.** One launch, copied Proton-exp prefix, WebView2 kept absent
via the proven `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER=<empty dir>` fail-clean
override (keeps Chromium message traffic out of the trace; the storm is
identical without WebView2 per the exoneration run). To keep the debug flood
out of the repo's `logs/ableton.log`, the launch replicated the runner's
exact no-registry command directly (source `config/env` with
`WAYDAW_ABLETON_RUNNER=proton-exp`, then
`env -u WAYLAND_DISPLAY -u WINEDLLOVERRIDES WINEDEBUG=+message,+win
WINEPREFIX=<test prefix> wine "<Ableton exe>" 2><scratch log>`), with a
1.5 GB size guard. Duration 104 s (08:06:50–08:08:34, dialog up by ~26 s);
final log 232 MB in session scratch (not committed). Session state matched
all prior runs: main `0x08c00003` 848×1052@165,28, dialog `0x08c00091`,
`_NET_WM_STATE_MAXIMIZED_VERT`, Motif `0x3,0x6,0x7a`, frame extents
`0,0,28,0`, UI process ~126–130% CPU. WM_DELETE sent at 08:08:08 —
**still ignored** (both windows mapped 8+ s later; and see the trace-level
proof below). Cleaned up clean; hashes unchanged.

**The exact cycle** (main window Wine HWND `0x100b6` this run, thread `0024`;
21,755 `NtUserSetWindowPos` calls on the main window in 104 s ≈ 209/s):

```
[worker tid 017c] WM_USER+1 (0x401) → helper window 0x200ac on UI thread
                                       (1267 deliveries; ~3.2 cycles/s)
  → UI thread: NtUserSetWindowPos hwnd 0x100b6, 165,0 (848x1080), flags 0x16
       (SWP_NOZORDER|SWP_NOACTIVATE — Ableton's TRUE desired geometry:
        848 wide, FULL 1080 screen height, at x=165, y=0)
  then, recursively, ~63 times, +4 px taller each iteration:
    WM_WINDOWPOSCHANGED "sent from self", WINDOWPOS h=N,
        flags 0x1216 (= 0x216 | SWP_NOCLIENTSIZE)      <-- client DID NOT change
      → handler calls NtUserSetWindowPos 0,0 (848 x N+4),
            flags 0x216 (NOMOVE|NOZORDER|NOACTIVATE|NOOWNERZORDER)
        → WM_WINDOWPOSCHANGING → WM_NCCALCSIZE (wp=1)
            rects e.g. new (165,0)-(1013,1300), old (165,0)-(1013,1296)
            result flags 0x1a16 (NOCLIENTSIZE|NOCLIENTMOVE)
        → WM_WINDOWPOSCHANGED (h=N+4) → recurse
  window-rect height climbs 1056 → ~1405 (21,076 × +4 steps), recursion
  unwinds (~63 deep ≈ the 167–201-frame backtrace oscillation), resets
  (paired −12/−236 steps, ~333 cycles), next WM_USER+1 restarts it. Forever.
```

Constant throughout: `WM_SIZE` always reports client `848×1096`
(`lp=04480350`) — **the client rect is pinned**; every storm
`WM_WINDOWPOSCHANGED` carries `SWP_NOCLIENTSIZE`. Note the impossible
geometry Wine maintains: **client height 1096 > requested window height 1080
> X reality 1052**, where 1096 = 1080 + 2×8 (Wine's maximized-window border
extension: a Windows-style vert-maximized window rect legitimately overhangs
the screen by the resize border; KWin's actual grant is 1052 = 1080 − 28
titlebar). The X server sees none of this — zero ConfigureNotify in steady
state; `set_window_pos` returns `status flags = 1006` each round with no
server-side change. Only 8 style messages total in 104 s and no
`SWP_FRAMECHANGED` in the storm: this is **not** style/frame churn.

**Trace-level starvation proof:** zero `WM_CLOSE` and zero `WM_SYSCOMMAND`
dispatches on the main window in the entire 104 s log, despite the WM_DELETE
close request mid-capture — posted messages are never retrieved.

**Classification (from the decision list): rect/size feedback divergence —
maximize/workarea mismatch (2+3+5), not a no-op re-delivery bug (4), not
style churn (1).** Precisely: a worker thread perpetually re-asserts
Ableton's desired full-screen-height rect (848×1080@165,0, unsatisfiable
under KWin's vert-maximize clamp); Wine pins the client rect at an
inconsistent 848×1096 (`SWP_NOCLIENTSIZE` every iteration), so Ableton's
`WM_WINDOWPOSCHANGED` handler — apparently reconciling window vs client
height and never observing convergence — grows the window +4 px per
synchronous re-entry until a recursion bound, then the worker restarts the
cycle. The UI thread spends ~100% of its time inside this loop, so posted
input/close messages starve.

This also closes the white-bars question: the pinned client (and hence the
DXVK swapchain) is 848×1096 while the X window shows 848×1052 — the same
1096-vs-1052 (44 px) inconsistency, one root cause for both defects.

**Why WebView2 stays exonerated:** this capture ran with zero
`msedgewebview2.exe` processes and reproduced the full storm; the cycle's
participants are an Ableton worker thread, Ableton's winproc, and
win32u/user32 — no browser, COM, or network component appears anywhere in
the loop. **Why KWin/controller stay exonerated:** the controller was not
loaded during capture; the storm generates no X traffic at all in steady
state, so no compositor policy is being exercised per-iteration — KWin's
only role is the initial (legitimate) vert-maximize clamp that Ableton's
geometry demand can never satisfy.

**Still unknown:** the exact arithmetic behind the +4 increment (which pair
of Ableton's height beliefs differs by 4 — likely a border term, but the
handler's internals are opaque without symbols); whether Wine's pinned
1096 client rect is Proton-specific maximize-border arithmetic or also
present in vanilla Wine 11; and whether Ableton stops the WM_USER+1
re-management heartbeat once authorized (prior working-prefix system-Wine
sessions do not show the storm, but that path differs in more than one way).

## Proposed next fix direction (NOT implemented — needs approval)

1. **Satisfy the geometry demand (recommended first — runner-scoped, low
   risk, also confirms the model).** The divergence needs "desired rect ≠
   grantable rect". The proton-exp runner already seeds `steamuser`'s
   `Preferences.cfg`; seed a placement that KWin can grant exactly (modest
   non-maximized rect inside the workarea, e.g. 848×1000 at y=28, no
   vert-maximize) and observe: if the storm never starts, interactability
   and the swapchain mismatch should both resolve in one move. Copied
   prefix only; no auth involvement; reversible by reverting the seed.
2. **Upstream Wine/Proton report** with this trace: under
   `_NET_WM_STATE_MAXIMIZED_VERT`, Wine reports a client rect (1096) larger
   than both the requested window rect (1080) and the actual X client
   (1052), and delivers unbounded synchronous `WM_WINDOWPOSCHANGED`
   recursion to an app that resizes from within its handler. Rebuilding the
   runner with a local Wine patch is out of scope (no package installs).
3. **App-scoped shim** (message filter/recursion breaker) — only if (1)
   fails; more invasive, needs its own design review.
   No Ableton binary patching; no auth/licensing involvement in any path.

## Hygiene

Two launches this session, both copied Proton-exp prefix, both cleaned with
`bin/ableton-proton-cleanup` (`cleanup_result=clean`, controller
`loaded=false`, zero prefix/WebView2 processes after each). No authorization
attempted; no auth-surface buttons clicked; no credentials. Perturbations were
X-level (wmctrl/xdotool geometry+state, reverted/moot after session end) and
env-only (WebView2 fixed-version folder, cleared with the session). Working
prefix and KWin config hashes identical before/after. Raw captures (winedbg
bt-all samples, thread/process monitors, xev logs) live in the session
scratchpad only; nothing was committed except this doc.
