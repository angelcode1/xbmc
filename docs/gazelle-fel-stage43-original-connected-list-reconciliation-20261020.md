# Gazelle FEL Stage 43 — P7 connected-list evidence reconciled with original pair-connection code

**2026-10-20. ORIGINAL OWNER ELF AND STAGE42 SANITIZED CAPTURE: OFFLINE PASS.** No new device actions. True P7 FEL residual pixel reconstruction **NOT PROVEN**.

## Original user capture (not an inferred hardware state)

The owner-supplied `stage42-connected-decoder-20261020-064046.zip` passed full ZIP CRC and SHA-256 pin:

`ca99ef1dd6dd1f564f5aaa166f3e83acb3d80df635bc0b735d361d5e3c7dbdb7`

The `gazelle-fel-stage42-v1` JSON reports `device_writes=false`, `raw_kernel_addresses_retained=false`, and exactly three consistent read-only samples per phase.

| Phase | Connected entries in `/sys/class/vdec/core` | Reportable entries in `/sys/class/vdec/vdec_status` | Dolby inst1 source |
|---|---:|---:|---|
| Idle | 0 ×3 | 0 ×3 | HDR10, stale/idle |
| Working P8 | 1 ×3 | 1 ×3 | DOVI |
| P7 FEL | **1 ×3** | **1 ×3** | **HDR10** |

All core/status/source/port reads returned `OK` in all nine samples. The owner-reported initialized Dolby HEVC port types stayed `0x1911` (stream) and `0x1d11` (frame), but the port flags are not an independently atomic FD owner/branch history observation. Prior owner process-FD captures already identified P7 playback on the frame device.

**New precise observation:** P7 has **no additional connected vdec object** listed in these samples. P8 also has exactly one. Stage42's connected list is a distinct, broader source from the Stage41 status callback list; Stage43 now ties it directly to the compiled pairing code.

## Original Amazon driver code verified offline

Owner original Fire OS PS7702.4965N archive `gazelle-fel-kernel-readonly-20261019-191050.zip` SHA-256:

`02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`

| Private original ELF | SHA-256 |
|---|---|
| `decoder_common.ko` | `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b` |
| `stream_input.ko` | `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` |

`tools/gazelle-fel/audit-stage43-connected-pair.py` verifies **33 exact AArch64 instructions**, **9 original ELF relocations**, and 3 exact function identities, with SHA-pinned original modules and the private owner archive, plus the actual sanitized Stage42 capture. Final marker `GAZELLE_FEL_STAGE43_OFFLINE_PASS`. Vendor ELF bytes are never committed.

### Exact connection/list relationship

1. `stream_input.ko:amstream_port_init` only calls `vdec_connect(primary)` at `0x20e8` after independent conditional port/vdec flags at `0x20d8–0x20e4`. Original `R_AARCH64_CALL26` identifies the callee `vdec_connect`.
2. `decoder_common.ko:vdec_connect` (`0x2688`, 308 B) checks the primary state (`0x26a8–0x26b0`), reads `primary->slave` at `+0x40` (`0x26d8`), and if present prepares separate waitqueue/state for the slave.
3. `0x2724–0x274c` attempts to insert the primary's linked-list node (`primary+0x8`), guarded by `__list_add_valid` at `0x273c`.
4. `0x2750–0x2780` explicitly checks `primary->slave`; if nonnull it attempts to insert `slave+0x8` into the **same list**, subject to its own `__list_add_valid` result at `0x2770`. A rejected list insertion is not equivalent to an absent allocated decoder; this caveat is essential.
5. The list-head pointer at `decoder_common:0x2710/0x2714/0x2758` and `core_show:0x8a70/0x8a74` is exactly the same original `vdec_core.llvm.7425214269774233008` symbol, relocation addend 0. `core_show` loops over its linked entries at `0x8aac–0x8b14`.

**Conclusion:** Under normal successful list insertion, a simultaneously connected primary/slave vdec pair would contribute **two connected-list entries**, even if the secondary lacks a status callback. The live P7 Stage42 connected-list count is one in all three samples. Thus **a second connected vdec was not observed during that P7 playback**. This is stronger than missing `dveldec` in VFM and stronger than one reportable channel in Stage41.

### Limits that remain

- A secondary vdec may have been **allocated but not connected**; list insertion can also be rejected under exceptional conditions.
- Status reads are sequential, so no single capture is an atomic decoder-lifetime snapshot.
- The P7 source showing HDR10 cannot, alone, tell us whether the true first failure was BL/EL parser routing, stream/frame mode choice, metadata option rejection, decoder configuration, or Dolby processing.
- A connected EL object would still be far from sufficient to prove EL frame decoding, correct RPU processing or **residual-sensitive visible FEL pixels**.
- Do not force `dv_toggle_prov_name`, global stream mode, `negative_dv`, `dv_duallayer`, kernel `0x179/0x301` ioctls or unvalidated Kodi HAL/OMX patches.

## Reproducibility

The Stage43 macOS ZIP includes the exact GitHub source `tools/gazelle-fel/audit-stage43-connected-pair.py` (Git blob `9f2554616c77f5a01a3a622fe8ecfcfdfe86650f`, SHA-256 `d348e953fac3252df2459bfed0684162c6cefb71a75c6dd93579c5511b299990`) and a runner verifying the source SHA before it operates. It reads only the owner kernel ZIP and the sanitized Stage42 ZIP in `~/Downloads`. It **does not connect to the Cube**. It writes only `~/Downloads/gazelle-fel-stage43-results/stage43-audit-results.txt`.

CI can run syntax/selftest/source safety; only the owner-original offline environment can run the ELF/capture audit. Locally both passed.

## Stage 44 engineering decision

The existing-frame-path P7 lacks a second connected vdec. **Do not request another unchanged idle/P8/P7 status sweep.** The next useful development work is an **offline native-interface contract and failure/rollback review** answering:

1. How the proprietary Amazon `libOmxVideo.so` chooses the **per-instance** stream vs frame device, with format/decoder ownership and buffer/PTS contract.
2. Whether Kodi and the OEM OMX backend can select that path **for a P7 FEL test only**, without changing P8, system properties, or other audio/voice/HDMI/optical workloads.
3. Which original kernel pair-connect/metadata steps must succeed before a test can proceed, and which existing read-only gates prove a safe rollback.
4. What controlled BL-only vs FEL-residual-sensitive oracle can independently establish actual pixel reconstruction.

If those gates cannot be established from private original code, **stop at design review** rather than implementing or installing a speculative backend. Preserve working Profile8, Kodi, Magisk, HDMI passthrough, voice satellite and UDF/MMBD.
