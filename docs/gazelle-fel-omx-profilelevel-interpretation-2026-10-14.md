# Gazelle Dolby plugin absence and OMX profile/level field interpretation

Date: 2026-10-14. User executed a root shell read-only `find` over `/system`, `/vendor`, `/product`, `/odm`, and `/system_ext`, searching for `libstagefrightdolby.so`; it produced no paths and completed. Thus this named plugin was **not found in the scanned trees**. It does not prove it could never be dynamically generated or live somewhere outside those trees. Earlier `media.codec` maps also did not have the Dolby plugin mapped. P8 Dolby Vision is working through `libstagefrighthw.so` and Amazon/Amlogic OMX, so plugin absence alone cannot explain P7 HDR10 fallback.

## Additional static interpretation of the vendor setter

Pinned `/vendor/lib/libomx_framework_alt.so` SHA-256: `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`.

`OmxVideoDecoder::setParameter()` handles vendor index `0x7f00010d` at `0x19488`:

- `0x19488`: reads `nSize` from input offset `+0x00`, requires at least **0x18**.
- `0x1949a`: reads version byte from input `+0x04`, requires **1**.
- `0x194a2 / 0x194a4`: input `+0x0c` → **owner+0x20**.
- `0x194a6 / 0x194a8`: input `+0x10` → **owner+0x24**.
- `0x194aa / 0x194ae`: checks owner coding at `+0x604` against HEVC **0x0b**.
- `0x194b4–0x194bc`: for the following HEVC-specific branch, compares first supplied value against **0x1000** or **0x2**. These compare only after both assignments and do not reject the preceding stores.

This is **structurally consistent with** Khronos/OpenMAX `OMX_VIDEO_PARAM_PROFILELEVELTYPE` with fields `nSize`, `nVersion`, `nPortIndex`, `eProfile` (offset `+0x0c`), `eLevel` (offset `+0x10`), `nProfileIndex`, total 0x18 bytes. The Android OpenMAX header documents this layout:
https://android.googlesource.com/platform/frameworks/native/+/master/headers/media_plugin/media/openmax/OMX_Video.h

**Caution**: `0x7f00010d` is a vendor-index branch, not necessarily the standard `OMX_IndexParamVideoProfileLevelCurrent`. The offset correspondence suggests **profile/level fields**; it does not prove the symbolic vendor type, the actual writer/caller, or which profile value (including `0x400`) P7/P8 sends. The code also has branches for other input formats. Treat `owner+0x20 == 0x400` as a Dolby subclass *profile-like condition*, not a verified FEL enable switch.

The previously observed Kodi `GAZELLE_DOVI_CODEC_SELECTED` capability filter (`P8=256`, `P7=0`) is **not** evidence of values being written to these OMX fields; that diagnostic reflects codec selection, not the vendor instance's actual parameter payload.

## Remaining engineering work

1. Trace the *caller and runtime payload* of vendor parameter `0x7f00010d`, or independently prove effective component profile/level during P7 vs P8. Existing Stagefright libraries forward OMX calls, but the index is not present as a direct literal in those three binaries. Do not infer a missing call from literal absence.
2. Correlate any profile difference with vendor `prepareEsData` / metadata extraction, `codec_set_dvmetawithel` invocation and actual `dveldec` activity.
3. Keep Kodi source self-contained and P8 unaffected. No speculative `MediaFormat` override, kernel writes or HAL injection. FEL success requires pixel-reconstruction evidence, not just `FORMAT_DOVI`.

All findings are based on the already uploaded vendor ELF data and the user's completed read-only filesystem search; **no change to Kodi or the device was made**.
