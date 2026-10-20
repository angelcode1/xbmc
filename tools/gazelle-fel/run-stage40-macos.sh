#!/usr/bin/env bash
# Stage40 original paired-decoder lifecycle audit. OFFLINE ONLY; no ADB.
set -euo pipefail
COMMIT=6193aa8b1697ca793d0b205e72998c2a8ff61ee4
BLOB=5e45e44e65001fafdfe7de938a5cb2b85d5eb935
OWNER_ZIP="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -gt 0 ]; then OWNER_ZIP="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage40-results"
mkdir -p "$OUT"
CHECK="$OUT/audit-stage40-pair-open-release.py"
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/tools/gazelle-fel/audit-stage40-pair-open-release.py" \
  -o "$CHECK"
python3 - "$CHECK" "$BLOB" <<'PY'
import hashlib,pathlib,sys
blob=pathlib.Path(sys.argv[1]).read_bytes()
sha=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
if sha!=sys.argv[2]:raise SystemExit("STAGE40_VERIFIER_SOURCE_PIN_MISMATCH")
print("GAZELLE_FEL_STAGE40_SOURCE_PIN_PASS")
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVM_BIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVM_BIN/llvm-objdump" ]; then echo 'Install: brew install llvm' >&2;exit 2;fi
 export PATH="$LLVM_BIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINUTILS_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
 EXE=''
 for f in "$BINUTILS_BIN/greadelf" "$BINUTILS_BIN/readelf"; do
  if [ -x "$f" ]; then EXE="$f";break;fi
 done
 if [ -z "$EXE" ]; then echo 'Install: brew install binutils' >&2;exit 2;fi
 mkdir -p "$OUT/tools"
 ln -sf "$EXE" "$OUT/tools/readelf"
 export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
if [ ! -f "$OWNER_ZIP" ]; then
 echo "Original private kernel ZIP missing: $OWNER_ZIP" >&2;exit 2
fi
python3 "$CHECK" "$OWNER_ZIP" | tee "$OUT/stage40-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage40-audit-results.txt"
echo 'Original Amazon binary data was NOT included in the output or uploaded to GitHub.'
