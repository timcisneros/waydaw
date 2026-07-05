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

## Verification suite

`bin/verify-proton-runner-mode` runs a launch-free, dry-run check of the whole
mode (default resolution, Proton resolution, unknown-runner rejection,
working-prefix refusal, DXVK reassertion against throwaway test DLLs, and
cleanup scoping). It never touches the working prefix (it reads its DXVK DLLs
read-only as the reassert source) and exits nonzero on any failure:

```bash
./bin/verify-proton-runner-mode
```

## Controlled cleanup

`bin/ableton-proton-cleanup` terminates only the copied-prefix Proton session,
using the runner's own `wineserver -k` bound to the copied prefix — never
`bin/kill-session` (which targets the working prefix). It refuses to act on the
working prefix. Preview with `--dry-run`:

```bash
./bin/ableton-proton-cleanup --dry-run   # show scoped commands, do nothing
./bin/ableton-proton-cleanup             # actually clean the copied session
```

## Do not yet

- Do not make Proton-exp the default.
- Do not point Proton mode at the working prefix.
- Do not perform or automate a real Ableton authorization without explicit
  user action.

## When you are ready later (authorization is a user-owned step, not required now)

Authorization is **not** a prerequisite for this project phase. Whenever you
choose to do it:

1. Launch: `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`
2. Wait for the 512x479 authorization dialog. **You** perform the legitimate
   authorization (online login or offline/no-internet) — the assistant will
   not click or type into it.
3. Confirm the editor becomes visible and interactable (menus, track clicks).
4. Ask the assistant to capture post-authorization state
   (`bin/ableton-thread-endstate-capture`) and check that:
   - no thread is in `RtlAcquireSRWLockExclusive`
   - no thread is wedged in `SendMessageW`
   - the UI thread shows forward progress
5. Relaunch once more (copied prefix) to confirm the authorization persists.
6. Do **not** change yet: the default launcher, the working prefix, KWin, or
   DXVK. A working-prefix migration plan is drafted only after copied-prefix
   authorization + editor interactivity + persistence are all confirmed.
