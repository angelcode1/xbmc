# -*- coding: utf-8 -*-
"""Android Kodi MMBD provider startup glue, based on the LG C5 service pattern.

Does not claim the E1F 15-second test broker is production-capable.
Does not start any root broker, touch optical devices, or read disc sectors.
"""
from __future__ import print_function
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import traceback

import xbmc
import xbmcvfs

TAG = 'GAZELLE_MMBD_STARTUP_V2'
LIB = 'libmmbd.so'
HELPER = 'libgazelle_mmbd_v2.so'
LIB_SHA = '826b5e6dfebfd628c1a6f851a22cb583fa831978600f4ddc2663af46794a8d0b'
HELPER_SHA = 'c8005d1b168f42024f72de78ae64dcf66f4b142583d3afc92fd97ac72ce9172c'
KEYS = ('LIBAACS_PATH', 'LIBBDPLUS_PATH', 'MAKEMKVCON')

def log(message, level=None):
    xbmc.log(TAG + ' ' + str(message), xbmc.LOGINFO if level is None else level)

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            block = stream.read(65536)
            if not block:
                return h.hexdigest()
            h.update(block)

def mapped_library():
    with open('/proc/self/maps', 'r') as maps:
        for line in maps:
            fields = line.strip().split(None, 5)
            if len(fields) != 6:
                continue
            path = fields[5].removesuffix(' (deleted)')
            # Fire OS may use both /data/app/org.xbmc.kodi-* and
            # /data/app/~~token/org.xbmc.kodi-* layouts after reinstall.
            if (path.startswith('/data/app/') and
                    '/org.xbmc.kodi-' in path and
                    '/lib/arm/' in path and path.endswith('/' + LIB)):
                return path
    raise RuntimeError('Kodi MMBD mapped ELF not found (not searching unreadable /data/app)')

def state_file():
    # Kodi maintains addon_data under the user's profile, not /data/adb.
    profile = Path(xbmcvfs.translatePath('special://profile/addon_data/service.gazelle.mmbd'))
    profile.mkdir(parents=True, exist_ok=True)
    return profile / 'startup.json'

def record(stage, **values):
    target = state_file()
    obj = {'schema': 1, 'timestamp_unix': int(time.time()),
           'kodi_pid': os.getpid(), 'stage': stage,
           'broker_started': False, 'ipc_tested': False,
           'disc_tested': False, 'playback_tested': False}
    obj.update(values)
    temp = target.with_name('startup.json.tmp')
    with open(temp, 'w') as handle:
        json.dump(obj, handle, indent=2, sort_keys=True)
        handle.write('\n')
    os.chmod(str(temp), 0o600)
    os.replace(str(temp), str(target))

def validate_android_native_install(lib_stat, helper_stat):
    """Reject mutable/untrusted helpers without requiring root-only APK ownership.

    Android PackageManager may extract both native libraries under UID 1000
    (system), not only UID 0. Accept only immutable regular root/system-owned
    files with matching owners, from the same mapped package native directory.
    Do not trust an app-UID-owned helper: its owner could chmod and replace it.
    """
    if not stat.S_ISREG(lib_stat.st_mode) or not stat.S_ISREG(helper_stat.st_mode):
        raise RuntimeError('v2 native payload is not a regular file (symlink rejected)')
    if lib_stat.st_uid not in (0, 1000) or helper_stat.st_uid != lib_stat.st_uid:
        raise RuntimeError(
            'v2 native ownership rejected: library_uid={} helper_uid={} '
            'allowed=root_or_system_and_matching'.format(lib_stat.st_uid, helper_stat.st_uid))
    if (lib_stat.st_mode | helper_stat.st_mode) & 0o022:
        raise RuntimeError('v2 native payload writable by group/other')
    if not (helper_stat.st_mode & 0o111):
        raise RuntimeError('v2 native helper not executable')


def configure():
    # Never alter an active playback session or hot-swap native providers.
    if xbmc.Player().isPlaying():
        raise RuntimeError('Playback already active; refusing provider hot-switch')
    lib = ctypes.CDLL(LIB, mode=getattr(ctypes, 'RTLD_GLOBAL', 0))
    path = mapped_library()
    if digest(path) != LIB_SHA:
        raise RuntimeError('LibMMBD SHA256 mismatch')
    helper = os.path.join(os.path.dirname(path), HELPER)
    # lstat() refuses APK-native symlinks; app-owned or writable binaries
    # must not become a programmable exec path for the root broker.
    validate_android_native_install(os.lstat(path), os.lstat(helper))
    if digest(helper) != HELPER_SHA:
        raise RuntimeError('v2 native helper SHA256 mismatch')
    fn = lib.mmbd_get_version_string
    fn.argtypes = []
    fn.restype = ctypes.c_char_p
    version = (fn() or b'unknown').decode('utf-8', 'replace')
    expected = {'LIBAACS_PATH': 'libmmbd',
                'LIBBDPLUS_PATH': 'libmmbd', 'MAKEMKVCON': helper}
    previous = {key: os.environ.get(key) for key in KEYS}
    if any(value is not None for value in previous.values()) and previous != expected:
        raise RuntimeError('Foreign or partial provider settings exist; refusing to override')
    if previous != expected:
        for key, value in expected.items():
            os.environ[key] = value
    return version, helper, 'already_configured' if previous == expected else 'configured'

def main():
    mon = xbmc.Monitor()
    log('BEGIN pid={} uid={} no_backend_launch=1'.format(os.getpid(), os.getuid()))
    try:
        version, helper, disposition = configure()
        record('ready', version=version, provider='libmmbd', helper_sha256=HELPER_SHA,
               library_sha256=LIB_SHA, config_result=disposition,
               user_notice='Configuration only: existing v2 broker must be started separately after authenticated device acceptance; no broker launched')
        log('READY pid={} uid={} version={} library_sha=PASS helper_sha=PASS '
            'LIBAACS_PATH=libmmbd LIBBDPLUS_PATH=libmmbd MAKEMKVCON={} '
            'disposition={} broker=NOT_STARTED playback=NOT_TESTED'.format(
                os.getpid(), os.getuid(), version, helper, disposition))
    except Exception as exc:
        try:
            record('failed', error_type=type(exc).__name__, error=str(exc))
        except Exception as recording_error:
            log('STATUS_WRITE_FAILED {}'.format(type(recording_error).__name__), xbmc.LOGWARNING)
        log('FAILED {} {}'.format(type(exc).__name__, str(exc)), xbmc.LOGERROR)
        return
    while not mon.waitForAbort(5):
        pass

if __name__ == '__main__':
    main()
