# Gazelle P7/P8 vendor decoder onset: active playback correlation (2026-10-19)

## Evidence and scope

User archive: `gazelle-fel-onset.zip`; SHA-256 `a674f26645a0f5bcf7105518fcb0f54b55910ecdee2b0145b56e1ac08f49d968`. P8 directory: `P8-20261019-115519`; P7 directory: `P7-20261019-115632`. Timestamp labels are Australia/Brisbane (+10:00); kernel timestamps are seconds since boot. The raw device logs remain **out of Git**.

Device: Fire TV Cube 3 Gazelle, PS7702.4965N, Linux `5.4.125-ab27`, Kodi 23.0-ALPHA1. Both captures arm logcat **before** playback, show decoder initialization, and take active sysfs snapshots while playback runs.

## Exact comparison

| Signal | P8 control | P7 FEL |
| --- | --- | --- |
| Decoder selection | `OMX.amlogic.dolby-vision.dvhe.decoder` | Same |
| Kodi capabilities | `advertised_profiles=16,32,256`; P8 present | Same advertised list; P7 absent |
| Kodi capability-filter value | 256 | 0 |
| Source profile / EL present | 8 / false | 7 / true |
| Android `MediaFormat` profile/level keys | Both absent | Both absent |
| Extradata bytes (source/injected) | 23/0 | 797/725 |
| `vdec_init` format/provider | HEVC format 11, `dvbldec` | Same |
| Printed `pdata->config` | `hevc_double_write_mode:3;` | Same |
| `[0]dv dual layer` in active kernel delta | Not observed | **Observed at 350620.667817** |
| Kernel parsed metadata | `DOVI` at 350567.249283 | `HDR10` at 350620.786454 |
| Kernel DV format transition | DOVI remains active | `HDR=>DV` then `DV=>HDR` within ~1.2 ms |
| Active `inst1` | mapped 1/valid 1, DV | mapped 1/valid 1, HDR10 |
| Active VFM | `dvbldec(1)`, `dveldec(0)` | `dvbldec(1)`, `dveldec(0)` |
| H265 frame/hw error count | 538 / 0 | 571 / 2 |
| Global parser / meta-with-EL / bypass | 1 / 0 / 0 | 1 / 0 / 0 |
| Specific vendor-config log `dv_duallayer:1;` / `mAmlCodecParam->config` | Not printed | Not printed |
| Per-instance `0x179` ioctl evidence | Not captured | Not captured |

Both experiments issue the **same two ACodec buffer-mode warnings** (`UnsupportedSetting`, `BadPortIndex`), so they are not P7-specific.

P7 logcat during this exact 11:56:46 stream contains 48 pre/post NAL-stat pairs, with equal counts: **384 BL slices, 48 RPU, 501 EL-wrapped units, 6 VPS, 6 SPS, 51 PPS, zero invalid**. 48/48 `GAZELLE_P7_INPUT_COPY` records report `equal=true`; no input-truncation warning. No `FELPAIR` message is expected for this combined single-track MKV. Data surviving Kodi/JNI is not evidence the vendor actually decoded its EL.

Both `before-decoder.txt` snapshots have `mapped 0`, `valid 0` and `No vdec.`; their `src_format` textual values may be **stale** from previous playback. Only active snapshots and startup kernel deltas determine the current run's mode.

## What the new capture resolves

1. Capturing late was no longer a confounder: the logcat stream includes selection, OMX allocation, MediaCodec configuration and first-frame processing for both runs.
2. P7 triggers a **kernel dual-layer parser indication** even though the rendered stream is treated as HDR10. The kernel does not show an active EL VFM provider; this is stronger than an absent EL flag in Kodi but **not** sufficient to localize the exact failing vendor function.
3. P8 and P7 show `hevc_double_write_mode:3;` as the printed kernel decoder config. Neither shows literal `dv_duallayer:1;`; this **cannot** establish that the vendor OMX setup code never appended it elsewhere, because kernel printing may omit private component config fields or per-instance controls.
4. The logs do not expose the runtime `OmxVideoDecoder owner+0x20` field, the caller of vendor `setParameter(0x7f00010d)`, or a decoder-local `AMSTREAM_SET_DV_META_WITH_EL (0x179)` invocation. Static vendor disassembly in the existing research docs shows possible paths, not active runtime values.
5. CoreELEC 22 support reports P7 FEL works on Cube 3 T7 POP1-G/A311D2 hardware (https://discourse.coreelec.org/t/firetv-3rd-gen-cube-soc-t7-pop1-g-a311d2-variant/59617). That is evidence of capacity under another software stack, not compatibility of its Dolby kernel module with Fire OS 5.4.

## Next targeted investigation (no device changes yet)

- **Highest information gain:** offline cross-reference all writers and callers of `OmxVideoDecoder::setParameter` vendor index `0x7f00010d` (owner `+0x20` / `+0x24`) and `AmlogicVideoDecoder::setUp()` `dv_duallayer:1;` branch, using the already SHA-pinned exact vendor binaries documented by `gazelle-fel-omx-owner-parameter-trace-2026-10-14.md` and `gazelle-fel-omx-duallayer-xref-2026-10-14.md`.
- Determine whether the **active** Android OMX peer uses the legacy decoder setup path, the alternate awesome path, or both. The shared log `AmlogicVideoDecoderAwesome: video layer sync version is 0` is not an EL result.
- If a runtime probe becomes justified, design a short-lived opt-in non-mutating *trace* of the actual vendor config and per-instance ioctl; define a no-execution gate and rollback first. Do **not** write to `/sys/module/amvdec_h265/parameters`, send raw ioctl `0x179`, override `MediaFormat.profile=128`, patch `media.codec` blindly, or transplant CoreELEC 5.15 modules onto Fire OS 5.4.
- True FEL success must be confirmed through EL-residual-sensitive pixel output, not merely a Dolby Vision output indicator.

No changes to the Cube, installed Kodi, P8, passthrough, satellite, Magisk or kernel-UDF/MMBD optical path were made in this investigation.
