# Gazelle P7 FEL under Fire OS — native OMX bridge decision
**21 October 2026 — offline binary analysis only. No changes to device, Kodi, Magisk, kernel, system properties, or hardware buffers.**

## Decision

**NO-GO for a simple Kodi profile setting, Android MediaFormat key, or global property workaround. CONDITIONAL GO for a separately scoped, native OMX proof of concept**, only if its surface-output and input-framing contracts can be shown safe before live use. Treat this as a major native Android multimedia integration task, not an unblocking of the earlier P7 packet queue experiments.

The user has already verified real P7 FEL playback in CoreELEC 22 on this exact T7 Cube 3. That fact demonstrates hardware capability but does **not** establish that the stock Fire OS 5.4 / V4L / vendor OMX pipeline can composite FEL.

## Evidence already established

1. Kodi's running Fire OS P7 session selects **`OMX.amlogic.dolby-vision.dvhe.decoder`**, requests `mime=video/dolby-vision`, recognizes `profile=7,el_present=1`, but its Android capability query advertises only **16,32,256** (no P7 128); its current MediaFormat has **no profile key**.
2. Owner's 27 P7 packet samples, instrumented just before copying to a MediaCodec input buffer, contain BL NAL units, EL NAL-63 units and RPU NAL-62 units. All 27 copy comparisons were byte-equal. **This does not independently prove every queued buffer was accepted or decoded.**
3. Fire OS active P7: `dvbldec(1),dveldec(0)`, single H265 VDEC and HDR10 output. Kernel dmesg emits `[0]dv dual layer` after first decoded frame, demonstrating the decoder can detect a dual-layer condition, **not** that it creates a second VDEC.
4. CoreELEC active P7: `dvbldec(1),dveldec(1)`; 3840×2160 BL and 1920×1080 EL channels advance together, Dolby output classified DV. **The owners' CoreELEC test has working FEL, but no pixel-derived residual proof was separately captured.**
5. Frame-port `/dev/amstream_dves_hevc_frame` is used by Fire OS; its original kernel port type `0x1d11` has bit10 set and skips the legacy paired `vdec_create` call. The stream port `/dev/amstream_dves_hevc` has port type `0x1911` (bit10 clear, bit12 set), allowing the constructor branch when other conditions pass. They are **different input contracts**; not interchangeable paths.
6. The owner read `vendor.media.omx.use_dv_frame=true`, and the HEVC capability profiles include `frame_dv`. An executable, conditionally reached late path in `AmlogicVideoDecoderAwesome::doCodecSpec` reads this flag and can choose native mode 1 (frame) or 2 (stream), then call `codec_reset()` (which closes and reopens the native codec) and update the associated video output mode. This alone cannot enable P7 FEL.

## New validated Android-to-vendor-OMX bridge finding

Owner's captured, immutable, original Fire OS ELF files:
- `/vendor/lib/libomx_framework_alt.so` SHA-256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`
- `/vendor/lib/libOmxVideo.so` SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`
- `/system/lib/libstagefright.so` SHA-256 `4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e`

- In the framework, `getExtensionIndex` registers **`OMX.amlogic.index.profileLevel` → `0x7f00010d`**. Its `setParameter()` handler at Thumb `0x19488–0x194a8` checks parameter `nSize>=24` and major version `1`, then copies two caller-supplied words (`+0xc/+0x10`) into the framework's **`this+0x20/+0x24`**. The constructor initializes these fields to zero.
- The legacy `AmlogicVideoDecoder::setUp()` in `libOmxVideo.so` at `0x21ac6–0x21afe` checks that same `this+4` shared object's `+0x20 == 0x10`. Only the matching branch appends **`dv_duallayer:1;`** to the native codec configuration. The value **0x10 is a proprietary Amlogic field condition**, not evidence of a P7 profile (Android's P7 codec profile constant is 128).
- The framework separately handles `OMX_IndexParamVideoDolbyVision` and stores Dolby-specific profile/level fields at `+0x36c/+0x370`. **The two parameter families are not interchangeable.**
- Static byte scans across all **116 collected Fire OS files** find the literal `OMX.amlogic.index.profileLevel` and framework logging identifier **only** in `libomx_framework_alt.so`; the literal `dv_duallayer:1;` appears only in `libOmxVideo.so`. Neither `libstagefright.so` nor `libmedia_omx.so` includes the vendor extension name.
- The platform `android::ACodec::setParameters_fosExt_processExtraParams(sp<AMessage> const&)` (ELF Thumb virtual entry `0x5a300`, symbol value `0x5a301`) is an instruction-level no-op: `movs r0,#0; bx lr` (returns `OK`). It is **not** a bridge to that specific vendor OMX extension. This does *not* prove there are no other dynamically named, computed-index, or service-side calls; it only eliminates this candidate.
- Standard Android 9 ACodec has explicit OMX parameter transactions; setting Java `MediaFormat.KEY_PROFILE` does **not** generally provide raw `OMX_GetExtensionIndex` + `OMX_SetParameter` access. See Android platform ACodec source at https://android.googlesource.com/platform/frameworks/av/+/9f51d59dbbe821b2403b2e619e7c6ef14c6849f2/media/libstagefright/ACodec.cpp . The captured Fire OS ACodec binary may have additional local modifications, so source correspondence is contextual and not exact proof of every call.
- A separate branch in `libOmxVideo.so` reads an in-band RPU-like pattern and can call `codec_reset()` to change frame/stream mode. This is an **output-coupled decoder close/reopen**, not a safe live property toggle.

### Corrected boundary of evidence

Presence of vendor extension **proves it is implemented and callable by an OMX client that controls the relevant node**. Presence of the caller data field **does not prove Kodi's Java MediaCodec config supplies it**. Byte-equal BL/EL/RPU copies show input preparation succeeds; this says nothing conclusive about the native framework's `mProfile` at runtime, pair construction or residual-aware Dolby compositing.

**No first-party caller supplying `0x10` to this extension was found in the collected binary set.** This remains negative static evidence, not a mathematical proof of unreachability. The vendor extension might have been intended for another supported DV dual-layer profile. It is incorrect to infer `0x10` is equivalent to P7 or to try it on stock Kodi.

## Engineering options and stop rule

**A. Native isolated OMX test harness (substantial, experimental):** would need 32-bit vendor-compatible native client, a component-scoped OMX node allocation and vendor `setParameter` request, a preserved initial/late-mode decision, exact stream-packet/framing and timestamps, controlled Surface/output lifetime, and strict rollback. First target would be observing a correctly initialized second HEVC channel and a successful shutdown with no impact to ordinary P8/MediaCodec. This document deliberately does not recommend invoking the vendor extension live before this contract is established.

**B. Supported stock Kodi/Java MediaCodec setting:** currently **NO-GO**, because the vendor index is outside the demonstrated interface, changing one global property is not sufficient, and P7 is not among advertised profiles.

**C. Port CoreELEC's native Amlogic decoder/render stack or a GPU FEL compositor to Fire OS:** would be a major kernel/Android media engineering port; no evidence of a quick compatible module replacement.

**Stopping rule:** If a component-scoped native OMX client cannot set up a stream-based BL/EL decode while preserving surface and Dolby output, suspend Fire OS native FEL development and use CoreELEC for FEL. Do not create more Kodi packet/EOS audit stages as a substitute for this missing hardware/driver integration.

**Operational safeguards:** never change shared OMX properties, kernel flags, system modules, MediaCodec service, vendor binaries, or installed Kodi just to exercise a conditional branch. Do not commit proprietary binaries or original UHD Blu-ray samples. Preserve working Fire OS P8, passthrough audio, UDF/MMBD, satellite and Magisk.
