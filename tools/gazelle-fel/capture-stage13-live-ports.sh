#!/usr/bin/env bash
# Gazelle Stage 13: read-only active kernel port-type evidence.
# NO system-property/sysfs writes, injection, installs, service restarts or log clears.
set -euo pipefail
if [ "$#" -ne 1 ] || { [ "$1" != P7 ] && [ "$1" != P8 ]; }; then
  printf 'Usage: bash %s P7|P8\n' "$0" >&2
  exit 2
fi
LABEL="$1"
ADB="${ADB:-adb}"
if ! command -v "$ADB" >/dev/null 2>&1; then
  FALLBACK='/Applications/adblink.app/Contents/MacOS/adbfiles/adb'
  if [ -x "$FALLBACK" ]; then ADB="$FALLBACK"; else
    echo 'ERROR: adb not found; set ADB=/path/to/adb' >&2
    exit 2
  fi
fi
if [ "$("$ADB" get-state 2>/dev/null)" != device ]; then
  echo 'ERROR: adb device not connected' >&2; exit 2
fi
ROOT="${OUT_ROOT:-$HOME/Desktop/gazelle-fel-stage13}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DIR="$ROOT/$LABEL-$STAMP"
mkdir -p "$DIR"

snapshot() {
  phase="$1"
  printf 'Snapshot %s ...\n' "$phase"
  {
    printf 'HOST_TIME_UTC=%s\nLABEL=%s\nPHASE=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$LABEL" "$phase"
    printf 'READ_ONLY_SOURCE=/sys/class/amstream/ports\n'
  } > "$DIR/$phase-info.txt"
  "$ADB" shell 'su -c "cat /sys/class/amstream/ports"' \
    > "$DIR/$phase-amstream-ports.txt" 2> "$DIR/$phase-ports-errors.txt" || true
  if [ ! -s "$DIR/$phase-amstream-ports.txt" ]; then
    echo "WARN: no amstream ports output for $phase; inspect $DIR/$phase-ports-errors.txt" >&2
  fi
  "$ADB" shell 'su -c "cat /sys/class/vfm/map"' \
    > "$DIR/$phase-vfm-map.txt" 2>&1 || true
  "$ADB" shell 'su -c "cat /sys/class/vdec/vdec_status"' \
    > "$DIR/$phase-vdec-status.txt" 2>&1 || true
  pid="$("$ADB" shell pidof media.codec 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  if [ -n "$pid" ] && printf '%s' "$pid" | grep -Eq '^[0-9]+$'; then
    "$ADB" shell "su -c 'ls -l /proc/$pid/fd'" 2>/dev/null \
      | grep -Ei '/dev/(amstream|vdec|amvideo)' \
      > "$DIR/$phase-decoder-fds.txt" || true
  else
    echo 'media.codec PID unavailable' > "$DIR/$phase-decoder-fds.txt"
  fi
}

echo "Output: $DIR"
echo 'Stop playback in Kodi, then press Enter to capture a baseline.'
IFS= read -r _
snapshot before
echo "Start $LABEL playback in Kodi. Leave video visibly moving, then press Enter."
IFS= read -r _
snapshot active-1
sleep 3
snapshot active-2
printf 'CAPTURE_SAFETY=READ_ONLY\nNO_SYSTEM_CHANGES=true\nNOT_A_FEL_PIXEL_PROOF=true\n' > "$DIR/README.txt"
(
  cd "$ROOT" || exit 1
  zip -qr "$LABEL-$STAMP.zip" "$LABEL-$STAMP"
)
echo "UPLOAD: $ROOT/$LABEL-$STAMP.zip"
echo 'NOTE: Both P7 and P8 snapshots help compare changing live port flags.'
