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
// workarea height. On the 2560x1080 workarea this puts the cap at frame 1000
// — just above the calm startup frame (994 = 966 client + 28 titlebar) and
// well below the full-workarea frame (1080) where the storm formed. Tradeoff:
// a drag past the cap rubber-bands at the cap height instead of following the
// pointer; heights up to (workarea − 80) resize normally.
const MANUAL_CAP_MARGIN = 80;
let capCount = 0;
let capLogMs = 0;   // rate-limit LOGS only; the clamp itself must always run

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
    if (vmax && typeof w.setMaximize === "function") { try { w.setMaximize(false, false); } catch (e) {} }
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
        pin(w, "frameGeometryChanged");
        guardMaximize(w, "frameGeometryChanged");
        guardManualHeight(w, "frameGeometryChanged");
    });
    if (typeof w.maximizedChanged !== "undefined" && w.maximizedChanged) {
        w.maximizedChanged.connect(() => guardMaximize(w, "maximizedChanged"));
    }
    w.closed.connect(() => { managed.delete(w); lastUnmax.delete(w); });
    if (isTarget(w)) {
        console.info(TAG, "target matched:", w.internalId, "caption=", w.caption);
        pin(w, "initial");
        guardMaximize(w, "initial");
        guardManualHeight(w, "initial");
    }
}

workspace.windowList().forEach(manage);
workspace.windowAdded.connect(manage);
console.info(TAG, "loaded; watching for steam_proton + 'Ableton Live 12 Suite' normal windows"
             + " (manual height cap: workarea - " + MANUAL_CAP_MARGIN + ")");
