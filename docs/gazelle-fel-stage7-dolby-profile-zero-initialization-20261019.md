# Gazelle FEL Stage 7: constructor zero-initialization → Dolby setter → native decoder read

Date: 2026-10-19. Static read-only analysis of two user-uploaded SHA-pinned archives: `gazelle-dv-omx-caller-libs-20261019-133457.zip` (5 Stagefright/OMX bridge binaries) and `gazelle-fel-vendor-private.zip` (3 OMX vendor binaries). This report is a **static dataflow analysis**, not an active instance measurement or working FEL implementation.

## Confirmed new link in exact Fire OS PS7702.4965N vendor framework

**Proprietary `libomx_framework_alt.so`** SHA `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`, `OmxComponent::OmxComponent`:

- `0x10ad0`: `vmov.i32 q4,#0` initializes the NEON register to all zeroes.
- `0x10ad4`: `add.w r0,r4,#0x360` points at component object base `+0x360`.
- `0x10ae0`: `vst1.8 {d8,d9},[r0]` clears sixteen bytes covering component offsets `+0x360` through `+0x36f`; thus it **initially zeros the Dolby profile storage at `+0x36c`**.
- `0x10ad8`: `movs r6,#0`; `0x10b0c`: `str.w r6,[r4,#0x370]` independently initializes the adjacent Dolby level to zero.

**Dolby-specific `OmxVideoDecoder::setParameter`** in the same binary:

- `0x18fdc` / `0x18fde`: `movs r0,#1`, `movt r0,#0x7f80` constructs **`0x7f800001`**.
- `0x18fe2`: checks the supplied index against it.
- `0x18ff2`: writes parameter structure offset `+0x0c` to owning component **`+0x36c`**.
- `0x18ffc`: writes `+0x10` to component **`+0x370`**.
- Vendor log string is `SetParameter:OMX_IndexParamVideoDolbyVision: profile:%d, level:%d`.

**Native `libOmxVideo.so`**, SHA `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`:

- `AmlogicVideoDecoder::intitalizeCodec()` at `0x1eb66` loads the owning component pointer through decoder offset `+0x4`.
- `0x1eb6e`: `ldr.w r8,[r2,#0x36c]` reads the very same Dolby profile field during native decoder initialization.
- Other downstream branches use that register (e.g. `0x1ee5c cmp.w r8,#0x400`, documented in Stage 6).

**Twelve of twelve exact instruction checks passed** against the private original binaries. The script checks ELF32/ARM/LSB, SHA256, instruction addresses and operand patterns; it does not execute or patch libraries. Proprietary ELF binaries remain out of public Git.

## New causal hypothesis, correctly bounded

The Dolby profile field begins **zero** on construction. It *can* be populated by a separate OMX Dolby Vision setter and it is *read* by the decoder. But the successful Stage 7 Android-side bridge audit found no direct vendor index `0x7f800001` construction in the five inspected upstream libraries, and the prior P7/P8 captures report no `MediaFormat.profile` key. Neither observation proves the setter was never called; forwarding through generic OMX and other libraries remains possible.

A possible failure is **P7 decoder init using a zero, unsupported, or otherwise incorrect effective Dolby profile**, or a later vendor dual-layer/metadata failure. We **have not measured the P7/P8 runtime field values**, discovered the actual setter caller, or demonstrated a true FEL output. Do not write `owner+0x36c`, inject `OMX_SetParameter`, change media.codec behavior, or force global kernel settings on this evidence.

## Next narrowly scoped engineering gate

1. Determine the actual call origin for vendor OMX Dolby index `0x7f800001` and what profile/level values are delivered for **P7** versus working **P8**. Static analysis of a larger verified caller graph may work. If not, any observational runtime instrumentation needs a separate opt-in, strict scope and rollback/coexistence review.
2. Only then evaluate whether correct per-instance Dolby metadata processing and enhancement-layer decoding can be brought up without compromising the known-good P8 path.
3. Retain requirement for *EL residual-sensitive pixel output proof*, not merely `DV_PROCESS` or a Dolby badge.

No modifications to Kodi binaries, Magisk, Fire OS, user applications, passthrough, PTT satellite, or optical decoder were made.
