#!/usr/bin/env bash
# Stage39 original-kernel provider-name decision-table audit. Host-only, no ADB.
set -euo pipefail
COMMIT=9b463f3e11133508538453e648fd87b3f503cf17
GIT_BLOB=2889aca4532a04bb9627332accc30c3b04e549b6
ORIGINAL="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -ge 1 ]; then ORIGINAL="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage39-results"
mkdir -p "$OUT"
CHECK="$OUT/audit-stage39-provider-names.py"
curl -fsSL --retry 3 \
 "https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/tools/gazelle-fel/audit-stage39-provider-names.py" -o "$CHECK"
python3 - "$CHECK" "$GIT_BLOB" <<'PY'
import hashlib,pathlib,sys
src=pathlib.Path(sys.argv[1]).read_bytes()
digest=hashlib.sha1(b'blob '+str(len(src)).encode()+b'\0'+src).hexdigest()
if digest!=sys.argv[2]:raise SystemExit('GAZELLE_STAGE39_VERIFIER_BLOB_MISMATCH')
print('GAZELLE_STAGE39_SOURCE_PIN_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVM_BIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVM_BIN/llvm-objdump" ]; then echo 'brew install llvm' >&2;exit 2;fi
 export PATH="$LLVM_BIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINUTILS_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
 GNUREADELF=''
 for f in "$BINUTILS_BIN/greadelf" "$BINUTILS_BIN/readelf"; do
   if [ -x "$f" ]; then GNUREADELF="$f";break;fi
 done
 if [ -z "$GNUREADELF" ]; then echo 'brew install binutils' >&2;exit 2;fi
 mkdir -p "$OUT/tools"; ln -sf "$GNUREADELF" "$OUT/tools/readelf"
 export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
if [ ! -f "$ORIGINAL" ]; then echo "Original kernel ZIP missing: $ORIGINAL" >&2;exit 2;fi
python3 "$CHECK" "$ORIGINAL" | tee "$OUT/stage39-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage39-audit-results.txt"
echo 'No device reads or writes performed. Proprietary ELFs remain private.'
