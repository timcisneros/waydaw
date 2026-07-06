// waydaw-ableton-decoration — KWin-side decoration pin for the Proton-exp
// Ableton main window (see docs/ableton-proton-custom-presentation-controller.md).
//
// Problem: while unauthorized, Ableton's busy re-init makes Wine re-derive
// _MOTIF_WM_HINTS, toggling decorations 0x7a <-> 0x0; KWin follows and the
// titlebar flickers (frame extents 28 <-> 0).
//
// Approach: never touch Wine's X properties (the xprop guard that did made
// churn worse). Instead, correct KWin's INTERNAL noBorder state whenever KWin
// flips it to true for the one matching window. Wine never reads this state
// back, so there is no two-writer property race.
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
const managed = new Set();

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
    w.frameGeometryChanged.connect(() => pin(w, "frameGeometryChanged"));
    w.closed.connect(() => managed.delete(w));
    if (isTarget(w)) {
        console.info(TAG, "target matched:", w.internalId, "caption=", w.caption);
        pin(w, "initial");
    }
}

workspace.windowList().forEach(manage);
workspace.windowAdded.connect(manage);
console.info(TAG, "loaded; watching for steam_proton + 'Ableton Live 12 Suite' normal windows");
