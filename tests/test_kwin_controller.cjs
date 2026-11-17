const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../config/kwin/waydaw-ableton-decoration.js'), 'utf8');
function signal() {
    const callbacks = [];
    return {
        connect(callback) { callbacks.push(callback); },
        emit(...args) { callbacks.forEach(callback => callback(...args)); },
        count() { return callbacks.length; },
    };
}
function window(target, optionalSignal) {
    const result = {
        normalWindow: true,
        resourceClass: target ? 'steam_proton' : 'unrelated',
        caption: target ? 'Ableton Live 12 Suite' : 'Other application',
        noBorder: true,
        frameGeometry: { x: 10, y: 10, width: 1200, height: 900 },
        maximizeMode: 0,
        fullScreen: false,
        captionChanged: signal(),
        frameGeometryChanged: signal(),
    };
    if (optionalSignal) result.noBorderChanged = signal();
    return result;
}
for (const optionalSignal of [false, true]) {
    const target = window(true, optionalSignal);
    const unrelated = window(false, optionalSignal);
    const workspace = {
        windowList: () => [target, unrelated],
        windowAdded: signal(),
        windowRemoved: signal(),
        clientArea: () => ({ x: 0, y: 0, width: 1920, height: 1080 }),
    };
    const context = vm.createContext({
        workspace,
        KWin: { MaximizeArea: 0 },
        console: { info() {}, warn() {} },
        target,
    });
    vm.runInContext(source, context);
    assert.equal(target.noBorder, false);
    assert.equal(unrelated.noBorder, true);
    assert.equal(vm.runInContext('managed.size', context), 2);
    workspace.windowAdded.emit(target);
    assert.equal(target.frameGeometryChanged.count(), 1);
    target.noBorder = true;
    if (optionalSignal) target.noBorderChanged.emit();
    else target.frameGeometryChanged.emit();
    assert.equal(target.noBorder, false);
    unrelated.frameGeometryChanged.emit();
    assert.equal(unrelated.noBorder, true);
    vm.runInContext('lastUnmax.set(target, 1); lastFloor.set(target, 1); resizeSeen.add(target); fitApplied.add(target)', context);
    workspace.windowRemoved.emit(target);
    assert.equal(vm.runInContext('managed.size', context), 1);
    for (const name of ['managed', 'lastUnmax', 'lastFloor', 'resizeSeen', 'fitApplied']) {
        assert.equal(vm.runInContext(`${name}.has(target)`, context), false);
    }
}
console.log('KWin compatibility checks passed with and without noBorderChanged.');
