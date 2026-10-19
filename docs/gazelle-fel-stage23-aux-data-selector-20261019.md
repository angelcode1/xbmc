# Gazelle FEL Stage 23 — HEVC auxiliary-data selector

**2026-10-19.** Original Fire OS PS7702.4965N kernel **offline SHA-pinned static verification PASS**. Profile 7 FEL pixel reconstruction remains **NOT PROVEN**. No device operations or configuration changes.

## Original inputs (remain private)

- `amvdec_h265.ko`: `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`
- `decoder_common.ko`: `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`
- `stream_input.ko`: `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c`

## Proven code path

`dolby_get_meta` (0xdc10) reaches `set_aux_data` (0xcee0). Original AArch64 relocations at 0xdc88 and 0xdcc0 bind to this local callee.

The **current instance** with `dolby_meta_with_el` or a slave invokes the callee with its own `+0xa28` buffer, `w2=0, w3=0`. Without either condition, when it has a master, it first invokes with the **master's** `+0xa28` buffer using `w2=0,w3=1`, then with its **own** buffer using `w2=0,w3=2`. There is also a conditional unpaired fallback with `w2=1,w3=0`. The callee's destination remains the current HEVC private instance.

At `set_aux_data`, the selector is `w3 & 0xff`; the copied entry's tag is at byte 7 of each eight-byte entry. Tag 0 and 255 are ignored.

| Selector | Accepted entry tags |
| --- | --- |
| 0 | All tags other than 0 and 255 |
| 1 | Tag 1 only |
| 2 | Tags other than 0, 1 and 255 |
| Other | No eligible tagged entries |

Both the sizing prepass (0xd08c–0xd0b8) and copying path (0xd144–0xd1f0) use this partition. The current instance's resulting auxiliary buffer is assembled by allocating, optionally retaining previous content via `memcpy`, and appending framed selected entries. This is **metadata selection and assembly**, not demonstrated EL pixel composition.

## Guard and failure observations

The callee returns early for a null input (0xcf20), for hardware-readiness predicates involving original `aml_read_dosbus` relocations (0xcf1c and 0xcf2c, address 0x30d6), for an oversized derived entry count (0xcff4–0xcff8), or for zero length/capacity (0xd040–0xd048). `w2` selects different source offsets and size/capacity calculations: its fallback value 1 must not be confused with the tag selector `w3=1`.

The `vzalloc` call at 0xd0cc can fail. That branch (0xd2d4 onward) frees any previous auxiliary pointer and clears the pointer/length (0xd2e8–0xd2f8), rather than preserving a successful merged result. No general memory-safety guarantee follows from these narrow checks.

## What this means for FEL

**New conclusion:** the master/current dual call does not simply forward both unfiltered buffers. It selects **tag-1 entries from the master's buffer** and **other valid tags from the current buffer**. The meaning of these producer tags, the consumer of the assembled auxiliary payload, and real device state are not yet established. Do **not** label the selectors "BL pixel" and "EL residual" based solely on this function.

Current P7 runtime evidence remains frame-mode `/dev/amstream_dves_hevc_frame` and `dveldec(0)`; P8 is working. No active secondary EL decoder or residual contribution has been demonstrated.

## Reproduce

```sh
python3 tools/gazelle-fel/audit-stage23-aux-data.py --selftest
python3 tools/gazelle-fel/audit-stage23-aux-data.py /path/to/private/extracted/modules
```

Offline original-ELF audit verified three hashes, 73 instruction locations/operands, two exact local symbols/sizes, eight relocation targets and synthetic tag-partition checks. Marker: `GAZELLE_FEL_STAGE23_AUX_DATA_OFFLINE_PASS`. GitHub CI exercises only syntax/selftest; proprietary vendor binaries are not committed.

**Stage 24:** trace the producer of tag byte `entry+7` and the downstream consumer of assembled auxiliary records from the private, pinned module. Only after those checks assess whether an existing read-only runtime diagnostic is discriminative. Avoid global `media.omx.stream_mode`, `nal_skip_policy`, `dolby_meta_with_el`, raw ioctls, and speculative Kodi APKs. Preserve P8, audio/HDMI/optical, satellite and Magisk coexistence.
