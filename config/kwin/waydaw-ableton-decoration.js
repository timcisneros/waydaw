// waydaw-ableton-decoration — KWin-side presentation guard for the Proton-exp
// Ableton main window (see docs/ableton-proton-custom-presentation-controller.md
// and docs/ableton-proton-exp-message-pump-starvation.md).
//
// Two guards for the ONE matching window, both KWin-internal (never touch
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
    w.frameGeometryChanged.connect(() => { pin(w, "frameGeometryChanged"); guardMaximize(w, "frameGeometryChanged"); });
    if (typeof w.maximizedChanged !== "undefined" && w.maximizedChanged) {
        w.maximizedChanged.connect(() => guardMaximize(w, "maximizedChanged"));
    }
    w.closed.connect(() => { managed.delete(w); lastUnmax.delete(w); });
    if (isTarget(w)) {
        console.info(TAG, "target matched:", w.internalId, "caption=", w.caption);
        pin(w, "initial");
        guardMaximize(w, "initial");
    }
}

workspace.windowList().forEach(manage);
workspace.windowAdded.connect(manage);
console.info(TAG, "loaded; watching for steam_proton + 'Ableton Live 12 Suite' normal windows");
