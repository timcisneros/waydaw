# Ableton runner-test harness

`bin/ableton-runner-test` — a deterministic, copied-prefix compatibility harness
for comparing Ableton Live 12 behavior across different Wine runners.

## Why a harness, not a patch (yet)
The current evidence (see `docs/ableton-wine-current-findings.md`) proves that
*many variants still fail* — DXVK versions, dxvk.conf knobs, X11 vs Wayland,
disabling WebView2, Proton-GE 10-34 — but it does **not** yet identify the exact
lower-level component to patch. The strong remaining signal is: **main editor not
interactable + mouse disappears over the main Ableton window + WebView2
instability**, and the runners tried so far are all wine-11.0-staging-based (too
close together).

Starting a low-level Wine/DXVK/WebView2 patch now would be premature. Instead we
build infrastructure to gather **comparative** data across genuinely different
Wine runners/bases, safely and repeatably, so the failing layer can be isolated
before any patch. **This harness is test infrastructure, not a patch.**

## Safety model
- The **working/source prefix is never written to.** The harness only `rsync -a
  --delete`s FROM the source INTO a separate test prefix, and only ever launches
  Wine against the test prefix.
- It **refuses** to run if the test prefix resolves to the source/working prefix.
- It **refuses** to launch if the runner's `wine` binary cannot be found.
- It never sets `DXVK_LOG_LEVEL=none`, never adds `dxvk.conf`, never uses a Wine
  virtual desktop, never changes KWin geometry, never changes DXVK DLLs, and
  never edits the launcher. Same native DXVK is kept so only the Wine runtime
  varies.
- It does not set `WINEDLLOVERRIDES=dxgi,d3d11=b` or
  `WAYDAW_ABLETON_GRAPHICS=wined3d`. The compatibility matrix must keep the
  copied prefix's DXVK DLLs active. A run is invalid if builtin `d3d11`/`dxgi`
  is forced.
- For runners that rewrite the copied prefix during first launch, use
  `--enforce-dxvk`. This runs the runner prefix update first, restores the
  source-prefix DXVK DLLs into the TEST prefix only, verifies hashes, and then
  launches with `WINEDLLOVERRIDES=d3d11,dxgi=n`. This native override is allowed;
  the forbidden builtin override remains `WINEDLLOVERRIDES=dxgi,d3d11=b`.
- Cleanup removes **only** the test prefix, and only with an explicit flag.

## How to run a copied-prefix runner test
```bash
# 1) Prepare only (copy + verify; no launch):
./bin/ableton-runner-test --label myrunner --runner /path/to/runner --prepare-only

# 2) Full run (prepare-if-needed, launch, wait for window, collect evidence):
./bin/ableton-runner-test --label myrunner --runner /path/to/runner --run

# 2b) Full runner comparison with enforced copied-prefix DXVK:
./bin/ableton-runner-test --label myrunner --runner /path/to/runner --enforce-dxvk --run

# 3) Re-collect evidence from an already-running session:
./bin/ableton-runner-test --label myrunner --probe

# 4) Clean up the test prefix (test prefix ONLY, explicit):
./bin/ableton-runner-test --label myrunner --runner /path/to/runner --cleanup-test-prefix
```
`--runner` may point at the runner root or its `files` dir; the harness looks for
`bin/wine`, `files/bin/wine`, then `<runner>/wine`. Default source prefix is
`$HOME/WinePrefixes/ableton12`; default test prefix is
`$HOME/WinePrefixes/ableton12-<label>-test`.

## Custom compatibility-layer parameters
The harness now accepts explicit launch parameters for the first custom fix path:

```bash
./bin/ableton-runner-test --label myrunner --runner /path/to/runner \
  --webview2-mode default --cursor-guard off --prepare-only
```

Supported values:
- `--webview2-mode default|disable-gpu|disable-gpu-no-sandbox|isolated-user-data`
- `--cursor-guard off|on`
- `--enforce-dxvk` for runner comparisons where the runner may overwrite copied
  prefix D3D DLLs during prefix update.

`--webview2-mode` is environment-only and follows
`bin/ableton-webview2-mode`. `--cursor-guard on` starts
`bin/ableton-cursor-guard --watch --force-visible` after the Ableton window is
detected; if the optional local X11 helper is not built, the guard logs
`helper_missing_not_forced` and remains probe-only. No Wine prefix, DXVK, KWin,
or launcher mutation is performed by these options.

The harness refuses to launch if inherited `WINEDLLOVERRIDES` forces builtin
`d3d11` or `dxgi`. This matrix isolates WebView2 mode, cursor guard mode, and
runner/prefix behavior; it is not a `wined3d` or builtin-D3D test.

`--enforce-dxvk` fields written to `result.env` and `dxvk-enforcement.txt`:

```text
dxvk_enforced=yes/no
dxvk_source_system32_d3d11_sha256=
dxvk_source_system32_dxgi_sha256=
dxvk_test_system32_d3d11_sha256=
dxvk_test_system32_dxgi_sha256=
dxvk_source_syswow64_d3d11_sha256=
dxvk_source_syswow64_dxgi_sha256=
dxvk_test_syswow64_d3d11_sha256=
dxvk_test_syswow64_dxgi_sha256=
dxvk_restored_after_runner_prefix_update=yes/no
dxvk_hashes_match_source=yes/no
launch_winedlloverrides=d3d11,dxgi=n
```

Runner comparisons are invalid unless DXVK hashes are verified after runner
prefix update. If `dxvk-enforcement.txt` reports a Wine builtin DLL signature,
the backend is invalid for DXVK comparison.

Loader-only diagnostics live outside `--run`:

```bash
bin/ableton-dxvk-loader-probe --runner .local-runners/kron4ek-wine-11.11-staging-tkg --label candidate2-kron4ek-wine-11-11
```

This script creates copied prefixes only, runs the candidate runner prefix
update, restores source-prefix `system32/d3d11.dll` and `system32/dxgi.dll`,
verifies hashes, and compares loader evidence under:

```text
WINEDLLOVERRIDES=d3d11,dxgi=n
WINEDLLOVERRIDES=d3d11,dxgi=n,b
```

It does not launch Ableton. Results go under
`logs/ableton-dxvk-loader-probes/`.

Candidate 2 loader-only result (2026-06-19): native-only `d3d11,dxgi=n` failed
to load copied prefix `d3d11.dll`/`dxgi.dll` with `status=c0000135`; `n,b`
mapped copied DLLs but loaded builtin `wined3d.dll`. This does not support
switching official runner comparisons to `n,b`; Candidate 2 remains
`blocked_backend_loader`.

Current Ableton prefix note: the 64-bit `system32/d3d11.dll` and `dxgi.dll` are
the DXVK DLLs required for 64-bit Ableton. `syswow64` DLLs are copied and hash-
verified when present, but they are not used as the primary DXVK validity signal
for this 64-bit Ableton comparison.

Initial matrix, not yet run without approval:
- A: `webview2_mode=default`, `cursor_guard=off`
- B: `webview2_mode=disable-gpu`, `cursor_guard=off`
- C: `webview2_mode=default`, `cursor_guard=on`
- D: `webview2_mode=disable-gpu`, `cursor_guard=on`

## Output
Each `--run`/`--probe` writes `logs/ableton-runner-tests/<timestamp>-<label>/`:
- `result.env` — all deterministic fields + user-observation placeholders
- `processes.txt`, `windows.txt` — live process/window snapshot
- `session-probe.txt` — full `bin/ableton-session-probe` output (30s churn window)
- `ableton-log-tail.txt` — this run's `logs/ableton.log` segment tail
- `webview2-summary.txt` — msedge process count + WebView2/crash lines from the
  TEST prefix's Ableton `Log.txt`
- `cursor-guard.txt` — cursor guard tail or one probe-only snapshot
- `dxvk-enforcement.txt` — copied-prefix DXVK hashes/signatures and native
  override state
- `restore-or-cleanup.txt` — how to stop + remove the test prefix safely

Loader-only probe output is separate:
- `logs/ableton-dxvk-loader-probes/<timestamp>-<label>-native_only/result.env`
- `logs/ableton-dxvk-loader-probes/<timestamp>-<label>-native_only/winedebug-loader.log`
- `logs/ableton-dxvk-loader-probes/<timestamp>-<label>-native_then_builtin/result.env`
- `logs/ableton-dxvk-loader-probes/<timestamp>-<label>-native_then_builtin/winedebug-loader.log`

A one-line JSON summary is appended to `logs/ableton-runner-tests/index.jsonl`.

## How to interpret results
Deterministic (collected automatically):
- `ableton_launched`, `window_detected`, `backend_effective` (must stay `dxvk`),
  `recreating_swapchain_count` (DXVK swapchain-loop proxy),
  `webview2_process_count`, `webview2_crash` (GPU/browser-process-exit lines),
  `kprior_crash` (Ableton's "Detected a prior crash" loop marker).

Still requires USER VISUAL OBSERVATION (left as `needs_user_observation`):
- `main_editor_interactable`, `mouse_disappears_over_main_editor`,
  `crash_on_interaction`, `flicker`, `responsiveness`.

Comparison guidance:
- If a runner leaves WebView2 still crashing **and** the cursor/input still fails,
  it is not a fix; prefer a genuinely different Wine base next (not another
  wine-11.0-staging build).
- If the cursor/input improves even while WebView2 still crashes, that isolates an
  input/cursor/d3d-window-integration clue worth preserving.
- DXVK churn is expected to stay roughly constant across runners (same DXVK); a
  large change there would itself be a finding.

## Cleaning up copied prefixes safely
A copied prefix is ~9–10 GB. To remove one:
```bash
./bin/ableton-runner-test --label <label> --runner <runner> --cleanup-test-prefix
# or manually (test prefix ONLY — never the source):
rm -rf "$HOME/WinePrefixes/ableton12-<label>-test"
```
The harness kills the test prefix's `wineserver` (via the runner) before removal.
The working prefix `$HOME/WinePrefixes/ableton12` is never deleted by this tool.
