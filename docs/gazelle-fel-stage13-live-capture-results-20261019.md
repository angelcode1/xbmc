# Gazelle FEL Stage 13 — live amstream port snapshots, P7 vs P8

**Date:** 2026-10-19. **Status:** LIVE_PORT_TYPES_VERIFIED / FEL_RESIDUAL_UNPROVEN.

Source: user's original read-only `gazelle-fel-stage13.zip`, SHA256 `d8c1fee89341a78e77515b55b8fb5cb66c8f82902a110aba3883e5f290de89ed`; capture subdirectories `P7-20261019-200856` and `P8-20261019-200929`. The upload contains nested ZIP copies and direct text files; analyze only the direct text snapshots to avoid double-counting. All three snapshots per profile contain a readable `/sys/class/amstream/ports` table, `vdec_status`, VFM map and active process FDs. Raw logs remain out of Git.

## Measured active capture

| Measurement | P7 FEL | P8 DV control |
| --- | --- | --- |
| Baseline time, Brisbane | 20:09:02 | 20:09:31 |
| First active time | 20:09:12 | 20:09:38 |
| Second active time | 20:09:15 | 20:09:42 |
| `media.codec` amstream FD | `/dev/amstream_dves_hevc_frame` | same |
| DV HEVC frame port type | `7441 = 0x1d11` | same |
| DV HEVC stream port type | `6417 = 0x1911` | same |
| Changed type/flag/Vformat values among all 19 entries, baseline vs either active sample | **0** | **0** |
| `dvbldec` / `dveldec` active provider map | `1 / 0` | `1 / 0` |
| `vdec_status` decoded frame count first → second active | `130 → 211` | `95 → 178` |
| `vdec_status` hardware errors first → second active | `2 → 2` | `0 → 0` |

All `ports-errors.txt` files are empty. Both baseline `vdec_status` files explicitly report `No vdec.` and the baseline `media.codec` decoder-FD extracts are empty. The before/active port types are unchanged in all six samples.

**Misleading driver bookkeeping:** both `amstream_hevc_frame` and `amstream_dves_hevc_frame` report `flag:267( Used )` even in the **baseline** where `No vdec.` is present. This flag is **not trustworthy as sole active-FD or decoder-allocation evidence**. The actual `/proc/PID/fd` symlink and advancing frame counts establish active decode.

## Correlate with independently SHA-pinned kernel disassembly

The Stage 12 `stream_input.ko` static port table shows:
- `/dev/amstream_dves_hevc_frame`: **`0x1d11`** = `PORT_TYPE_FRAME(0x400)` **plus** `PORT_TYPE_DUALDEC(0x1000)`.
- `/dev/amstream_dves_hevc`: **`0x1911`** = `PORT_TYPE_DUALDEC` **without** `PORT_TYPE_FRAME`.

The exact `amstream_open()` instruction `0x1620` checks FRAME and skips second-decoder creation before `0x1628` checks DUALDEC. Thus the observed P7 frame-device FD and live flags agree with the **default no-slave creation branch**. Stream-port flags have not changed and indicate eligibility to *attempt* secondary allocation. **No device stream-mode switch was made.**

The sysfs samples are not a continuous trace at the instant of open; unusual transient changes cannot be categorically ruled out. `dveldec(0)` is not a direct pointer observation of `vdec->slave`. These captures do not include Dolby source classification or per-instance ioctl `0x179` use; refer to the earlier separately captured P7/P8 Dolby output evidence for that distinction.

## Development decision: hold live experiment until scoped mode control exists

The current integrated Kodi `android-firetv-unified` uses a standard Android MediaCodec configuration in `xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp`, calling `createVideoFormat`, optional color/HDR/CSD setup, then `m_codec->configure()` and `start()`. Its `GAZELLE_DOVI_MEDIAFORMAT` diagnostic explicitly observes that both `profile` and `level` are normally **absent**, and it does not expose a **verified per-instance stream-mode API**.

The Fire OS vendor OMX constructor and native decoder have **global property based** stream/frame switches (`media.omx.stream_mode`, `vendor.media.omx.stream_mode`, `vendor.media.omx.use_dv_frame`). Changing one globally is not a safely isolated P7-only Kodi experiment. Previous kernel `nal_skip_policy` and `dolby_meta_with_el` global changes either failed or destabilized playback; do not repeat them.

**Next engineering gates (must hold before constructing an APK)**:
1. Discover and verify a supported **per-codec-instance**, not global, native mode-selection mechanism or else plan a separately isolated decoder backend; no raw process injection or patched installed vendor libraries.
2. Require eligibility for P7 FEL only, opt-in default-off, no changes to P8 control and clean decoder destruction/fallback if stream or slave allocation fails.
3. Verify decoder `master/slave` and metadata-with-EL handshake, actual EL provider, valid Dolby metadata and an FEL *residual-sensitive image/pixel test* before claiming success.
4. Review coexistence with the Fire TV HDMI passthrough module, voice satellite and disc reading; test only on explicit agreement and with rollback.

**No changes were made** to the Cube, Kodi APK, Magisk, sysfs/kernel flags, voice satellite or optical UDF/MMBD. The next stage is bounded design/offline static analysis, not an automatic live switch.

## Reproducibility

A standalone read-only local ZIP parser `gazelle_fel_stage13_analyze_capture.py` produced the accompanying Markdown and JSON: it requires one P7 and one P8 capture, three checkpoints, 19 parsed ports per checkpoint, actual process FD, VFM provider counters and frame/hardware-error counters. Output marker `GAZELLE_FEL_STAGE13_CAPTURE_ANALYSIS_PASS`. Parser, report and structured data can be retained privately; this document includes the grounded findings without uploading raw captures.
