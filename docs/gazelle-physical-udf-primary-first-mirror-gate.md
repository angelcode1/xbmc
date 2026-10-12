# UDF 2.50 physical optical primary-first metadata workaround (2026-10-13)

## Live evidence

The Cube 3 read-only GZOB path now verifies actual UDF root-directory data: FSD at LBA320 tag256, root EFE at LBA321 tag266, root directory data at LBA322, all 180 directory bytes parsed with three directory entries and `BDMV` recognized. Python v5 attempted the remote mirror EFE at LBA16292191 first; it failed and caused subsequent FSD to fail. Python v6 skipped mirror and immediately succeeded on FSD/root. Kodi's native `udf://` remains empty/open-failed.

`xbmc/filesystem/UDFContext.cpp::Mount` calls libudfread's `udfread_open_input` with `UDFBlockInput` forwarding reads into Kodi VFS. `cube3` `PhysicalVFS.cpp::Read` calls `h->file.Close()` on read exceptions. Upstream libudfread's `_map_metadata_partition` reads both primary and mirror EFE unconditionally. Thus native's mirror probe is the strongest failure hypothesis, **not native-trace-confirmed**.

## Change

Added `tools/depends/target/udfread/002-primary-first-metadata.patch`, a 1.2.0 patch at `_map_metadata_partition` that skips the mirror when a valid primary extent has been mapped. If the primary mapping is missing, the mirror fallback remains intact; if both are missing, it fails. Both `Makefile` and `cmake/modules/FindUdfread.cmake` now apply the existing Windows patch and the new patch. No change in protocol, root daemon, Magisk, AACS, movie data or kernel UDF.

New gate `gazelle-udf-mirror-preflight.yml` downloads exactly Kodi's pinned `libudfread-1.2.0.tar.bz2`, requires matching SHA512 from `UDFREAD-VERSION`, applies **both** patches, compiles the actual modified mapper with synthetic block input exercising primary pass/mirror unreadable, normal primary, mirror fallback and both failures, then builds actual libudfread on host.

## Deployment restrictions

CI source/host acceptance does **not** mean Kodi APK assembled, installed or working on Cube 3. The repository's existing `android-firetv-bluray.yml` can build an ARMv7 APK after dependency patch acceptance. Do not replace the user's functional Kodi APK automatically. Capture and compare existing APK signing certificate and package version before attempting install; Android `adb install -r` rejects signing mismatch, and any custom install could affect existing Kodi database/addons. AACS, BD-J navigation and protected streams untested.

Never mount kernel UDF on Gazelle (previous watchdog lock).
