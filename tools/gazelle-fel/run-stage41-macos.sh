#!/usr/bin/env bash
# Stage41 offline original kernel status gate plus opt-in read-only live comparison
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/stage41-instance-status.py"
ARCHIVE="$HOME/Downloads/gazelle-fel-kernel-readonly-20261019-191050.zip"
if [ "$#" -gt 0 ]; then ARCHIVE="$1"; fi
OUT="$HOME/Downloads/gazelle-fel-stage41-results"
mkdir -p "$OUT"
python3 - "$CHECK" <<'PYIN'
import pathlib,hashlib,sys
p=pathlib.Path(sys.argv[1]);b=p.read_bytes()
expected='0388105f67e77b856a5bb9d34bfaf908b83df32e'
got=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\x00'+b).hexdigest()
if got != expected:raise SystemExit('STAGE41_SOURCE_BLOB_PIN_MISMATCH')
print('GAZELLE_FEL_STAGE41_SOURCE_PIN_PASS')
PYIN
if ! command -v llvm-objdump >/dev/null 2>&1; then
  LLVM="$(brew --prefix llvm 2>/dev/null)/bin" || true
  if [ ! -x "$LLVM/llvm-objdump" ]; then echo 'Install: brew install llvm' >&2;exit 2;fi
  export PATH="$LLVM:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
  BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
  EXE=""
  for f in "$BIN/greadelf" "$BIN/readelf"; do if [ -x "$f" ]; then EXE="$f";break;fi;done
  if [ -z "$EXE" ]; then echo 'Install: brew install binutils' >&2;exit 2;fi
  mkdir -p "$OUT/tools";ln -sf "$EXE" "$OUT/tools/readelf"
  export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
python3 "$CHECK" --audit "$ARCHIVE" | tee "$OUT/stage41-offline-audit.txt"
printf '\nThe optional next step ONLY reads existing sysfs status endpoints.\n'
printf 'It requires ADB and manual idle, P8, P7 playback.\n'
printf 'Press Enter to start read-only capture, or type N and press Enter to stop: '
read -r ANSWER
if [ -n "$ANSWER" ]; then
  echo "Offline audit complete: $OUT/stage41-offline-audit.txt"
  exit 0
fi
python3 "$CHECK" --capture --out "$OUT"
