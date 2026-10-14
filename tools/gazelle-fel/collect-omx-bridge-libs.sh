#!/usr/bin/env bash
# Local, read-only collection. Does not alter the Cube, Android services, or Kodi.
set -euo pipefail
ADB="${ADB:-/Applications/adblink.app/Contents/MacOS/adbfiles/adb}"
OUT_ROOT="${OUT_ROOT:-$HOME/Downloads}"
OUT="$OUT_ROOT/gazelle-omx-bridge-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
PID=$("$ADB" shell pidof media.codec | tr -d '\r' | awk '{print $1}')
if [ -z "$PID" ]; then echo 'ERROR: media.codec not running' >&2; exit 1; fi
"$ADB" shell "su -c 'cat /proc/$PID/maps'" > "$OUT/media-codec-maps.txt"
"$ADB" shell getprop ro.build.fingerprint | tr -d '\r' > "$OUT/build-fingerprint.txt"
"$ADB" shell getprop vendor.media.omx.use_dv_frame | tr -d '\r' > "$OUT/omx-use-dv-frame.txt"
count=0
while IFS= read -r path; do
  case "$path" in
    */libOmxVideo.so|*/libOmxCore.so|*/libamavutils.so|*/libmediahal_resman.so|*/libstagefrighthw.so|*/libomx_framework_alt.so|*/libOmxBase.so) ;;
    *) continue ;;
  esac
  dest="$OUT/rootfs$path"
  mkdir -p "$(dirname "$dest")"
  if "$ADB" pull "$path" "$dest" >> "$OUT/adb-pull.txt" 2>&1; then
    echo "PULLED $path"; count=$((count + 1))
  else
    echo "UNREADABLE $path"; rm -f "$dest"
  fi
done < <(awk '$NF ~ /^\/(vendor|system)\/lib\/.*\.so$/ {print $NF}' "$OUT/media-codec-maps.txt" | sort -u)
if [ "$count" -eq 0 ]; then echo "No allowed libs: $OUT" >&2; exit 1; fi
find "$OUT/rootfs" -type f -name '*.so' -exec shasum -a 256 {} \; > "$OUT/sha256.txt"
(cd "$OUT_ROOT" && zip -qr "$(basename "$OUT").zip" "$(basename "$OUT")")
echo "READ_ONLY_PASS files=$count archive=$OUT.zip"
echo 'Proprietary binaries: store privately, never commit to Git.'
