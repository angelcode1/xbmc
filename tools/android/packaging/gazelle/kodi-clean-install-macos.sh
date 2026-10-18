#!/usr/bin/env bash
# macOS clean-install companion for the Gazelle Kodi CI APK (never runs in APK).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_HELPER="$SCRIPT_DIR/kodi-uid-provision.sh"
ADB="${ADB:-/Applications/adblink.app/Contents/MacOS/adb}"
if [[ ! -x "$ADB" ]]; then
  ADB="$(command -v adb || true)"
fi
if [[ -z "$ADB" || ! -x "$ADB" ]]; then
  echo "ERROR: adb not found. Set ADB=/path/to/adb" >&2
  exit 2
fi
[[ -f "$ROOT_HELPER" ]] || { echo "ERROR: UID helper not found beside this script" >&2; exit 2; }
REMOTE=/data/local/tmp/gazelle-kodi-uid-provision.sh

usage() {
  echo "Usage: $0 --preflight | --clean-install /path/to/kodi.apk" >&2
  echo "For clean install set GAZELLE_CONFIRM_KODI_DATA_LOSS=DELETE_KODI_DATA" >&2
  exit 2
}

[[ "$#" -ge 1 ]] || usage
MODE="$1"
[[ "$MODE" == --preflight || ( "$MODE" == --clean-install && "$#" == 2 ) ]] || usage
if [[ "$MODE" == --clean-install ]]; then
  APK="$2"
  [[ -f "$APK" ]] || { echo "ERROR: APK not found: $APK" >&2; exit 2; }
  [[ "${GAZELLE_CONFIRM_KODI_DATA_LOSS:-}" == DELETE_KODI_DATA ]] || {
    echo "REFUSE: this is a destructive CLEAN uninstall. Export" >&2
    echo "GAZELLE_CONFIRM_KODI_DATA_LOSS=DELETE_KODI_DATA after making backups." >&2
    exit 2
  }
fi

"$ADB" devices -l
"$ADB" push "$ROOT_HELPER" "$REMOTE" >/dev/null
"$ADB" shell -T su -c "sh $REMOTE --selftest"
# No automatic unmount/reboot or module manipulation, even during clean install.
"$ADB" shell -T su -c "sh $REMOTE --preflight"

if [[ "$MODE" == --preflight ]]; then
  echo "GAZELLE_PREFLIGHT_ONLY_PASS"
  exit 0
fi

BACKUP_DIR="$PWD/gazelle-kodi-before-clean-install-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
OLD_PATH=$("$ADB" shell pm path org.xbmc.kodi | tr -d '\r' | sed -n '1s/^package://p')
if [[ -n "$OLD_PATH" ]]; then
  "$ADB" pull "$OLD_PATH" "$BACKUP_DIR/kodi-installed-base.apk" >/dev/null
  "$ADB" shell pm path org.xbmc.kodi > "$BACKUP_DIR/package-path.txt"
  "$ADB" shell -T su -c "grep '^org.xbmc.kodi ' /data/system/packages.list" > "$BACKUP_DIR/old-package-uid.txt"
  echo "Backed up existing APK and package UID to $BACKUP_DIR"
  echo "WARNING: this does NOT back up Kodi application databases or private playback credentials."
  "$ADB" shell am force-stop org.xbmc.kodi
  "$ADB" uninstall org.xbmc.kodi
else
  echo "Kodi not installed; proceeding with a fresh installation."
fi

"$ADB" install "$APK"
# Verify Android allocated fresh UID and app data. Then repair *only* files dir.
"$ADB" shell -T su -c "sh $REMOTE --post-install"

echo "GAZELLE_CLEAN_INSTALL_UID_PASS"
echo "Kodi user data was deleted by uninstall; no UDF was mounted by this script."
echo "Do not attempt protected-disc playback until the MMBD addon/libraries and"
echo "root broker have been separately checked against the new UID."
