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

## Source tile defaults and add-on activation

The source-based entries are created on the first Android settings load even if
no optical media is inserted: Videos / Blu-ray Disc, Pictures / Disc Pictures,
Music / Audio CD and Music / Disc Music Files. They are **Kodi sources**, not
independent top-level Estuary home buttons; Music also exposes the Sources
widget. A missing mount produces an inaccessible disc source, not a mount.

The addon is packaged as an *optional system addon*. Kodi enables newly
discovered optional system addons by default; an existing persisted disabled
state remains disabled. The Python navigator checks the read-only UDF mount
before listing paths, and does not install kernel modules or start root services.
CDDA playback on Fire TV Cube has not been verified.

**Do not replace a working Kodi APK solely because CI passes.** The build
may use an ephemeral signing certificate when no stable signing keystore secret
is configured. Verify the installed and candidate signatures match, and
preserve the installed APK and user data before attempting an update.

## Clean installation with a changing Kodi UID (runtime guard)

The APK **cannot repair a root-owned parent directory before Kodi starts**:
Android does not grant that permission to the application's new UID. This
workflow therefore includes a separate, operator-invoked macOS clean-install
helper and a root-only provisioning script in the APK artifact. Neither is
executed by the APK or silently triggered at boot.

1. Preserve the last working locally signed APK and any wanted Kodi user
   data. The helper saves the old base.apk and package UID, but **not**
   private Kodi databases, installed addons, registration files or media.
2. Run `kodi-clean-install-macos.sh --preflight`. It refuses *any* live mount
   under Kodi's application tree, including `/data/data` and `/data/user/0`
   aliases. It never attempts an unmount; resolve mounts safely outside this
   script before deciding to uninstall.
3. For an explicitly approved data-destructive clean installation, set
   `GAZELLE_CONFIRM_KODI_DATA_LOSS=DELETE_KODI_DATA` and run
   `kodi-clean-install-macos.sh --clean-install <built.apk>`.
4. **After** Android's package installer creates the new app data, the root
   helper derives the new UID from `/data/system/packages.list`, verifies
   the app-root owner and MCS categories, then creates or normalizes *only*
   the `files` parent. It refuses any mount within the app tree and never
   recursively modifies a mounted UDF.
5. The addon's `/proc/self/mountinfo` verification also requires the
   mounted UDF's `uid=` and `gid=` options to match the running Kodi
   process; it refuses a stale mount from a previous installation.

**This does not reprovision the kernel mount or update a running MMBD
broker.** Both are external privileged services. An old root broker snapshots
Kodi's UID at startup; after reinstall its operator must restart the *known
working* broker safely with the new package UID, avoiding duplicate listeners.
The standalone APK does not bundle the separate LibMMBD native library,
its trusted helper, the MMBD startup service, or private MakeMKV runtime.
Until these are provisioned and qualified, clean-install testing covers Kodi
startup, local media, source tiles and addon safety—not AACS playback.
