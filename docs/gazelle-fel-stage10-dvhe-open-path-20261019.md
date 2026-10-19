# Gazelle FEL Stage 10 — active Dolby HEVC class and frame/stream device routing

Date: 2026-10-19. Original exact user-provided Amazon PS7702.4965N `/vendor/lib/libOmxVideo.so` SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`. Analysis used ARM/Thumb `llvm-objdump`, ELF sections and `readelf -rW` PLT/GOT symbol relocations. All steps **offline**, no device changes, no proprietary binaries committed.

## Result 1: named Dolby class is a conditional AV1/Awesome wrapper

The vendor registers `OMX.amlogic.dolby-vision.dvhe.decoder` (source-matched factory registration documented in `gazelle-fel-omx-bridge-audit-2026-10-14.md`). `AmlogicVideoDecoderDolbyVision` has an actual C++ constructor `0x308ac`, `doCodecSpec` `0x30948`, and `prepareEsData` `0x309b2`. Each call target was **independently resolved through ARM veneers -> PLT -> GOT -> R_ARM_JUMP_SLOT**, not guessed from an objdump symbol's nearest name.

| Native callsite | Resolved symbol |
| --- | --- |
| `0x308b0` via `0x66b24` | `AmlogicVideoDecoderAv1::AmlogicVideoDecoderAv1()` |
| `0x30986` via `0x66b44` | `AmlogicVideoDecoderAv1::doCodecSpec()` |
| `0x309a4` via `0x66b54` | `AmlogicVideoDecoderAwesome::doCodecSpec()` |
| `0x309ce` via `0x66b64` | `AmlogicVideoDecoderAv1::prepareEsData()` |
| `0x309d2` via `0x66b74` | `AmlogicVideoDecoderAwesome::prepareEsData()` |

The wrapper checks the owning OMX component's `+0x20 == 0x400` or `+0x3dc == 0x7f100001` and dispatches to the AV1 route if either is true, otherwise to Awesome. The `.dvhe` constructor initializes `+0x3dc = 0x0b` (HEVC) in the pinned vendor framework, so **the ordinary HEVC case is expected to use Awesome input handling**, unless the independently writable owner `+0x20` has a special value. The *runtime* owner value remains unmeasured.

These two short Dolby wrapper methods contain no independent P7-specific EL allocation logic. That is not a whole-library proof of absence: inherited methods and lower kernel code may handle EL and/or split decoder creation.

## Result 2: original `codec_init()` has two physical Dolby HEVC devices

Native `codec_init` at `0x58bdc`, not Android `MediaCodec.configure()`, contains:

| Code | Behavior |
| --- | --- |
| `0x590d0` | Takes `codec_para_t + 0x10a0`, a mode word |
| `0x590d4 / 0x590e0` | Loads literal `/dev/amstream_dves_hevc_frame` at VA `0x79f22` |
| `0x590dc / 0x590e2` | Loads literal `/dev/amstream_dves_hevc` at VA `0x79f40` |
| `0x590d8` | Reads the current mode word |
| `0x58ce6 / 0x58cea` | Selects **frame** device if the mode word equals `1`; otherwise keeps **stream** device |
| `0x58cec` | Calls the underlying `open` function with the selected path |

The device path literals were verified by section-aware PC-relative word recovery (not merely `strings`), and the conditional `cmp r2,#1; moveq r0,r3` was checked from disassembly. The Stage 9 audit separately proves that `AmlogicVideoDecoder::intitalizeCodec()` sets a related codec mode word at offset `0x10a0`.

The **observed actual P7** `media.codec` file descriptor in the previous active runtime capture was `/dev/amstream_dves_hevc_frame`; both P7 and P8 kernel decoders were `VDEC_TYPE_FRAME_BLOCK`. Therefore the active device path aligns with this frame case. It does **not** establish that switching to stream mode suffices for FEL; native EL allocation, metadata/RPU handling and Dolby driver's mode contract remain open.

## Result 3: no proven second EL decoder instantiated from this wrapper

Neither the wrapper's `doCodecSpec` nor its `prepareEsData` allocates a separate visible enhancement decoder; both **delegate** to existing implementations. Both P7 startup and active decoder snapshots retain `dveldec(0)`, stable `HDR10 FORMAT_HDR10`, despite the source containing P7 FEL RPU/EL and a kernel `[0]dv dual layer` indication. P8 correctly reaches DOVI. The engine could allocate EL internally through `codec_init`, a kernel ioctl or the Dolby kernel module, so no static absence claim follows.

**Avoid** generic `MediaFormat.profile=128`, property changes (`media.omx.stream_mode`), writing `nal_skip_policy`, kernel global `dolby_meta_with_el`, injecting ioctl `0x179`, or transplanting CoreELEC 5.15 modules into Fire OS kernel 5.4. Earlier isolated property/kernel experiments did not establish FEL and some destabilized video playback.

## Verification and next experiment

Offline `gazelle_fel_stage10_route_audit.py` re-checks the exact ELF SHA, fourteen ARM/Thumb instructions over three method regions, five veneer/PLT/GOT dynamic target identities, and both resolved Dolby HEVC `/dev/amstream` paths. It reports `GAZELLE_STAGE10_DV_HEVC_ROUTE_GATE_PASS`. The previously committed research-branch `audit-fireos-profile-boundary.py` has new pinned instruction windows for these paths; its GitHub Actions gate checks **source syntax/selftests**, not this user's proprietary binaries.

**Next highest-value evidence:** determine whether `codec_init` and the *Fire OS 5.4 kernel modules* can enable an actual EL vdec/provider under the correctly initialized stream mode, **without** changing global kernel parameters. Inspect exact offline kernel module source/binaries (the prior pinned `stream_input.ko`, `decoder_common.ko`, `amvdec_h265.ko` notes) and compare CoreELEC 22's stream/FEL contract. A paired decoder and residual-sensitive pixel output must be proved before calling P7 FEL supported on Fire OS.

No changes to Kodi, the Cube, P8 playback, PTT satellite, HDMI passthrough, Magisk, UDF or MMBD were made.
