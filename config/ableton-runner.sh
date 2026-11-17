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
#     them keeps the pinned native DXVK DLLs intact through launch.
#   * DXVK is force-enabled and, defensively, the pinned DXVK DLL hashes are
#     re-asserted into the test prefix (restored read-only from the working
#     prefix) in case a prior boot drifted them.

_waydaw_runner="${WAYDAW_ABLETON_RUNNER:-}"

if [[ -n "$_waydaw_runner" && "$_waydaw_runner" != system ]]; then
  _waydaw_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  source "$_waydaw_root/config/validated-runtime.sh"
  source "$_waydaw_root/config/prefix-safety.sh"
  case "$_waydaw_runner" in
    proton-exp)
      _rbin="$_waydaw_root/.local-runners/kron4ek-proton-exp-11.0/bin"
      if [[ ! -x "$_rbin/wine" ]]; then
        printf 'WAYDAW runner ERROR: proton-exp wine not found at %s\n' "$_rbin/wine" >&2
        return 1
      fi

      _working_prefix="$WINEPREFIX"
      # Proton mode targets the copied test prefix only.
      WINEPREFIX="$(waydaw_copied_prefix)" || return 1
      export WINEPREFIX
      if [[ ! -d "$WINEPREFIX" ]]; then
        printf 'WAYDAW runner ERROR: proton-exp test prefix does not exist: %s\n' "$WINEPREFIX" >&2
        return 1
      fi

      export PATH="$_rbin:$PATH"
      # Keep DXVK on and skip registry writes (see design notes above).
      export WAYDAW_ABLETON_GRAPHICS="${WAYDAW_ABLETON_GRAPHICS:-dxvk}"
      export WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY="${WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY:-1}"

      # KWin decoration controller (titlebar-flicker protection). Only FLAGGED
      # here — actually loaded by bin/ableton at real launch time (never on
      # source, never on dry-run), and unloaded by bin/ableton-proton-cleanup.
      # Set WAYDAW_ABLETON_KWIN_CONTROLLER=0 to opt out. See
      # docs/ableton-proton-custom-presentation-controller.md.
      export WAYDAW_ABLETON_KWIN_CONTROLLER="${WAYDAW_ABLETON_KWIN_CONTROLLER:-1}"

      # Windows-side sizing shim (full-height latch prevention). Only FLAGGED
      # here — bin/ableton installs the proxy version.dll into the COPIED
      # prefix and gates loading via WINEDLLOVERRIDES=version=n,b at real
      # launch only (never on source, never on dry-run). Set
      # WAYDAW_ABLETON_SIZING_SHIM=0 to opt out. See
      # docs/ableton-proton-full-height-preapply-options.md.
      export WAYDAW_ABLETON_SIZING_SHIM="${WAYDAW_ABLETON_SIZING_SHIM:-1}"
      export WAYDAW_ABLETON_SIZING_SHIM_DLL="${WAYDAW_ABLETON_SIZING_SHIM_DLL:-$_waydaw_root/.local-tools/ableton-sizing-shim/version.dll}"

      printf 'WAYDAW runner=proton-exp | wine=%s | prefix=%s | graphics=%s | no_registry=%s | kwin_controller=%s | sizing_shim=%s\n' \
        "$_rbin/wine" "$WINEPREFIX" "$WAYDAW_ABLETON_GRAPHICS" "$WAYDAW_ABLETON_DIAGNOSTIC_NO_REGISTRY" \
        "$WAYDAW_ABLETON_KWIN_CONTROLLER" "$WAYDAW_ABLETON_SIZING_SHIM" >&2
      ;;
    *)
      printf 'WAYDAW runner ERROR: unknown WAYDAW_ABLETON_RUNNER=%s (expected: system, proton-exp)\n' "$_waydaw_runner" >&2
      return 1
      ;;
  esac
  unset _rbin _working_prefix
fi

unset _waydaw_runner _waydaw_root

# Verification is separate from preparation: Wine startup (including Bome)
# may update prefix DLLs after preparation. Never repair a live Bome session.
waydaw_require_native_dxvk() {
  if head -c 128 -- "$1" 2>/dev/null | LC_ALL=C grep -aFq 'Wine builtin DLL'; then
    printf 'ERROR: DXVK %s has a Wine builtin marker; upstream native DXVK is required.\n' "$1" >&2
    return 1
  fi
}

waydaw_verify_dxvk() {
  local pair file expected actual
  for pair in "d3d11.dll:$WAYDAW_D3D11_SHA256" "dxgi.dll:$WAYDAW_DXGI_SHA256" "d3d10core.dll:$WAYDAW_D3D10CORE_SHA256"; do
    file="${pair%%:*}"; expected="${pair#*:}"
    actual="$(sha256sum "$WINEPREFIX/drive_c/windows/system32/$file" 2>/dev/null | awk '{print $1}')" || actual=""
    if [[ "$actual" != "$expected" ]]; then
      printf 'ERROR: DXVK verification failed for %s after prefix preparation; launch blocked.\n' "$file" >&2
      return 1
    fi
    waydaw_require_native_dxvk "$WINEPREFIX/drive_c/windows/system32/$file" || return 1
  done
}

# Sourcing config/env only selects a runner. Preparation is explicit and runs
# after inspection exits and after the supervisor has acquired its lock.
waydaw_prepare_proton_prefix() {
  [[ "${WAYDAW_ABLETON_RUNNER:-}" == proton-exp ]] || return 0
  local prefix system source_system pair file expected actual source_hash preferences seed
  prefix="$(waydaw_copied_prefix)" || return 1
  system="$prefix/drive_c/windows/system32"
  source_system="$HOME/WinePrefixes/ableton12/drive_c/windows/system32"
  for pair in "d3d11.dll:$WAYDAW_D3D11_SHA256" "dxgi.dll:$WAYDAW_DXGI_SHA256" "d3d10core.dll:$WAYDAW_D3D10CORE_SHA256"; do
    file="${pair%%:*}"; expected="${pair#*:}"
    actual="$(sha256sum "$system/$file" 2>/dev/null | awk '{print $1}')" || actual=""
    if [[ "$actual" == "$expected" && ! -L "$system/$file" ]]; then
      waydaw_require_native_dxvk "$system/$file" || return 1
      continue
    fi
    source_hash="$(sha256sum "$source_system/$file" 2>/dev/null | awk '{print $1}')" || source_hash=""
    if [[ "$source_hash" != "$expected" ]]; then
      printf 'ERROR: required DXVK %s is missing or changed; no verified restore source.\n' "$file" >&2
      return 1
    fi
    waydaw_require_native_dxvk "$source_system/$file" || return 1
    # Never follow a copied-prefix DLL symlink into the working prefix.
    rm -f -- "$system/$file" || return 1
    cp -- "$source_system/$file" "$system/$file" || return 1
    printf 'WAYDAW: restored verified DXVK %s in copied prefix\n' "$file"
  done
  # Use the current Linux user's copied profile rather than a hard-coded name.
  preferences="$(find "$prefix/drive_c/users/steamuser/AppData/Roaming/Ableton" -path '*/Preferences' -type d 2>/dev/null | sort | tail -1)" || preferences=""
  seed="$(find "$prefix/drive_c/users/${USER:-$(id -un)}/AppData/Roaming/Ableton" -path '*/Preferences/Preferences.cfg' -type f 2>/dev/null | sort | tail -1)" || seed=""
  if [[ -n "$preferences" ]]; then
    local resolved_preferences
    resolved_preferences="$(realpath -m -- "$preferences/Preferences.cfg")" || return 1
    [[ "$resolved_preferences/" == "$prefix/"* ]] || {
      printf 'ERROR: Preferences.cfg escapes the copied prefix.\n' >&2
      return 1
    }
  fi
  if [[ -n "$preferences" && ! -e "$preferences/Preferences.cfg" && -n "$seed" ]]; then
    cp -- "$seed" "$preferences/Preferences.cfg" || return 1
  fi
  if [[ -n "$preferences" && -f "$preferences/Preferences.cfg" ]]; then
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bin/ableton-proton-normalize-placement" \
      "$preferences/Preferences.cfg" "${WAYDAW_ABLETON_MAX_WINDOW_HEIGHT:-1026}" || return 1
  fi
}
