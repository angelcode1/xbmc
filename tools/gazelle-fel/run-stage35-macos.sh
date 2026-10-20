#!/usr/bin/env bash
# Host-only replay: fetch SHA-pinned Stage35 verifier and audit owner's local kernel module.
set -euo pipefail
COMMIT=2994900d33ca9fe5829671ffe714eb6e36fa4a1e
BLOB=a4df61a9d9fb3d96ac309b8361cc6b7508dfa0e9
OUT="$HOME/Downloads/gazelle-fel-stage35-results"
PRIVATE="$OUT/private-original-module"
ARCHIVE="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -gt 0 ]; then ARCHIVE="$1"; fi
mkdir -p "$OUT" "$PRIVATE"
SCRIPT="$OUT/audit-stage35-hevc-alias-consumers.py"
curl -fsSL --retry 3 \
"https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/tools/gazelle-fel/audit-stage35-hevc-alias-consumers.py" -o "$SCRIPT"
python3 - "$SCRIPT" "$BLOB" "$ARCHIVE" "$PRIVATE" <<'PY'
import hashlib,pathlib,sys,zipfile
b=pathlib.Path(sys.argv[1]).read_bytes()
blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
if blob!=sys.argv[2]:raise SystemExit('STAGE35_SOURCE_PIN_MISMATCH')
print('GAZELLE_FEL_STAGE35_SOURCE_PIN_PASS')
archive=pathlib.Path(sys.argv[3]).expanduser()
if not archive.is_file():raise SystemExit('Original owner ZIP missing: '+str(archive))
if hashlib.sha256(archive.read_bytes()).hexdigest()!='02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44':
 raise SystemExit('STAGE35_ORIGINAL_ARCHIVE_HASH_MISMATCH')
member='gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_amvdec_h265.ko'
with zipfile.ZipFile(archive) as z:
 info=[i for i in z.infolist() if i.filename==member and not i.is_dir()]
 if len(info)!=1 or info[0].file_size!=1341624:raise SystemExit('STAGE35_MODULE_INVENTORY_MISMATCH')
 data=z.read(info[0])
if hashlib.sha256(data).hexdigest()!='0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040':
 raise SystemExit('STAGE35_ORIGINAL_MODULE_SHA_MISMATCH')
(pathlib.Path(sys.argv[4])/'amvdec_h265.ko').write_bytes(data)
print('GAZELLE_FEL_STAGE35_ORIGINAL_MODULE_PIN_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVMBIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVMBIN/llvm-objdump" ]; then echo 'brew install llvm' >&2; exit 2; fi
 export PATH="$LLVMBIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINDIR="$(brew --prefix binutils 2>/dev/null)/bin" || true
 EXE=''
 for f in "$BINDIR/greadelf" "$BINDIR/readelf"; do
  if [ -x "$f" ]; then EXE="$f"; break; fi
 done
 if [ -z "$EXE" ]; then echo 'brew install binutils' >&2; exit 2; fi
 mkdir -p "$OUT/tools"
 ln -sf "$EXE" "$OUT/tools/readelf"
 export PATH="$OUT/tools:$PATH"
fi
python3 "$SCRIPT" --selftest
python3 "$SCRIPT" "$PRIVATE/amvdec_h265.ko" | tee "$OUT/stage35-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage35-audit-results.txt"
