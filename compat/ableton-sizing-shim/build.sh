#!/usr/bin/env bash
# Build the WayDAW sizing shim (proxy version.dll) with the system mingw
# cross-compiler. Output goes to .local-tools/ableton-sizing-shim/ (untracked
# build artifact); the proton-exp runner installs it into the COPIED test
# prefix at real launch. Never installed anywhere by this script.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SRC_DIR/../.." && pwd)"
OUT_DIR="$ROOT_DIR/.local-tools/ableton-sizing-shim"

CC="${WAYDAW_MINGW_CC:-x86_64-w64-mingw32-gcc}"
if ! command -v "$CC" >/dev/null 2>&1; then
  echo "build ERROR: $CC not found (mingw cross-compiler required)" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
"$CC" -shared -O2 -Wall -Wextra \
  -o "$OUT_DIR/version.dll" \
  "$SRC_DIR/version-shim.c" "$SRC_DIR/version.def" \
  -luser32 -lkernel32 -static-libgcc

echo "built: $OUT_DIR/version.dll"
sha256sum "$OUT_DIR/version.dll"
