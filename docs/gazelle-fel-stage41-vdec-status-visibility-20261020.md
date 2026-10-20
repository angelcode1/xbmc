# Gazelle FEL Stage 41 — original read-only vdec status enumeration and visible-instance comparison

**2026-10-20. Owner-uploaded Stage40 result PASSED; original Stage41 static kernel status audit PASSED. Live Stage41 P8/P7 capture NOT YET RUN.** Proprietary ELF binaries remain local and are not committed.

## Stage 40 checkpoint and constraints

Owner `stage40-audit-results.txt` passed both original modules, **72 original ARM64 instruction checks and 13 call relocations**, and independently proved the original frame port `amstream_dves_hevc_frame` (initial `0x1d11`) bypasses normal secondary `vdec_create` even with DUALDEC, whereas stream port `amstream_dves_hevc` (initial `0x1911`) attempts a second `vdec_create`, checks its pointer and fails open with `-ENOMEM` if null. These findings do **not** establish safe stream-mode switching or running EL reconstruction. Stage 38 measured P8 DOVI/P7 HDR10 with `dvbldec(1)`, `dveldec(0)`, and earlier owner P7 FD evidence identified the **frame** device.

## New original-module read-only status evidence

The owner original kernel archive `gazelle-fel-kernel-readonly-20261019-191050.zip`, SHA-256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`, contains `decoder_common.ko` SHA-256 `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`.

The `class_attr_vdec_status` object is at original `.data+0x3c8`, size 32. The original bytes contain sysfs mode `0x124` = **octal 0444**, and `R_AARCH64_ABS64` relocations identify the original `vdec_status` name and `vdec_status_show` at `0x8be0` (size 868). This establishes the **read-only** existing status interface `/sys/class/vdec/vdec_status`, assuming normal class registration.

Original `vdec_status_show` has a distinct global-list traversal at `0x8c18–0x8c54` and `0x8e58–0x8e78`, with a state filter at `0x8e68–0x8e74` and an optional per-instance status callback at `0x8ea0–0x8eb8`. The original format at `.rodata+0x28f6` is `vdec channel %u statistics:\n`. Unlike prior Stage28's coarse `no_vdec/nonempty` classification, these **status record headers** can be counted without retaining raw kernel text or identifying pointers.

**Critical limitation:** the show routine selects reportable decoder entries using state and callback availability. Thus, **one visible status record does not prove that only one vdec was allocated**, and a distinct pair of records is positive evidence for two *reportable* entries, not proof of an EL master/slave relationship. No pointer identity `vdec_s.master`/`slave` and no residual pixels are exposed by this bounded status check.

## Stage 41 verifier and optional privacy-reduced capture

`tools/gazelle-fel/stage41-instance-status.py` has three modes:

- `--selftest`: synthetic status-header, ambiguity, port-type and source-format checks;
- `--audit ORIGINAL_KERNEL_ZIP`: SHA-pin original archive and ELF, validate two exact symbol identities, sysfs name and mode, status format, 25 addressed AArch64 instructions and five expected relocations. Marker `GAZELLE_FEL_STAGE41_ORIGINAL_STATUS_OFFLINE_PASS`. This audit **passed locally** against owner's original private archive.
- `--capture`: **optional**, requires user-controlled idle/P8/P7 playback and authorized ADB. Takes three samples per phase using only the allowlisted existing files `/sys/class/vdec/vdec_status`, `/sys/class/amstream/ports` and `/sys/class/amdolby_vision/src_format`. Each read times out after 12 seconds; raw output stays in memory, is capped and is discarded after extraction. Only counts/channel ordinals, known port types/flags, coarse source class and timestamps are saved.

The bundled `run-stage41-macos.sh` SHA-verifies the exact Git blob of its bundled source, performs the full **offline** audit first, and then asks the owner to press Enter to opt into the live comparison; entering N skips all device access. Output is at `~/Downloads/gazelle-fel-stage41-results/` with `stage41-offline-audit.txt` and, if opted into capture, a **sanitized** `stage41-visible-instances-*.zip`.

Do not upload raw device logs or original Amazon modules. Stage41 uses no setprop, sysfs writes, `logcat -c`, process stop, APK installation, direct ioctl 0x179/0x301, firmware change or decoder-mode toggle.

## Evidence decisions

- If both P8 and P7 display one reportable record, then the visible report count is the same. **A hidden allocated secondary is not excluded** by this status API.
- If P7 displays two or more independently numbered reportable decoder channels, then multiple reportable instances exist in P7's status list; the missing EL metadata path and pixel contribution remain separate.
- If the status endpoint is inaccessible, unreadable or unparseable, report `UNAVAILABLE`/`UNPARSEABLE`; do not substitute a provider count and claim slave allocation.
- If the P7 frame port remains selected, that is consistent with the Stage40 original default no-slave allocation branch, but no branch history has been measured directly.

**Stage42:** interpret this genuinely new status-record signal first. If it fails to expose a distinct linked vdec, review any *other existing non-mutating instance-scoped endpoint* only if grounded in original module source. Avoid invasive instrumentation or speculative native Kodi changes. FEL requires an active EL decoder, valid metadata and independent residual-sensitive pixel output proof.

Working Profile8, HDMI/audio passthrough, PTT satellite, UDF/MMBD, Magisk and integrated Kodi were not modified.
