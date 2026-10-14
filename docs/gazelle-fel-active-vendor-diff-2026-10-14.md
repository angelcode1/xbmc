# Gazelle active vendor OMX comparison: Profile 8.1 vs Profile 7 FEL

Date: 2026-10-14. Kodi build verified in preceding Stage 2 test: `86526e2`. This report supersedes the inactive/after-teardown P7 capture at 12:50. All conclusions below use the active playback P7 capture at **12:53:26–12:53:55 AEST** and the active P8 control at **12:49:22–12:49:52 AEST**.

## Evidence (user-supplied archives; raw files kept out of repository)

| ZIP | SHA-256 | Interpretation |
| --- | --- | --- |
| `gazelle-omx-runtime-P8_VENDOR-20261014-124922.zip` | `46c83a56ea834d172b883ccb861e4c09e5f273f8a257b627eab54619cd9c3936` | active P8 control |
| `gazelle-omx-runtime-P7_VENDOR-20261014-125026.zip` | `e7242c4823fac1dc6f226cb300148a2e467781cc4ce7297f6a44b323764a58e1` | P7 after decoder teardown, **not** an active control |
| `gazelle-omx-runtime-P7_VENDOR-20261014-125326.zip` | `5d5358d6d1d5278cb5fb9b456b03dbc3df1f9d2f136ed8d0d0330c6c92f57e25` | active P7 playback; valid comparison |

The `logcat-full.txt` buffers contain **earlier playback sessions** from the same device. Attribute events to the indicated startup times, not merely their presence in the entire logcat file.

## Six-checkpoint summary

| Metric | P8 control | P7 FEL |
| --- | --- | --- |
| Active DV instance `inst1` | mapped 1 / valid 1 in 6/6 | mapped 1 / valid 1 in 6/6 |
| Kernel DV source | `DV FORMAT_DOVI` in 6/6 | `HDR10 FORMAT_HDR10` in 6/6 |
| Media.codec PID | 680 | 680 |
| Open decoder fd | `/proc/680/fd/17 -> /dev/amstream_dves_hevc_frame` | same |
| Base VFM path | `dvbldec(1) -> v4lvideo.0` | same |
| Enhancement VFM path | `dveldec(0) -> dvel` | same, **inactive** |
| Composer VFM path | `video_composer.0(1) -> video_render.0` | same |
| Video composer total_get_count | 17096 -> 18232 (**+1136**) | 19013 -> 20187 (**+1174**) |
| Global H265 settings | nal skip=2, global dolby_meta_with_el=0, bypass=0, parser DV=1 | same |
| OMX properties | use_dv_frame=true; stream mode unset | same |

All six P7 checkpoints show active video; the prior capture at 12:50 was after teardown, with mapped=0 and static composer counters, so must not be treated as an equivalent test.

## Startup-time evidence, compared without stale logcat history

**P8 — 12:49:19 AEST:**
- 12:49:19.455: Kodi `GAZELLE_DOVI_CODEC_SELECTED profile=8 el_present=0 capability_filter_profile=256`, named `OMX.amlogic.dolby-vision.dvhe.decoder`, Surface=true.
- 12:49:19.458: Android ACodec reports `setPortMode on output to DynamicANWBuffer failed`, with `UnsupportedSetting` / `BadPortIndex` errors.
- 12:49:19.499: Kernel `vdec_init ... VDEC_TYPE_FRAME_BLOCK, format: 11`.
- 12:49:19.549: `vdec->port_flag=0x102, port_flag=0x10b`.
- 12:49:19.554 / 19.598 / 19.676: first input / frame ready / frame rendered.
- 12:49:19.714: Dolby `HDR=>DV`, `parse_metadata ... DOVI`; remains DOVI while active.

**P7 — 12:53:22 AEST:**
- 12:53:22.648: Kodi `GAZELLE_DOVI_CODEC_SELECTED profile=7 el_present=1 capability_filter_profile=0`, **same OMX component**, Surface=true.
- 12:53:22.652: **same** Android `DynamicANWBuffer` warning and OMX error classes as P8.
- 12:53:22.694: Kernel `vdec_init ... VDEC_TYPE_FRAME_BLOCK, format: 11`.
- 12:53:22.717: same `vdec->port_flag=0x102, port_flag=0x10b`.
- 12:53:22.725 / 22.770 / 22.867: first input / frame ready / frame rendered.
- 12:53:22.904–22.905: Dolby initially logs `HDR=>DV`, then `parse_metadata ... HDR10`, then immediately `DV=>HDR`. The transient `HDR=>DV` is **not evidence that P7 successfully decoded Dolby metadata**.
- All six subsequent checkpoints remain HDR10; EL provider `dveldec(0)`.

## Interpretation and next gate

The experiment rules out the claim that P7 fell back to HDR10 merely because no video decoder had been initialized: an active decoder fd, BL provider, valid Dolby instance, rising composer counts and actual first-frame render are all present. The Android OMX buffer-mode warnings are shared with **working P8**, so are not a unique P7 failure signature.

Prior Stage 2 proved **48/48 exact source→JNI buffer copies for P7** with BL/RPU/EL NAL counts preserved. Combined with this active playback test, the remaining unproven boundary is **vendor OMX/driver dual-layer configuration, metadata processing and EL decode**. Neither logcat prints the effective `mAmlCodecParam->config` / `dv_duallayer:1;`, nor a decoder-local `AMSTREAM_SET_DV_META_WITH_EL (0x179)` transaction. Absence of such printouts cannot prove no ioctl was issued.

Do **not** force `dv_duallayer` through a speculative Android `MediaFormat` key or inject ioctl `0x179` into a separate kernel file description. The safe engineering step is to continue the previously documented **offline** Thumb disassembly of the exact `libOmxVideo.so` SHA `eb79f44c...`: trace the source and assignments of the vendor component field at `+0x20` that gates `AmlogicVideoDecoder::setUp()` appending `dv_duallayer:1;`, then inspect the init/config chain for any per-decoder `0x179` dispatcher. If observation later requires runtime tracing, design a narrowly scoped, reversible, explicit opt-in diagnostic with a rollback plan before touching `media.codec`.

No device settings were written and no native FEL fix is claimed. P8 Dolby Vision remains functional; native Profile 7 FEL reconstruction on Fire OS remains unverified.
