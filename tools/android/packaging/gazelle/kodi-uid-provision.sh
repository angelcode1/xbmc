#!/system/bin/sh
# Gazelle / Kodi *clean-install* UID provisioning. Root-only; no device mounts.
# Intentionally refuses an existing UDF/bind mount beneath Kodi app data.
set -eu

PACKAGE=org.xbmc.kodi
APP=/data/user/0/org.xbmc.kodi
ALIAS=/data/data/org.xbmc.kodi
FILES="$APP/files"

expected_label_from_uid() {
  app_uid="$1"
  user_id=$((app_uid / 100000))
  app_id=$((app_uid % 100000 - 10000))
  if [ "$app_id" -lt 0 ] || [ "$app_id" -ge 10000 ]; then
    echo "REFUSE: not an Android app UID" >&2
    return 1
  fi
  c1=$((app_id % 256))
  c2=$((256 + (app_id / 256)))
  c3=$((512 + (user_id % 256)))
  c4=$((768 + (user_id / 256)))
  printf 'u:object_r:app_data_file:s0:c%s,c%s,c%s,c%s\n' "$c1" "$c2" "$c3" "$c4"
}

no_app_mounts() {
  # Field 5 of mountinfo is the mountpoint. Avoid grep-based substring matches.
  while IFS= read -r entry; do
    set -- $entry
    case "${5:-}" in
      "$APP"|"$APP"/*|"$ALIAS"|"$ALIAS"/*)
        echo "REFUSE: active mount in Kodi app tree: ${5}" >&2
        echo "Do not uninstall, remount, or alter this mount automatically." >&2
        return 1
        ;;
    esac
  done < /proc/self/mountinfo
}

kodi_installed_uid() {
  [ -r /data/system/packages.list ] || {
    echo "REFUSE: cannot read trusted Android package registry" >&2; return 1;
  }
  line=$(grep "^$PACKAGE " /data/system/packages.list || true)
  [ -n "$line" ] || { echo "REFUSE: Kodi not registered" >&2; return 1; }
  set -- $line
  case "${2:-}" in
    ""|*[!0-9]*) echo "REFUSE: invalid package UID" >&2; return 1 ;;
  esac
  printf '%s\n' "$2"
}

inspect() {
  no_app_mounts || return 1
  if [ -d "$APP" ]; then
    echo "APP_UID_ON_DISK=$(stat -c %u "$APP")"
    echo "APP_SELINUX_ON_DISK=$(ls -Zd "$APP")"
  fi
  if [ -d "$FILES" ]; then
    echo "FILES_UID_ON_DISK=$(stat -c %u "$FILES")"
    echo "FILES_SELINUX_ON_DISK=$(ls -Zd "$FILES")"
  fi
  echo "INSTALLED_PACKAGE_UID=$(kodi_installed_uid)"
  echo "GAZELLE_CLEAN_INSTALL_PREFLIGHT_PASS no_app_mounts=1"
}

provision() {
  no_app_mounts || return 1
  [ -d "$APP" ] && [ ! -L "$APP" ] || {
    echo "REFUSE: Android did not create a regular Kodi app directory" >&2; return 1;
  }
  APP_UID=$(kodi_installed_uid)
  ROOT_UID=$(stat -c %u "$APP")
  ROOT_GID=$(stat -c %g "$APP")
  if [ "$ROOT_UID" != "$APP_UID" ] || [ "$ROOT_GID" != "$APP_UID" ]; then
    echo "REFUSE: app root owned by $ROOT_UID:$ROOT_GID, package UID $APP_UID" >&2
    echo "Android must create the new app root; do not recursively chown it." >&2
    return 1
  fi

  actual_label=$(ls -Zd "$APP")
  set -- $actual_label
  actual_label="$1"
  correct_label=$(expected_label_from_uid "$APP_UID") || return 1
  if [ "$actual_label" != "$correct_label" ]; then
    echo "REFUSE: Android app-root SELinux category mismatch" >&2
    echo "ACTUAL=$actual_label EXPECTED=$correct_label" >&2
    return 1
  fi

  [ ! -L "$FILES" ] || { echo "REFUSE: symlinked files directory" >&2; return 1; }
  if [ -e "$FILES" ]; then
    [ -d "$FILES" ] || { echo "REFUSE: files is not a directory" >&2; return 1; }
  else
    mkdir "$FILES"
  fi
  # Do not silently rewrite a data tree carried across an uninstall.
  for child in "$FILES"/.kodi "$FILES"/gazelle-kernel-udf; do
    if [ -e "$child" ]; then
      child_uid=$(stat -c %u "$child")
      [ "$child_uid" = "$APP_UID" ] || {
        echo "REFUSE: leftover child with mismatched UID: $child" >&2
        return 1
      }
    fi
  done

  # Only modify the single parent directory; NEVER traverse mounted media.
  chown "$APP_UID:$ROOT_GID" "$FILES"
  chmod 700 "$FILES"
  chcon "$correct_label" "$FILES"
  [ "$(stat -c %u "$FILES")" = "$APP_UID" ] || {
    echo "REFUSE: post-install UID verification failed" >&2; return 1;
  }
  files_label=$(ls -Zd "$FILES")
  set -- $files_label
  [ "$1" = "$correct_label" ] || {
    echo "REFUSE: post-install SELinux verification failed" >&2; return 1;
  }
  echo "GAZELLE_CLEAN_KODI_DIR_PASS current_uid=$APP_UID"
  echo "MMBD broker, if running, may still trust the old UID; validate separately."
}

case "${1:-}" in
  --selftest)
    a=$(expected_label_from_uid 10250)
    b=$(expected_label_from_uid 10252)
    [ "$a" = "u:object_r:app_data_file:s0:c250,c256,c512,c768" ] || exit 5
    [ "$b" = "u:object_r:app_data_file:s0:c252,c256,c512,c768" ] || exit 6
    echo "GAZELLE_UID_MCS_SELFTEST_PASS"
    ;;
  --preflight)
    [ "$(id -u)" = 0 ] || { echo "REFUSE: root required" >&2; exit 2; }
    inspect
    ;;
  --post-install)
    [ "$(id -u)" = 0 ] || { echo "REFUSE: root required" >&2; exit 2; }
    provision
    ;;
  *)
    echo "Usage: sh kodi-uid-provision.sh --selftest|--preflight|--post-install" >&2
    exit 2
    ;;
esac
