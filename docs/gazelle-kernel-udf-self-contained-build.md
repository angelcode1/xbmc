# Self-contained kernel-UDF Kodi APK

The Android workflow checks out only the triggering `angelcode1/xbmc`
revision. Kernel-UDF and MMBD service addons, the ARMv7 Android LibMMBD
binary, and the native helper source are **all committed locally**.
The Android Makefile compiles the PIE helper from local C source with
the configured NDK, stages both libraries under `lib/armeabi-v7a/`,
injects its exact SHA-256 into the bundled startup service, and checks
the final APK's service and native library hashes. No private checkout,
token, source repository, or artifact download is used for these items.

The kernel itself must already expose a **read-only** UDF mount from
`/dev/block/sr0` at
`/data/user/0/org.xbmc.kodi/files/gazelle-kernel-udf`.
The addon detects the mount in `/proc/self/mountinfo` and exposes Blu-ray
playback and file navigation without invoking root, raw-sector I/O or mounts.
Kodi's native media-source tiles and `bd_open_files()` routing are retained.

Old userspace `vfs.gazelle.physical` and
`script.gazelle.physicaludfcheck` are no longer bundled.

**Runtime boundary:** The APK does not distribute the proprietary Linux MakeMKV runtime,
device-specific kernel modules, privileged MMBD brokers, registration
files, keys, or private media. It does distribute the standalone
open-source Android LibMMBD v1.8.0 binary and separately compiled helper. Existing libbluray AACS source changes remain, but playback needs the
separate self-contained Magisk backend to be locally provisioned and
qualified on the rooted Cube. CI pass does not qualify the new source
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

## MMBD native provenance and packaging

- Android `libmmbd.so` exact SHA-256: `826b5e6dfebfd628c1a6f851a22cb583fa831978600f4ddc2663af46794a8d0b`.
- Android PIE `libgazelle_mmbd_v2.so` compiled from the independently
  stored C source in this repository. The build SHA changes with compiler
  version, so the build stages and pins its SHA in the Kodi startup service.
- The startup service is optional and validates ownership, trusted native
  origin and matching SHA-256 before it configures `LIBAACS_PATH`,
  `LIBBDPLUS_PATH` and `MAKEMKVCON`; it does not start a root broker.
- The APK alone cannot mount UDF or launch the Linux ARMhf MakeMKV
  environment. These stay in the independently built Magisk backend.
- Reusing the MakeMKV OSS LibMMBD under its applicable LGPL obligations
  requires retaining corresponding-source and license information.
  Do not confuse this freely redistributable LibMMBD component with
  proprietary, private MakeMKV binaries or license state.
- The previously working rooted-Cube helper checksum was
  `c8005d1b168f42024f72de78ae64dcf66f4b142583d3afc92fd97ac72ce9172c`. A recompiled helper is not automatically equivalent;
  on-device authentication and protected-disc playback are not certified.

## Independent backend/frontend release contract (18 October 2026)

The Magisk module is assembled offline using a user-provided private
ARMhf/glibc runtime backup as input. It packages a sanitized runtime
archive alongside pinned kernel modules and the MMBD broker; it does
not publish or embed MakeMKV registration, private keys or disc material.
Provisioning the module runtime locally is a guarded explicit action.
No unattended kernel module insertion, UDF mount or broker startup
is enabled. The Kodi APK never pulls files from that repository.

For a new installation: install the approved Magisk ZIP and standalone
Kodi APK, verify the app's newly allocated UID and SELinux categories,
then explicitly activate the rootfs, approved read-only mount and
current-UID-authenticated broker. Keep working signed APK and Magisk ZIP
for rollback. Neither the new helper compiled with NDK r28c nor a source
build has proven binary-equivalent to the working October 17 ELF; verify
it on the device before treating protected disc support as complete.

## LibMMBD distribution notices

The APK includes the LGPL-2.1 text and source retrieval instructions in
`assets/licenses/`. The binary was built from MakeMKV OSS 2.0.0 with an
Android ARMv7/API28 cross-build. Its corresponding source and license are
available separately from the upstream MakeMKV OSS package; it is
**not** the proprietary Linux ARMhf MakeMKV runtime. For local copies
and redistributions, verify the applicable license obligations and retain
the corresponding source/build information. No MakeMKV registration keys
or proprietary runtime snapshots are stored in this public repository.
