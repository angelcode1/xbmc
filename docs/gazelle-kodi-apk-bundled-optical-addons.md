# Cube 3 Kodi APK with embedded optical VFS and UDF checker

## Packaging implemented

`angelcode1/xbmc` branch `android-firetv-fel`: Android APK workflow checks out exactly pinned `angelcode1/cube3` commit `057074684f260588c2153580a53a2064b3662a59`, compiles `libvfs.gazelle.physical.so` for ARMv7 from the tested physical VFS source, and stages the system addon resources into Kodi's normal Android packaging prefixes. The bundled addons are `vfs.gazelle.physical` v0.1.0 and `script.gazelle.physicaludfcheck` v0.1.6. Android packaging's existing asset and native library collection picks up the staged addon files. The resulting APK is *rejected* by CI unless it contains both addon manifests, the Python checker files, and one ELF32 ARM optical VFS binary.

This packaging is **not** an assertion that the addon auto-enables at first boot, that the root optical service is already running, or that protected discs work. The root service must be installed separately, and the Magisk module does not yet auto-start it. A clean Kodi reinstall can change the app's Linux UID, requiring the root optical service to be stopped and started again so its `/data/system/packages.list` Kodi UID authorization is refreshed. On Kodi first launch, check the binary VFS is installed and enabled.

## Disc support matrix

- Blu-ray UDF 2.50: real physical descriptor traversal and 3-entry root FID `BDMV` passed via the GZOB VFS; native `udf://` listing awaits acceptance of the pinned libudfread primary-first mirror patch in the new APK. No protected playback/AACS success has been established.
- DVD-Video: potentially readable through the same raw-sector VFS if its UDF/ISO structure is supported, but libdvdnav integration, VIDEO_TS navigation, CSS and drive behavior are still separate unproven live gates.
- Audio CDs: CD-DA is not UDF and requires a separate authenticated read-only CD sector/raw-audio interface, track discovery and Kodi player adapter. **Not implemented by this APK bundling**.
- Magisk module `gazelle_optical_stack` has optical kernel modules and MakeMKV but is manual-only. It does not currently install/activate the GZOB service as an automatic boot daemon and the APK cannot perform that privileged job.

No kernel UDF mount: previous Cube 3 watchdog hard hang. Never package or load `udf.ko`.

## Build acceptance

[Android FireTV Blu-ray Build](https://github.com/angelcode1/xbmc/actions/workflows/android-firetv-bluray.yml) must pass through both `Compile and embed ARMv7 Gazelle optical Kodi addons` and `Verify Gazelle addons actually exist inside APK`. At that point the APK may be installed after an optional clean uninstall, then root service restarted, Kodi addon activation checked, and v7 diagnostic repeated. Do not mistake APK CI pass for live BD/DVD/CD playback.
