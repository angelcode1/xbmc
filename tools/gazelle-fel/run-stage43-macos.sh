#!/usr/bin/env bash
# Stage43: verify original connected-list bridge and sanitized Stage42 ZIP OFFLINE.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/audit-stage43-connected-pair.py"
PIN='d348e953fac3252df2459bfed0684162c6cefb71a75c6dd93579c5511b299990'
ORIGINAL="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
CAPTURE="$HOME/Downloads/stage42-connected-decoder-20261020-064046.zip"
if [ "$#" -ge 1 ]; then ORIGINAL="$1"; fi
if [ "$#" -ge 2 ]; then CAPTURE="$2"; fi
RESULTS="$HOME/Downloads/gazelle-fel-stage43-results"
mkdir -p "$RESULTS"
python3 - "$CHECK" "$PIN" <<'PY'
from pathlib import Path
import hashlib,sys
if hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()!=sys.argv[2]:
 raise SystemExit('STAGE43_VERIFIER_SHA256_MISMATCH')
print('GAZELLE_FEL_STAGE43_SCRIPT_PIN_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVM_BIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVM_BIN/llvm-objdump" ]; then echo 'Run: brew install llvm' >&2; exit 2; fi
 export PATH="$LLVM_BIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINUTILS_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
 EXE=""
 for f in "$BINUTILS_BIN/greadelf" "$BINUTILS_BIN/readelf"; do
  if [ -x "$f" ]; then EXE="$f"; break; fi
 done
 if [ -z "$EXE" ]; then echo 'Run: brew install binutils' >&2; exit 2; fi
 mkdir -p "$RESULTS/tools";ln -sf "$EXE" "$RESULTS/tools/readelf"
 export PATH="$RESULTS/tools:$PATH"
fi
python3 "$CHECK" --selftest
python3 "$CHECK" "$ORIGINAL" "$CAPTURE" | tee "$RESULTS/stage43-audit-results.txt"
echo "UPLOAD_FILE=$RESULTS/stage43-audit-results.txt"
echo 'No Cube access and no proprietary ELFs or raw kernel pointers in this report.'
