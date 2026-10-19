#!/usr/bin/env bash
# Gazelle Stage 28: host-only verified download, selftest and opt-in ADB reads.
set -euo pipefail
COMMIT=667dc10c13a1c6e493bd2591d70c4b56aef82836
BLOB=85fc0fd09af7416e1181365edab6b333c674327e
REL=tools/gazelle-fel/capture-stage28-active-comparison.py
ROOT="$HOME/Downloads/gazelle-fel-stage28"
mkdir -p "$ROOT"
DEST="$ROOT/capture-stage28-active-comparison.py"
URL="https://raw.githubusercontent.com/angelcode1/xbmc/$COMMIT/$REL"
echo "Fetching pinned Stage 28 code from $COMMIT"
curl -fsSL --retry 3 "$URL" -o "$DEST"
python3 - "$DEST" "$BLOB" <<'PY'
import hashlib
import pathlib
import sys
data=pathlib.Path(sys.argv[1]).read_bytes()
actual=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
if actual!=sys.argv[2]:
    raise SystemExit("STAGE28_SCRIPT_HASH_MISMATCH expected=%s got=%s"%(sys.argv[2],actual))
print("GAZELLE_FEL_STAGE28_SCRIPT_PIN_PASS")
PY
python3 "$DEST" --selftest
echo
echo "Stage 28 reads only existing sysfs decoder status nodes via ADB."
echo "Kodi playback is controlled manually by you."
echo "No settings, logs, services, module state or firmware will be modified."
echo
python3 "$DEST" --capture
