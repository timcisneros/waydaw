# Proton-exp copied-prefix user validation — dialog interactable (2026-07-04)

First user-driven validation of the opt-in Proton-exp runner mode
(`WAYDAW_ABLETON_RUNNER=proton-exp`). Copied test prefix only; working prefix
never touched. The user performed all interaction; the assistant did not click
or type into any Ableton control.

Run bundle: `logs/ableton-proton-user-auth/20260704-181143/`.

## Result

- **Authorization dialog interactable: YES.** Under Proton-exp the 512x479
  authorization dialog (`0x0b20000f`, transient for main `0x0b200003`, PID
  234980) accepted the user's clicks. On interaction it dismissed, leaving the
  main editor window (`0x0b200003`, 1920x1080) mapped. This is the decisive
  difference from system wine-staging 11.0, whose dialog never responded to
  activation or clicks.
- **Authorization completed: NO — deferred by user** ("I will authorize
  another time"). The interactability question was answered; the licensing
  flow was intentionally not carried through this session.
- **Thread end-state after interaction (Proton winedbg, copied prefix):**
  - `main_thread_forward_progress=executing`, 6/6 progress samples non-empty,
    top frames changed across samples.
  - `main_thread_cpu_ticks_per_3s=39` (~13% core) — live pump, not a spin.
  - `main_thread_in_srw_exclusive=no`; `threads_in_srw_exclusive=` (none);
    `threads_in_sendmessage=` (none).
  - 69-thread UI process; `main_thread_state=S`.
- **SRW deadlock reappeared: NO.** **`SendMessageW` wedge reappeared: NO** —
  even after the user interacted with the dialog.
- **Crash on interaction: NO.**
- **Editor reached: window present** (main 1920x1080 mapped after dialog
  dismissed). **Editor interactable: NOT YET CONFIRMED** — the user deferred
  further interaction, so full editor usability is unverified.
- **WebView2:** running (6 processes at dialog time, some churn to 2–4 during
  capture); no crash cascade blocked the session.
- **Working prefix touched: NO** (DXVK `557c1f50…` unchanged). Copied-prefix
  DXVK intact (`557c1f50…`) pre and post.

## Interpretation

Proton-exp clears the specific bar that system wine-staging 11.0 fails: the
authorization dialog is interactable and the UI thread stays healthy (no SRW
deadlock, no `SendMessageW` wedge) through interaction. Two things remain
unproven and gate any working-prefix/default move:

1. A completed legitimate authorization.
2. Confirmed editor interactivity after authorization.

## Next recommended move

Resume the opt-in Proton-exp session (copied prefix) when the user is ready to
complete a legitimate authorization, then confirm editor interactivity. Per
the decision rules, if the copied-prefix authorization succeeds, relaunch once
in the copied prefix to verify the authorization state persists **before** any
controlled working-prefix migration plan is drafted. Do not switch the default
launcher.
