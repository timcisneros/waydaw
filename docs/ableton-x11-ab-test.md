# Ableton flicker — X11 vs KDE-Wayland/XWayland A/B test

The DXVK swapchain-recreation loop (`Presenter: Got VK_SUBOPTIMAL_KHR, recreating
swapchain`; swapchain buffer `840x1096` ≠ window `832x1052`) is the remaining
flicker suspect and lives in the **presentation path**. wined3d is not viable
(DXVK is mandatory to launch) and no dxvk.conf knob changed the loop. The one
environment variable left to isolate is the session/compositor: **native X11 vs
KDE Wayland with Ableton on XWayland.**

## Rules of the test
- **Logging must be ON.** Use the normal `./bin/ableton` (NOT
  `DXVK_LOG_LEVEL=none`). `recreating_swapchain` is the deterministic proxy; the
  probe **refuses to run** (errors + exits nonzero) if it detects
  `DXVK_LOG_LEVEL=none` in its env or the Ableton process env.
- `bin/ableton-session-probe` is strictly read-only: it does NOT launch/kill
  Ableton and does NOT change Wine/KWin/DXVK/env/geometry. Launch with
  `./bin/ableton` first, then probe.
- Do not change Wine prefix, DXVK version, launcher, KWin geometry, or add
  dxvk.conf / Wine virtual desktop. No screenshots.
- The same `./bin/ableton` works in both sessions unchanged (`env -u
  WAYLAND_DISPLAY` is a no-op in X11).
- The recreate rate is **state-dependent** (~78–135/30s on Wayland across runs),
  so the meaningful signal is a **large drop toward ~0** in X11, not a small
  delta. Keep app state similar (start dialog only, no project loaded). Optionally
  run each session twice and compare the lower bounds.

---

## A. Wayland baseline (ALREADY CAPTURED — Fedora KDE Wayland 6, Ableton→XWayland)

    echo $XDG_SESSION_TYPE        # -> wayland
    ./bin/kill-session || true
    ./bin/ableton                 # logging ON; do NOT set DXVK_LOG_LEVEL=none
    # WAIT until the tall main editor window is fully visible (not just the
    # splash) — if you probe too early you get window_detected=no. Then:
    ./bin/ableton-session-probe | tee logs/ableton-session-probe-wayland.txt
    # (the probe takes ~30s: it measures a 30s swapchain-churn window)

Representative recorded result:

| field | value |
|---|---|
| XDG_SESSION_TYPE | wayland (KDE_SESSION_VERSION=6) |
| ableton_launched / window | yes / 0x02000003 (child dialog 0x02000009) |
| main_NET_WM_STATE | _NET_WM_STATE_MAXIMIZED_VERT |
| main_NET_FRAME_EXTENTS | 0, 0, 28, 0 |
| main_xwininfo_geometry | 169,28 832x1052 (ground truth) |
| geometry_state | **fits_workarea** (decorated B=1080 ≤ workarea 1080) |
| interaction_state | blocked_by_child_or_modal (expected Ableton dialog) |
| backend_effective | dxvk |
| recreating_swapchain_count (30s window) | **30** (range ~30–135 across runs; state-dependent) |
| VK_SUBOPTIMAL_KHR_count (30s) | 30 |
| Presenter_count (30s) | 76 |
| swapchain_buffer_size | 840x1096(×149) + transient sizes; ≠ window 832x1052 |
| swapchain_loop_log_observable | true |
| subjective_flicker / responsiveness | needs_user_observation |

---

## B. X11 test (YOU run this — requires a session switch)

1. Log out of the current Plasma (Wayland) session.
2. At the SDDM login screen, use the session selector → choose **Plasma (X11)**.
3. Log in.
4. Confirm the session, then run the same collection:

       echo $XDG_SESSION_TYPE        # MUST print: x11
       cd ~/Documents/waydaw
       ./bin/kill-session || true
       ./bin/ableton                 # logging ON
       # WAIT until the tall main editor window is fully visible, then (~30s probe):
       ./bin/ableton-session-probe | tee logs/ableton-session-probe-x11.txt

If the probe prints `ERROR: DXVK_LOG_LEVEL=none ...`, you have logging disabled —
relaunch with a plain `./bin/ableton` and rerun the probe.

Then paste back `logs/ableton-session-probe-x11.txt` AND your subjective
flicker/responsiveness observations (better / same / worse).

---

## Comparison rules (applied to the two probe outputs + your observation)
- **X11 much lower VK_SUBOPTIMAL_KHR / recreating_swapchain AND visibly less flicker:**
  `derived_issue = wayland_xwayland_kwin_presentation_path`
  → use an X11 session for Ableton, or test KDE-Wayland compositor settings.
- **X11 similar counts AND similar flicker:**
  `derived_issue = dxvk_or_wine_build_specific`
  → next: test a different DXVK version or Wine build.
- **X11 improves counts BUT still flickers:**
  `derived_issue = mixed_graphics_and_decoration_path`
  → split the remaining flicker from the swapchain loop (decoration/repaint vs present).
- **X11 breaks launch or interaction** (no login, no window, broken audio/MIDI, etc.):
  report it; do NOT recommend switching.

Nothing here is permanent. Return to normal by logging out and selecting
Plasma (Wayland) again.
