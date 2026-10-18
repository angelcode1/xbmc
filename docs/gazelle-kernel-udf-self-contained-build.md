# Self-contained kernel-UDF Kodi APK

The Android workflow checks out only the triggering `angelcode1/xbmc`
revision. The kernel UDF navigation add-on is sourced from this repository
and staged through Kodi's Android addon packaging prefix. No private
repository checkout or private artifact download is required.

The kernel itself must already expose a **read-only** UDF mount from
`/dev/block/sr0` at
`/data/user/0/org.xbmc.kodi/files/gazelle-kernel-udf`.
The addon detects the mount in `/proc/self/mountinfo` and exposes Blu-ray
playback and file navigation without invoking root, raw-sector I/O or mounts.
Kodi's native media-source tiles and `bd_open_files()` routing are retained.

Old userspace `vfs.gazelle.physical` and
`script.gazelle.physicaludfcheck` are no longer bundled.

**Runtime boundary:** The APK does not distribute proprietary MakeMKV
binaries, device-specific kernel modules, privileged MMBD brokers,
registration files, keys, or private media. Existing libbluray AACS source
changes remain, but protected-disc playback requires the separately
installed qualified MMBD runtime. CI pass does not qualify the new source
APK on a Cube; preserve the currently working signed APK for rollback.
