#!/usr/bin/env bash
# Gazelle FEL Stage37 original-module audit: offline only, no device access.
set -euo pipefail
COMMIT=ba2216da061f6d88daf4507c5254caaafce4cff7
GIT_BLOB=2cea08d212ffb9d685a789389708cbcead6dfb86
OWNER_ZIP="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -ge 1 ]; then OWNER_ZIP="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage37-results"
mkdir -p "$OUT"
SCRIPT="$OUT/audit-stage37-provider-bridge.py"
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/tools/gazelle-fel/audit-stage37-provider-bridge.py" \
  -o "$SCRIPT"
python3 - "$SCRIPT" "$GIT_BLOB" <<'PY'
import hashlib,pathlib,sys
src=pathlib.Path(sys.argv[1]).read_bytes()
blob=hashlib.sha1(b"blob "+str(len(src)).encode()+b"\0"+src).hexdigest()
if blob!=sys.argv[2]:raise SystemExit("GAZELLE_FEL_STAGE37_SCRIPT_HASH_MISMATCH")
print("GAZELLE_FEL_STAGE37_SOURCE_PIN_PASS")
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVMBIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVMBIN/llvm-objdump" ]; then
  echo "Install LLVM: brew install llvm" >&2;exit 2
 fi
 export PATH="$LLVMBIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINDIR="$(brew --prefix binutils 2>/dev/null)/bin" || true
 EXE=''
 for f in "$BINDIR/greadelf" "$BINDIR/readelf"; do
  if [ -x "$f" ]; then EXE="$f";break;fi
 done
 if [ -z "$EXE" ]; then echo "Install binutils: brew install binutils" >&2;exit 2;fi
 mkdir -p "$OUT/tools";ln -sf "$EXE" "$OUT/tools/readelf"
 export PATH="$OUT/tools:$PATH"
fi
python3 "$SCRIPT" --selftest
if [ ! -f "$OWNER_ZIP" ]; then
 echo "Original kernel ZIP missing: $OWNER_ZIP" >&2; exit 2
fi
python3 "$SCRIPT" "$OWNER_ZIP" | tee "$OUT/stage37-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage37-audit-results.txt"
