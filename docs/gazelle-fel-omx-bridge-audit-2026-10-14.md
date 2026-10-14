# Gazelle vendor OMX bridge: source-matched static audit (2026-10-14)

Source capture: `gazelle-omx-bridge-20261014-131538.zip`, SHA256 `77c528c14b475d6a26b1a9adfad8a91e23dffa507eea60ce3fcd1793839a1df9`. Device firmware `PS7702.4965N`; frame-mode property `vendor.media.omx.use_dv_frame=true`. All five libraries are 32-bit ARM Android ELF and are mapped in `media.codec`. Proprietary library payloads and raw process maps are intentionally **not committed**.

| Library | SHA256 |
| --- | --- |
| `libOmxVideo.so` | `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` |
| `libOmxCore.so` | `fd9c062d8aedd288ea3620183c3c429776977b9c14f16912a07e0cbe9df15e1c` |
| `libstagefrighthw.so` | `7885067c20f640faa5485d8d1468c32ef7ac50c1d47732b2f9411ffb5725c695` |
| `libamavutils.so` | `43a4520e0874e74b8cc03984f328432912d8315792b207e1bf8862f65916a6e3` |
| `libmediahal_resman.so` | `a43d5567acc42501d9d70e951cb8ede01f96f4eccd3b82b373c09457bd7fdb35` |

## Concrete library/registration chain

- `libstagefrighthw.so` exports `android::createOMXPlugin` and `AmlogicOMXPlugin::makeComponentInstance`; it contains `libOmxCore.so` and imports `dlopen`/`dlsym`.
- `libOmxCore.so` exports `OmxCoreInit` and declares `libOmxVideo.so`, `libOmxBase.so`, `libomx_framework_alt.so` and other companions as dynamic dependencies. Its `DolbyVision` feature-list string is **not proof of active EL decoding**.
- `libOmxVideo.so`'s component registration data at file offset `0xac5a4` maps the role `video_decoder.dolby-vision` to the exact selected component `OMX.amlogic.dolby-vision.dvhe.decoder`. Neighboring table entries register secure and `.awesome2` variants. Prior P7 and P8 runs select the same *named legacy decoder*.
- `libamavutils.so` exposes `media_config_*` and `am_getconfig*`. `libmediahal_resman.so` exposes resource-manager functions. Neither has a named `codec_set_dvmetawithel` import, although both import generic `ioctl`.

## Direct Thumb instruction findings (valid only for libOmxVideo SHA above)

- `AmlogicVideoDecoder::setUp()` tests internal codec format at `+0x18 == 0xb` (HEVC) at `0x21a62–0x21a6a` and *separately* the vendor peer field `[decoder+4]+0x20 == 0x10` at `0x21ac6–0x21acc`. If both hold, code starting at `0x21ad0` appends `dv_duallayer:1;` (literal virtual address `0x6ae9b`) to its codec config. No Profile 7 test appears within that block.
- `AmlogicVideoDecoder::intitalizeCodec()` at `0x1ec0c–0x1ec30` sets codec-param flag `0x40` when a vendor field byte at `+0x114` is set **or** the same peer field `+0x20 == 0x10`.
- A *different* code path in `AmlogicVideoDecoderDolbyVision::doCodecSpec()` at `0x30956–0x3095e` compares `[peer+0x20]` with `0x400`. The meaning/assignments of this peer field need further analysis: `0x10` must not be casually labeled a 'FEL bit' or presumed present merely because HEVC initialization succeeded.
- `codec_set_dvmetawithel()` at Thumb address `0x5a1a1` is exported and wraps AMSTREAM `0x179`. A full-library `llvm-objdump` direct-branch search found **no call to its symbol**. The four new bridge libraries have **no matching dynamic import or relocation**. This does **not** rule out indirect calls or an independently constructed ioctl.
- The `.gnu_debugdata` ELF section in `libOmxVideo.so` can be LZMA-unpacked to recover additional local symbol names, including `OmxComponentManagerImpl::registerFactory`. It does **not** contain structure-type DWARF mapping the vendor peer `+0x20` field.

## Interpretation and precise next gate

The bridge archive confirms a valid path to the named decoder; it **does not** reveal which peer field value was selected at runtime, the effective `mAmlCodecParam->config`, or whether ioctl `0x179` was applied to the live decoder instance. The active playback differential already established P8 `FORMAT_DOVI` and P7 `FORMAT_HDR10` with `dveldec(0)`, despite working base-layer rendering, and Stage 2 established 48/48 exact JNI input buffer copies.

**Next:** revisit the prior `gazelle-omx-companions-20261014-085629.zip` offline, specifically `libomx_framework_alt.so` and `libOmxBase.so`, tracing how the peer's `+0x20` field is assigned or changed by `setParameter`. The earlier relocation scan was not a dataflow audit. No new playback test or device write is required if that archive is still available.

Avoid a speculative MediaFormat key, hardcoded `0x179` injection, or a global H265 parameter change. A DV indicator or `FORMAT_DOVI` alone is not proof of full FEL pixel reconstruction.

### Offline reproduction

```sh
readelf -Ws libOmxVideo.so | grep codec_set_dvmetawithel
llvm-objdump -d --triple=thumbv7a-linux-android --start-address=0x21a62 --stop-address=0x21b20 libOmxVideo.so
llvm-objdump -d --triple=thumbv7a-linux-android --start-address=0x1ec0c --stop-address=0x1ec34 libOmxVideo.so
readelf -d libOmxCore.so | grep NEEDED
readelf -Ws libstagefrighthw.so | grep createOMXPlugin
```

Related earlier analysis: [dual-layer xref](gazelle-fel-omx-duallayer-xref-2026-10-14.md), [active P8/P7 comparison](gazelle-fel-active-vendor-diff-2026-10-14.md), [validated Stage 2 copies](gazelle-fel-stage2-validated-2026-10-14.md).
