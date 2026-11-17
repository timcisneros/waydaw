#!/usr/bin/env bash
# Process identity and bounded cleanup for session-owned processes.
waydaw_process_start() {
  local stat
  [[ "$1" =~ ^[0-9]+$ && -r "/proc/$1/stat" ]] || return 1
  stat="$(cat "/proc/$1/stat" 2>/dev/null)" || return 1
  stat="${stat##*) }"
  # Field 22 after removing PID/comm. The optional second argument requires
  # a matching process group. Zombies have exited, even before reaping.
  awk -v group="${2:-}" '$1 == "Z" || $1 == "X" || (group != "" && $3 != group) {exit 1} {print $20}' <<<"$stat"
}

waydaw_same_process() {
  [[ -n "$2" && "$(waydaw_process_start "$1" "${3:-}" || true)" == "$2" ]]
}

waydaw_wait_process_exit() {
  local pid="$1" birth="$2" deadline=$((SECONDS + $3))
  while waydaw_same_process "$pid" "$birth"; do
    (( SECONDS < deadline )) || return 1
    sleep 0.05
  done
}

waydaw_stop_owned_bridge() {
  local receipt="$1" pid birth
  local -a owner
  [[ -e "$receipt" ]] || return 0
  mapfile -t owner < "$receipt"
  if [[ ${#owner[@]} != 2 || ! "${owner[0]}" =~ ^[0-9]+$ || ! "${owner[1]}" =~ ^[0-9]+$ ]]; then
    printf 'ERROR: invalid bridge ownership record; recovery required.\n' >&2
    return 1
  fi
  pid="${owner[0]}"; birth="${owner[1]}"
  if waydaw_same_process "$pid" "$birth"; then
    kill -TERM "$pid" 2>/dev/null || true
    if ! waydaw_wait_process_exit "$pid" "$birth" 2; then
      # Recheck identity immediately before escalation; never kill a reused PID.
      if waydaw_same_process "$pid" "$birth"; then
        kill -KILL "$pid" 2>/dev/null || true
        printf 'bridge_stop=forced\n'
      fi
      if ! waydaw_wait_process_exit "$pid" "$birth" 2; then
        printf 'ERROR: owned MIDI bridge did not exit; recovery required.\n' >&2
        return 1
      fi
    fi
  fi
  rm -f -- "$receipt"
}

waydaw_stop_worker() {
  local receipt="$1" label="$2"
  [[ -e "$receipt" ]] || return 0
  # Recover bridge receipts written by the earlier PID-only launcher as well.
  if [[ "$label" == bridge && "$(wc -l < "$receipt")" == 2 ]]; then
    waydaw_stop_owned_bridge "$receipt"
  else
    python3 "$ROOT_DIR/config/session-worker.py" stop "$receipt" "$label"
  fi
}
