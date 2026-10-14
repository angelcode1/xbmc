# Gazelle native FEL: Stage 2 results — 2026-10-14

Kodi build: `20261014-86526e2`, fresh ARMv7 install. Tests: P8 `DV8_TEST.mp4`, P7 `DV FEL Power Rangers Credits Test.mkv`, captured 12:36–12:38 AEST. Source logs were inspected; raw device logs are not checked into Git.

| Diagnostic | P8 control | P7 FEL |
| --- | --- | --- |
| OMX decoder | `OMX.amlogic.dolby-vision.dvhe.decoder` | same |
| MIME / Surface | `video/dolby-vision` / true | same |
| Dolby profile / EL present | 8 / 0 | 7 / 1 |
| Codec capability-filter profile | 256 | 0 |
| Input extradata bytes | 23 | 797 |
| Dimensions | 3840×2014 | 3840×2160 |
| Kernel source format | `DV FORMAT_DOVI` | `HDR10 FORMAT_HDR10` |
| DV instance | valid, mapped, DV | valid, mapped, HDR10 |
| Kodi RPU classification | Profile 8, FEL false | Profile 7, `el_type=FEL`, FEL true |

**P7 Stage 2 gate PASSED**: 48/48 sampled `GAZELLE_P7_INPUT_COPY` records have `equal=true`. The diagnostic uses `memcmp` to compare converted access-unit bytes with the copied JNI buffer. 1,894,800 bytes total; no differences in the sampled copies.

The 48 paired `GAZELLE_P7_NALS` pre/post records preserve per-type totals: BL 384, RPU 48, EL 501, VPS 6, SPS 6, PPS 51, invalid 0. Original input bytes total 1,895,817 in length-prefixed format; converted output bytes total 1,894,800 in Annex B format. The **1,017-byte size difference does not by itself imply lost video payload**; a per-NAL payload comparison would be needed to establish why it differs.

**Interpretation**: Kodi identifies FEL, selects a Dolby OMX component, preserves typed NAL counts, and copies the processed access units correctly into MediaCodec buffers. This excludes a corrupt Kodi-to-JNI copy for sampled units, not failed downstream vendor consumption. P7 remains classified HDR10, whereas P8 is Dolby Vision.

**Remaining gates**: Determine whether Amazon OMX actually appends `dv_duallayer:1;` when P7 is configured, whether the active decoder receives the per-instance `AMSTREAM_SET_DV_META_WITH_EL (0x179)` control, and whether an EL decoder/provider becomes active. Existing passive diagnostic: `tools/gazelle-fel/capture-omx-runtime.sh`. Capture P8 and P7 separately, with restart between sessions; retain vendor logcat and VFM evidence. Do not force global HEVC settings or inject ioctls based on these logs. A true FEL fix requires independent proof that the enhancement-layer pixels contribute to output.
