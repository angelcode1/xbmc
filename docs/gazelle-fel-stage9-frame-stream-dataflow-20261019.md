# Gazelle Stage 9 — Fire OS OMX frame/stream decoding dataflow (2026-10-19)

## Scope, pinned evidence, and safety

Offline static ARM32 Thumb disassembly of the **original** vendor libraries supplied by the device owner:
- `libomx_framework_alt.so` SHA256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`
- `libOmxVideo.so` SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`
- `libOmxBase.so` SHA256 `7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee`

Also cross-checked the prior *active, non-stale* `gazelle-fel-onset.zip` P7/P8 captured kernel and Android logs from the installed `android-firetv-unified` Kodi. No device changes, process tracing, system-property writes, module loading or native binary patching. Vendor binaries remain **out of public Git**.

## 1. Framework constructor: three mode-related component fields are distinct

In `libomx_framework_alt.so`, `OmxVideoDecoder::OmxVideoDecoder()`:

| Field | Static code / role |
| --- | --- |
| owner `+0x109` | Initially zeroed by an unaligned 32-bit store at `0x163d4`; multidecoder-capability/configuration decisions can set it at `0x16572` and clear it at `0x16780` |
| owner `+0x10a` | Set to `1` at `0x16832–0x16834` in one multi-decoder supported branch; subsequently cleared at `0x16886–0x16888` when the `media.omx.stream_mode` property is interpreted as enabling stream mode |
| owner `+0x10b` | The **separate** `vendor.media.omx.use_dv_frame` property is looked up at `0x16632–0x1663a` and written to this field at `0x16650`; it is **not** the same field as owner `+0x10a` |
| owner `+0x10c` | Separately set via `vdec_common`/no-single-mode path at `0x1668c`; not established as an EL decoder enable |

The resolved PC-relative property-string references use exact binary VAs: `vendor.media.omx.use_dv_frame` `0x28204`, `media.omx.stream_mode` `0x28372`. String xrefs establish configuration *reads*, not the values that the active P7/P8 sessions received.

## 2. Direct handoff to Amlogic decoder

In `libOmxVideo.so`, `AmlogicVideoDecoderAwesome::setUp()`:

- `0x2612c` loads **owner+0x109**; `0x26130` writes decoder **+0xdc**.
- `0x26134` loads **owner+0x10a**; `0x26138` writes decoder **+0xdd**.
- `0x263f8` reads decoder `+0xdd`, and `0x26402` copies that byte into `mAmvideoDev+0x18`. Nearby format strings are `mAmvideoDev->use_frame_mode=%d` and `mAmvideoDev->use_frame_mode=%d, mUseFrameMode=%d`.

This confirms a **framework-to-Amlogic-to-amvideo frame-mode flag path**. It does not prove which value was used in a live P7 or P8 run: the existing Android log shows the `AmlogicVideoDecoderAwesome` tag, but does not include the associated mode-value log at the captured verbosity.

## 3. Another property fallback in AmlogicVideoDecoder::intitalizeCodec()

The same pinned `libOmxVideo.so` contains a separate mode-decision sequence:

- `0x1ef7a`: checks decoder flag `+0xdc` before property-dependent handling.
- `0x1ef80/0x1ef84`: PC-relative `vendor.media.omx.stream_mode` property reference, string VA `0x6a1fb`.
- `0x1ef8c/0x1ef90`: fallback `media.omx.stream_mode` property reference, string VA `0x6a218`.
- When the control flow allows and neither property reports enabled, `0x1ef98–0x1ef9a` sets decoder flag `+0xdd` to `1`.
- `0x1efb6–0x1efd2` selects one of three *numeric* codec input-mode values by consulting `+0xdd` and `+0xdc`: `1` if `+0xdd` set, otherwise `2` if `+0xdc` set, otherwise `0`. Store location uses codec parameter pointer plus offset `0x10a0`.
- **These numeric values have not been mapped to authoritative named enum constants in this exact binary.** Do not label them `STREAM_TYPE_FRAME` or `STREAM_TYPE_STREAM` solely from the integers without another independent ABI reference.

This is a related but distinct internal path from `AmlogicVideoDecoderAwesome::setUp()`; runtime selection/inheritance of the active named OMX component is still not completely traced.

## 4. Reality check against device captures

- Both P8 (working native DV) and P7 (falling back to HDR10) initialize the **same** `OMX.amlogic.dolby-vision.dvhe.decoder` and the kernel reports `VDEC_TYPE_FRAME_BLOCK`, format 11.
- P7 kernel additionally reports `[0]dv dual layer`, but never activates `dveldec` in the active VFM snapshot and parses output as HDR10.
- P7 Kodi-to-MediaCodec 48/48 input copies preserve typed BL, EL and RPU units; that is **not** EL reconstruction proof.
- Earlier captures noted `vendor.media.omx.use_dv_frame=true`, while stream-mode properties were not populated. This observation **does not prove** a particular OMX owner or decoder mode byte without direct logging.
- Working CoreELEC 22's `AMLCodec.cpp` uses a coordinated `STREAM_TYPE_STREAM`, NAL skip policy and `dv_debug enable_fel / enable_mel` lifecycle. Its kernel 5.15 implementation **cannot** be transplanted to Amazon Fire OS 5.4 by setting one property.

## Offline verification

Twenty-two addressed Thumb instruction/operand checks passed using LLVM 17 on the pinned 2 vendor ELFs for the new constructor flags, property reader, Awesome mode handoff and alternate mode-selection block. The isolated research-branch `tools/gazelle-fel/audit-fireos-profile-boundary.py` now incorporates these windows and instruction checks together with Stage 6–8 evidence.

**Highest-value next question:** whether the *actual P7* decoder selects a different instance configuration or requires additional EL allocation/metadata transfer within the V4L2/OMX/Dolby driver path. There is **no evidence that toggling `media.omx.stream_mode` alone enables FEL**.

## Safety

Do not set or clear the stream-mode properties, change `nal_skip_policy`/`dolby_meta_with_el`, write Dolby DRM/sysfs gates, inject `AMSTREAM_SET_DV_META_WITH_EL (0x179)`, hot-patch `media.codec`, or substitute a CoreELEC module as an experiment based only on this static analysis. Preserve the working P8, PTT satellite, passthrough, kernel-UDF and optical MMBD paths.
