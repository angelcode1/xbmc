# Gazelle FEL Stage 42 — connected decoder enumeration, distinct from status callback filtering

**2026-10-20. Original owner kernel offline audit PASS. Stage42 live P8/P7 comparison NOT YET PERFORMED.** No Cube configuration, Kodi, Magisk, passthrough, voice satellite or optical-disc changes.

## Stage 41 owner capture: primary input

User-uploaded `stage41-visible-instances-20261020-044914.zip` has SHA-256:

`9428fe2493155755d10dde580a01c0c7ceb9970e483c107b3a85482c89c89fda`

Archive integrity passed, containing one sanitized JSON and one summary TXT. JSON schema `gazelle-fel-stage41-v1`; exactly three samples for each of idle, known-good P8 and P7 FEL. All 27 status/port/source reads returned `OK`. No raw sysfs data or device identifiers were stored. The queries are sequential rather than atomic.

| Evidence | Idle (3/3) | Working P8 (3/3) | P7 FEL test (3/3) |
|---|---|---|---|
| `vdec_status` classification | `NO_VDEC` | `STATUS_RECORDS` | `STATUS_RECORDS` |
| Visible status records | 0 | 1 | 1 |
| Visible channel ordinal | — | 0 | 0 |
| Dolby `inst1` source format | HDR10, stale/idle | **DOVI** | **HDR10** |
| `amstream_dves_hevc_frame` type / flag | `0x1d11` / 267 | `0x1d11` / 267 | `0x1d11` / 267 |
| `amstream_dves_hevc` type / flag | `0x1911` / 0 | `0x1911` / 0 | `0x1911` / 0 |

This is strong consistency evidence that P7 has **no second status-reportable decoder** under the original `vdec_status` output contract, but that API filters by decoder state and optional status-callback availability. One visible record is **not** a conclusive count of all allocated or connected `vdec_s` objects. The frame-port `flag=267` even during idle also demonstrates why the flag must not be interpreted as a unique live playback reference.

## New, independently checked original Amazon kernel interface

Original owner-supplied `gazelle-fel-kernel-readonly-20261019-191050.zip` SHA-256
`02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`, containing private original `decoder_common.ko` SHA-256 `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`.

The original `class_attr_core` object at `.data+0x3a8` is **octal 0444**, and relocations point to the exact `core` literal at `.rodata+0x37ca` and the original `core_show` function at `0x8a44` (412 bytes). This is a separate read-only interface **`/sys/class/vdec/core`** under normal class registration. Original `class_attr_vdec_status` is also 0444, but its routine at `0x8be0` has extra state/optional-callback filters.

`core_show` traverses the original **connected decoder list** under a core lock, with a distinct per-entry format `\tvdec.%d (` (`.rodata+0x1a52`) and an explicit `connected vdec list empty` message. That routine does **not** perform the `vdec_status_show` state/callback filter; thus **it can show connected decoders even when they have no status record**. It does *not* include never-connected, allocated-but-unlinked objects, and it does not prove two entries are BL/EL master/slave merely by count.

The original `core` formatter also prints **raw kernel pointer addresses**. Do **not** manually capture or upload unredacted `/sys/class/vdec/core`. Stage42 stores only the number of structurally recognized per-vdec lines and a parse status, with raw text immediately discarded. Its static offline audit verifies original kernel SHA, four symbols, two sysfs 0444 permissions, original string formats, **32 exact original AArch64 instructions**, and **eight original relocations**. The audit passed against the exact owner module:

`GAZELLE_FEL_STAGE42_ORIGINAL_CORE_OFFLINE_PASS`

The bundled Python source, committed to the branch, matches GitHub blob SHA **`35eea469e25ab015c9f9a286efff6c44a55c40d7`** and raw SHA-256 **`424582bb1ccac54bba507ca14a15bce0866d0abcd37189c30f22af2d1a1b09bd`**. The Mac runner verifies that SHA before execution. Private original binaries are **never** committed.

## Optional live test, separately opt-in

`tools/gazelle-fel/stage42-connected-core.py` and `run-stage42-macos.sh` are source-only and perform an offline original-module audit by default. The Mac runner explicitly asks the owner to type **`YES`** before any live ADB operations; Enter or other responses finish offline only.

If opted in, manually stop Kodi playback, play P8, and then play P7 as prompted. The collector takes three observations per phase via allowlisted read-only endpoints:

- `/sys/class/vdec/core` — connected decoder records, parsed and immediately redacted;
- `/sys/class/vdec/vdec_status` — filtered status record counts;
- `/sys/class/amdolby_vision/src_format` — Dolby DOVI/HDR10/SDR classification;
- `/sys/class/amstream/ports` — just the known two Dolby HEVC port types/flags, included in the sanitized JSON.

No kernel pointers, raw sysfs text, serials, PIDs or filenames are saved in the output ZIP. Reads have 12-second timeouts, a 32 KiB raw output cap, and fail as `UNAVAILABLE`/`OVERSIZE`/`UNPARSEABLE`, not zero records.

### Interpretation limits

- `core=2, vdec_status=1` for P7: *positive evidence of one additional connected vdec object unreported by status*, subject to non-atomic sampling; not proof of EL role, initialized decode or residual pixels.
- `core=1, vdec_status=1` for P7: the two endpoints see one object; **does not exclude an allocated-but-not-connected slave**.
- `core=0` in live video: inconsistent with expectations, or transition/inaccessibility; repeat the read-only control once, do not infer hardware absence.
- unreadable/unparseable `core`: endpoint cannot resolve connected decoder enumeration; leave question unknown.

Do not treat provider names or counts as proof of FEL. Do not change the frame-to-stream data contract, properties, `nal_skip_policy`, metadata 0x179/0x301 ioctls, firmware or Kodi build based on this alone.

## Stage43 decision

Interpret the P8/P7 connected-vs-reportable counts first. If only one connected object appears in P7 while the frame-port evidence stays intact, the leading hypothesis is still that the default FRAME port bypasses linked vdec creation, **not a proven HDR10 root cause**. A future safe FEL-specific native backend would require separate validation of stream buffer layout/PTS, paired decoder initialization, RPU metadata, rollback, and residual-sensitive pixel output. Preserve working P8 and all shared services.
