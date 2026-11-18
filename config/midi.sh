#!/usr/bin/env bash
# Optional MIDI route maintenance; sourced by the guarded supervisor.
waydaw_midi_next_check=0
waydaw_midi_status=""
waydaw_midi_input_verified=0
waydaw_midi_mode() {
  local mode="off" config_file="${XDG_CONFIG_HOME:-$HOME/.config}/waydaw/midi-route"
  if [[ ${WAYDAW_MIDI_ROUTE+x} ]]; then
    mode="${WAYDAW_MIDI_ROUTE:-off}"
  elif [[ -e "$config_file" || -L "$config_file" ]]; then
    [[ -f "$config_file" && -r "$config_file" ]] || {
      printf 'ERROR: MIDI route configuration is not a readable file.\n' >&2; return 1;
    }
    mode="$(cat -- "$config_file")" || return 1
  fi
  case "$mode" in
    off|bome) printf '%s\n' "$mode" ;;
    *) printf 'ERROR: MIDI route configuration must be off or bome.\n' >&2; return 1 ;;
  esac
}

waydaw_maintain_midi_routes() {
  local root="$1" mode="$2" with_bome="$3" report status
  local -a reconnect=()
  [[ "$mode" == bome && "$with_bome" == 1 ]] || return 0
  (( SECONDS >= waydaw_midi_next_check )) || return 0
  # The Python helper checks session and application ownership before every
  # change. Unavailable ports must leave Ableton open for audio and saving.
  status=waiting
  [[ "$waydaw_midi_input_verified" != 1 ]] || reconnect=(--reconnect)
  if report="$(timeout --kill-after=1 2 python3 "$root/config/midi-routing.py" route --mode bome --apply "${reconnect[@]}" 9>&- 2>&1)"; then
    status=ready
    waydaw_midi_input_verified=1
  fi
  waydaw_midi_next_check=$((SECONDS + 2))
  if [[ "$status" != "$waydaw_midi_status" ]]; then
    printf 'midi_routing=%s\n' "$status" || true
    [[ "$status" != waiting ]] || printf '%s\n' "$report" || true
    waydaw_midi_status="$status"
  fi
  return 0
}
