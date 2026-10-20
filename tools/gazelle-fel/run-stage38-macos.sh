#!/usr/bin/env bash
# Stage38: pinned Mac-only, read-only live sysfs provider graph capture.
set -euo pipefail
COMMIT=6846ec5b3bffabc4dc7a72d40dc7c9d82a6f680a
BLOB=db018c08a019796aca618b9085f0f27110ef6ef4
DIR="$HOME/Downloads/gazelle-fel-stage38-results"
mkdir -p "$DIR"
SCRIPT="$DIR/capture-stage38-provider-graph.py"
URL="https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/tools/gazelle-fel/capture-stage38-provider-graph.py"
echo 'Downloading SHA-pinned Stage38 source.'
curl -fsSL --retry 3 "$URL" -o "$SCRIPT"
python3 - "$SCRIPT" "$BLOB" <<'PY'
import hashlib,pathlib,sys
src=pathlib.Path(sys.argv[1]).read_bytes()
sha=hashlib.sha1(b'blob '+str(len(src)).encode()+b'\0'+src).hexdigest()
if sha!=sys.argv[2]:raise SystemExit('GAZELLE_FEL_STAGE38_SCRIPT_PIN_MISMATCH')
print('GAZELLE_FEL_STAGE38_SOURCE_PIN_PASS')
PY
python3 "$SCRIPT" --selftest
printf '\nStage38: this does not change the Cube or playback.\n'
printf 'Only known provider/route names and status codes will be retained.\n'
printf 'You will manually select idle, P8, then P7 playback.\n\n'
python3 "$SCRIPT" --capture --out "$DIR"
