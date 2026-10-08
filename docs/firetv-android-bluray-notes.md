# Fire OS 7 / Android Blu-ray and Dolby Vision FEL — Gazelle engineering status

> **Experimental status (2026-10-08):** The Kodi ARMv7 Fire TV branch supports the ongoing Blu-ray and Dolby Vision experiments. Dolby Vision Profile 7 **full enhancement layer (FEL) reconstruction is not yet proven working on Fire OS 7**. This document separates observations from hypotheses.

## Platform and existing milestones

- Device: Amazon Fire TV Cube 3 (AFTGAZL / gazelle, Amlogic POP1-G / A311D2 family), Fire OS 7 / Android 9 base; root via Magisk used only for read-only inspection and experimental configuration.
- Kodi branch: `android-firetv-bluray`; ARMv7 is the supported device ABI for this build.
- Blu-ray: Android build integrates libbluray/udfread and is used alongside experiments with MakeMKV/libmmbd. Optical drive / AACS / BD+ integration remains separately under investigation; do not claim all retail discs are supported.
- The existing workflow `.github/workflows/android-firetv-bluray.yml` builds the Android dependencies and APK and uploads APKs as run artifacts. This is not a GitHub Release publication job.

## Reproduced Dolby Vision observations

| Area | Profile 7 FEL (woman / Power Rangers) | Profile 8.1 control (`DV8_TEST.mp4`) |
|---|---|---|
| Kodi opens video | Yes (individual test session; direct sample switch can fail) | Yes |
| Actual OMX component | `OMX.amlogic.dolby-vision.dvhe.decoder` | Same |
| Active decoder stream device | `/dev/amstream_dves_hevc` | Same |
| First frames render | Yes | Yes |
| Driver source classification | `FORMAT_HDR10` | `FORMAT_DOVI` |
| True FEL reconstruction | **Not verified** | Not applicable (no enhancement layer) |

The kernel has been seen to transition DV → HDR after interpreting Profile 7 metadata as HDR10, while Profile 8.1 remains classified DOVI. Registering `dveldec` does **not** establish that BL+EL reconstruction occurs.

## CoreELEC comparison / why Stage 1 exists

CoreELEC 22 source references:

- [`BitstreamConverter.cpp`](https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/utils/BitstreamConverter.cpp): obtains RPU `DoviRpuDataHeader.el_type`, classifies FEL versus MEL on first valid RPU.
- [`DVDVideoCodecAmlogic.cpp`](https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAmlogic.cpp): passes FEL decision to decoder initialization after the bitstream converter detects it.
- [`AMLCodec.cpp`](https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp): for FEL, enables driver FEL/MEL settings and `STREAM_TYPE_STREAM`, applies HEVC `nal_skip_policy=1` on stream path, and resets settings on teardown.

The CoreELEC decoder path uses libamcodec/DRM and a 5.15 kernel. Android Fire OS uses MediaCodec/OMX and a 5.4 kernel; compatibility of the CoreELEC driver controls on Fire OS is **not established**. Avoid applying live H265 sysfs changes, patching the OMX binary, or widening seccomp merely because CoreELEC uses a similarly named setting.

## Stage 1 diagnostic instrumentation in this branch

- `CBitstreamConverter` now retains `GetDoviIsFEL()` and `GetDoviELTested()`, parsed from the first valid RPU independently of whether RPU conversion was requested (requires `HAVE_LIBDOVI`).
- Kodi emits `GAZELLE_DOVI_RPU profile=... el_type=... fel=...` once RPU classification occurs.
- For the first 48 Profile 7 access units, Kodi emits bounded `GAZELLE_P7_NALS stage=pre/post ...` counts for BL (NAL <=31), RPU (62), EL (63), VPS (32), SPS (33), PPS (34), plus invalid NALs.
- `pre` counts describe demuxed packet content; `post` counts are from the converted buffer after the input-buffer capacity limit. Note: packet pairing remains gated by `packet.isDualStream`; a single-track sample uses the ordinary converter path.
- Logging does not alter decoder selection, HAL policy, NAL skip settings, seccomp, or the vendor library. It is a diagnostic APK, **not** a FEL fix.

Log capture after starting a **known Profile 7** sample in Kodi:

```sh
ADB=/Applications/adblink.app/Contents/MacOS/adbfiles/adb
"$ADB" shell 'su -c "cat /sdcard/Android/data/org.xbmc.kodi/files/.kodi/temp/kodi.log"' | \
  grep -E 'GAZELLE_(DOVI_RPU|P7_NALS)|Open Using codec|FELPAIR' | tail -180
"$ADB" shell 'su -c "cat /sys/class/amdolby_vision/src_format; cat /sys/class/amdolby_vision/dv_inst_status"'
```

To avoid the observed `InstanceGuard locked` on rapid switching, force-stop Kodi between tests before restarting the test sample. The passive log instrumentation is intended to distinguish lost RPU/EL NALs from vendor decoder configuration problems. Use the visual woman/credits tests to assess actual reconstruction.

## Highest-priority next steps

1. Build/install the Stage 1 APK and compare NAL logs for Profile 7 and the prior working Profile 8.1 baseline. Profile 8.1 has no special Stage 1 NAL logging, so use its existing logs and `FORMAT_DOVI` status as control.
2. If RPU/EL data is missing at MediaCodec, repair Kodi's demux/bitstream conversion and verify byte-level NAL packaging before any HAL changes.
3. If correctly packaged BL + EL + RPU reaches the Dolby OMX decoder, inspect vendor OMX initialization and determine whether per-decoder `codec_set_dvmetawithel(codec,1)` plus other FEL controls are needed **before the first frame**.
4. Avoid the earlier external ioctl helper: reopening `/proc/<pid>/fd/<fd>` does not reliably duplicate the original per-decoder open file description.
5. Independently diagnose the Kodi decoder-lifecycle `InstanceGuard locked` error after direct sample switching.

## Historical limitations

The original milestone was to build Android with `HAVE_LIBBLURAY`, `HAS_UDFREAD`, `bluray://` and unencrypted BDMV support. MakeMKV/libmmbd, AACS/BD+, optical-device integration, and retail-disc behavior require separate validation. Past source notes mentioning future ARM64 support are outdated for the current ARMv7 Fire OS environment.
