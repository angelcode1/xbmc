#!/usr/bin/env bash
# Gazelle FEL Stage47: source-only demux/VideoPlayer/MediaCodec contract audit.
# Downloads immutable source text, never accesses Cube or modifies Kodi.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HOME/Downloads/gazelle-fel-stage47-results"
SRC="$OUT/pinned-kodi"
CHECK="$OUT/audit-stage47-demux-contract.py"
VERIFIER_COMMIT="00715ebdab98f3aa1605884d5eaa178d97b8dd46"
VERIFIER_BLOB="97a50d0cf4145fd57a035a578687f182f5fcfd3c"
KODI_COMMIT="a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd"
mkdir -p "$SRC"
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$VERIFIER_COMMIT/tools/gazelle-fel/audit-stage47-demux-contract.py" -o "$CHECK"
python3 - "$CHECK" "$VERIFIER_BLOB" <<'PY'
import hashlib,sys
from pathlib import Path
data=Path(sys.argv[1]).read_bytes()
digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
if digest!=sys.argv[2]:raise SystemExit("STAGE47_VERIFIER_GIT_BLOB_MISMATCH")
print("GAZELLE_FEL_STAGE47_VERIFIER_SOURCE_PIN_PASS")
PY
python3 "$CHECK" --selftest
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$KODI_COMMIT/xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp" -o "$SRC/DVDDemuxFFmpeg.cpp"
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$KODI_COMMIT/xbmc/cores/VideoPlayer/VideoPlayer.cpp" -o "$SRC/VideoPlayer.cpp"
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/angelcode1/xbmc/$KODI_COMMIT/xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp" -o "$SRC/DVDVideoCodecAndroidMediaCodec.cpp"
python3 "$CHECK" --source-dir "$SRC" 2>&1 | tee "$OUT/stage47-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage47-audit-results.txt"
echo "Host-only pinned Kodi source audit; no Cube access or Kodi patch."
