# WayDAW pre-authorization phase — completion state (2026-07-04)

This records that the Proton-exp runner path is **complete for the
pre-authorization phase**: a clean, documented, reproducible, opt-in runner
that is safe to use later for authorization, without requiring authorization
now and without touching the working prefix.

## What is proven

- System `wine-staging 11.0` deadlocks Ableton's UI thread in
  `RtlAcquireSRWLockExclusive` (`owners=3/waiters=1`, `SendMessageW`-wedged
  helper). Build-specific, not general Wine 11.0.
- The cached non-staging `Proton-exp 11.0` runner avoids that deadlock, reaches
  the authorization dialog, the dialog accepts user clicks, no crash on first
  interaction, and the post-interaction thread state stays healthy.
- The working prefix has never been touched.

## Runner path (the deliverable)

- Opt-in only: `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`. The **only**
  Proton entry point. Default `./bin/ableton` remains system Wine.
- Selection centralized in `config/ableton-runner.sh` (sourced by `config/env`);
  `bin/ableton` body unchanged.
- Proton mode: prepends the runner bin to `PATH`; keeps `env -u WAYLAND_DISPLAY`;
  forces DXVK; forces diagnostic no-registry (no `wine reg` writes → no Proton
  prefix-update DXVK clobber); no virtual desktop; KWin untouched; targets the
  **copied** test prefix only and refuses the working prefix; re-asserts the
  debug-DXVK DLL hashes into the copied prefix (restored read-only from the
  working prefix on drift).
- Reproducible cleanup: `bin/ableton-proton-cleanup` (runner wineserver, copied
  prefix; refuses the working prefix). Not `bin/kill-session`.
- Verification: `bin/test-proton-runner-mode` (launch-free dry-run suite,
  22 checks, working prefix read-only).

## Readiness checklist

Complete (not gated by authorization):

- [x] Opt-in Proton-exp runner mode (`WAYDAW_ABLETON_RUNNER=proton-exp`).
- [x] Default launcher unchanged (system Wine, working prefix).
- [x] Proton mode refuses the working prefix; copied prefix only.
- [x] Runner binary resolution explicit + dry-runnable.
- [x] `env -u WAYLAND_DISPLAY` preserved; no Wine virtual desktop.
- [x] DXVK enabled + deterministic hash reassertion (verified by test).
- [x] Scoped cleanup via the runner's wineserver + copied prefix.
- [x] Verification suite passes (22/22), working prefix untouched.
- [x] Docs: runner mode, operator "when ready later" section, this checklist.
- [x] Scripts and docs committed on the diagnosis branch.

Gated by authorization (LATER, user-owned — NOT required for this phase):

- [ ] Legitimate authorization completed in the copied prefix.
- [ ] Editor interactivity confirmed post-authorization.
- [ ] Authorization persistence across a copied-prefix relaunch.
- [ ] Controlled working-prefix migration plan (only after the three above).
- [ ] Any decision to make Proton-exp the default launcher.

## Not in scope here / intentionally untouched

- The working prefix (`~/WinePrefixes/ableton12`).
- The default launcher behavior.
- KWin settings, DXVK versions, virtual desktop.
- The broader ruled-out investigation tooling (KWin/geometry/WebView2/
  DXVK-loader probes) remains as untracked working-tree files; it is unrelated
  to the runner path and is neither committed nor removed by this phase.

## Single next action — LATER, when the user chooses to authorize

Run `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`, perform the legitimate
authorization by hand, confirm editor interactivity, then ask for a
post-authorization capture and a persistence relaunch. Until then, nothing
about the default launcher or working prefix changes.
