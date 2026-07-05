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
- Verification: `bin/verify-proton-runner-mode` (launch-free dry-run suite,
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

## Dirty/untracked file classification (as of phase completion)

Nothing in the working tree is still required for this phase — the runner
path, verification, cleanup, and docs are all committed. Everything below is
intentionally left untouched.

Unrelated pre-existing work (tracked, modified):

- `.gitignore` — user's docs allowlist edits (predates this work).
- `README.md` — pre-existing edits.
- `bin/ableton-contained` — pre-existing edits.

Unrelated pre-existing diagnostic tooling (untracked; historically useful,
referenced by the findings record, not part of the runner path):

- `bin/ableton-session-probe` — session snapshot probe. Note: the committed
  `bin/ableton-dxvk-version-test` calls it; that dependency predates this
  phase and only matters when re-running the DXVK A/B harness.
- `bin/ableton-runner-test` — copied-prefix runner comparison harness.
- `bin/ableton-window-ownership-probe`, `bin/ableton-windowing-status`,
  `bin/diagnose-ableton-graphics-backend`, `bin/diagnose-ableton-interaction`,
  `bin/diagnose-ableton-windowing` — investigation probes.
- `docs/ableton-custom-compat-layer.md`, `docs/ableton-dxvk-loader-audit.md`,
  `docs/ableton-runner-candidate-plan.md`,
  `docs/ableton-runner-test-harness.md`,
  `docs/ableton-system-wine-baseline-next.md`, `docs/ableton-x11-ab-test.md`
  — investigation records for closed branches (gitignored by `docs/*`).

Obsolete diagnostic leftovers (untracked; belong to ruled-out branches —
KWin/geometry/cursor/WebView2/wined3d/loader — candidates for deletion in a
future cleanup, not deleted here):

- `bin/ableton-cursor-guard`, `bin/fix-ableton-window-bounds`,
  `bin/install-ableton-kwin-rule`, `bin/log-ableton-window-geometry`,
  `bin/watch-ableton-window-geometry` — geometry/cursor/KWin branch (ruled out).
- `bin/ableton-webview2-mode` — WebView2 flag modes (ruled out as fix).
- `bin/ableton-graphics-wined3d-cleantest` — wined3d test (not viable).
- `bin/ableton-dxvk-loader-probe`, `bin/ableton-dxvk-pe-loader-probe`,
  `.local-tools/` (built PE probe), `tools/` (cursor helper sources) —
  abandoned runner-candidate loader audit.

## Merge status — ON HOLD (deliberate, user-gated)

Closeout audit accepted 2026-07-04 at commit `e90bc4c` on
`diagnosis/auth-dialog-interaction-rethink`. The branch is **merge-ready in
principle**: 9 commits ahead of `main` (`7cb64ab`), merge-base is `main`
itself, so a **fast-forward of `main` to `e90bc4c` is possible** with no
conflicts. Verification suite passed 22/22 at closeout.

The actual merge is deliberately **on hold** until explicitly instructed, and
must be preceded by deliberate handling of the unrelated dirty **tracked**
files in the working tree: `.gitignore`, `README.md`, `bin/ableton-contained`.
Do not merge from the dirty tree.

Known cosmetic issue to resolve at merge time: the **committed** `.gitignore`
ignores `docs/*` wholesale while this branch tracks five docs files; the
user's uncommitted allowlist covers the six older investigation docs but not
the four newer committed ones
(`ableton-authorization-interaction-rethink.md`, `ableton-proton-runner-mode.md`,
`ableton-proton-phase-completion.md`, `ableton-proton-user-auth-validation.md`).
Tracked files stay tracked regardless, but the allowlist should be extended
with those four `!docs/…` negations when `.gitignore` is next committed.

Agreed future merge procedure (execute only when explicitly instructed):
protect/resolve the three unrelated dirty tracked files first, then
fast-forward `main` to `e90bc4c`.

## Single next action — LATER, when the user chooses to authorize

Run `WAYDAW_ABLETON_RUNNER=proton-exp ./bin/ableton`, perform the legitimate
authorization by hand, confirm editor interactivity, then ask for a
post-authorization capture and a persistence relaunch. Until then, nothing
about the default launcher or working prefix changes.
