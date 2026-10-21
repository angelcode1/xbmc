# Gazelle Fire OS vs CoreELEC — active P7 FEL decoder comparison

**Date:** 21 October 2026. Evidence-only; no codec, sysfs, kernel, Kodi, Magisk or device writes.

**Private capture sources (not committed):**
- `gazelle-native-fel-fireos-20261021-052214.zip` — 116 extracted binary/config files; 12 runtime snapshots; all 116 manifest SHA-256 checks passed.
- `gazelle-native-fel-coreelec-20261021-055202.zip` — 17 extracted files; 12 runtime snapshots; all 17 manifest SHA-256 checks passed.
- CoreELEC phase labels are user-selected, not independently authenticated by collector. Both captured T7 Cube hardware. Fire OS kernel `5.4.125-ab27`, 32-bit Android 9 userspace; CoreELEC `5.15.196`, aarch64 CoreELEC 22 Piers rc1.

## Key empirical result

| Phase | Fire OS `vfm/map` | CoreELEC `vfm/map` |
| --- | --- | --- |
| Idle | `dvbldec(0)`, `dveldec(0)` | `dvbldec(0)`, `dveldec(0)` |
| P8 | `dvbldec(1)`, `dveldec(0)` | `dvbldec(1)`, `dveldec(0)` |
| P7 FEL | `dvbldec(1)`, **`dveldec(0)`** | **`dvbldec(1)`, `dveldec(1)`** |
| After P7 seek | `dveldec(0)` | **`dveldec(1)`** |

### Stronger independent evidence from `/sys/class/vdec/vdec_status`

CoreELEC P7 creates **two amvdec_h265 channels**:
- **BL channel 0:** 3840 × 2160, 24 fps, frames 166 → 215 → 263 for the three P7 snapshots.
- **EL channel 1:** 1920 × 1080, 24 fps, **the same 166 → 215 → 263 frame counts**.
- Following a seek: both channels read 127 → 176 → 225. Each phase reports 0 dropped frames. The P7 status does show `fra err count: 2` / `hw err count: 2`, which did not increase across the three sampled snapshots.
- Dolby source during CoreELEC P7: `DV FORMAT_DOVI`; mapped Dolby instance `fmt DV,3840x2160`.

Fire OS P7 instead has **one** `amvdec_h265` channel, with frames increasing 77 → 158 → 239, and `HDR10 FORMAT_HDR10`, while the P8 phase advertises DV. The Fire OS P7 output route is `dvblpath { dvbldec(1) v4lvideo.0 }`, unlike CoreELEC's `dvblpath { dvbldec(1) amlvideo(1) deinterlace(1) amvideo }`. This distinguishes the actual handoff/render pipeline, not just a sysfs name.

**Caveat:** Two active hardware channels and correctly reported DV source are compelling evidence of native P7 BL/EL decoding, especially in a CoreELEC install where the user confirms FEL works. They are not in themselves a residual-sensitive pixel comparison, and no direct video pixels were captured.

### Important negative finding about a tempting control

`/sys/module/amvdec_h265/parameters/dolby_meta_with_el` remains **0 in both environments**, including working CoreELEC P7 with two active decoder channels. It is therefore **not a valid diagnostic switch for FEL activation** and must not be blindly set. The exported `codec_set_dvmetawithel` in Fire OS `libOmxVideo.so` is a *per-decoder ioctl wrapper*; its presence is not evidence that the particular Kodi P7 session invokes it.

### Fire OS static candidate capability

The captured Fire OS `stream_input.ko` / `decoder_common.ko` / `amvdec_h265.ko` still contain the native dual-decoder and enhancement references identified in the preceding reverse-engineering report. `libOmxVideo.so` is a 32-bit ARM ELF with exported `codec_set_dvmetawithel`, dedicated Amlogic Dolby Vision decoder classes, and strings `dv_duallayer:1;` plus Dolby decoder component names. `/vendor/etc/media_codecs.xml` advertises `OMX.amlogic.dolby-vision.dvhe.decoder` with 3840x2160 capability; **the advertised component does not prove Profile7 FEL support**. The source path by which Kodi creates or configures a dual-layer native decoder has not been demonstrated.

### Architectural portability limit

CoreELEC uses the newer `dovi_gen_5_15_2026` Dolby module on Linux 5.15.196 and direct `amlvideo` output path; Fire OS uses `dovi_vs12` on Linux 5.4.125 and Android `v4lvideo.0` / OMX handoff. CoreELEC's loaded `.ko` payloads were **not collected** because the collector found no files under its configured module roots, so ABI/binary compatibility has not been demonstrated. Copying CoreELEC's `dovi.ko` to Fire OS is not a legitimate quick fix.

## Engineering decision and single next gate

**Conditional GO for one narrowly scoped Fire OS OMX/native initialization audit.** The kernel appears to contain a secondary decoder constructor, but the observed Android P7 playback does not create channel 1 and does not classify the output as DV.

Before any runtime patch, establish **exactly**:
1. Which actual OMX decoder class handles Fire OS's P7 stream and whether it sees P7 dual-layer identification/extradata.
2. Whether it prepares an `amstream` dual-layer request (`dv_duallayer:1;` / equivalent flags) and/or opens the paired decoder node.
3. Whether it submits the RPU/EL and selects the Dolby Vision path before/at decoder creation (Fire OS P7 currently reports HDR10).
4. How this path intersects `v4lvideo.0` versus CoreELEC's `amlvideo` path, and whether a second native channel can coexist safely with current Fire OS vendor services.

**NO-GO** for manual ioctl pokes, module swaps, sysfs forcing, global OMX or `dovi` changes and installed Kodi patches on the current evidence. If a feasible initialization path cannot be traced, stop the native Fire OS option and classify a port as major kernel/codec work. Preserve known-working P8, HDMI passthrough, satellite, UDF/MMBD and Magisk.
