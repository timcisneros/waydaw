#!/usr/bin/env bash
# Pure path validation shared by launch and cleanup. Resolve symlink aliases.
waydaw_copied_prefix() {
  local working candidate
  working="$(realpath -m -- "$HOME/WinePrefixes/ableton12")" || return 1
  candidate="$(realpath -m -- "${WAYDAW_ABLETON_RUNNER_PREFIX:-$HOME/WinePrefixes/ableton12-winebase-protonexp-test}")" || return 1
  if [[ "$candidate" == "$working" || "$candidate/" == "$working/"* || "$working/" == "$candidate/"* ]]; then
    printf 'ERROR: refuses to target the working prefix or an overlapping path: %s\n' "$candidate" >&2
    return 1
  fi
  if [[ "$candidate" == *$'\n'* ]]; then
    printf 'ERROR: prefix paths must not contain newlines.\n' >&2
    return 1
  fi
  local path resolved
  for path in "$candidate/drive_c/windows/system32" "$candidate/drive_c/users" "$candidate/drive_c/ProgramData" "$candidate/drive_c/Program Files" "$candidate/drive_c/Program Files (x86)"; do
    resolved="$(realpath -m -- "$path")" || return 1
    [[ "$resolved/" == "$candidate/"* ]] || {
      printf 'ERROR: copied-prefix directory escapes the prefix: %s\n' "$path" >&2
      return 1
    }
  done
  printf '%s\n' "$candidate"
}
