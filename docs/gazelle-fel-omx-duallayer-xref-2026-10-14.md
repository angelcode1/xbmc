# Confirmed OMX dual-layer configuration reference (2026-10-14)

Source: read-only disassembly of the user's original `/vendor/lib/libOmxVideo.so`, SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`.

## Exact cross reference

- Literal `dv_duallayer:1;` appears in `.rodata` at virtual address `0x6ae9b`.
- A Thumb PC-relative load (`0x21ad4`, followed by `ADD PC` at `0x21ada`) references this exact literal in `android::amlpeer::AmlogicVideoDecoder::setUp()`.
- The enclosing branch at `0x21a62` checks the codec parameter at offset `+0x18` against `0x0b` (corresponding to Amlogic `VFORMAT_HEVC=11` in public headers); the inner check at `0x21ac6` reads `*(component + 4) + 0x20` and compares against `0x10` at `0x21aca`.
- If the tests pass, the following block beginning `0x21ad0` loads the `dv_duallayer:1;` string and appends it to the codec configuration buffer; it also advances the configuration length and formats debug logs using `mAmlCodecParam->config=%s` and `mAmlCodecParam->config_len=%d` literals.
- `0x21acc` branches around the append to `0x21d82` when the component-field check fails.

## Interpretation — what remains unknown

The literal is **referenced by executable code**, not just embedded as unused text. However, the active P7 path may or may not satisfy the `component+0x20==0x10` condition. The October 14 runtime confirms `format: 11` at `vdec_init`, but never exposes that component field or prints the effective codec-config string. In the inspected local block, no RPU `el_type=FEL` classification is evident. Thus `dv_duallayer` may be selected by component type rather than by presence of an enhancement layer.

The separate `codec_set_dvmetawithel()` wrapper (`0x5a1a0`, ioctl subcommand `0x179`) still has no established call site. **Do not equate adding `dv_duallayer` with enabling actual BL/EL reconstruction.** No native dual-layer output has been observed.

## Reproduction

Run on the local copy of the same ARM32 vendor library, with `readelf` and `llvm-objdump` installed:

    python3 tools/gazelle-fel/omx-string-xrefs.py /path/to/libOmxVideo.so --needle 'dv_duallayer:1;'

Expected for the examined SHA:

    STRING VA=0x6ae9b literal=dv_duallayer:1;
    XREF: _ZN7android7amlpeer19AmlogicVideoDecoder5setUpEv: LDR=0x21ad4 ADD_PC=0x21ada STRING=0x6ae9b

To inspect the branch without executing it:

    llvm-objdump -d --triple=thumbv7a-linux-android --start-address=0x21a60 --stop-address=0x21b20 /path/to/libOmxVideo.so

## Follow-up gate

1. Map the component `+0x20` value for the active Dolby decoder; compare P8 and P7 without altering the decoder process.
2. Establish effective configuration string and initialization point before deciding whether a native FEL opt-in can be implemented safely.
3. Identify whether any component actually invokes or reimplements `AMSTREAM_SET_DV_META_WITH_EL (0x179)` on the same decoder instance.
4. Preserve working P8 and require actual enhancement-layer reconstruction proof rather than `FORMAT_DOVI` alone.

The script only identifies direct PC-literal + PC string references. No hit is not evidence of no other reference.

## Stage 2 Kodi-side verification (2026-10-14)

The Kodi branch now emits `GAZELLE_DOVI_CODEC_SELECTED` when a Dolby codec is selected and `GAZELLE_DOVI_MEDIAFORMAT` immediately before calling `MediaCodec.configure()`. These markers record the source Dolby profile, EL-present flag, capability-filter profile, component name, MIME, Surface selection, dimensions and CSD-source length. **The capability-filter profile only controls codec enumeration**; Kodi does not send it as a vendor dual-layer command.

For the first 48 P7 access units, `GAZELLE_P7_INPUT_COPY` computes FNV-1a fingerprints of the processed bytes and the actual copied JNI input buffer after `memcpy()`. `equal=true` rules out a Kodi-side copy corruption for the sampled access unit; it does **not** prove the MediaCodec/OMX service consumes BL/EL/RPU or that native FEL reconstruction occurs. Fingerprints are not cryptographic proofs of equality.

The `component+0x20 == 0x10` check in `AmlogicVideoDecoder::setUp()` is also used by `AmlogicVideoDecoder::intitalizeCodec()` at `0x1ec12` to set the decoder parameter bit `0x40`. The exact semantic name of the vendor component field is **not yet established**; it must not be conflated with `vdec_init format=11`, which is a different field. Thus, the successful HEVC check alone cannot establish that the `dv_duallayer` path runs.

These changes are observational. No global kernel change, vendor ioctl, MediaFormat profile override or new decoder instance has been introduced.
