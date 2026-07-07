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

## Proposed next step (NOT implemented — needs approval)

Capture the storm's parameters, then decide the fix:

1. Short runner-scoped run with `WINEDEBUG=+message,+win` (log to file,
   seconds-long capture) to record the exact SetWindowPos flags/rect/style
   cycle: confirms whether the loop is `SWP_FRAMECHANGED` style churn (the
   Motif-hints/decoration toggling already seen as the flicker driver) or a
   rect oscillation, and which Ableton belief (1096?) never converges.
2. Fix directions depending on (1): stop the feedback Wine-side (the X11
   driver answering frame-changed SetWindowPos with another synchronous
   WM_WINDOWPOSCHANGED even when nothing changed), or satisfy Ableton's
   demand (window rules/size environment so its desired frame is achievable),
   or upstream Wine/Proton issue triage with this backtrace signature.
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
