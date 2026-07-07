#!/usr/bin/env bash
# WayDAW runner selection — sourced by config/env AFTER WINEPREFIX is set.
#
# Default (WAYDAW_ABLETON_RUNNER unset/empty or "system"): no-op. System Wine
# and the working prefix are used exactly as before. This file must not change
# any behavior unless a non-default runner is explicitly requested.
#
# WAYDAW_ABLETON_RUNNER=proton-exp: EXPERIMENTAL. Routes Ableton through the
# cached non-staging Proton-exp 11.0 runner, which (unlike system wine-staging
# 11.0) does not hit the RtlAcquireSRWLockExclusive UI-thread deadlock. This
# mode is intentionally restricted to the COPIED test prefix; it refuses to
# target the working prefix. See docs/ableton-proton-runner-mode.md.
#
# Design notes:
#   * PATH is prepended with the runner bin dir so unqualified wine/wineserver/
#     winedbg resolve to the runner.
#   * Proton mode forces the diagnostic no-registry launch path so bin/ableton
#     does NOT issue `wine reg` writes; those trigger a Proton prefix-update
#     that overwrites the prefix's DXVK d3d11/dxgi with Wine builtins. Skipping
#     them keeps the debug DXVK DLLs intact through launch (matches the
#     validated 2026-07-04 progress runs).
#   * DXVK is force-enabled and, defensively, the debug-DXVK DLL hashes are
#     re-asserted into the test prefix (restored read-only from the working
#     prefix) in case a prior boot drifted them.

_waydaw_runner="${WAYDAW_ABLETON_RUNNER:-}"

if [[ -n "$_waydaw_runner" && "$_waydaw_runner" != system ]]; then
  _waydaw_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  # Known-good debug DXVK (2.7) DLL hashes — the mandatory backend for this
  # prefix. The working prefix is the authoritative read-only source.
  _dxvk_d3d11_sha=557c1f50e7ff73bcd24968a02352519df89d8b3fe037d47580091ffafe1940dd
  _dxvk_dxgi_sha=f31cd64b547c59441956b17e2a013791dcb62abb1e671fb31d49ff4d6c2b3fd7

  case "$_waydaw_runner" in
    proton-exp)
      _rbin="$_waydaw_root/.local-runners/kron4ek-proton-exp-11.0/bin"
      if [[ ! -x "$_rbin/wine" ]]; then
        printf 'WAYDAW runner ERROR: proton-exp wine not found at %s\n' "$_rbin/wine" >&2
        return 1
      fi

      _working_prefix="$WINEPREFIX"
      # Proton mode targets the copied test prefix only.
      WINEPREFIX="${WAYDAW_ABLETON_RUNNER_PREFIX:-$HOME/WinePrefixes/ableton12-winebase-protonexp-test}"
      export WINEPREFIX
      if [[ "$WINEPREFIX" == "$_working_prefix" ]]; then
        printf 'WAYDAW runner ERROR: proton-exp refuses to target the working prefix (%s).\n' "$_working_prefix" >&2
        printf 'Set WAYDAW_ABLETON_RUNNER_PREFIX to a copied test prefix.\n' >&2
        return 1
      fi
      if [[ ! -d "$WINEPREFIX" ]]; then
        printf 'WAYDAW runner ERROR: proton-exp test prefix does not exist: %s\n' "$WINEPREFIX" >&2
        return 1
      fi

      export PATH="$_rbin:$PATH"
      # Keep DXVK on and skip registry writes (see design notes above).
      export WAYDAW_ABLETON_GRAPHICS="${WAYDAW_ABLETON_GRAPHICS:-dxvk}"
      export WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY="${WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY:-1}"

      # Defensive DXVK re-assert into the test prefix (working prefix read-only).
      _tsys="$WINEPREFIX/drive_c/windows/system32"
      _wsys="$_working_prefix/drive_c/windows/system32"
      _waydaw_sha() { sha256sum "$1" 2>/dev/null | awk '{print $1}'; }
      for _pair in "d3d11.dll:$_dxvk_d3d11_sha" "dxgi.dll:$_dxvk_dxgi_sha"; do
        _f="${_pair%%:*}"; _want="${_pair#*:}"
        if [[ "$(_waydaw_sha "$_tsys/$_f")" != "$_want" ]]; then
          if [[ "$(_waydaw_sha "$_wsys/$_f")" == "$_want" ]]; then
            cp -f "$_wsys/$_f" "$_tsys/$_f" \
              && printf 'WAYDAW runner: re-asserted debug DXVK %s into test prefix\n' "$_f" >&2
          else
            printf 'WAYDAW runner WARN: DXVK %s drifted and working-prefix source hash mismatch; not restored\n' "$_f" >&2
          fi
        fi
      done
      unset -f _waydaw_sha 2>/dev/null

      # Window-placement seed (copied prefix only). Proton runs Ableton as the
      # Windows user "steamuser", which has NO Preferences.cfg, so Ableton opens
      # with its default fullscreen (maximized both) window that Wine renders
      # frameless. Seed steamuser's Preferences.cfg from the prefix's own
      # "timcis" profile (the working-prefix-derived prefs, which open a normal
      # maximized-vertical decorated window). Only when steamuser has none, so
      # Ableton's own later saves win. See docs/ableton-proton-window-presentation.md.
      _abl="AppData/Roaming/Ableton"
      _su_pref="$(ls -d "$WINEPREFIX"/drive_c/users/steamuser/"$_abl"/Live\ */Preferences 2>/dev/null | head -1)"
      _tc_pref="$(ls -d "$WINEPREFIX"/drive_c/users/timcis/"$_abl"/Live\ */Preferences 2>/dev/null | head -1)"
      if [[ -n "$_su_pref" && -n "$_tc_pref" \
            && ! -f "$_su_pref/Preferences.cfg" && -f "$_tc_pref/Preferences.cfg" ]]; then
        cp -f "$_tc_pref/Preferences.cfg" "$_su_pref/Preferences.cfg" \
          && printf 'WAYDAW runner: seeded steamuser Ableton Preferences.cfg (decorated window placement)\n' >&2
      fi
      # Clamp the seeded/saved MainWindow placement to strictly SHORTER than the
      # screen. The stock seed height (1096) exceeds the 1080px screen, so the
      # window is coerced to vertical-maximize; Wine then loops forever
      # reconciling its 1096 client belief against the WM's 1052 grant, starving
      # the UI-thread message pump (no input, no close) while unauthorized. A
      # height that fits under the screen is granted verbatim -> no maximize ->
      # no storm. Runs every launch (idempotent) so Ableton-saved drift is
      # corrected too. See docs/ableton-proton-exp-message-pump-starvation.md.
      if [[ -n "$_su_pref" && -f "$_su_pref/Preferences.cfg" ]]; then
        if [[ "${WAYDAW_ABLETON_DRY_RUN:-0}" == 1 ]]; then
          printf 'WAYDAW runner: [dry-run] would clamp MainWindow placement height to <= %s in %s (no mutation)\n' \
            "${WAYDAW_ABLETON_MAX_WINDOW_HEIGHT:-1000}" "$_su_pref/Preferences.cfg" >&2
        else
          "$_waydaw_root/bin/ableton-proton-normalize-placement" \
            "$_su_pref/Preferences.cfg" "${WAYDAW_ABLETON_MAX_WINDOW_HEIGHT:-1000}" >&2 || true
        fi
      fi
      unset _abl _su_pref _tc_pref

      # KWin decoration controller (titlebar-flicker protection). Only FLAGGED
      # here — actually loaded by bin/ableton at real launch time (never on
      # source, never on dry-run), and unloaded by bin/ableton-proton-cleanup.
      # Set WAYDAW_ABLETON_KWIN_CONTROLLER=0 to opt out. See
      # docs/ableton-proton-custom-presentation-controller.md.
      export WAYDAW_ABLETON_KWIN_CONTROLLER="${WAYDAW_ABLETON_KWIN_CONTROLLER:-1}"

      printf 'WAYDAW runner=proton-exp | wine=%s | prefix=%s | graphics=%s | no_registry=%s | kwin_controller=%s\n' \
        "$_rbin/wine" "$WINEPREFIX" "$WAYDAW_ABLETON_GRAPHICS" "$WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY" \
        "$WAYDAW_ABLETON_KWIN_CONTROLLER" >&2
      ;;
    *)
      printf 'WAYDAW runner ERROR: unknown WAYDAW_ABLETON_RUNNER=%s (expected: system, proton-exp)\n' "$_waydaw_runner" >&2
      return 1
      ;;
  esac
  unset _rbin _working_prefix _tsys _wsys _pair _f _want
fi

unset _waydaw_runner _waydaw_root _dxvk_d3d11_sha _dxvk_dxgi_sha
