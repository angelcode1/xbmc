#!/usr/bin/env bash
# Gazelle Stage34 read-only original kernel DWARF/register-base audit. NO ADB.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/audit-stage34-hevc-register-bases.py"
MODULE_ZIP="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -gt 0 ]; then MODULE_ZIP="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage34-results"
PRIVATE="$OUT/private-original-kernel"
mkdir -p "$OUT" "$PRIVATE"
python3 - "$CHECK" "$MODULE_ZIP" "$PRIVATE" <<'PY'
from pathlib import Path
import hashlib,sys,zipfile
src=Path(sys.argv[1]).read_bytes()
blob=hashlib.sha1(b'blob '+str(len(src)).encode()+b'\0'+src).hexdigest()
EXPECTED_SCRIPT='TO_REPLACE_WITH_BUNDLED_SCRIPT_BLOB'
if blob!=EXPECTED_SCRIPT:raise SystemExit('GAZELLE_STAGE34_SCRIPT_SHA_MISMATCH '+blob)
print('GAZELLE_FEL_STAGE34_SCRIPT_PIN_PASS')
zipfile_path=Path(sys.argv[2]).expanduser()
if not zipfile_path.is_file():raise SystemExit('OWNER_ARCHIVE_MISSING '+str(zipfile_path))
sha=hashlib.sha256(zipfile_path.read_bytes()).hexdigest()
if sha!='02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44':
    raise SystemExit('GAZELLE_STAGE34_KERNEL_ARCHIVE_HASH_MISMATCH')
prefix='gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_'
pins={
 'amvdec_h265.ko':('0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040',1341624),
 'decoder_common.ko':('a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b',4015344),
}
with zipfile.ZipFile(zipfile_path) as z:
 for name,(expected,length) in pins.items():
    module=prefix+name
    infos=[i for i in z.infolist() if i.filename==module and not i.is_dir()]
    if len(infos)!=1 or infos[0].file_size!=length:
        raise SystemExit('GAZELLE_STAGE34_UNEXPECTED_MODULE '+name)
    b=z.read(infos[0])
    if hashlib.sha256(b).hexdigest()!=expected:
        raise SystemExit('GAZELLE_STAGE34_PRIVATE_MODULE_SHA_MISMATCH '+name)
    (Path(sys.argv[3])/name).write_bytes(b)
    print('GAZELLE_STAGE34_ORIGINAL_EXTRACTION_PASS',name)
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
    LLVMBIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
    if [ ! -x "$LLVMBIN/llvm-objdump" ]; then
        echo 'ERROR: brew install llvm' >&2; exit 2
    fi
    export PATH="$LLVMBIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
    BINUTILS="$(brew --prefix binutils 2>/dev/null)/bin" || true
    ORIGINAL_READELF=''
    for f in "$BINUTILS/greadelf" "$BINUTILS/readelf"; do
      if [ -x "$f" ]; then ORIGINAL_READELF="$f"; break; fi
    done
    if [ -z "$ORIGINAL_READELF" ]; then
       echo 'ERROR: brew install binutils' >&2; exit 2
    fi
    mkdir -p "$OUT/tools"
    ln -sf "$ORIGINAL_READELF" "$OUT/tools/readelf"
    export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
python3 "$CHECK" "$PRIVATE" | tee "$OUT/stage34-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage34-audit-results.txt"
echo "Original module files stay private under $PRIVATE"
