#!/usr/bin/env bash
# Gazelle FEL Stage46: Kodi source-only pairing and capacity regression audit.
# No ADB, Kodi compilation/patch/install, native ABI calls or device access.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/audit-stage46-p7-input-guards.py"
EXPECTED_SHA="ba942beda9cad95e6f9da043705305bf1a8d4673b380339064fa163ab15cb931"
RESULTS="$HOME/Downloads/gazelle-fel-stage46-results"
mkdir -p "$RESULTS"
python3 - "$CHECK" "$EXPECTED_SHA" <<'PY'
import hashlib,pathlib,sys
actual=hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()
if actual!=sys.argv[2]:raise SystemExit('GAZELLE_FEL_STAGE46_SCRIPT_PIN_MISMATCH')
print('GAZELLE_FEL_STAGE46_BUNDLED_SOURCE_PIN_PASS')
PY
python3 "$CHECK" --selftest
if [ "$#" -gt 0 ]; then
  KODI="$1"
elif [ -f "$HOME/Downloads/gazelle-fel-stage45-results/DVDVideoCodecAndroidMediaCodec.cpp" ]; then
  KODI="$HOME/Downloads/gazelle-fel-stage45-results/DVDVideoCodecAndroidMediaCodec.cpp"
elif [ -f "$HOME/Downloads/DVDVideoCodecAndroidMediaCodec.cpp" ]; then
  KODI="$HOME/Downloads/DVDVideoCodecAndroidMediaCodec.cpp"
else
  KODI="$RESULTS/DVDVideoCodecAndroidMediaCodec.cpp"
  curl -fsSL --retry 3 \
    'https://raw.githubusercontent.com/angelcode1/xbmc/a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd/xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp' \
    -o "$KODI"
fi
python3 "$CHECK" --kodi "$KODI" \
  --json "$RESULTS/stage46-source-model-report.json" 2>&1 \
  | tee "$RESULTS/stage46-audit-results.txt"
echo "UPLOAD_FILE=$RESULTS/stage46-audit-results.txt"
echo 'No Cube access. Only the source-only research model and regression tests were executed.'
