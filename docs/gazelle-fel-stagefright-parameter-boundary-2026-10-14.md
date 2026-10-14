# Gazelle Stagefright ↔ vendor OMX parameter boundary — 2026-10-14

Scope: strictly offline analysis of user-supplied Android 9 ARM32 ELF binaries from Fire TV Cube 3 PS7702.4965N. This is **not** an implementation of native FEL. No device commands, service restarts, binary modifications, or sysfs writes were made.

## Inputs and provenance

Archive: `gazelle-stagefright-20261014-145648.zip`, SHA256 `9b4fa154e6033e04910949c09f5b39fa8e1dc7a73338c855920eb819a6a95cd2`. The three ELF hashes matched the archive's `SHA256SUMS.txt`.

| ELF | Original device location | SHA-256 |
| --- | --- | --- |
| `libstagefright.so` | `/system/lib/libstagefright.so` | `4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e` |
| `libstagefright_omx.so` | `/system/lib/vndk-28/libstagefright_omx.so` | `849f1dd58078216f59d0cd82da5f7b01b1ab09b2e1cf4a0ccb7e20861dd6389a` |
| `libmedia_omx.so` | `/system/lib/vndk-28/libmedia_omx.so` | `1b06ef4802acd0cb24099149f43c91422170cbdda34c861056324f2df987f44c` |

## Verified codepaths

1. `libstagefright.so` exports `android::ACodec::configureCodec()` (0x5213d) and `ACodec::setupVideoDecoder()` (0x53f39), and includes `parseDolbyVisionProfileLevelFromDvcc` and the string `DolbyVision`. It knows Dolby Vision stream profiles, but **no evidence here shows a P7-specific OMX extension being sent**.
2. `libstagefright_omx.so`'s `OMXMaster::addVendorPlugin()` (Thumb 0x1eb78) has **two** PC-relative library-name targets: `libstagefrighthw.so` (0x3c322) and `libstagefrightdolby.so` (0x3c336). This is confirmed by instruction-relative pointers, not mere embedded strings. It attempts to load a plugin and locate `createOMXPlugin`; both paths are optional. AOSP [OMXMaster reference](https://android.googlesource.com/platform/frameworks/av/+/927bea3241dc300fb56df9c30f72f2b5b112de10/media/libstagefright/omx/OMXMaster.cpp) confirms the general plugin interface (not the Fire OS second-plugin addition).
3. `OMXNodeInstance::setParameter()` at 0x21562–0x2156a calls the actual component function pointer via `ldr r3,[r0,#0x1c]` then `blx r3`. This is a direct verified forwarding boundary.
4. The HIDL OMX adapters also provide dispatch boundaries: `LWOmxNode::setParameter()` at 0x346f2 uses `blx r5`; `TWOmxNode::setParameter()` at 0x35e68 uses `blx r6`. No P7-specialization was inferred from these generic calls.
5. **Zero direct little-endian 32-bit matches** of vendor index `0x7f00010d` occur in all three ELF binaries. This is a narrow, useful **negative literal scan**, NOT proof the index is never sent: code may construct it via instructions, receive it from another library, or forward it generically.
6. The earlier active `media.codec` memory-map archive contains three mappings of `libstagefrighthw.so` and none of `libstagefrightdolby.so`. **Do not infer the latter is absent from disk or was never loaded**. P8 Dolby Vision worked in the recorded environment, so this mapping alone cannot explain P7 FEL failure.

7. `libstagefright.so` also exports `ACodec::setDolbyParameter()`, but the associated strings include `omx.index.dolby.dax_state`, `omx.index.dolby.profile_index` and `setDolbyParameterOnProcessedAudio`. These are **Dolby audio / DAX-related signals**, not evidence of a native Dolby Vision enhancement-layer switch. Do not treat every Dolby-named Stagefright function as a DV FEL control.

## Implication for the preceding vendor trace

Previous `libomx_framework_alt.so` analysis identified the vendor OMX setter index **0x7f00010d**, copying parameter offsets `+0x0c` and `+0x10` into owning component fields `+0x20` / `+0x24`. The Dolby class in `libOmxVideo.so` consults owner `+0x20` against `0x400`, or `owner+0x3dc` against `0x7f100001`. These system libraries **forward OMX parameters but do not identify the source/value of that particular vendor setter**.

Combined with runtime P8 `FORMAT_DOVI` and P7 `FORMAT_HDR10` (valid base-layer provider, inactive EL provider) and Kodi's 48/48 exact P7 buffer copies, the remaining unknown is whether the vendor's per-instance Dolby HEVC format, EL metadata parser, and enhancement decode route were actually configured for P7.

## Reproducible test

```sh
python3 tools/gazelle-fel/audit-stagefright-omx.py /path/to/unpacked-stagefright \
  --maps /path/to/media-codec-maps.txt
```

On the pinned binaries the offline verifier reports `STAGEFRIGHT_OFFLINE_PASS`. This only verifies string pointers, forwarding instructions, library SHA pins, and index-literal absence. It does not read/alter the device.

## Safe next investigation

- Discover whether `libstagefrightdolby.so` exists and where (read-only `ls` or `find` on the Cube), but **do not treat it as required for FEL**, because working P8 has already been observed without a mapping.
- Locate any other implementation that **constructs or supplies** `0x7f00010d`, including upstream OMX parameter callers in the vendor plugin/core; do not force a speculative `MediaFormat` key in Kodi.
- Establish actual per-instance values and EL decode activation *before* modifying Kodi or kernel. Avoid remote process injection given prior media.codec restrictions and shared audio-HAL coexistence.

The proprietary ELF files remain outside the public repo. Related: [OMX owner-field trace](gazelle-fel-omx-owner-parameter-trace-2026-10-14.md), [Dolby component gate](gazelle-fel-dolby-component-gates-2026-10-14.md), [P8/P7 active runtime comparison](gazelle-fel-active-vendor-diff-2026-10-14.md).
