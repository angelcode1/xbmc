#!/usr/bin/env bash
# Gazelle FEL Stage36: strictly offline original HEVC metadata-export audit.
# No ADB, sysfs writes, OMX, Kodi, Magisk or device access.
set -euo pipefail
COMMIT=cd60d680483b11c4df3020205ded36d41d120b68
BLOB=5172e475f2e1f93cfbe640b7b693527d68b2c7f5
ZIP="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -gt 0 ]; then ZIP="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage36-results"
PRIVATE="$OUT/private-original-module"
mkdir -p "$PRIVATE"
CHECK="$OUT/audit-stage36-meta-export-gates.py"
URL="https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/tools/gazelle-fel/audit-stage36-meta-export-gates.py"
curl -fsSL --retry 3 "$URL" -o "$CHECK"
python3 - "$CHECK" "$BLOB" "$ZIP" "$PRIVATE" <<'PY'
import hashlib,pathlib,sys,zipfile
script=pathlib.Path(sys.argv[1]).read_bytes()
blob=hashlib.sha1(b'blob '+str(len(script)).encode()+b'\x00'+script).hexdigest()
if blob != sys.argv[2]:raise SystemExit('STAGE36_VERIFIER_HASH_MISMATCH')
print('GAZELLE_FEL_STAGE36_SCRIPT_PIN_PASS')
zipfile_path=pathlib.Path(sys.argv[3]).expanduser()
if not zipfile_path.is_file():raise SystemExit('Original kernel ZIP missing: '+str(zipfile_path))
if hashlib.sha256(zipfile_path.read_bytes()).hexdigest()!='02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44':
 raise SystemExit('STAGE36_OWNER_KERNEL_ARCHIVE_HASH_MISMATCH')
member='gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_amvdec_h265.ko'
with zipfile.ZipFile(zipfile_path) as z:
 records=[i for i in z.infolist() if i.filename==member and not i.is_dir()]
 if len(records)!=1 or records[0].file_size!=1341624:raise SystemExit('STAGE36_OWNER_MODULE_INVENTORY_MISMATCH')
 raw=z.read(records[0])
if hashlib.sha256(raw).hexdigest()!='0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040':
 raise SystemExit('STAGE36_OWNER_MODULE_SHA_MISMATCH')
(pathlib.Path(sys.argv[4])/'amvdec_h265.ko').write_bytes(raw)
print('GAZELLE_FEL_STAGE36_OWNER_MODULE_PIN_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
  LLVMBIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
  if [ ! -x "$LLVMBIN/llvm-objdump" ]; then echo 'Run: brew install llvm' >&2; exit 2; fi
  export PATH="$LLVMBIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
  BINUTILSBIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
  READELF=''
  for candidate in "$BINUTILSBIN/greadelf" "$BINUTILSBIN/readelf"; do
    if [ -x "$candidate" ]; then READELF="$candidate"; break; fi
  done
  if [ -z "$READELF" ]; then echo 'Run: brew install binutils' >&2; exit 2; fi
  mkdir -p "$OUT/tools"
  ln -sf "$READELF" "$OUT/tools/readelf"
  export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
python3 "$CHECK" "$PRIVATE/amvdec_h265.ko" | tee "$OUT/stage36-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage36-audit-results.txt"
echo "Original proprietary module remains private on your Mac: $PRIVATE"
