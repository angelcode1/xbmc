# Gazelle Stage 12: Dolby HEVC device selection directly gates paired decoder creation

Date: 2026-10-19. Status: **OFFLINE_STATIC_VERIFIED, RUNTIME_FEL_NOT_PROVEN**.

## Original Amazon evidence

Original user-provided `gazelle-fel-kernel-readonly-20261019-191050.zip`, `stream_input.ko` SHA256 `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` (PS7702.4965N, Linux 5.4.125-ab27, ELF64 little-endian AArch64). Proprietary modules remain private, **not** committed.

The module's **`ports[]` static table** is a local symbol in `.data` at offset `0x5f0`, size `1520` bytes: 19 rows of **80 bytes**. The actual `stream_port_s` DWARF defines `type` at member offset **24 (`0x18`)**, and `amstream_open()` constructs `&ports[minor] + 0x18` then reads `[x24]` as the port type at `0x161c`. These independent sources agree.

Resolved each table row's device name via its **`R_AARCH64_ABS64` relocation** in `.rela.data.userdata_mutex` into `.rodata`. The six relevant original initialized port types are:

| Table index | Name | Initial `port->type` | FRAME 0x400 | DUALDEC 0x1000 | Pair creation path |
| ---: | --- | ---: | --- | --- | --- |
| 11 | `amstream_hevc` | `0x0111` | no | no | no, absent debug override |
| 12 | `amstream_hevc_frame` | `0x0d11` | yes | no | skipped |
| 14 | `amstream_dves_avc` | `0x1811` | no | yes | attempted after primary |
| 15 | **`amstream_dves_hevc`** | **`0x1911`** | **no** | **yes** | **attempted after primary** |
| 16 | `amstream_dves_avc_frame` | `0x1c11` | yes | yes | skipped |
| 17 | **`amstream_dves_hevc_frame`** | **`0x1d11`** | **yes** | **yes** | **skipped** |

This is a stronger conclusion than Stage 11's generic `port->type` bit analysis. The *real* Amazon static device table supplies the values and names; they are not inferred from Amlogic examples.

## Branch and exact callsite (same original module)

In `stream_input.ko:amstream_open()` (offset `0x1320`):

- `0x1600–0x1610` confirms a video-type port and calls `vdec_create(port, NULL)`.
- `0x161c` loads `port->type` from the port entry.
- `0x1620`: if bit 10 (`0x400`) is **set**, jump to `0x1654`, skipping second-vdec allocation.
- `0x1628`: if bit 12 (`0x1000`) is **set**, jump to `0x1638`, entering the second decoder allocation.
- Otherwise `0x162c/0x1630` check `vdec_get_debug_flags() & 0x100` as another entrance (do not set this debugging flag).
- `0x163c`: `vdec_create(port, primary)`. `0x1644` stores the returned pointer to `primary->slave`; allocation failure is handled separately.
- All three call targets were independently verified through `R_AARCH64_CALL26` relocations. A second `vdec_create` call **attempt** is not guaranteed success, connection, decoded EL or pixel residual reconstruction.

The `stream_port_s` public definitions were also independently cross-checked with a pinned A311D2 header:
`PORT_TYPE_FRAME 0x400`, `PORT_TYPE_DECODER_SCHED 0x800`, `PORT_TYPE_DUALDEC 0x1000`:
https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/include/linux/amlogic/media/utils/amstream.h

The *header naming* is public independent background; Amazon's exact static types, control-flow and relocations come from the owner's pinned binary.

## End-to-end correlation with Stage 10 and the actual P7 capture

Stage 10 verified `libOmxVideo.so:codec_init()` can open **either** `/dev/amstream_dves_hevc_frame` or `/dev/amstream_dves_hevc`, controlled by the internal mode word. Earlier *active* P7 records show that `media.codec` opened `/dev/amstream_dves_hevc_frame`, and its kernel decoder is `VDEC_TYPE_FRAME_BLOCK` with `dveldec(0)` and HDR10 processing. P8 working playback also uses the frame device, where `dveldec(0)` is normal.

**Mechanistic explanation:** on the original initialized `/dev/amstream_dves_hevc_frame` port, `0x1d11 & PORT_TYPE_FRAME` is set, so `amstream_open()` takes the branch that **does not allocate a slave**; `0x1911` on the stream device lacks `PORT_TYPE_FRAME` and includes `PORT_TYPE_DUALDEC`, causing an attempt at a second `vdec_create(port, primary)` on the ordinary successful video-open path.

**Boundaries:** the table describes ELF **initial** port types, not a live `port->type` memory sample. `amstream_open()` can mutate the type flags in some conditions (for example `0x142c` ORs `0x1000`). Other live kernel code may modify type fields. Thus this is a verified expected cause for the observed frame-path pairing absence, **not** an in-memory measurement proving the actual branch history on the Cube.

CoreELEC's FEL pipeline selects stream mode and separately enables FEL/MEL and appropriate decoder policy; that code is not directly portable to Fire OS. In particular, **stream device selection is necessary for the default paired allocation branch, but not sufficient for actual FEL**. The Dolby metadata `0x179` ioctl, HEVC EL readiness, configuration strings, stream parser, and residual-sensitive pixel output remain unproven on Fire OS.

## Offline audit

New source-only script `tools/gazelle-fel/audit-stage12-port-pair.py` validates:

- exact module SHA and ELF64-AArch64 header,
- local `ports` symbol at `.data+0x5f0` of size 19×80,
- 19 name relocations resolving into `.rodata`,
- six original HEVC/AVC, DV/non-DV, stream/frame `port->type` values,
- 11 exact ARM64 branch instructions and three `vdec_create`/`vdec_get_debug_flags` relocations,
- and both resulting branches.

An independent local audit on the original module returned **`GAZELLE_FEL_STAGE12_PORT_PAIR_AUDIT_PASS`**. Full proprietary-binary checks run offline; the GitHub CI `--selftest` only verifies the source's expected mask invariants and syntax.

## Safe next action

Keep current integrated Kodi unchanged. The next *engineering* gate is an **optional, isolated** experiment that can select stream mode specifically for FEL only, with automatic P8/default fallback, decoder teardown cleanup, verification of paired decoder allocation, and a hard abort if the vendor codec errors or the satellite/passthrough HAL is impacted. It **must not** be implemented by setting global `media.omx.stream_mode`, `nal_skip_policy`, `dolby_meta_with_el`, or injecting arbitrary ioctls on the live Cube without an independently reviewed rollback plan.

First, trace any remaining stream-path `codec_init` preconditions and per-decoder Dolby metadata handshake. Require `dveldec` actual active status, genuine Dolby metadata and independent EL-residual-sensitive pixel evidence before declaring true FEL supported.
