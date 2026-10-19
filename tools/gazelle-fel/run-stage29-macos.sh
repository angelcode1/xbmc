#!/usr/bin/env bash
# Stage 29: host-only ZIP analysis; never connects to Cube or runs ADB.
set -euo pipefail
RESEARCH_COMMIT=2a898e402a69e221ba1a8968412bd95ad13b9980
SOURCE_BLOB=636c4a0069b332e49aee11ad8775148046d386d8
SCRIPT=tools/gazelle-fel/audit-stage29-live-gates.py
DIR="$HOME/Downloads/gazelle-fel-stage29"
INPUT="$HOME/Downloads/stage28-active-comparison-20261019-134212.zip"
if [ "$#" -gt 0 ]; then INPUT="$1"; fi
mkdir -p "$DIR"
DEST="$DIR/audit-stage29-live-gates.py"
OUTPUT="$DIR/stage29-audit-results.txt"
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$RESEARCH_COMMIT/$SCRIPT" \
  -o "$DEST"
python3 - "$DEST" "$SOURCE_BLOB" <<'PY'
import hashlib,pathlib,sys
raw=pathlib.Path(sys.argv[1]).read_bytes()
sha=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
if sha!=sys.argv[2]:
    raise SystemExit("STAGE29_SOURCE_HASH_MISMATCH")
print("GAZELLE_FEL_STAGE29_SCRIPT_PIN_PASS")
PY
python3 "$DEST" --selftest
test -f "$INPUT" || { echo "ERROR: original Stage28 ZIP not found: $INPUT" >&2; exit 2; }
python3 "$DEST" "$INPUT" --output "$OUTPUT"
echo "UPLOAD_FILE=$OUTPUT"
