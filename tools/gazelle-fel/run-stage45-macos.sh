#!/usr/bin/env bash
# Stage45: host-only. Pinned original vendor ABI + immutable Kodi input source.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/audit-stage45-input-contract.py"
CHECK_SHA="6b650fcd057109b03e30864118a25544605ba7085da50658373e30b7909ea10d"
KODI_REF="a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd"
KODI_BLOB="1a313fdc297db69607b2a3f0e82069def4b198f3"
OUT="$HOME/Downloads/gazelle-fel-stage45-results"
VENDOR="$HOME/Downloads/gazelle-fel-recovered-private/libOmxVideo.so"
if [ "$#" -ge 1 ]; then VENDOR="$1"; fi
KODI="$OUT/DVDVideoCodecAndroidMediaCodec.cpp"
if [ "$#" -ge 2 ]; then KODI="$2"; fi
mkdir -p "$OUT/tools"
python3 - "$CHECK" "$CHECK_SHA" <<'PY'
import hashlib,pathlib,sys
actual=hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()
if actual!=sys.argv[2]:raise SystemExit('STAGE45_BUNDLED_VERIFIER_HASH_MISMATCH')
print('GAZELLE_FEL_STAGE45_BUNDLE_SHA_PASS')
PY
if ! command -v llvm-objdump >/dev/null 2>&1; then
 LLVM_BIN="$(brew --prefix llvm 2>/dev/null)/bin" || true
 if [ ! -x "$LLVM_BIN/llvm-objdump" ]; then echo 'Install LLVM: brew install llvm' >&2;exit 2;fi
 export PATH="$LLVM_BIN:$PATH"
fi
if ! command -v readelf >/dev/null 2>&1; then
 BINUTILS_BIN="$(brew --prefix binutils 2>/dev/null)/bin" || true
 E=''
 for a in "$BINUTILS_BIN/greadelf" "$BINUTILS_BIN/readelf";do
   if [ -x "$a" ]; then E="$a";break;fi
 done
 if [ -z "$E" ]; then echo 'Install GNU readelf: brew install binutils' >&2;exit 2;fi
 ln -sf "$E" "$OUT/tools/readelf"
 export PATH="$OUT/tools:$PATH"
fi
python3 "$CHECK" --selftest
if [ ! -f "$VENDOR" ]; then
 echo "Original libOmxVideo.so not found at: $VENDOR" >&2
 echo 'Pass exact existing original library path as the first argument.' >&2
 exit 2
fi
# If the user provides an existing Kodi file, verify the exact source. Otherwise
# fetch the immutable commit once. No Kodi binaries or private ELFs are fetched.
if [ "$#" -lt 2 ]; then
 curl -fsSL --retry 3 \
 "https://raw.githubusercontent.com/angelcode1/xbmc/$KODI_REF/xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp" -o "$KODI"
fi
python3 - "$KODI" "$KODI_BLOB" <<'PY'
import pathlib,hashlib,sys
b=pathlib.Path(sys.argv[1]).read_bytes()
s=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
if s!=sys.argv[2]:raise SystemExit('STAGE45_KODI_PIN_MISMATCH')
print('GAZELLE_FEL_STAGE45_PINNED_KODI_SOURCE_PASS')
PY
python3 "$CHECK" --original "$VENDOR" --kodi "$KODI" 2>&1 | tee "$OUT/stage45-audit-results.txt"
echo "UPLOAD_FILE=$OUT/stage45-audit-results.txt"
echo 'No ADB, device changes, native code execution or Kodi build performed.'
