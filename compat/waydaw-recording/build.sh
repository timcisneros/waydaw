#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out="$root/.local-tools/waydaw-recording"
mkdir -p -- "$out"
temporary=$(mktemp -- "$out/.headroom-XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
if [[ -n "${WAYDAW_PIPEWIRE_INCLUDE_ROOT:-}" ]]; then
  include="$WAYDAW_PIPEWIRE_INCLUDE_ROOT"
  flags=(-isystem "$include/pipewire-0.3" -isystem "$include/spa-0.2")
  libraries=(-l:libpipewire-0.3.so.0)
else
  read -r -a flags <<< "$(pkg-config --cflags libpipewire-0.3)"
  # Dependency headers have their own warning policy.
  for i in "${!flags[@]}"; do flags[$i]=${flags[$i]/#-I/-isystem}; done
  read -r -a libraries <<< "$(pkg-config --libs libpipewire-0.3)"
fi
cc -std=gnu11 -Wall -Wextra -Werror -O2 "${flags[@]}" \
  "$root/compat/waydaw-recording/headroom.c" "${libraries[@]}" -o "$temporary"
chmod 755 "$temporary"
mv -f -- "$temporary" "$out/headroom"
