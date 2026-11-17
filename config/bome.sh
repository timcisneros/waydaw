#!/usr/bin/env bash
# Read-only Bome discovery, result parsing, and session health inspection.
waydaw_bome_executable() {
  local prefix="$1" candidate="" path
  local -a candidates=()
  for path in \
    "$prefix/drive_c/Program Files/Bome MIDI Translator Pro/MIDITranslator.exe" \
    "$prefix/drive_c/Program Files/Bome/Bome MIDI Translator Pro/MIDITranslator.exe" \
    "$prefix/drive_c/Program Files (x86)/Bome MIDI Translator Pro/MIDITranslator.exe" \
    "$prefix/drive_c/Program Files (x86)/Bome/Bome MIDI Translator Pro/MIDITranslator.exe"; do
    if [[ -f "$path" ]]; then candidate="$path"; break; fi
  done
  if [[ -z "$candidate" ]]; then
    # Exact application names exclude setup programs and executable backups.
    mapfile -d '' -t candidates < <(find "$prefix/drive_c" -type f \( -iname 'MIDITranslator.exe' -o -iname 'Bome MIDI Translator Pro.exe' \) -print0 2>/dev/null)
    if [[ ${#candidates[@]} -gt 1 ]]; then
      printf 'ERROR: Multiple Bome executables found outside the standard locations; install Bome in a standard location.\n' >&2
      return 1
    fi
    candidate="${candidates[0]:-}"
  fi
  if [[ -z "$candidate" ]]; then
    printf 'ERROR: Bome MIDI Translator Pro is missing from %s; install it before starting a full session.\n' "$prefix" >&2
    return 1
  fi
  if [[ "${WAYDAW_ABLETON_RUNNER:-}" == proton-exp ]]; then
    candidate="$(realpath -e -- "$candidate")" || return 1
    [[ "$candidate/" == "$prefix/"* ]] || {
      printf 'ERROR: Bome executable escapes the copied prefix.\n' >&2
      return 1
    }
  fi
  printf '%s\n' "$candidate"
}

waydaw_bome_exit_code() {
  local value
  if [[ ! -f "$1" || ! -r "$1" ]]; then
    printf '1\n'
    return 0
  fi
  value="$(cat -- "$1" 2>/dev/null)" || value=1
  if [[ "$value" =~ ^[0-9]{1,3}$ ]] && (( 10#$value <= 255 )); then
    printf '%s\n' "$((10#$value))"
  else
    # A missing or malformed result is a monitoring failure, never success.
    printf '1\n'
  fi
}

waydaw_bome_status_code() {
  local log_file="$1" receipt="$2" directory result_file path owner_valid=0 ready
  local -a owner=()
  # Legacy session records have no log path. Never guess from another session.
  [[ -n "$log_file" ]] || return 0
  directory="${log_file%/*}"
  result_file="$directory/bome.result"
  for path in "$directory/bome.exit" "$result_file"; do
    if [[ -e "$path" || -L "$path" ]]; then
      waydaw_bome_exit_code "$path"
      return 0
    fi
  done
  # The session lock guards this receipt, which remains available when session
  # log storage is unreadable. A visible GUI acknowledgement must also be valid.
  if [[ -e "$directory/bome.ready" || -L "$directory/bome.ready" ]]; then
    if [[ ! -f "$directory/bome.ready" || ! -r "$directory/bome.ready" ]]; then
      printf '1\n'
      return 0
    fi
    ready="$(cat -- "$directory/bome.ready" 2>/dev/null)" || ready=""
    if [[ "$ready" != ready ]]; then printf '1\n'; return 0; fi
  elif [[ ! -e "$receipt" && ! -L "$receipt" ]]; then
    return 0
  fi
  if [[ -f "$receipt" ]] && { mapfile -n 5 -t owner < "$receipt"; } 2>/dev/null \
      && [[ ( ${#owner[@]} -eq 3 || ( ${#owner[@]} -eq 4 && "${owner[3]:-}" == waiting ) )
         && "${owner[0]:-}" =~ ^[1-9][0-9]*$ && "${owner[0]}" != 1
         && "${owner[1]:-}" =~ ^[0-9]+$ && "${owner[2]:-}" == process-group-v1 ]] \
      && waydaw_same_process "${owner[0]}" "${owner[1]}" "${owner[0]}"; then
    owner_valid=1
  fi
  # Completion publishes the result before the waiting receipt. Re-read after
  # checking ownership to include a result published during this inspection.
  if [[ -e "$result_file" || -L "$result_file" ]]; then
    waydaw_bome_exit_code "$result_file"
  elif [[ "$owner_valid" == 0 || ${#owner[@]} -eq 4 ]]; then
    printf '1\n'
  fi
  return 0
}
