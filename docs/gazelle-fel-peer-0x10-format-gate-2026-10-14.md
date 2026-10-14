# Gazelle Dolby Vision OMX: HEVC peer-field gate refinement

Date: 2026-10-14. Based on the original vendor ARM32 `libOmxVideo.so`, SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`. Binary remains outside Git.

## New cross-class disassembly: `peer+0x20 == 0x10` is a codec-format discriminator

The prior [bridge audit](gazelle-fel-omx-bridge-audit-2026-10-14.md) identified a test of `[decoder+4]+0x20 == 0x10` before appending `dv_duallayer:1;` in `AmlogicVideoDecoder::setUp()`. **It should not be interpreted as a FEL-specific enable bit.**

An independent selection path in `AmlogicVideoDecoder2::setUp()` corroborates the format interpretation:

| Instruction | Observed action |
| --- | --- |
| `0x3b692` | Load the vendor peer pointer from decoder + 4 |
| `0x3b694` | Load peer field at + 0x20 |
| `0x3b69c` | Compare it to `0x10` |
| `0x3b69e` | Branch to `0x3b734` if equal |
| `0x3b746` | `movs r6, #0xb` — select kernel HEVC VFORMAT 11 |
| `0x3b7c8` | Store selected format from `r6` to decoder at + `0x150` |

This is a direct, checked association between the **peer field value 0x10 and HEVC format 11** in the alternate decoder. Other peer values are handled by other codec branches. It is evidence for a vendor **codec-format / component-mode selector**, not for an RPU `FEL` discriminator. The exact enum name and the active P7 runtime value have not been established.

For the legacy `AmlogicVideoDecoder::setUp()`:

- `0x21a68`: compares internal codec format to HEVC `0x0b`.
- `0x21ac8 / 0x21aca`: compares peer `+0x20` to `0x10`.
- `0x21ad4 / 0x21ada`: resolves and appends `dv_duallayer:1;` to codec config when both checks hold.
- `intitalizeCodec()` at `0x1ec12 / 0x1ec14 / 0x1ec2c` also tests `0x10` before setting flag `0x40` (subject to another independent condition).
- Dolby-specific `doCodecSpec()` tests peer value `0x400` at `0x30958 / 0x3095a`. This is a distinct format/component case, not evidence that 0x10 toggles FEL.

**Inference**: Since the active P8 and P7 sessions instantiate the same named OMX component and HEVC frame decoder, this type selector may be identical for both. The two sessions' exact peer memory values and internal codec strings were **not** captured; this remains a hypothesis rather than a proven runtime observation. Even if `dv_duallayer:1;` is present, no enhancement decoder/provider was active in the previously recorded P7 snapshots.

## Per-decoder metadata wrapper remains unlinked

`codec_set_dvmetawithel` at `0x5a1a0` constructs `AMSTREAM_IOC_SET` / subcommand `0x179`; its presence proves an implementation exists. We have **not** established that it is called for Profile 7 (or for any active playback session). Existing direct-branch and relocation searches are insufficient to rule out indirect invocation or a separate ioctl site.

## Offline verification

Run the pinned read-only checker, which tests the relevant instructions against the binary SHA without changing the file:

```sh
python3 tools/gazelle-fel/audit-duallayer-gate.py /path/to/libOmxVideo.so
# expected: OFFLINE_GATE_PASS
```

A passing result **is not a runtime FEL result**.

## Revised next step

1. Do **not** introduce a speculative `MediaFormat` key or force `dv_duallayer:1;` based on Profile 7 alone.
2. Trace whether the **instance decoder initialization/config** uses the per-decoder metadata/EL control and whether the vendor code has an actual EL decoder setup stage. The missing behavior is distinct from the HEVC format selector.
3. If the vendor path is opaque, establish a safe *observational*, tightly scoped method for capturing the effective codec string or ioctl use. The user’s `firetv-passthrough` module shares the media HAL environment, so no service restart or process injection without a separate opt-in safety plan.
4. Require EL contribution and real FEL reconstruction before describing the feature as implemented.

Earlier runtime controls remain: P8 native DV output, P7 FEL RPU and EL copied to JNI without corruption (48/48), but kernel `FORMAT_HDR10` and EL VFM `dveldec(0)`.

## Later clarification: owning OMX component fields (14 October 2026)

The two-library framework trace resolved the pointer level: `VendorPeerComponent::setOwner()` stores its `OmxVideoDecoder` owner pointer at peer+4, and the Dolby subclass reads the owner's `+0x20` and `+0x3dc` fields through that pointer. The framework writes owner+0x20/+0x24 from vendor parameter index `0x7f00010d` and initializes owner+0x3dc to `0x0b` for `.dvhe`. Thus earlier descriptions of `peer+0x20 == 0x10` as an intrinsic HEVC-format selector were incomplete: this value can originate from an OMX parameter field and is not a proven FEL-specific switch. See [pinned owner/parameter dataflow trace](gazelle-fel-omx-owner-parameter-trace-2026-10-14.md). The actual runtime value remains unknown.
