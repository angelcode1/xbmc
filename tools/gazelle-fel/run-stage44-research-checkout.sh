#!/usr/bin/env bash
# Offline Stage44 original Fire OS native ABI gate from research checkout.
# This never accesses the Cube. Requires owner's private vendor archive locally.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ARCHIVE="$HOME/Downloads/03-vendor-odm.zip"
if [ "$#" -gt 0 ]; then ARCHIVE="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage44-results"
PRIVATE="$OUT/private-original-vendor-libraries"
mkdir -p "$OUT" "$PRIVATE"
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVM_BIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVM_BIN/llvm-objdump" ]; then
  echo 'Install: brew install llvm' >&2;exit 2
 fi
 export PATH="$LLVM_BIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINUTILS_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
 READELF=''
 for p in "$BINUTILS_BIN/greadelf" "$BINUTILS_BIN/readelf"; do
  if [ -x "$p" ]; then READELF="$p";break;fi
 done
 if [ -z "$READELF" ]; then echo 'Install: brew install binutils' >&2;exit 2;fi
 mkdir -p "$OUT/tools"
 ln -sf "$READELF" "$OUT/tools/readelf"
 export PATH="$OUT/tools:$PATH"
fi
python3 "$HERE/audit-stage44-native-abi-readiness.py" --selftest
python3 "$HERE/extract-stage30-vendor.py" "$ARCHIVE" "$PRIVATE"
python3 "$HERE/audit-stage44-native-abi-readiness.py" "$PRIVATE" 2>&1 \
 | tee "$OUT/stage44-research-checkout-audit.txt"
echo "REPORT=$OUT/stage44-research-checkout-audit.txt"
