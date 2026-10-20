#!/usr/bin/env bash
# Stage33 original HEVC config ABI audit. Host-only; zero Cube/ADB actions.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/audit-stage33-original-hevc-config.py"
EXPECTED_BLOB=14cbd648a32d492c58ad3a9dde75f076cbcb5837
ARCHIVE="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -ge 1 ]; then ARCHIVE="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage33-results"
PRIVATE="$OUT/private-original-module"
mkdir -p "$OUT" "$PRIVATE"
python3 - "$CHECK" "$EXPECTED_BLOB" "$ARCHIVE" "$PRIVATE" <<'PY'
import hashlib,pathlib,sys,zipfile
script=pathlib.Path(sys.argv[1]).read_bytes()
blob=hashlib.sha1(b'blob '+str(len(script)).encode()+b'\0'+script).hexdigest()
if blob != sys.argv[2]:raise SystemExit('GAZELLE_STAGE33_SCRIPT_PIN_MISMATCH')
print('GAZELLE_STAGE33_SCRIPT_PIN_PASS')
p=pathlib.Path(sys.argv[3]).expanduser()
if not p.is_file():raise SystemExit('Original owner kernel ZIP absent: '+str(p))
sha=hashlib.sha256(p.read_bytes()).hexdigest()
if sha!='02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44':
    raise SystemExit('GAZELLE_STAGE33_KERNEL_ARCHIVE_SHA_MISMATCH')
src='gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_amvdec_h265.ko'
with zipfile.ZipFile(p) as z:
    matches=[i for i in z.infolist() if i.filename==src and not i.is_dir()]
    if len(matches)!=1 or matches[0].file_size!=1341624:
        raise SystemExit('GAZELLE_STAGE33_ORIGINAL_MODULE_PATH_MISMATCH')
    content=z.read(matches[0])
if hashlib.sha256(content).hexdigest()!='0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040':
    raise SystemExit('GAZELLE_STAGE33_ORIGINAL_HEVC_SHA_MISMATCH')
f=pathlib.Path(sys.argv[4])/'amvdec_h265.ko'
f.write_bytes(content)
print('GAZELLE_STAGE33_ORIGINAL_MODULE_EXTRACT_PIN_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
  LLVM_BIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
  if [ ! -x "$LLVM_BIN/llvm-objdump" ]; then
    echo 'ERROR: Install LLVM: brew install llvm' >&2
    exit 2
  fi
  export PATH="$LLVM_BIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
  BINUTILS_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
  READELF=''
  for candidate in "$BINUTILS_BIN/readelf" "$BINUTILS_BIN/greadelf" "$(command -v greadelf 2>/dev/null || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then READELF="$candidate"; break; fi
  done
  if [ -z "$READELF" ]; then
    echo 'ERROR: Install GNU readelf: brew install binutils' >&2
    exit 2
  fi
  mkdir -p "$OUT/tools"
  ln -sf "$READELF" "$OUT/tools/readelf"
  export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
python3 "$CHECK" "$PRIVATE/amvdec_h265.ko" | tee "$OUT/stage33-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage33-audit-results.txt"
echo "PRIVATE_ORIGINAL_MODULE=$PRIVATE/amvdec_h265.ko (do not publish)"
