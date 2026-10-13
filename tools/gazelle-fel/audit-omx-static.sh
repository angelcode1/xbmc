#!/usr/bin/env bash
# Offline only. Read a local copy of Amazon's libOmxVideo.so; NEVER patch or deploy it.
set -euo pipefail
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "usage: $0 /path/to/libOmxVideo.so" >&2; exit 2
fi
F="$1"
OUT="${OUT:-$(pwd)/gazelle-omx-static-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
echo "SHA256: $(shasum -a 256 "$F")" | tee "$OUT/identity.txt"
file "$F" | tee -a "$OUT/identity.txt"
readelf -hW "$F" > "$OUT/elf-header.txt"
readelf -SW "$F" > "$OUT/elf-sections.txt"
readelf -Ws "$F" > "$OUT/elf-symbols.txt"
readelf -rW "$F" > "$OUT/elf-relocations.txt"
strings -a -t x "$F" > "$OUT/strings-with-offsets.txt"
grep -iE 'codec_set_dvmetawithel|AmlogicVideoDecoder(2)?DolbyVision|codec_init' "$OUT/elf-symbols.txt" > "$OUT/relevant-symbols.txt" || true
grep -iE 'dv_duallayer|dolby.vision|amstream|stream.mode|dv.frame|codec_init' "$OUT/strings-with-offsets.txt" > "$OUT/relevant-strings.txt" || true
grep -iE 'codec_set_dvmetawithel|ioctl' "$OUT/elf-relocations.txt" > "$OUT/relevant-relocations.txt" || true
if command -v llvm-objdump >/dev/null 2>&1; then
  llvm-objdump -d --triple=thumbv7a-linux-android "$F" > "$OUT/disassembly.txt"
  # Address below is valid ONLY for SHA256 eb79f44c..., not arbitrary vendor versions.
  if shasum -a 256 "$F" | grep -q '^eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77 '; then
    llvm-objdump -d --triple=thumbv7a-linux-android --start-address=0x5a1a0 --stop-address=0x5a1ba "$F" > "$OUT/dvmeta-wrapper.txt"
  fi
else
  echo 'llvm-objdump missing: disassembly not produced' >&2
fi
echo "Wrote read-only static report to: $OUT"
echo 'WARNING: a symbol/constant/relocation scan cannot prove that a runtime ioctl is absent.'
