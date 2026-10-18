# Gazelle kernel-UDF source entries and playback route

Current implementation: `android-firetv-unified`. The 17 October 2026
proof is a **historical single-device acceptance** obtained with a
four-byte ARMv7 binary patch. The maintainable source route now calls
`bd_open_files()` for the exact app-private kernel-UDF location.
It still requires fresh on-device acceptance testing.

Kodi registers four *media source entries* on initial settings load
without requiring a disc to be mounted:
- Videos / Blu-ray Disc
- Pictures / Disc Pictures
- Music / Audio CD
- Music / Disc Music Files

These are source entries rather than four standalone home-screen
buttons. The kernel navigator refuses UDF mounts with an old Kodi UID,
or mounted from a device other than `/dev/block/sr0`. It does not
mount, eject, read raw sectors, start a broker or change SELinux.

Only a separately qualified Magisk backend may load the optical/UDF
drivers and provide the root MMBD broker and complete ARMhf runtime.
CDDA and true FEL playback remain unqualified on a clean-installed Cube.

See [standalone APK build](gazelle-kernel-udf-self-contained-build.md).
