# Gazelle P7: Android profile handoff — 2026-10-14

## Verified distinctions

- Kodi intentionally leaves the Dolby P7 **codec capability filter** at `0` (unless converting to Profile 8), so it may choose a Dolby decoder even if Android does not advertise P7. P8 uses filter `256`. This local value is checked against `codec_caps.profileLevels()` before codec creation and is **not** itself passed to `MediaCodec.configure()`.
- In the reviewed `ConfigureMediaCodec()` code, Kodi does not add a `profile` or `level` key to the Dolby `MediaFormat`. Android defines Dolby P7 (`DvheDtb`) as `128`, P8 (`DvheSt`) as `256` ([Android SDK](https://developer.android.com/reference/android/media/MediaCodecInfo.CodecProfileLevel)). Neither value should be equated to vendor OMX owner fields without evidence.
- Exact Amazon `libstagefright.so` SHA256 `4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e` (PS7702.4965N). `ACodec::setupVideoDecoder()` at Thumb `0x53f38` loads optional message key `profile` at `0x53f8c/0x53f92`; it branches around HEVC profile validation at `0x53f9a` when absent.
- The HEVC validation at `0x53fa0/0x53fa6` compares the requested profile against `0x1000` and `0x2`. Its `0x53fda/0x53fdc` instruction sequence synthesizes **standard OMX index `0x0600000f`** (`ProfileLevelQuerySupported`), not the proprietary setter `0x7f00010d`. [AOSP comparison](https://android.googlesource.com/platform/frameworks/av/+/69e86ab47181f93fce4c119d0f293a147c2e687f/media/libstagefright/ACodec.cpp) is background only, not the device binary.

## Reproducible audit and passive Kodi instrumentation

- `python3 tools/gazelle-fel/audit-stagefright-profile-read.py /path/to/libstagefright.so` should produce `STAGEFRIGHT_HEVC_PROFILE_READ_PASS` on the pinned ELF; this verifies static instruction bytes only.
- Kodi commit `dbf3ba3` adds **logging only**: `GAZELLE_DOVI_CAPABILITIES` records the selected codec's bounded Android advertised profile list, P7/P8 capability flags and the old selection filter. `GAZELLE_DOVI_MEDIAFORMAT` now also reports actual Android `profile`/`level` key presence and values, and injected CSD byte length.
- New [ARMv7 build](https://github.com/angelcode1/xbmc/actions/runs/38521964129) is not presumed successful until GitHub Actions confirms.

## Remaining unknown

Neither these Kodi values nor the Stagefright branch prove who invokes Amlogic's `0x7f00010d` vendor profile-like setter, the live owning component's `+0x20` value, the `0x179` decoder ioctl, or EL pixel contribution. Keep P8 output unchanged. Do not set Android `128`, vendor `0x400` or `dv_duallayer:1;` speculatively based on code naming alone.