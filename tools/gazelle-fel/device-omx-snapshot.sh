#!/system/bin/sh
# Gazelle non-mutating playback snapshot: no sysfs writes, ioctls, ptrace or restarts.
echo '=== time ==='
date
echo '=== firmware and OMX properties ==='
for name in vendor.media.omx.stream_mode vendor.media.omx.use_dv_frame media.omx.stream_mode; do
  value=$(getprop "$name")
  if [ -z "$value" ]; then value='<unset-or-empty>'; fi
  echo "$name=$value"
done
echo '=== HEVC kernel baseline ==='
for name in nal_skip_policy dolby_meta_with_el force_bypass_dvenl parser_dolby_vision_enable; do
  path="/sys/module/amvdec_h265/parameters/$name"
  if [ -r "$path" ]; then
    printf '%s=' "$name"; cat "$path"
  else
    echo "$name=<not-readable>"
  fi
done
echo '=== DV source and instance ==='
cat /sys/class/amdolby_vision/src_format 2>&1
cat /sys/class/amdolby_vision/dv_inst_status 2>&1
echo '=== media codec ==='
PID=$(pidof media.codec)
echo "media.codec PID=$PID"
if [ -n "$PID" ]; then
  for fd in /proc/"$PID"/fd/*; do
    dest=$(readlink "$fd" 2>/dev/null)
    case "$dest" in /dev/amstream*|/dev/amvideo|/dev/video*|/dev/v4lvideo*) echo "$fd -> $dest";; esac
  done
fi
echo '=== VFM map ==='
cat /sys/class/vfm/map 2>&1
echo '=== composer counters ==='
for name in total_get_count total_put_count; do
  p="/sys/class/video_composer/$name"
  if [ -r "$p" ]; then printf '%s=' "$name"; cat "$p"; fi
done
