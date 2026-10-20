#!/usr/bin/env bash
# Host-only original Fire OS vendor ELF audit. No ADB or device writes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VERIFIER="$HERE/audit-stage31-config-ack.py"
EXPECTED_BLOB=b8371b0b2a74590b5535c134a2b9347a7062e901
ORIGINAL="$HOME/Downloads/gazelle-fel-stage30-results/private-original-vendor-libraries/libOmxVideo.so"
if [ "$#" -gt 0 ]; then ORIGINAL="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage31-results"
mkdir -p "$OUT"
python3 - "$VERIFIER" "$EXPECTED_BLOB" <<'PY'
import hashlib,pathlib,sys
raw=pathlib.Path(sys.argv[1]).read_bytes()
sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
if sha!=sys.argv[2]:raise SystemExit('STAGE31_SCRIPT_PIN_MISMATCH')
print('GAZELLE_FEL_STAGE31_SCRIPT_PIN_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo 'ERROR: Install Homebrew LLVM with: brew install llvm' >&2
    exit 2
  fi
  LLVM_BIN="$(brew --prefix llvm)/bin"
  [ -x "$LLVM_BIN/llvm-objdump" ] || { echo 'ERROR: brew install llvm' >&2; exit 2; }
  export PATH="$LLVM_BIN:$PATH"
fi
if [ ! -f "$ORIGINAL" ]; then
  echo "ERROR: Original vendor ELF not found at $ORIGINAL" >&2
  echo 'Run Stage30 first, or pass /path/to/libOmxVideo.so as argument.' >&2
  exit 2
fi
python3 "$VERIFIER" --selftest
python3 "$VERIFIER" "$ORIGINAL" | tee "$OUT/stage31-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage31-audit-results.txt"
