#!/usr/bin/env bash
# Authorization delivery runs in the supervisor's owned worker lifecycle.
# Runtime paths and worker identity are supplied by bin/waydaw.
# shellcheck disable=SC2154
waydaw_cancel_authorization() {
  [[ -d "$1/authorization" ]] || return 0
  python3 "$ROOT_DIR/config/ableton-authorization.py" cancel "$1/authorization"
}

waydaw_authorization_reply() {
  python3 "$ROOT_DIR/config/ableton-authorization.py" reply "$1" "$2" || {
    printf 'WARN: Could not report authorization delivery.\n' >&2 || true
  }
}

check_authorization_requests() {
  local request result
  if [[ -n "$authorization_pid" ]]; then
    if [[ -f "$log_dir/authorization.result" ]]; then
      result="$(cat "$log_dir/authorization.result" 2>/dev/null)" || result=1
    elif (( SECONDS >= authorization_deadline )); then
      result=1
    elif (( SECONDS >= authorization_owner_check )); then
      authorization_owner_check=$((SECONDS + 1))
      waydaw_same_process "$authorization_pid" "$authorization_birth" && return 0
      result=1
    else
      return 0
    fi
    [[ "$result" == 0 ]] || result=1
    waydaw_stop_worker "$runtime_dir/authorization.state" authorization || result=1
    waydaw_authorization_reply "$authorization_request" "$result"
    rm -f -- "$authorization_request" "$log_dir/authorization.result" || true
    if [[ "$result" == 0 ]]; then
      printf 'authorization_request=delivered\n' || true
    else
      printf 'ERROR: Authorization delivery failed; Ableton remains open.\n' >&2 || true
    fi
    if ! waydaw_same_process "$authorization_pid" "$authorization_birth"; then
      wait "$authorization_pid" 2>/dev/null || true
    fi
    authorization_pid=""
  fi
  [[ ! -f "$log_dir/ableton.result" ]] || return 0
  for request in "$log_dir/authorization/"*.request; do
    [[ -f "$request" && ! -L "$request" ]] || continue
    if [[ -e "$runtime_dir/authorization.state" ]]; then
      waydaw_authorization_reply "$request" 1
      rm -f -- "$request" || true
      return 0
    fi
    authorization_request="$request"
    launch_worker authorization python3 "$ROOT_DIR/config/ableton-authorization.py" \
      dispatch "$request" "$ROOT_DIR" "$prefix" "$ableton_file" >/dev/null 2>&1
    authorization_pid="$worker_pid"
    authorization_birth="$(waydaw_process_start "$authorization_pid" || true)"
    authorization_deadline=$((SECONDS + 30))
    authorization_owner_check=$((SECONDS + 1))
    break
  done
  return 0
}
