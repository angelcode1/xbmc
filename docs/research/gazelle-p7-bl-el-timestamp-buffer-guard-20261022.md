# Gazelle Profile 7 BL/EL packet integrity guard — source branch only

22 October 2026. This is a **real Kodi fork code fix**, not a functioning Fire OS FEL decoder.

## Defects fixed

1. `CDVDVideoCodecAndroidMediaCodec::AddData()` previously selected the **first opposite-layer packet** in `m_doviLayerPackets`. During out-of-order demux it could join BL and EL pictures from different DTS/PTS times, potentially corrupting a Dolby Vision Profile 7 access unit.
2. It previously silently cut a Profile 7 assembled packet down to `CJNIMediaCodec` input capacity, passing a corrupt partial HEVC access unit to the decoder.

## Code

New header `xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPairing.h` has a header-only, host-testable `FindMate()`, `SameAccessUnit()`, `CanBuffer()`:

- Match only packets of opposing BL/EL type that share **DTS within 100 microseconds** if both DTS exist. Otherwise require PTS within 100 microseconds. A conflict between two valid DTS clocks is never overridden by matching PTS.
- A pending packet must have a usable DTS or PTS clock. Queue is limited to eight packets, 16 MiB per packet and 64 MiB aggregate; overflow fails closed and clears the pending queue instead of silently dropping a layer.
- EL/BL byte lengths must not overflow converter's signed 32-bit API.
- Oversize **Profile 7** MediaCodec input now logs an error and returns false; **non-P7** truncation handling remains unchanged (out of scope). No buffer resizing claim.
- No device writes, no global `enable_fel`, `debugflags`, `enable_stream_mode_multi_dec`, VFM map, video input port or codec format manipulation.

## Verification

Source-only host test `tests/TestGazelleFELPairing.cpp` validates DST/PTS selection under reorder, conflict, missing timestamps and queue bounds; `.github/workflows/gazelle-fel-pairing-host.yml` is an automatic gate (workflow execution **not independently confirmed**).

Locally compiled and ran the equivalent helper tests with Clang, both optimized and ASan/UBSan:

```
GAZELLE_FEL_P7_PAIRING_HOST_PASS timestamps=true bounds=true device=false FEL_decode=false
```

No Android Kodi compile or device playback verification was performed, and this code is only on the research branch. A GitHub Actions workflow has been added but whether its run completed is **unknown**.

## Critical remaining limitation

The actual Fire TV Cube 3rd generation has a compiled Dolby `enable_fel` flag, HEVC BL/EL picture association, and native `vdec_create` master/slave mechanism. However its read-only live profile 7 playback evidence had **one BL decoder, no EL decoder**, with grey instead of white credits; current idle decoder global flags are zero. Merely feeding correctly paired NAL63 and NAL62 to the stock Android Surface decoder will not activate FEL residual reconstruction. The API28 no-Surface Main10 test exposed only 8-bit YUV420_888, so there is no verified 10-bit CPU pipeline substitute.

A working end-to-end FEL implementation additionally needs a per-session isolated paired native HEVC input, real EL decoding, frame binding, RPU interpretation, output ownership and fence-safe Dolby display. No deployed patch or visual FEL success is claimed.

## Owner Mac validation — 22 October 2026

Owner executed `CXX=clang++ GAZELLE_RUN_SANITIZERS=1 sh tools/run_tests.sh` from the no-Git source-only bundle and reported exactly:

```text
GAZELLE_FEL_P7_PAIRING_HOST_PASS timestamps=true bounds=true device=false FEL_decode=false
```

This confirms that the standalone C++ timestamp/bounds tests run on the owner's host; it does **not** prove Kodi Android compiles, the patched Kotlin/Java/MediaCodec path runs on FireOS, dual VDEC starts or FEL pixels are reconstructed. No APK deployed or Cube settings changed as part of this gate.
