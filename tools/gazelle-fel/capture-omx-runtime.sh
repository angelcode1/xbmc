#!/usr/bin/env bash
# Collect while ONE playing video is visibly moving; restart Kodi between P8 and P7 tests.
# Only adb push of this read-only script; no sysfs writes, log clearing or ioctl injection.
set -euo pipefail
ADB="${ADB:-/Applications/adblink.app/Contents/MacOS/adbfiles/adb}"
LABEL="${1:-P7_FEL}"
LABEL="${LABEL//[^A-Za-z0-9_-]/_}"
THIS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT_ROOT:-$HOME/Downloads}/gazelle-omx-runtime-${LABEL}-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
echo "Collecting $LABEL to $OUT"
"$ADB" push "$THIS/device-omx-snapshot.sh" /data/local/tmp/gazelle-omx-snapshot.sh >/dev/null
for i in 1 2 3 4 5 6; do
  echo "===== CAPTURE $i/6 ====="
  "$ADB" shell 'su -c "sh /data/local/tmp/gazelle-omx-snapshot.sh"' > "$OUT/snapshot-$(printf %02d "$i").txt" 2>&1 || true
  if [ "$i" -lt 6 ]; then sleep 5; fi
done
"$ADB" logcat -d -b all -v threadtime > "$OUT/logcat-full.txt" 2>&1 || true
grep -Ei 'GAZELLE_DOVI_RPU|GAZELLE_P7_NALS|AMDV:|OMX|amstream|dv_duallayer|dolby|vdec' "$OUT/logcat-full.txt" > "$OUT/logcat-filtered.txt" || true
"$ADB" shell 'su -c "cat /sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp/kodi.log"' > "$OUT/kodi.log" 2>&1 || true
(cd "$(dirname "$OUT")" && zip -qr "$(basename "$OUT").zip" "$(basename "$OUT")")
echo "UPLOAD: $OUT.zip"
