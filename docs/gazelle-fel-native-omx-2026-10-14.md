# Gazelle / Fire TV Cube 3: Dolby Vision Profile 7 FEL investigation

Last updated: 2026-10-14. Branch: `android-firetv-bluray`. Status: **FEL reconstruction not working on Fire OS**. This page is the current reference; earlier `docs/firetv-android-bluray-notes.md` describes historical Stage 1.

## Platform and test boundary

- Fire TV Cube 3 `AFTGAZL`, Fire OS 7 / Android API 28, ARM32 (`armeabi-v7a`) OMX userspace, ARM64 Linux `5.4.125-ab27` kernel, Amazon build `PS7702.4965N`.
- Kodi uses `OMX.amlogic.dolby-vision.dvhe.decoder` with `MediaCodec (Surface)` enabled. Disabling Surface prevented playback in an earlier attempt and is not a valid control.
- Existing Kodi diagnostics classify RPU Profile 7 FEL and count BL/RPU/EL NAL types before/after BitstreamConverter. Counts are not byte-identical proof or evidence that OMX consumed the EL.
- The P8 and P7 results below were collected in separate runs on 2026-10-14, with six checkpoints per run. Use `tools/gazelle-fel/capture-omx-runtime.sh` to reproduce.

## Controlled P8 versus P7 runtime observation

| Observation | Profile 8.1 control (`DV8_TEST.mp4`) | Profile 7 FEL (`Woman at 80s`) |
| --- | --- | --- |
| Driver source, 6/6 samples | `DV FORMAT_DOVI` | `HDR10 FORMAT_HDR10` |
| Dolby instance | `inst1 mapped 1 valid 1` | `inst1 mapped 1 valid 1` |
| OMX decoder | `OMX.amlogic.dolby-vision.dvhe.decoder` | same |
| Active video FD | `/dev/amstream_dves_hevc_frame` | same |
| BL VFM | `dvbldec(1) v4lvideo.0` | same |
| Video composer VFM | `video_composer.0(1) video_render.0` | same |
| EL VFM | `dveldec(0) dvel` | same (not active) |
| Global `nal_skip_policy` | `2` | `2` |
| Global `dolby_meta_with_el` | `0` | `0` |
| OMX properties | `use_dv_frame=true`, stream-mode properties unset | same |

- P8 first frame at 09:10:00.763; driver classified its metadata `DOVI` at 09:10:00.792.
- P7 first frame at 09:11:32.394; driver parsed `HDR10` and logged `DV=>HDR` at 09:11:32.432. The prior P8 session explains the transition; it does **not** represent a successful P7 DV frame.
- The first **48 paired P7 access units** preserved type-count totals BL=48, RPU=48, EL=549, VPS/SPS/PPS=3 each; invalid=0. RPU classified `el_type=FEL`. EL reconstruction nevertheless remains **unproven**.
- The `video_composer` get count increased in both runs (P8 1387→2532, P7 3792→4909). The earlier idle-route hypothesis that the Cube never uses the composer is disproven by live playback.
- No active `dveldec` provider observed. Absent kernel log strings are not proof that an ioctl was never issued.

## Failed and reverted tests — do not repeat as fixes

- With global `nal_skip_policy=1`, all samples retained `FORMAT_HDR10` under P7. Script restored original policy `2`; this alone does not enable FEL.
- With global `/sys/module/amvdec_h265/parameters/dolby_meta_with_el=1`, three playback attempts showed loading wheels / invalid decoder state. It was restored to `0`. **Do not conflate this global module flag with per-decoder `vdec->dolby_meta_with_el`.**
- Kodi `InstanceGuard locked` occurs on rapid direct sample switching; force-stop/relaunch between controlled trials.
- Known baseline: global metadata flag **0**, NAL skip policy **2**, parser DV enabled **1**, force-bypass **0**. Do not alter global kernel settings or patch in-place vendor binaries based solely on metadata classification.

## Kernel-side evidence (offline analysis of user's firmware archives)

- `stream_input.ko` contains `amstream_ioctl_set()` and handles `AMSTREAM_SET_DV_META_WITH_EL = 0x179`. Dispatch calls `vdec_set_dv_metawithel()`, including the paired decoder if present.
- `decoder_common.ko` defines `vdec_set_dv_metawithel()` and stores the per-decoder boolean; the setter writes to `vdec_s::dolby_meta_with_el` (DWARF offset `0x11db9` in this build).
- `amvdec_h265.ko`'s `dolby_get_meta()` reads that instance field. A **different** global `dolby_meta_with_el` parameter participates in dual-layer decoder-mode decisions.
- `struct am_ioctl_parm` is 16 bytes with data at offset 0, command at offset 8 and reserved bytes at offset 12. Generic ioctl `AMSTREAM_IOC_SET = 0x401053c2`; selector `0x179`. ABI is documented for inspection only; **do not inject it via a separately opened `/proc/PID/fd` path**.
- Modules inspected: `stream_input.ko`, `decoder_common.ko`, `amvdec_h265.ko`, `dovi_vs12.ko`, `firmware.ko`; binaries deliberately not committed.

## Userspace vendor OMX evidence

- `/vendor/lib/libOmxVideo.so`, 721100 bytes, SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`.
- It exports `codec_set_dvmetawithel()` at Thumb address `0x5a1a1`; wrapper builds generic ioctl `0x401053c2` with subcommand `0x179` on decoder FD.
- String `dv_duallayer:1;` exists, and both Dolby decoder stream/frame variants are present. Neither string presence nor wrapper existence proves they are used in P7 initialization.
- No direct in-library call or dynamic relocation to the wrapper was found in the previous static pass. Six mapped companion libraries likewise have no direct dynamic import/relocation to it. Indirect calls, another library, or a direct ioctl remain possible.
- `media.codec` process was PID 680 during the October 14 samples. Session properties `vendor.media.omx.use_dv_frame=true`; other stream-mode properties empty. An earlier baseline used `false` and `1` respectively; these are distinct configurations.

## GPU fallback / djnice comparison

- `djnice/kodi-fel-android` implements BL + HEVC EL decoding, VICP AFBC conversion, GPU FEL prediction/NLQ, and DV display composition for S928X/Dune firmware. It is not a ready-to-load Cube module.
- Gazelle has GE2D/GDC (`CONFIG_AMLOGIC_MEDIA_GE2D=y`, `...GDC=y`), `/dev/ge2d`, `/dev/ion`, `vfm_map_add` and `dmabuf_get_vframe`, but no observed VICP kernel interface. GE2D is **not** an established 10-bit AFBC-to-linear VICP replacement.
- The *active* Cube playback route does use `video_composer.0 → video_render.0`, leaving a possible interception design. Native T7 dual-layer configuration should be investigated first; hardware FEL is not proven available under Amazon's Fire OS.

## Next engineering gates

1. **Read-only disassembly** of `libOmxVideo.so`: find the exact references to `dv_duallayer:1;` in the Dolby decoder initialization path, and reconstruct conditions, buffer modes and timing. See `tools/gazelle-fel/audit-omx-static.sh`.
2. Establish whether the active OMX implementation issues generic ioctl subcommand `0x179` itself or invokes a wrapper indirectly. Examine actual caller chain or make an opt-in, narrowly targeted diagnostic that records configuration **without changing it**.
3. Confirm how the frame-based MediaCodec input is packaged and whether EL NALs pass the OMX boundary unchanged. The existing NAL-type counters are necessary but insufficient.
4. Only after reproducing the missing control, consider a **separately installable and reversible** experimental code path. Preserve P8 control and keep default behaviour unchanged.
5. Require both `FORMAT_DOVI` and independent FEL **pixel reconstruction** evidence (EL provider/counters and/or validated test image). A Dolby output icon alone is insufficient.

## Evidence provenance / offline archive hashes

| Archive (kept outside Git) | SHA256 |
| --- | --- |
| `gazelle-native-fel.zip` | `f38dda62f3f32bcf2c4e48792aa87173f369caa0588e598b2525cff7daf1f505` |
| `gazelle-omx-investigation.zip` | `c447635574390b440d2a99c59564046ab9cef1bffac221cf7f96fddf1f61e1e7` |
| `gazelle-omx-companions-20261014-085629.zip` | `1a17df4414e887cac04a787e8db7de8c1e86d66fdf7a7aa21ec43f83e600b443` |
| `gazelle-omx-runtime-P8_CONTROL-20261014-091036.zip` | `ccdc323a1ffb679a69d683422f2968b5926acb43dde80c3a0ae3277e543b2214` |
| `gazelle-omx-runtime-P7_FEL-20261014-091147.zip` | `d4367c09cdad7a48ead0ee9c7b3f2355fd476a58cea87e3855129e546117dc74` |

Raw logs, test media, and proprietary Amazon firmware libraries/modules are intentionally omitted from Git. These hashes let the observations be correlated with locally preserved evidence.

## Public source comparison (not asserted binary-identical)

- [A311D2 amstream header](https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/include/linux/amlogic/media/utils/amstream.h)
- [Older Amlogic HEVC decoder](https://github.com/McMCCRU/linux-amlogic/blob/3d4ab79ea3638850a736bf2f7f65e55cb47368c4/drivers/amlogic/media/frame_provider/decoder/h265/vh265.c)
- [djnice GPU-composition implementation](https://github.com/djnice/kodi-fel-android)
- [CoreELEC AMLCodec FEL initialization](https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp)

## New static trace (later on 2026-10-14)

The `dv_duallayer:1;` literal is **executably referenced** by `AmlogicVideoDecoder::setUp()` at Thumb `0x21ad4` / `0x21ada`, with a HEVC format `0x0b` and component-field `0x10` gate. It is not merely an unreferenced string. See [exact disassembly findings](gazelle-fel-omx-duallayer-xref-2026-10-14.md) and reproducible offline cross-reference script. Whether the active P7 decoder satisfies the second check or receives a per-decoder `0x179` ioctl remains unknown.

## Bridge-library audit (2026-10-14, 13:15 AEST)

The verified five-library bridge capture confirms the plugin loader (`libstagefrighthw.so`) → OMX core (`libOmxCore.so`) → video decoder (`libOmxVideo.so`) chain and maps the active `OMX.amlogic.dolby-vision.dvhe.decoder` to the registered `video_decoder.dolby-vision` role. It does **not** establish the effective peer `+0x20` value, the `dv_duallayer` config string, or a per-decoder ioctl. [Full source-matched disassembly and next gate](gazelle-fel-omx-bridge-audit-2026-10-14.md). No code or device configuration was changed.

## Peer field reclassification (2026-10-14, offline disassembly)

A later cross-class instruction trace demonstrates that the alternate decoder maps peer field `+0x20 == 0x10` to HEVC format `0x0b` and stores that selection in its codec-format field. The legacy decoder's `dv_duallayer:1;` append is gated by that same peer value and HEVC format. This is **not a demonstrated FEL toggle**. Review the [peer gate and instruction evidence](gazelle-fel-peer-0x10-format-gate-2026-10-14.md) and [read-only binary verification tool](../tools/gazelle-fel/audit-duallayer-gate.py). Effective per-instance configuration, `0x179` invocation and EL decoding remain unknown; do not use this field as grounds to alter kernel or vendor settings.

## Later clarification: owning OMX component fields (14 October 2026)

The two-library framework trace resolved the pointer level: `VendorPeerComponent::setOwner()` stores its `OmxVideoDecoder` owner pointer at peer+4, and the Dolby subclass reads the owner's `+0x20` and `+0x3dc` fields through that pointer. The framework writes owner+0x20/+0x24 from vendor parameter index `0x7f00010d` and initializes owner+0x3dc to `0x0b` for `.dvhe`. Thus earlier descriptions of `peer+0x20 == 0x10` as an intrinsic HEVC-format selector were incomplete: this value can originate from an OMX parameter field and is not a proven FEL-specific switch. See [pinned owner/parameter dataflow trace](gazelle-fel-omx-owner-parameter-trace-2026-10-14.md). The actual runtime value remains unknown.

## Android Stagefright parameter boundary (2026-10-14)

The three pinned Android 9 Stagefright libraries have been audited separately from the vendor OMX implementation. The OMX service provides generic `setParameter` forwarding and its plugin loader tries both `libstagefrighthw.so` and optional `libstagefrightdolby.so`. The captured active `media.codec` map has the hardware plugin but no Dolby plugin mapping; working P8 Dolby output in this environment makes that absence non-diagnostic for P7. No direct 32-bit literal `0x7f00010d` was found in these three Stagefright binaries, but this does not exclude computed indices or forwarding from other code. [Report](gazelle-fel-stagefright-parameter-boundary-2026-10-14.md) and [pinned read-only verifier](../tools/gazelle-fel/audit-stagefright-omx.py). Neither establishes live OMX values or FEL EL output.
