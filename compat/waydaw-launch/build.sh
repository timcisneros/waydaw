#!/usr/bin/env bash
# Build only; never execute Wine or modify a prefix.
set -euo pipefail
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SRC_DIR/../.." && pwd)"
OUT_DIR="$ROOT_DIR/.local-tools/waydaw-launch"
CC="${WAYDAW_MINGW_CC:-x86_64-w64-mingw32-gcc}"
command -v "$CC" >/dev/null || { printf 'ERROR: %s is required.\n' "$CC" >&2; exit 1; }
mkdir -p "$OUT_DIR"
"$CC" -municode -O2 -Wall -Wextra -Werror -o "$OUT_DIR/wait-bome.exe" \
  "$SRC_DIR/wait-bome.c" -luser32 -static-libgcc -Wl,--no-insert-timestamp
printf 'built: %s\n' "$OUT_DIR/wait-bome.exe"
sha256sum "$OUT_DIR/wait-bome.exe"
