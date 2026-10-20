#!/usr/bin/env bash
# Offline only. SHA-pin bundled Python source + immutable Kodi sources.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT="$HERE/stage48-pairing-contract.py"
AUDIT_SHA='2a65f1e0e60b3dcb7086b2bb58ae3ca01235ff569361d025122f1b764cd9d583'
OUT="$HOME/Downloads/gazelle-fel-stage48-results"
SRC="$OUT/pinned-kodi"
mkdir -p "$OUT" "$SRC"
python3 - "$AUDIT" "$AUDIT_SHA" <<'PY'
from pathlib import Path
import hashlib,sys
if hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()!=sys.argv[2]:
    raise SystemExit('GAZELLE_FEL_STAGE48_BUNDLED_SOURCE_SHA_MISMATCH')
print('GAZELLE_FEL_STAGE48_BUNDLED_SOURCE_PIN_PASS')
PY
python3 "$AUDIT" --selftest
if [ "$#" -ge 1 ]; then
  SOURCE_DIR="$1"
elif [ -f "$HOME/Downloads/gazelle-fel-stage47-results/pinned-kodi/DVDDemuxFFmpeg.cpp" ] && \
     [ -f "$HOME/Downloads/gazelle-fel-stage47-results/pinned-kodi/VideoPlayer.cpp" ] && \
     [ -f "$HOME/Downloads/gazelle-fel-stage47-results/pinned-kodi/DVDVideoCodecAndroidMediaCodec.cpp" ]; then
  SOURCE_DIR="$HOME/Downloads/gazelle-fel-stage47-results/pinned-kodi"
else
  SOURCE_DIR="$SRC"
  PIN='a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd'
  ROOT="https://raw.githubusercontent.com/angelcode1/xbmc/$PIN/xbmc/cores/VideoPlayer"
  curl -fsSL --retry 3 "$ROOT/DVDDemuxers/DVDDemuxFFmpeg.cpp" -o "$SRC/DVDDemuxFFmpeg.cpp"
  curl -fsSL --retry 3 "$ROOT/VideoPlayer.cpp" -o "$SRC/VideoPlayer.cpp"
  curl -fsSL --retry 3 "$ROOT/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp" -o "$SRC/DVDVideoCodecAndroidMediaCodec.cpp"
fi
python3 "$AUDIT" --source-dir "$SOURCE_DIR" 2>&1 | tee "$OUT/stage48-audit-results.txt"
printf 'UPLOAD_FILE=%s\n' "$OUT/stage48-audit-results.txt"
echo 'OFFLINE_ONLY=YES; Kodi, Cube, modules and settings unchanged'
