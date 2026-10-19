#!/usr/bin/env bash
# Stage30 host-only original vendor audit. Does not contact the Cube.
set -euo pipefail
ZIP="$HOME/Downloads/03-vendor-odm.zip"
if [ "$#" -ge 1 ]; then ZIP="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage30-results"
PRIVATE="$OUT/private-original-vendor-libraries"
COMMIT=03833bc9f64e4afdaf1db686a1913b52de5c9a97
BLOB=6f6973eb158129b3e5e21a0353f02aa80a386ebf
SCRIPT=tools/gazelle-fel/audit-stage30-vendor-profile.py
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT" "$PRIVATE"
if ! command -v llvm-objdump >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew LLVM missing; install Homebrew and brew install llvm" >&2
    exit 2
  fi
  LLVMBIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
  if [ -x "$LLVMBIN/llvm-objdump" ]; then export PATH="$LLVMBIN:$PATH"
  else echo "ERROR: brew install llvm" >&2; exit 2; fi
fi
test -f "$ZIP" || { echo "ERROR: original 03-vendor-odm.zip missing: $ZIP" >&2; exit 2; }
python3 "$HERE/extract-stage30-vendor.py" "$ZIP" "$PRIVATE"
DEST="$OUT/audit-stage30-vendor-profile.py"
curl -fsSL --retry 3 "https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/$SCRIPT" -o "$DEST"
python3 - "$DEST" "$BLOB" <<'PY'
import hashlib,pathlib,sys
b=pathlib.Path(sys.argv[1]).read_bytes()
h=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
if h != sys.argv[2]:raise SystemExit('GAZELLE_STAGE30_SCRIPT_BLOB_MISMATCH')
print('GAZELLE_STAGE30_SCRIPT_PIN_PASS')
PY
python3 "$DEST" --selftest
python3 "$DEST" "$PRIVATE" | tee "$OUT/stage30-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage30-audit-results.txt"
echo "KEEP PRIVATE: original ELF copies are stored locally under $PRIVATE"
