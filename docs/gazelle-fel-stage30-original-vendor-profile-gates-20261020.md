# Gazelle FEL Stage 30 — original vendor OMX profile and HEVC config gate

**20 October 2026. Original Fire OS PS7702.4965N ELF audit PASS. FEL pixel reconstruction NOT PROVEN.**

## Inputs and provenance

Owner-supplied private archive **03-vendor-odm.zip**, SHA256 **63c0aacc8647def650751a17b1fdba7ae6a67fed5ce6de7c88ab834d13e41622** contains raw vendor.img, SHA256 **8021a1ba7956f01fe705b90e0005c377c04570adbec0e2e4399962617ab5553a**. A read-only local ext4 reader recovered exactly two libraries under /lib:

- libOmxVideo.so: **eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77**
- libomx_framework_alt.so: **fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba**

They match the exact original vendor pins from earlier stages. No proprietary binaries have been committed. No device, ADB, Kodi, Magisk, HDMI, optical, satellite or audio modifications.

## Original ELF verification: 48 instructions, 3 PC-relative literals, 2 hashes

| Verified region | Original ARM/Thumb gate | Meaning |
| --- | --- | --- |
| OMX DV setter | 0x18fdc/0x18fde constructs 0x7f800001; 0x18ff2 stores owner+0x36c; 0x18ffc stores owner+0x370 | Dolby Vision profile/level parameter |
| Distinct OMX Amlogic setter | 0x194a4/0x194a8 stores owner+0x20/+0x24 | Different profile/level parameter |
| .dvhe constructor | 0x164c8/0x164ca writes subtype 0x0b into owner+0x3dc | Independent HEVC classification field |
| Native initializeCodec | 0x1edaa–0x1edce tests subtype 0x0b and jumps around 0x1ee5c | HEVC branch can bypass Dolby profile 0x400 comparison; zero Dolby profile alone is not a demonstrated P7 failure |
| DolbyVision wrapper | 0x30958–0x309a4 and 0x309ce–0x309d2 | Delegates to AV1 or Awesome implementation depending on Amlogic owner profile/subtype |
| Awesome doCodecSpec | 0x281c4 HEVC check, 0x281e4–0x281fa builds inline 512-byte config, 0x28202–0x28234 conditional append | Resolved appended literal **negative_dv:1;** |
| Older AmlogicVideoDecoder setUp | 0x21ac8–0x21ae4, profile owner+0x20 equals 0x10 gate | A **different** conditional append: **dv_duallayer:1;** |
| Native codec_init | 0x590d0/0x590d8 reads codec_para_t+0x10a0; 0x58ce6/0x58cea selects frame path when value=1 | Independent stream/frame device mode |

Three actual PC-relative literal xrefs were decoded: 0x288d8 for HEVC dimensions/double-write config, 0x288dc for **negative_dv:1;**, and 0x21fd0 for **dv_duallayer:1;**. Their mere presence is NOT evidence either was sent during P7 playback.

Result: **GAZELLE_FEL_STAGE30_OFFLINE_PASS** from an original-ELF SHA-pinned local audit. GitHub CI can verify source and selftest only.

## Cross-check against Stage 28–29 runtime

In the user-selected nine-sample live test, both P8 and P7 had an active HEVC decoder and dvbldec(1), but P8 reached **DV FORMAT_DOVI** and P7 reached **HDR10 FORMAT_HDR10**, with dveldec(0). Both had unchanged frame/stream port flags, including stale Used flags during idle. Stage 30 does **not** establish which configuration string the active P7 decoder submitted, whether the vendor 0x301 ioctl succeeded, whether parser metadata was accepted, or whether a separate EL decoder was ever created.

**Do not** set global stream-mode properties, change nal_skip_policy or dolby_meta_with_el, issue direct 0x301/0x179 ioctls, patch installed vendor libraries, install a speculative APK, or infer residual-pixel success from a Dolby indicator. The separate 512-byte inline configuration span is not a complete codec_para_t ABI; the observed optional append uses a bound of 0xffffffff, not the remaining available buffer.

## Reproduction

Run the committed offline verifier:

    python3 tools/gazelle-fel/audit-stage30-vendor-profile.py --selftest
    python3 tools/gazelle-fel/audit-stage30-vendor-profile.py /private/original/vendor-libraries

Requires llvm-objdump. Companion macOS ZIP provides a standard-Python original-image extractor and a pinned downloader, no ADB.

**Stage 31:** trace native per-instance configuration acceptance and source-format metadata interpretation without changing device state. If further live evidence is needed, separately design an opt-in read-only time-correlated P7/P8 logging gate. A safe instance-scoped P7 backend must prove complete ABI, correct packet/PTS feeding, paired EL allocation and genuine residual-sensitive pixel contribution.
