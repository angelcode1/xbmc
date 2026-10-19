# Gazelle Fire OS FEL after P7/P8 hardware and kernel comparison (2026-10-19)

## Scope and evidence provenance

**Target:** Amazon Fire TV Cube 3 (Gazelle), T7 POP1-G / A311D2 variant, rooted Fire OS PS7702.4965N, Linux 5.4.125-ab27, Kodi 23.0-ALPHA1. Source base: `android-firetv-unified` at `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

**Own device captures (not stored in Git):** P7 playback and P8 control from `gazelle-fel-apk-test(1).zip` and `gazelle-fel-apk-test(2).zip`, with additional original bitstream, RPU and extracted EL verification. The ZIPs include persistent Kodi logs: always attribute markers to the relevant playback start time, not simply their occurrence in the full log.

**External comparison:** CoreELEC's September 2026 support report for this exact SoC says Cube 3 boots CoreELEC 22 (Amlogic-no) and plays FEL: https://discourse.coreelec.org/t/firetv-3rd-gen-cube-soc-t7-pop1-g-a311d2-variant/59617 . CoreELEC's May 2026 Amlogic-no FEL thread requires a *correct patched Dolby module for its 5.15 stack*: https://discourse.coreelec.org/t/fel-amlogic-no-support/58631 . These reports demonstrate a working *alternate OS/software stack*, **not** working FEL on Amazon Fire OS.

## Established findings

| Boundary | Profile 7 FEL | Profile 8.1 control |
| --- | --- | --- |
| Source | P7; 240 RPU frames report FEL; substantial extracted type-63 enhancement data | P8, no EL by design |
| Kodi source/decoder | `OMX.amlogic.dolby-vision.dvhe.decoder` | Same decoder |
| Android advertised capability | P7 (128) **not** advertised; codec selector filter 0 | P8 (256) advertised; selector filter 256 |
| Kodi native buffers | First 48 access units: 501 EL NALs and 48 RPUs preserved before/after converter; 48/48 exact JNI byte copies | DV activation without EL |
| Kernel | `[0]dv dual layer`; initially HDR=>DV then DV=>HDR; stable HDR10 | Stable DV / `DV_PROCESS` |
| VFM | `dvbldec(1)`, `dveldec(0)` | `dvbldec(1)`, `dveldec(0)` as expected |

The P7 source and Kodi-to-JNI data copy **pass**. Native EL video decode and FEL residual contribution to final pixels have **not** been observed. The same Dolby-labelled decoder handles P8 and P7 differently. Lack of P7 codec advertisement is evidence of a Fire OS vendor-support boundary, not proof of silicon incapability.

## Reuse previous pinned vendor binary work — do not rediscover it

- `docs/gazelle-fel-omx-owner-parameter-trace-2026-10-14.md` identifies `libomx_framework_alt.so` vendor index `0x7f00010d` writing owner fields `+0x20` and `+0x24`. The caller and runtime payload for the P7/P8 sessions are unknown.
- `docs/gazelle-fel-omx-duallayer-xref-2026-10-14.md` documents `libOmxVideo.so`: owner `+0x20 == 0x10` gates appending `dv_duallayer:1;` in one decoder setup path. Another Dolby subclass checks `+0x20 == 0x400` or component subtype. These are **not** equivalent to Kodi's Android capability filter.
- `codec_set_dvmetawithel`, ioctl subcommand `0x179`, exists in that vendor library, but no active-instance call was established. A global `dolby_meta_with_el=0` reading does not reveal an instance-local ioctl state.
- Existing static tools: `tools/gazelle-fel/audit-omx-peer-fields.py` and `audit-duallayer-gate.py`. They are pinned to a particular PS7702 binary SHA; they cannot prove runtime invocation or pixels.
- The P7 Kodi CSD records 797 source extradata bytes and 725 bytes injected into MediaCodec; P8 23 source bytes and zero injected. This likely reflects HEVC VPS/SPS/PPS conversion, but these lengths do not prove a malformed CSD or a missing DV descriptor. Avoid altering CSD speculatively.

## New observational experiment: capture *before* decoder initialization

On macOS (with Kodi stopped, then manually start playback only after logcat is armed):

```bash
bash tools/gazelle-fel/capture-fireos-vendor-onset.sh P8
bash tools/gazelle-fel/capture-fireos-vendor-onset.sh P7
```

The script streams **new** Android main/system events via `adb logcat -T 1` before video starts, captures before/active sysfs decoder states plus kernel logs, and saves Kodi logs. It **does not** clear log buffers, change properties, change sysfs, mount drives, inject ioctls, attach debuggers, change policies, reboot, or install APKs. Root reads use an entire quoted remote `su -c 'cat ...'` argument, avoiding the broken split-command invocation.

**Evaluation:** Compare early OMX/ACodec/MediaCodec config logs at P8 and P7 startup; correlate `[0]dv dual layer`, `parse_metadata`, `dveldec` and Kotlin/Android codec markers by timestamps. A vendor-config message such as `mAmlCodecParam->config=...dv_duallayer:1;` (if printed) would be interesting. Absence of such a line does *not* establish the condition did not execute.

## Next source-level branch only after this evidence

1. Establish **actual runtime owner+0x20 value** for P7 and P8, and which writer sets it. A targeted, opt-in debug build may be considered only with an exact instrumentation point and rollback. No generic `MediaFormat.profile=128` override or `0x7f00010d` guess.
2. Establish whether per-decoder `AMSTREAM_SET_DV_META_WITH_EL (0x179)` is invoked and whether the kernel starts `dveldec` for P7. A missing VFM provider is a strong sign of no EL decode, not the full causal chain.
3. Compare *source-level* CoreELEC 22 T7 V4L2/FEL/updated Dolby module init with Amazon's 5.4.125 stack where source is available. A CoreELEC 5.15 `dovi.ko` binary is **not compatible** with the Fire OS 5.4 module ABI and must not be installed on this Cube.
4. FEL success requires a dedicated EL-residual-sensitive test image or equivalent pixel proof. Dolby Vision output formatting by itself is insufficient; a P7→P8 fallback intentionally discards the residual.
5. If true FEL remains inaccessible under Fire OS, a separately booted CoreELEC 22 USB test could validate the same sample on the same silicon; **do not** flash eMMC/modify boot or change the installed OS during this investigation.

## Change isolation

This research branch changes only a host-side read-only capture script and this document. Preserve P8 DV playback, PTT voice satellite, HDMI passthrough, kernel-UDF optical/MMBD and current Magisk setup. The integrated source branch and the Cube are untouched by these additions.
