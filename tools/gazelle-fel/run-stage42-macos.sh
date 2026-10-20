#!/usr/bin/env bash
# Stage42: exact local source pin + original-kernel offline audit;
# optional separate opt-in manual playback, read-only vdec/core capture.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/stage42-connected-core.py"
EXPECTED_SHA="424582bb1ccac54bba507ca14a15bce0866d0abcd37189c30f22af2d1a1b09bd"
ARCHIVE="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -gt 0 ]; then ARCHIVE="$1"; fi
RESULTS="$HOME/Downloads/gazelle-fel-stage42-results"
mkdir -p "$RESULTS"
python3 - "$CHECK" "$EXPECTED_SHA" <<'PY'
import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1]);digest=hashlib.sha256(p.read_bytes()).hexdigest()
if digest!=sys.argv[2]:raise SystemExit('STAGE42_BUNDLED_SOURCE_SHA256_MISMATCH')
print('GAZELLE_FEL_STAGE42_SOURCE_SHA_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
  LLVM="$(brew --prefix llvm 2>/dev/null)/bin" || true
  if [ ! -x "$LLVM/llvm-objdump" ]; then echo 'Install llvm: brew install llvm' >&2;exit 2;fi
  export PATH="$LLVM:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
  GNU_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
  READELF=''
  for f in "$GNU_BIN/greadelf" "$GNU_BIN/readelf"; do if [ -x "$f" ];then READELF="$f";break;fi;done
  if [ -z "$READELF" ];then echo 'Install binutils: brew install binutils' >&2;exit 2;fi
  mkdir -p "$RESULTS/tools";ln -sf "$READELF" "$RESULTS/tools/readelf"
  export PATH="$RESULTS/tools:$PATH"
fi
python3 "$CHECK" --selftest
python3 "$CHECK" --audit "$ARCHIVE" | tee "$RESULTS/stage42-offline-audit-results.txt"
printf '\nOptional separate capture: only read /sys/class/vdec/core and existing status files.\n'
printf 'Original raw core output includes kernel pointer addresses but will NOT be saved.\n'
printf 'To capture manually-controlled idle, P8 and P7, type YES; otherwise press Enter: '
read -r ANSWER
if [ "$ANSWER" != 'YES' ]; then
  echo "OFFLINE_COMPLETE=$RESULTS/stage42-offline-audit-results.txt"
  exit 0
fi
python3 "$CHECK" --capture --out "$RESULTS"
