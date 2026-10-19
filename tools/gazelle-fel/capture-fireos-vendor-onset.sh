#!/usr/bin/env bash
# Fire TV Cube 3 P7/P8 vendor-onset capture. Device access is read-only.
# Starts Android logcat BEFORE playback; leaves log buffers and sysfs unchanged.
set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: bash $0 P7|P8 [host-output-dir]" >&2
  exit 2
fi
case "$1" in P7|P8) label="$1";; *) echo 'Expected P7 or P8' >&2; exit 2;; esac
ADB="${ADB:-adb}"
root="${2:-$HOME/Desktop/gazelle-fel-onset}"
command -v "$ADB" >/dev/null 2>&1 || { echo 'adb not found' >&2; exit 1; }
[ "$("$ADB" get-state 2>/dev/null)" = device ] || { echo 'No connected ADB device' >&2; exit 1; }
stamp="$(date +%Y%m%d-%H%M%S)"
out="$root/$label-$stamp"
mkdir -p "$out"
log_pid=''

stop_logcat() {
  if [ -n "$log_pid" ]; then
    kill "$log_pid" 2>/dev/null || true
    wait "$log_pid" 2>/dev/null || true
    log_pid=''
  fi
}
trap stop_logcat EXIT
trap 'stop_logcat; exit 130' INT
trap 'stop_logcat; exit 143' TERM

snapshot() {
  phase="$1"
  {
    printf 'PHASE=%s HOST_UTC=%s\n' "$phase" "$(date -u +%FT%TZ)"
    "$ADB" shell 'uname -r'
    "$ADB" shell 'getprop ro.build.fingerprint'
    for node in \
      /sys/class/amdolby_vision/src_format \
      /sys/class/amdolby_vision/dv_inst_status \
      /sys/class/amdolby_vision/dv_provider \
      /sys/class/amdolby_vision/dv_mode \
      /sys/class/vfm/map \
      /sys/class/vdec/vdec_status \
      /sys/module/amvdec_h265/parameters/parser_dolby_vision_enable \
      /sys/module/amvdec_h265/parameters/dolby_meta_with_el \
      /sys/module/amvdec_h265/parameters/force_bypass_dvenl
    do
      printf '\n--- %s ---\n' "$node"
      "$ADB" shell "su -c 'cat $node'" 2>&1 || true
    done
  } > "$out/$phase-decoder.txt"
}

echo 'STOP Kodi playback, then press Enter to begin logging BEFORE starting video.'
read -r _
snapshot before
"$ADB" shell 'su -c "dmesg"' > "$out/before-kernel.log" 2>&1 || true
# Tail one old entry, then capture new events. No logcat -c and no crash-buffer access.
"$ADB" logcat -b main -b system -T 1 -v threadtime > "$out/onset-logcat.txt" 2> "$out/logcat-errors.txt" &
log_pid="$!"
sleep 1
kill -0 "$log_pid" 2>/dev/null || echo 'WARN: logcat exited; inspect errors' >&2
echo "Start $label now in Kodi; leave it playing for about 20 seconds."
echo 'Press Enter WHILE the video is still playing.'
read -r _
snapshot active
"$ADB" shell 'su -c "dmesg"' > "$out/active-kernel.log" 2>&1 || true
"$ADB" shell 'su -c "cat /sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp/kodi.log"' > "$out/kodi.log" 2> "$out/kodi-errors.txt" || true
if [ ! -s "$out/kodi.log" ]; then
  "$ADB" shell 'su -c "cat /data/user/0/org.xbmc.kodi/files/.kodi/temp/kodi.log"' > "$out/kodi.log" 2>> "$out/kodi-errors.txt" || true
fi
stop_logcat
grep -Ei 'GAZELLE_|OMX|ACodec|MediaCodec|amstream|dv_duallayer|dvel|dolby|vdec|parse_metadata|setParameter|codec_set_dv' "$out/onset-logcat.txt" > "$out/onset-filtered.txt" || true
grep -Ei 'GAZELLE_|FELPAIR|ConvertFEL|AddData.*error' "$out/kodi.log" > "$out/kodi-filtered.txt" || true
printf 'LABEL=%s\nUTC=%s\nDEVICE_WRITES=NONE\nKodi log may include earlier sessions; use timestamps.\n' "$label" "$(date -u +%FT%TZ)" > "$out/README.txt"
echo "CAPTURE_COMPLETE=$out"
echo "Create ZIP: cd \"$root\" && zip -qr \"$label-$stamp.zip\" \"$label-$stamp\""
