# Gazelle Stage 7: exact Stagefright / OMX caller-boundary analysis

Date: 2026-10-19. User archive `gazelle-dv-omx-caller-libs-20261019-133457.zip`. All data analyzed **offline**; no modifications to the Fire TV Cube 3, installed Kodi, vendor binaries, Magisk, Dolby kernel module, or audio HAL.

## SHA-pinned source files

Five original 32-bit ARM little-endian Amazon PS7702.4965N libraries:

| File | SHA256 |
| --- | --- |
| `/system/lib/libstagefright.so` | `4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e` |
| `/system/lib/vndk-28/libstagefright_omx.so` | `849f1dd58078216f59d0cd82da5f7b01b1ab09b2e1cf4a0ccb7e20861dd6389a` |
| `/system/lib/vndk-28/libmedia_omx.so` | `1b06ef4802acd0cb24099149f43c91422170cbdda34c861056324f2df987f44c` |
| `/vendor/lib/libstagefrighthw.so` | `7885067c20f640faa5485d8d1468c32ef7ac50c1d47732b2f9411ffb5725c695` |
| `/vendor/lib/libOmxCore.so` | `fd9c062d8aedd288ea3620183c3c429776977b9c14f16912a07e0cbe9df15e1c` |

Original library payloads are **not** in GitHub.

## Verified ARM instruction flow

1. `libstagefright.so`, `android::ACodec::setupVideoDecoder()`:
   - `0x53f8c/0x53f92`: PC-relative lookup of NUL-terminated `profile` at VMA `0xd7e39`.
   - `0x53f98/0x53f9a`: when this optional message value is missing, branch past the HEVC profile-query path to `0x5404e`.
   - `0x53fda/0x53fdc`: constructs **standard OMX `0x0600000f`** for supported profile/level query, **not** vendor DV index `0x7f800001`. Virtual call at `0x53fe0`.
   - Kodi P7 and P8 traces both had `has_profile_key=false`, so that optional key is not being supplied in the observed sessions. This does not rule out other profile logic.
2. `libstagefright_omx.so`, `OMXNodeInstance::setParameter()` `0x21568/0x2156a`: loads the component's function pointer from `[r0,#0x1c]` and calls it via `blx r3`. This generic bridge can forward dynamically supplied vendor indices.
3. `libstagefrighthw.so`: exports `android::createOMXPlugin` and `AmlogicOMXPlugin::makeComponentInstance`.
4. `libOmxCore.so`: dynamic dependencies include `libOmxVideo.so`, `libOmxBase.so`, `libomx_framework_alt.so`, and `libstagefrighthw.so`. This confirms the expected registration/implementation path, **not** which proprietary setter actually runs.

## Negative scans carefully bounded

Neither proprietary index `0x7f800001` (`OMX_IndexParamVideoDolbyVision`) nor `0x7f00010d` (`OMX_IndexAmlogicProfileLevel`) occurs as a raw little-endian 32-bit constant in **any** of these five libraries. That does **not** eliminate instruction synthesis, generic forwarding, or callers in other libraries.

Full Thumb disassembly found **18** `movt #0x7f80` sites in `libstagefright.so`. Each pairs with `movw #0x7f81`, forming **`0x7f807f81`**, a colour conversion arithmetic multiplier — **not** `0x7f800001` vendor OMX index. Avoid false-positive inference from substring or high-halfword scanning.

## Current root-cause boundary

Stage 6 analysis of exact vendor framework ELF identified the distinct native *receivers*:
- `OMX_IndexParamVideoDolbyVision 0x7f800001` writes owner `+0x36c/+0x370`.
- `OMX_IndexAmlogicProfileLevel 0x7f00010d` writes owner `+0x20/+0x24`.

Stage 7 confirms a generic Android OMX forwarding route and optional standard Android `profile` handling, but **does not establish a sender, runtime payload, or actual invocation** of either vendor-specific handler.

The earlier P7 transfer is verified (48/48 JNI buffer copies, 501 EL NALs/48 RPUs), but P7 native output remains HDR10, `dveldec(0)`, while P8 outputs Dolby Vision. Missing instance metadata ioctl `0x179` and absent active EL decode remain open questions. Nothing here proves an FEL reconstruction fix.

## Engineering next step

Search remaining **pinned vendor OMX implementation / initialisation paths** for construction and calling of index `0x7f800001`, or design a strictly opt-in, observational runtime trace after a separate coexistence safety review. Do not set a speculative Android `profile=128`, force vendor memory fields, write sysfs decoder knobs, inject ioctls, replace vendor .so files or transplant CoreELEC 5.15 modules onto Fire OS 5.4.

An independent reproducible source-only verifier `gazelle-fel-stage7-caller-audit.py` was run locally against the user's exact five-file archive and ended with `GAZELLE_STAGE7_OFFLINE_CALLER_GATE_PASS`. It checks SHA pins, instruction addresses, profile literal, plugin exports, dynamic dependencies, literal absence, and 18 arithmetic false positives. Store verifier and report separately; no proprietary binaries have been published.
