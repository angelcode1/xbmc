# Gazelle kernel-UDF Blu-ray and optical media tiles — 2026-10-17

## Verified device baseline
The user confirmed physical UHD Blu-ray playback works on rooted Fire TV Cube 3
with the kernel UDF mount at
`/data/user/0/org.xbmc.kodi/files/gazelle-kernel-udf`, read-only
`uid=10250,gid=10250`, and root MMBD broker
`48652fca416514026ff7c6e4d998491209a5bdd9ab79bd3320c12e1a72d99421`.
LibMMBD v1.8.0 and the native helper passed their SHA checks.
The successful installed APK used a four-byte ARM instruction patch,
patched core SHA256
`7b583d7b9201d6ef3d2b2a0b1da7823732beb1302ecf076ee56d0b8a61965401`.

**This source change has NOT been built or run on the device.** It expresses
the working binary route as an exact-mount-path C++ condition. Never
combine the source change with the old unconditional instruction patch.

## Automatic Kodi media-source tiles
On Kodi source settings load, when the app-private Gazelle mountpoint exists:
- Videos: `Blu-ray Disc` => mounted filesystem
- Pictures: `Disc Pictures` => mounted filesystem
- Music: `Audio CD` => `cdda://local/`
- Music: `Disc Music Files` => mounted filesystem

Kodi's built-in sources directory is used, with an Estuary Music sources widget;
there is no manual Add Source step on initial setup.
Known legacy `Physical Blu-ray Drive` userspace source entries are migrated
only when matching the exact older VFS path. Existing unrelated sources remain.
CDDA playback and its virtual path on this Fire OS kernel are **untested**;
a CD audio tile is not proof of CD playback. UDF mount visibility and content
classification for inserted optical media still require device acceptance.
The source manager does not start root services or mount media.

## Repository preservation / upstream updates
- This feature branch is based on `android-firetv-unified`.
- The previous userspace UDF VFS lives in `angelcode1/cube3` under
  `blu-ray/physical-udf` and related historical branches. Archive it;
  do not delete files or history.
- Keep MMBD startup service `service.gazelle.mmbd`, LibMMBD, the native
  helper and authenticated root broker. After reinstalling Kodi, its UID
  changes; restart the broker to refresh its authenticated Kodi UID.
- Keep Linux ARMhf MakeMKV's private runtime, settings and disc secrets
  off GitHub. The official upstream Kodi merge must preserve exact-path
  `bd_open_files()` routing, automatic sources and the native library
  provisioning contract.
- To sync with upstream, fetch upstream Kodi, rebase/cherry-pick the
  focused changes to these three files, resolve API/skin changes, then
  rebuild/sign and test on the Cube. Do not overwrite the last known
  working locally signed APK or change workflows as part of this work.
