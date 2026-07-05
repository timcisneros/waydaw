# Ableton Proton-exp runner mode (experimental, opt-in)

Status: 2026-07-04. Diagnostic/validation stage. **Not the default launcher.**

## Why this exists

System `wine-staging 11.0` deadlocks Ableton's UI thread in
`RtlAcquireSRWLockExclusive` (`owners=3 / exclusive_waiters=1`), with a helper
thread wedged in `SendMessageW`, at the authorization dialog. The deadlock is
**build-specific**: the cached non-staging `Proton-exp 11.0` runner reaches the
same dialog and keeps the UI thread executing (verified forward progress, no
SRW/`SendMessageW` wedge). Full evidence:
`docs/ableton-authorization-interaction-rethink.md` and
`docs/ableton-wine-current-findings.md`.

## Default is unchanged

With `WAYDAW_ABLETON_RUNNER` unset (or `=system`), `bin/ableton` behaves
exactly as before: system `/usr/bin/wine`, the working prefix
`~/WinePrefixes/ableton12`, and the normal registry/windowing setup. This mode
is the only supported path for real use today.

## Opt-in Proton-exp mode

```bash
WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton
```

What it does (see `config/ableton-runner.sh`, sourced from `config/env`):

- Prepends `.local-runners/kron4ek-proton-exp-11.0/bin` to `PATH`, so
  `wine`, `wineserver`, and `winedbg` resolve to the Proton-exp runner.
- Keeps `env -u WAYLAND_DISPLAY` (forced XWayland) — unchanged from default.
- Forces `WAYDAW_ABLETON_GRAPHICS=dxvk` (DXVK stays enabled; never the wined3d
  builtin override).
- Forces `WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY=1`, so the launcher does **not**
  issue `wine reg` writes. Those trigger a Proton prefix-update that overwrites
  the prefix's DXVK `d3d11.dll`/`dxgi.dll` with Wine builtins; skipping them
  keeps DXVK intact through launch (matches the validated progress runs).
- Does **not** use a Wine virtual desktop and does **not** change KWin.

### Copied test prefix only

Proton mode targets the **copied** prefix
`~/WinePrefixes/ableton12-winebase-protonexp-test` (override with
`WAYDAW_ABLETON_RUNNER_PREFIX=…`). It **refuses to run against the working
prefix** `~/WinePrefixes/ableton12`. Rationale: Proton boots/updates the prefix
differently from system Wine; until authorization + editor interactivity are
proven under Proton, the working prefix must not be exposed to it.

### DXVK hash re-assertion

Before launch, the mode verifies the test prefix's `d3d11.dll`/`dxgi.dll`
against the known debug-DXVK 2.7 hashes
(`557c1f50…1940dd` / `f31cd64b…2b3fd7`). If either drifted (e.g. a prior
Proton `wineboot` replaced them with builtins), it restores that DLL by copying
from the working prefix **read-only** — the working prefix is never written.

## Verify without launching

The existing dry-run path prints the resolved runner, prefix, and command
without starting Ableton:

```bash
WAYDAW_ABLETON_RUNNER=proton-exp WAYDAW_ABLETON_DRY_RUN=1 ./bin/ableton
```

Expected: `wine_binary=…/kron4ek-proton-exp-11.0/bin/wine`,
`wineprefix=…-winebase-protonexp-test`, `graphics_mode=dxvk`,
`registry_mutation_enabled=no`, `virtual_desktop_mutation_enabled=no`.

## Do not yet

- Do not make Proton-exp the default.
- Do not point Proton mode at the working prefix.
- Do not perform or automate a real Ableton authorization without explicit
  user action.

## Next step

Run the opt-in mode against the copied prefix and let the user perform a
legitimate authorization attempt. Only after successful authorization **and**
confirmed editor interactivity should Proton-exp be considered for the working
prefix or the default launcher.
