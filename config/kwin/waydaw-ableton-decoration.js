// waydaw-ableton-decoration — KWin-side presentation guard for the Proton-exp
// Ableton main window (see docs/ableton-proton-custom-presentation-controller.md
// and docs/ableton-proton-exp-message-pump-starvation.md).
//
// Three guards for the ONE matching window, all KWin-internal (never touch
// Wine's X properties — the xprop guard that did made churn worse):
//
// 1. Decoration pin. While unauthorized, Ableton's busy re-init makes Wine
//    re-derive _MOTIF_WM_HINTS, toggling decorations 0x7a <-> 0x0; KWin
//    follows and the titlebar flickers (frame extents 28 <-> 0). We correct
//    KWin's INTERNAL noBorder state whenever KWin flips it to true. Wine never
//    reads this state back, so there is no two-writer property race.
//
// 2. Vertical-maximize / full-height guard. A window at/over the screen height
//    is coerced to vertical-maximize; Wine then keeps a client rect taller
//    than the WM grant and Ableton's WM_WINDOWPOSCHANGED handler loops
//    forever, starving the UI-thread message pump (no input, no close). The
//    runner's placement seed clamps the STARTUP height, but a user
//    vertical-maximize / full-height resize can still re-enter the bad state.
//    This guard detects vertical-maximize (or full-height / fullscreen) on the
//    target window and immediately restores the last known safe (non-maximized,
//    sub-screen-height) geometry, so the storm cannot form. Normal small moves
//    and resizes are left alone.
//
// 3. Manual-resize height cap. A live capture (2026-07-07, see
//    docs/ableton-proton-manual-resize.md) showed a user EDGE-DRAG to full
//    workarea height re-enters the storm with maximizeMode still 0 and
//    _NET_WM_STATE empty — guard 2 never fires on that path. This guard caps
//    the raw frame height: on every frameGeometryChanged, if the frame height
//    exceeds (workarea height − MANUAL_CAP_MARGIN), it is clamped back below
//    the danger zone in the same synchronous handler, before Ableton can latch
//    a full-height configure. x/y/width are preserved. This is PREVENTION
//    during the drag, not a restore-after loop: once capped the height never
//    reaches full workarea, so the app-side storm has nothing to latch. Below
//    the threshold, moves and resizes are untouched.
//
// Scope guard (all three required — must not affect any other Proton/Steam
// window, and excludes Ableton's authorization Dialog via normalWindow):
//   resourceClass === "steam_proton"
//   caption contains "Ableton Live 12 Suite"
//   normalWindow
//
// Loaded/unloaded at runtime via bin/ableton-kwin-decoration-controller
// (org.kde.kwin.Scripting D-Bus). Nothing persists across a KWin restart.
//
// Logs to the journal with prefix "waydaw-ableton-decoration:".
// Verify with: journalctl --user -b | grep waydaw-ableton-decoration

const TAG = "waydaw-ableton-decoration:";
let pinCount = 0;
let unmaxCount = 0;
const managed = new Set();
// Per-window guard against rapid re-fire (ms since last un-maximize action).
const lastUnmax = new Map();

// Manual-resize cap: frame height must stay at least this many px below the
// workarea height. This is now a BACKSTOP only — the Windows-side sizing shim
// (proxy version.dll, WM_GETMINMAXINFO clamp) is the primary lever and holds
// the window at its cap (~1040) pre-apply. This guard must therefore sit
// ABOVE the shim's band so it never fights a legitimate shim-allowed height;
// margin 20 → clamp at workarea−20 (frame ~1060), catching only a true
// near-full-workarea escape the shim somehow missed. If the shim is loaded
// (always, in the runner path) this should stay a zero/near-zero-fire
// sentinel. See docs/ableton-proton-full-height-preapply-options.md.
const MANUAL_CAP_MARGIN = 20;
let capCount = 0;
let capLogMs = 0;   // rate-limit LOGS only; the clamp itself must always run

// Manual-resize floor (guard 4, 2026-07-07). The Windows-side sizing shim
// floors WM_GETMINMAXINFO min height at 820 so Ableton can never enter its
// menu-less compact/borderless mode (app-side switch around frame ~740-750,
// docs/ableton-proton-decoration-menubar-occlusion.md). But Wine adopts
// WM-imposed configures through a raw path that sends no sizing messages, so
// a hard interactive shrink can leave the X window stuck as a short sliver
// (measured: 861x41 after a hard shrink drag; Wine's win32 belief stayed
// tall, _MOTIF stayed 0x7a, CPU calm — pure X-side geometry, invisible to
// the shim). This guard is the WM-side backstop: any granted frame height
// below MANUAL_FLOOR_MIN is raised back to MANUAL_FLOOR_RESTORE in the same
// synchronous frameGeometryChanged handler. MANUAL_FLOOR_MIN sits BELOW the
// shim's floor band (win32 820 ≈ frame ~840+) so this never fights a
// legitimate shim-allowed height; the restore target is the band bottom so a
// user's intent to have a short window is honored as closely as allowed.
// Skips fullscreen/maximize (guard 2 owns those), minimized and shaded
// windows (their frame heights are legitimately small/special).
const MANUAL_FLOOR_MIN = 800;
const MANUAL_FLOOR_RESTORE = 848;
let floorCount = 0;
let floorLogMs = 0;
// Unlike guard 3, the floor write MUST be rate-limited and must never fight
// an in-progress interactive resize: during a held shrink drag KWin re-applies
// the pointer geometry after every write, and an unlimited floor degenerates
// into a compositor-level geometry war (measured 2026-07-07: 3858 writes in
// ~12s; ALL interactive resizing turned sluggish with repaint bars). Mid-drag
// slivers are safe to allow — the Windows-side shim keeps the app's height
// belief >= 820 so the menu-less mode cannot latch — only the FINAL settled
// geometry matters, corrected on release (interactiveMoveResizeFinished /
// next frameGeometryChanged) with one write per 400ms settle window.
const lastFloor = new Map();

// Safe-fit (2026-07-08, docs/ableton-proton-presentation-contract.md).
// What "maximize" MEANS for this window: full workarea width via REAL
// horizontal-only maximize, height left at the app's believed value — never
// real vertical maximize (full workarea height is the storm trigger), never
// the menu-less short mode.
let fitCount = 0;
// Windows we put into safe-fit (horizontal maximize). A second maximize
// request while in safe-fit means "go back" and is restored NATIVELY by
// KWin (setMaximize(false,false) -> KWin's own pre-maximize bookkeeping).
const fitApplied = new Set();

// Why horizontal-only REAL maximize is the safe-fit mechanism (measured
// 2026-07-08): imposed frameGeometry writes and external resize requests
// are adopted by Wine without a re-layout — the app keeps painting its
// believed height (e.g. 1006) inside the bigger rect, leaving a permanent
// dead strip at the bottom (imposed 1030/1031 painted only ~1006; imposing
// exactly 1006 painted fully). The app's height belief moves ONLY through
// Wine's messaged path (interactive drags, real maximize state changes).
// Horizontal maximize IS such a messaged state change, is KWin-tracked
// (native restore), only touches width (measured-free axis), and painted
// edge-to-edge in the probe. Height is deliberately left at the app's own
// believed value — raising it belongs to the app/user via drags, not to a
// WM-side imposition that cannot reflow the app.

// Post-resize renegotiation nudge (guard 5, 2026-07-07). When an interactive
// resize ends, the app's counter-configure can be lost — KWin ignores client
// configure requests during the drag — leaving the X window taller than the
// app paints (measured: X client 1032, app painted 1006, permanent 26px
// black bar at the bottom; _MOTIF 0x7a, CPU calm). Any post-release
// configure request forces Wine/app renegotiation and the app's preferred
// size wins (measured: a 1px external resize snapped the window to 1006 and
// the bar was repainted). So: when an interactive resize on the target
// window finishes, shrink the frame height by 1px once. If the app adopted
// the dragged size the 1px is imperceptible; if its counter-configure was
// swallowed, this replays the renegotiation and the mismatch heals.
const resizeSeen = new Set();

function isTarget(w) {
    return w.normalWindow
        && w.resourceClass === "steam_proton"
        && w.caption.includes("Ableton Live 12 Suite");
}

function pin(w, why) {
    if (!isTarget(w)) return;
    if (w.noBorder) {
        pinCount += 1;
        console.info(TAG, "re-pin noBorder=false (#" + pinCount + ", " + why + ") on",
                     w.internalId, "caption=", w.caption);
        w.noBorder = false;
    }
}

// Vertical-maximize / fullscreen guard.
//
// The storm is triggered by the window entering vertical-maximize / full
// height. Once the storm is actually running it is self-sustaining APP-side
// (Ableton re-asserts full height ~3x/s) and CANNOT be recovered from KWin —
// clearing the maximize state then, or fighting geometry, does not stop it
// (measured). The lever that DOES work is PREVENTION: clear the maximize the
// instant KWin applies it — setMaximize(false,false) runs synchronously on the
// frameGeometryChanged signal, before Ableton latches the full-height configure,
// so the window never actually reaches full height and the storm never forms.
// KWin then keeps the window's pre-maximize geometry (no geometry war) and the
// _NET_WM_STATE atom is cleared. Measured: with this guard loaded, repeated
// vertical/both maximize requests all stay calm; with it unloaded the same
// request storms. maxSize/maximizable are read-only in KWin scripting, so
// intercept-and-clear is the only available lever.
//
// Acts ONLY on KWin-tracked maximize (maximizeMode vertical bit) or fullscreen,
// rate-limited so it fires once per transition and never spins. A synthetic
// client that pokes _NET_WM_STATE_MAXIMIZED_VERT directly WITHOUT a KWin
// maximize (maximizeMode stays 0) is not intercepted here; that path was not
// observed to storm on its own once the startup placement is clamped. See
// docs/ableton-proton-exp-message-pump-starvation.md.
function guardMaximize(w, why) {
    if (!isTarget(w)) return;
    var vmax = (typeof w.maximizeMode === "number") && ((w.maximizeMode & 1) !== 0);
    var fs = (w.fullScreen === true);
    if (!vmax && !fs) return;
    var now = Date.now();
    var prev = lastUnmax.get(w) || 0;
    if (now - prev < 400) return;   // don't spin; one action per settle window
    lastUnmax.set(w, now);
    unmaxCount += 1;
    console.info(TAG, "undo vertical-maximize/fullscreen (#" + unmaxCount + ", " + why +
                 ") maximizeMode=" + w.maximizeMode + " fullScreen=" + w.fullScreen +
                 " fg.h=" + w.frameGeometry.height);
    if (fs) { try { w.fullScreen = false; } catch (e) {} }
    if (vmax && typeof w.setMaximize === "function") {
        // Translate, don't swallow (2026-07-08): cancelling alone also threw
        // away the SAFE horizontal half of a full-maximize, so the user's
        // click visibly did nothing and they clicked again. First maximize
        // request -> horizontal-only real maximize (safe-fit; see the
        // mechanism comment at fitApplied). Second request while already in
        // safe-fit -> native KWin restore ("unmaximize" that actually goes
        // back). Rate-limited by lastUnmax above.
        if (fitApplied.has(w)) {
            fitApplied.delete(w);
            fitCount += 1;
            console.info(TAG, "safe-fit toggle: native restore (#" + fitCount + ", " + why + ")");
            try { w.setMaximize(false, false); } catch (e) {}
        } else {
            fitApplied.add(w);
            fitCount += 1;
            console.info(TAG, "maximize -> safe-fit horizontal-only (#" + fitCount + ", " + why + ")");
            try { w.setMaximize(false, true); } catch (e) {}
        }
    }
}

// Manual full-height resize cap (guard 3).
//
// Fires on raw frame height alone, so it covers the interactive edge-drag
// path where maximizeMode stays 0 and _NET_WM_STATE stays empty (the case
// guard 2 is blind to, measured 2026-07-07). It must PREVENT the full-height
// configure from ever being granted: it clamps synchronously inside
// frameGeometryChanged, the same lever that made guard 2 work. It must NOT
// degenerate into a restore-after loop — that variant was measured harmful
// (135 restores/40s, storm continues). The difference: the clamp keeps every
// granted height below the danger zone during the drag, so the app never
// latches the full-height belief that makes it fight back. Re-entrancy is
// safe: our own write re-fires frameGeometryChanged with height == cap,
// which passes the threshold check and no-ops.
//
// When the window IS vertically maximized or fullscreen, guard 2 owns the
// transition (setMaximize/fullScreen are the correct levers there — a raw
// geometry write would fight KWin's maximize bookkeeping), so this guard
// skips those states.
function guardManualHeight(w, why) {
    if (!isTarget(w)) return;
    if (w.fullScreen === true) return;
    if ((typeof w.maximizeMode === "number") && ((w.maximizeMode & 1) !== 0)) return;
    var area;
    try { area = workspace.clientArea(KWin.MaximizeArea, w); } catch (e) { area = null; }
    if (!area || !(area.height > 0)) return;
    var capH = area.height - MANUAL_CAP_MARGIN;
    var fg = w.frameGeometry;
    if (!(fg.height > capH)) return;
    capCount += 1;
    var now = Date.now();
    var logged = false;
    if (now - capLogMs >= 1000) {
        capLogMs = now;
        logged = true;
        console.info(TAG, "cap manual height (#" + capCount + ", " + why + ") fg=" +
                     fg.width + "x" + fg.height + "+" + fg.x + "+" + fg.y +
                     " -> h=" + capH + " (workarea.h=" + area.height + ")");
    }
    // Preserve x/y/width; only pull the frame height back under the cap.
    // Mutate-and-assign-back keeps the rect valid even if a field is odd.
    try {
        var g = w.frameGeometry;
        g.height = capH;
        w.frameGeometry = g;
    } catch (e) {
        if (logged) console.warn(TAG, "cap write threw:", e);
        return;
    }
    if (logged && w.frameGeometry.height > capH) {
        console.warn(TAG, "cap write did not take: fg.h=" + w.frameGeometry.height +
                     " (wanted " + capH + ")");
    }
}

// Manual short-resize floor (guard 4). Mirror of guard 3 on the short side;
// same synchronous-clamp lever, same re-entrancy story (our own write
// re-fires frameGeometryChanged with height == restore, which passes the
// threshold check and no-ops).
function guardManualFloor(w, why) {
    if (!isTarget(w)) return;
    if (w.fullScreen === true) return;
    if ((typeof w.maximizeMode === "number") && ((w.maximizeMode & 1) !== 0)) return;
    if (w.minimized === true) return;
    if (typeof w.shade !== "undefined" && w.shade === true) return;
    var fg = w.frameGeometry;
    if (!(fg.height < MANUAL_FLOOR_MIN)) return;
    // User drag in progress: stand down (see comment at MANUAL_FLOOR_MIN).
    if (w.move === true || w.resize === true) return;
    var now = Date.now();
    var prevW = lastFloor.get(w) || 0;
    if (now - prevW < 400) return;   // don't spin; one action per settle window
    lastFloor.set(w, now);
    floorCount += 1;
    var logged = false;
    if (now - floorLogMs >= 1000) {
        floorLogMs = now;
        logged = true;
        console.info(TAG, "floor manual height (#" + floorCount + ", " + why + ") fg=" +
                     fg.width + "x" + fg.height + "+" + fg.x + "+" + fg.y +
                     " -> h=" + MANUAL_FLOOR_RESTORE);
    }
    try {
        var g = w.frameGeometry;
        g.height = MANUAL_FLOOR_RESTORE;
        w.frameGeometry = g;
    } catch (e) {
        if (logged) console.warn(TAG, "floor write threw:", e);
        return;
    }
    if (logged && w.frameGeometry.height < MANUAL_FLOOR_MIN) {
        console.warn(TAG, "floor write did not take: fg.h=" + w.frameGeometry.height +
                     " (wanted " + MANUAL_FLOOR_RESTORE + ")");
    }
}

// Post-resize renegotiation nudge (guard 5). Runs once per finished
// interactive resize; its own write re-fires frameGeometryChanged with
// resizeSeen already cleared, so it cannot loop.
function renegotiateAfterResize(w) {
    if (!isTarget(w)) return;
    if (!resizeSeen.has(w)) return;
    resizeSeen.delete(w);
    if (w.fullScreen === true) return;
    if ((typeof w.maximizeMode === "number") && (w.maximizeMode !== 0)) return;
    var fg = w.frameGeometry;
    if (!(fg.height > MANUAL_FLOOR_MIN)) return;  // floor guard owns short results
    console.info(TAG, "post-resize renegotiation nudge fg=" +
                 fg.width + "x" + fg.height + " -> h=" + (fg.height - 1));
    try {
        var g = w.frameGeometry;
        g.height = g.height - 1;
        w.frameGeometry = g;
    } catch (e) {
        console.warn(TAG, "renegotiation nudge threw:", e);
    }
}

function manage(w) {
    if (managed.has(w)) return;
    managed.add(w);
    // Caption arrives late on Proton windows; re-evaluate on every change.
    w.captionChanged.connect(() => pin(w, "captionChanged"));
    w.noBorderChanged.connect(() => pin(w, "noBorderChanged"));
    // Measured (2026-07-06): KWin's X11 Motif-hint handler drops the
    // decoration WITHOUT emitting noBorderChanged, so that signal alone
    // sleeps through the churn. The decoration drop always changes the frame
    // geometry (client reclaims the 28px titlebar), so frameGeometryChanged
    // is the reliable in-KWin trigger. Re-entrancy is safe: our own
    // noBorder=false restores geometry once, after which noBorder reads
    // false and pin() no-ops.
    w.frameGeometryChanged.connect(() => {
        // Remember that a user resize touched this window; consumed by the
        // renegotiation nudge when the interaction finishes.
        if (w.resize === true) resizeSeen.add(w);
        // Leaving maximize entirely (drag, restore, app change) invalidates
        // the safe-fit toggle state.
        if (fitApplied.has(w) && typeof w.maximizeMode === "number" && w.maximizeMode === 0)
            fitApplied.delete(w);
        pin(w, "frameGeometryChanged");
        guardMaximize(w, "frameGeometryChanged");
        guardManualHeight(w, "frameGeometryChanged");
        guardManualFloor(w, "frameGeometryChanged");
    });
    if (typeof w.maximizedChanged !== "undefined" && w.maximizedChanged) {
        w.maximizedChanged.connect(() => guardMaximize(w, "maximizedChanged"));
    }
    if (typeof w.interactiveMoveResizeFinished !== "undefined" && w.interactiveMoveResizeFinished) {
        w.interactiveMoveResizeFinished.connect(() => {
            guardManualFloor(w, "moveResizeFinished");
            renegotiateAfterResize(w);
        });
    } else if (isTarget(w)) {
        console.warn(TAG, "interactiveMoveResizeFinished unavailable; floor/nudge rely on frameGeometryChanged only");
    }
    w.closed.connect(() => { managed.delete(w); lastUnmax.delete(w); lastFloor.delete(w); resizeSeen.delete(w); fitApplied.delete(w); });
    if (isTarget(w)) {
        console.info(TAG, "target matched:", w.internalId, "caption=", w.caption);
        pin(w, "initial");
        guardMaximize(w, "initial");
        guardManualHeight(w, "initial");
        guardManualFloor(w, "initial");
    }
}

workspace.windowList().forEach(manage);
workspace.windowAdded.connect(manage);
console.info(TAG, "loaded; watching for steam_proton + 'Ableton Live 12 Suite' normal windows"
             + " (manual height cap: workarea - " + MANUAL_CAP_MARGIN
             + ", manual height floor: <" + MANUAL_FLOOR_MIN + " -> " + MANUAL_FLOOR_RESTORE
             + ", maximize -> safe-fit horizontal-only, toggle restores)");
