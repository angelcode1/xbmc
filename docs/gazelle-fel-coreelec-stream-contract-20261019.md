# Fire TV Cube 3 FEL — exact CoreELEC stream-mode contract vs Fire OS (2026-10-19)

## Source references and confidence

Compared the user-provided P7 and P8 Fire OS startup captures (11:55:52 P8, 11:56:46 P7, Brisbane time) and the existing SHA-pinned Amazon vendor OMX notes in this repository with **CoreELEC source** at `CoreELEC/xbmc`, branch `aml-5.15.196-22.0`, file `xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp`:

https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp

Do **not** infer Fire OS behavior from CoreELEC's kernel 5.15 driver. This is a source-level comparison only, not a compatible transplant.

## New, exact behavior in CoreELEC OpenDecoder

- Around lines 2330–2403, the normal codec configuration begins with `gcodec.dec_mode=STREAM_TYPE_FRAME`.
- If Dolby Vision is available and the stream is Profile 4 or 7 **with** `doviIsFEL`, Kodi writes these two `dv_debug` **DRM property** values: `enable_fel 1` and `enable_mel 1`. It also switches `gcodec.dec_mode=STREAM_TYPE_STREAM`, before calling `codec_init_para()` and `codec_init()`.
- Around lines 2480–2490, if the selected format is HEVC and stream mode is selected, it writes `nal_skip_policy=1`. For frame mode it selects `nal_skip_policy=2`.
- Around lines 2517–2542, it translates codec parameters and calls `codec_init()` **after** selecting decoder mode and setting the above driver knobs.
- Around lines 2746–2748, the close path disables `enable_fel`, disables `enable_mel`, and requests `force_unmap`. This is coordinated setup and cleanup, not a permanent global preference.

These are source-code observations, not instructions to execute the writes on Fire OS.

## Fire OS contrast: P7 and P8 startup traces

| Boundary | Fire OS P7 FEL | Fire OS P8 | CoreELEC source P7 FEL |
| --- | --- | --- | --- |
| Frontend | Android `MediaCodec` with Amlogic DV OMX | Same | Native AML codec API |
| Source | P7 FEL with BL/RPU/EL, 48/48 intact JNI input copies | P8 with BL/RPU | P7 FEL |
| Kernel decode mode | `VDEC_TYPE_FRAME_BLOCK` | `VDEC_TYPE_FRAME_BLOCK` | Selects `STREAM_TYPE_STREAM` **before** codec init |
| Kernel video classification | `HDR10 FORMAT_HDR10` | `DV FORMAT_DOVI` | Different software stack reported working FEL |
| Enhancement VFM | `dveldec(0)` | `dveldec(0)` (expected) | Requires EL decode and metadata acceptance; not inferred from this code alone |
| FEL/MEL gates | Live values not captured | Live values not captured | Explicitly set to 1 via DRM property for FEL |
| NAL skip | Fire OS previously recorded policy 2 | Fire OS previously recorded policy 2 | Selects 1 for stream decode |
| Disable/cleanup | Unknown native component path | Unknown native component path | Explicitly resets both gates on decoder close |

Fire OS P7 logs additionally print `[0]dv dual layer` and then `HDR=>DV=>HDR` with metadata parsed as HDR10. That is recognition of dual-layer signalling, not a completed EL decoder.

**Prior Fire OS failed experiments:** writing global `nal_skip_policy=1` in isolation did not make P7 output DV; writing global `dolby_meta_with_el=1` caused loading wheels / invalid decode and was restored. These separate interventions did **not** reproduce the CoreELEC contract. Do not repeat them or combine them speculatively.

## Why the vendor profile values are not standalone FEL toggles

The Android OpenMAX `OMX_VIDEO_DOLBYVISIONPROFILETYPE` enumeration in current AOSP headers defines:

- `0x10` / 16 = `DolbyVisionProfileDvheDtr` (P4-MEL)
- `0x20` / 32 = `DolbyVisionProfileDvheStn` (P5)
- `0x80` / 128 = `DolbyVisionProfileDvheDtb` (P7)
- `0x100` / 256 = `DolbyVisionProfileDvheSt` (P8)
- `0x400` / 1024 = `DolbyVisionProfileDvav110` (P10 AV1)

Reference: https://android.googlesource.com/platform/frameworks/native/+/master/headers/media_plugin/media/openmax/OMX_VideoExt.h

Cube's Android OMX advertises 16/32/256; it does not advertise 128. The *separate proprietary component-owner* offsets `+0x20` and `+0x24`, written by vendor OMX index `0x7f00010d`, remain semantically unresolved. Values `0x10` and `0x400` at those fields **cannot** be declared either standard profiles or FEL enable signals without the exact caller and structure definition. Kodi's `capability_filter_profile=0` for P7 is only a codec-selection filter, not a value shown sent to this vendor index.

## New highest-value next evidence

1. Confirm the **actual vendor decoder implementation** selected by `OMX.amlogic.dolby-vision.dvhe.decoder` on this Amazon build: legacy `AmlogicVideoDecoder` vs `AmlogicVideoDecoderAwesome` / Dolby subclass. Logged `video layer sync version is 0` is suggestive but does not conclusively resolve the inheritance and dispatch graph.
2. Offline static caller/argument tracing for the proprietary `OmxVideoDecoder::setParameter(0x7f00010d)` writer and `AmlogicVideoDecoder::setUp()` dual-layer string gate, using already pinned `/vendor/lib/libomx_framework_alt.so` SHA `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`, `libOmxVideo.so` SHA `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`, and `libOmxBase.so` SHA `7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee`.
3. Determine whether that active decoder can *in principle* instantiate EL and select stream mode through a supported input contract. Forcing kernel flags without EL instantiation is not progress.
4. If no supported Fire OS route exists, a wholly separate CoreELEC USB boot (not eMMC flashing) would be an alternate validation platform; it must not be done automatically in this project.
5. Require a residual-sensitive FEL visual or frame-comparison proof, not the television's DV icon.

No Fire OS device/SELinux/sysfs/OMX writes, system reboot, Magisk changes or changes to integrated Kodi were made by this source analysis. Vendor binaries are not committed or publicly redistributed.
