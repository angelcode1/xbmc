# FireOS / Android Blu-ray experiment

Goal: enable Kodi's upstream Blu-ray plumbing on Android/FireOS.

## First milestone

Build Android Kodi with:

- `HAVE_LIBBLURAY`
- `HAS_UDFREAD`
- `bluray://` support
- unencrypted BDMV folder playback

## Not included yet

- MakeMKV `libmmbd`
- retail Blu-ray decryption
- AACS/BD+ runtime packaging
- FireOS optical-drive mount handling

## Reason

Kodi's Android build plumbing does not currently wire `libbluray`/`udfread` into Android depends by default. This branch first tests whether Android ARM64 Kodi can build and run with libbluray enabled.

## Later milestones

1. Confirm APK contains libbluray strings/symbols.
2. Open unencrypted BDMV folder.
3. Check Kodi log for Blu-ray open path.
4. Add Android-compatible AACS/BD+ packaging.
5. Investigate Android-compatible libmmbd only after libbluray works.
6. Test audio passthrough with FireOS Dolby/DTS-HD Magisk modules.
