# Gazelle Kodi unified AACS + Dolby Vision — verified playback source snapshot

**2026-10-15 read-only provenance record; not a new build.**

This branch was created from the exact Kodi core used in the user's
locally signed and installed APK:

- Immutable source commit: `024e1e686cd1aa1f10a7b670660dd8fd04b95920`.
- Matching private Cube3 integrated source: `8956427c6c3cc50471b9e482bd3fc24d4e9de1a5`.
- Installed APK SHA256: `c026a074ae767b11cb2a089a382b86b919bf5d0817575e86b48b6798b5a7e37e`.
- On-device results 2026-10-15: Gazelle physical optical VFS opened UHD
  AACS-protected playlist 33 via libbluray/LibMMBD/MakeMKV; `open_end rc=0`;
  3840x2160 HEVC Main10 hardware decoder and AV playback started.
  Visual playback was short and stuttered.
- First audio buffering stall preceded the temporary external 150-second
  broker test timeout. The native broker source already provides a persistent
  listener and a maximum session lifetime of 10800 seconds. Ending the
  temporary broker shell caused repeated AACS decrypt errors.
- Dolby Vision P8 reached DV output; P7 FEL chose the Amlogic DV decoder
  but vendor output remained HDR10 with no active EL decoder. P7 FEL is NOT solved.

**Preserve source + patches + diagnostics unchanged in this checkpoint.**
No shared libraries, historical patches, or compiled artifacts were removed.
A future **separate, opt-in lean-build branch** must remove debug
instrumentation from compiled production code without changing the
validated FEL/HDMI and AACS routing behaviour. A rebuilt core needs its
own hash pin and on-device playback regression tests.

The private, more detailed handoff is held in `angelcode1/cube3` at
`blu-ray/GAZELLE-UHD-FIRST-PLAYBACK-WORKING-CHECKPOINT-20261015.md`.
