# P1 / exact Fire OS source boundary: original per-instance mode writers

**25 October 2026 — read-only, original-owner OEM binaries; no device action.**

This is a narrow, reproducible **original binary** check of the first Android mismatch named in [the master plan](GAZELLE_FEL_ANDROID_MASTER_PLAN.md). Do not replace or copy original vendor binaries to the public Kodi fork; the new script accepts owner-private ELF paths only and refuses any unpinned version.

## Evidence from the real native binaries

Owner-original SHA-256 pins:

- `libOmxVideo.so`: `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`.
- `libomx_framework_alt.so`: `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`.

The audit parses **every directly encoded store to the relevant byte offsets**, using ARM Thumb disassembly plus exact function-symbol ranges. It checked **19** stores overlapping native decoder `+0xdc/+0xdd` and **7** stores overlapping framework `+0x109/+0x10a` (including halfword/word stores). Some matches refer to the *separate encoder*, not the active HEVC decoder; they must not be treated as decoder-mode writers. The static scan does **not** rule out indirect writes via pointers, code from other libraries, or side effects of callees; byte offsets are object-relative and their meaning depends on the function.

The important verified, linked path is:

1. Framework `OmxVideoDecoder` constructor populates owner `+0x109` / `+0x10a` under its own profile/property/component-specific conditions.
2. Native `AmlogicVideoDecoderAwesome::setUp()` at `0x2612a..0x26138`, and `Awesome2::setUp()` at `0x3d790..0x3d7a0`, copy those framework bytes into native decoder `+0xdc` / `+0xdd`.
3. Native `AmlogicVideoDecoder::intitalizeCodec` at `0x1efb6..0x1efd2` resolves the two flags and stores its selected input mode to `codec_para_t+0x10a0`. The original Fire OS runtime captured **frame** `/dev/amstream_dves_hevc_frame`, with `dveldec(0)`, not proven FEL.
4. The one directly mapped `OmxVideoDecoder::setParameter` store overlapping these framework flags at `0x1a1e0` is a **zero-valued halfword store** from `r8`, which is set to zero in the corresponding original `0x19e66` block; the path is gated by the existing `media.support.mvc` property according to earlier original-source tracing. It is **not** a positive per-FEL stream-mode setter.
5. The other native direct writes occur during setup/construction, stop/teardown, encoder handling or **late** `doCodecSpec` (which is not equivalent to isolated pre-init mode selection). No direct named `setParameter` mode-enabling store was identified in this bounded map.

## Decision: do not build a mere alias forwarding shim

Merely adding the research codec alias to `MediaCodecList` and forwarding its `makeComponentInstance` to the existing OEM `OMX_GetHandle("OMX.amlogic.dolby-vision.dvhe.decoder")` would reproduce the constructor/init choices of the **stock** decoder unless an **additional, proven component-private early selector** is implemented. It would not by itself create a secondary EL decoder or preserve Android `/dev/video30` output in stream mode. The current optional research plugin **refuses all component creation** and must remain non-deployable.

The next implementation is **not another packet/seek model**. Prioritise either:

- **A:** find and verify a component-local pre-init control that genuinely affects native `+0xdc/+0xdd` or `codec_para_t+0x10a0` without global properties, late reset or kernel/VFM writes; demonstrate correct OEM call/lifetime and the guarded FEL-only identity before use. No such positive write is proven yet.
- **B:** if A cannot be established, build a *separate*, version-pinned native decoder adapter that owns the Fire OS stream-mode codec, master/slave VDEC, V4L/Surface buffer lifetimes and protected/nonprotected separation. CoreELEC's native setup is a reference, not an Android ABI.

R0 independent preboot rollback is still unresolved. The master plan's P2–P5 gates (safe loader, authentic FEL-sensitive output, then Kodi/add-on/Magisk packaging) do not change. **Do not enable FEL, install an alias/XML/Magisk plugin, restart OMX or write global flags.**

## Reproduce on separately retained private originals

```
python3 tools/gazelle-fel/audit-fireos-original-mode-writers.py --selftest
python3 tools/gazelle-fel/audit-fireos-original-mode-writers.py \
  --video /PRIVATE/libOmxVideo.so \
  --framework /PRIVATE/libomx_framework_alt.so \
  --report /PRIVATE/NEW-local-report.json
```

Requires `llvm-objdump` with ARM Thumb support and `readelf`. Refuses SHA mismatch, unexpected direct stores, method-owner mismatch and report overwrite. No secret firmware bytes or device data is included in the source or this report. GitHub CI exercises the **synthetic selftest only**, not original binaries; the exact-original verification above was independently executed locally on the two hash-matching recovered owner ELFs.