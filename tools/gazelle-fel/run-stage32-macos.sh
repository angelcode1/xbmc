#!/usr/bin/env bash
# P8/P7 passive log collector. No device configuration changes.
set -euo pipefail
COMMIT=833ed7e33beadbe1dd46f78d09450cd5812a7011
GIT_BLOB=72f61d2258ee4bc94159e78236fe9059ded61548
SCRIPT=tools/gazelle-fel/capture-stage32-log-gates.py
OUT="$HOME/Downloads/gazelle-fel-stage32"
mkdir -p "$OUT"
FILE="$OUT/capture-stage32-log-gates.py"
curl -fsSL --retry 3 "https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/$SCRIPT" -o "$FILE"
python3 - "$FILE" "$GIT_BLOB" <<'PY'
import hashlib,pathlib,sys
b=pathlib.Path(sys.argv[1]).read_bytes()
actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
if actual != sys.argv[2]:
    raise SystemExit('GAZELLE_FEL_STAGE32_SCRIPT_BLOB_MISMATCH')
print('GAZELLE_FEL_STAGE32_SCRIPT_PIN_PASS')
PY
python3 "$FILE" --selftest
printf '\nRead-only capture. Start playback ONLY when prompted.\n'
python3 "$FILE" --capture
