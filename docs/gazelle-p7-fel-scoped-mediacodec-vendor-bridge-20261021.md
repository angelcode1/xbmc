# Gazelle Fire OS: component-scoped P7 FEL MediaCodec vendor bridge — build design

21 October 2026. **Source design only**, not an implementation or tested build. **No Fire OS property changes, module loading, OEM binary changes or production Kodi patch**. This document supersedes the narrow assertion in `gazelle-fel-fireos-native-omx-bridge-decision-20261021.md` that there is no usable *Android* vendor-extension bridge: the Fire OS vendor framework **does** expose such a bridge. It does **not** supersede the overall no-go for a *proven working FEL* fix.

## Key newly verified native route

These owners' original proprietary binaries remain private:
- `/vendor/lib/libomx_framework_alt.so` (SHA256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`);
- `/vendor/lib/libOmxVideo.so` (SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`);
- `/system/lib/libstagefright.so` (SHA256 `4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e`).

1. `android::OmxVideoDecoder::init_vendor_extensions` (framework, address `0x1747c`) registers a vendor extension with **Android vendor name `profile-level`**, **two INT32 keys `n-profile`, `n-level`**, and corresponding private OMX index `0x7f00010d` (`OMX.amlogic.index.profileLevel`).
2. The Android MediaCodec key convention is `vendor.<extension-name>.<parameter-name>`, so its candidate `CJNIMediaFormat::setInteger` keys are exactly `vendor.profile-level.n-profile`, `vendor.profile-level.n-level`. The owner's captured Fire OS `libstagefright.so` retains `android::ACodec::setVendorParameters(sp<AMessage> const&)` at virtual `0x55c5c`, with recognized `vendor.` prefix and corresponding `OMX_IndexConfigAndroidVendorExtension` binder route. Android 9 analogue has a `setVendorParameters(msg)` call within `configureCodec` in addition to dynamic `setParameters`: https://raw.githubusercontent.com/LineageOS/android_frameworks_av/lineage-16.0/media/libstagefright/ACodec.cpp (configureCodec near source line 2284). **Call ordering in the exact Fire OS compiled ACodec and actual vendor instance acceptance still require direct confirmation.**
3. The *vendor* `OmxVideoDecoder::set_vendor_extension_config()` at Thumb `0x1b9f8` contains a resolved jump-table case at `0x1bc88` for index `0x7f00010d`, reads the two named 32-bit integers, assembles an OMX parameter structure, and invokes the component's `setParameter(0x7f00010d, ...)` via its function pointer at `0x1bcee–0x1bcf0`. That parameter handler at `0x19488` writes framework `mProfile`/`mLevel`, with `mProfile` at `+0x20`.
4. `AmlogicVideoDecoder::setUp` in `libOmxVideo.so` checks that private `mProfile==0x10` and conditionally appends `dv_duallayer:1;`. **The meaning/safe value of vendor mProfile=0x10 is NOT independently established**. It is not Android's P7 profile value 128; forcing either would be premature.
5. The same Kodi instance already selects `OMX.amlogic.dolby-vision.dvhe.decoder` for real P7, and 27/27 pre-submit samples contain EL/RPU NALs and byte-equal input copies. The primary observed missing action is creation of the native EL decoder on Fire OS. The **separate** input mode issue persists: `vendor.media.omx.use_dv_frame=true`, `frame_dv` capability, `/dev/amstream_dves_hevc_frame` port type 0x1d11 bit10 gate skips paired `vdec_create`. The stream port 0x1911 is not interchangeable with frame port and may require a different Android Surface/video output contract.

## Proposed integration, no default behavior change

Keep the existing `DVDVideoCodecAndroidMediaCodec.cpp` selection, playback queue, HDMI/audio and output ownership unchanged. A new small bridge helper owned by our Kodi fork should:

- Evaluate exact `OMX.amlogic.dolby-vision.dvhe.decoder`, Android `video/dolby-vision`, Fire OS T7 capability and P7 with EL.
- Distinguish true **FEL** from **MEL** by inspecting a real RPU before MediaCodec `configure()`; `el_present_flag=1` alone means EL present and does **not** prove FEL. Kodi's current `GetDoviIsFEL()` is populated after packet conversion in `AddData`, which occurs after codec configuration; simply checking it in `ConfigureMediaCodec()` would not work. Until early FEL classification exists, limit any trial to a known FEL sample and label it P7-with-EL, not strict FEL-only.
- Use `CJNIMediaFormat::setInteger("vendor.profile-level.n-profile", candidateProfile)` and `setInteger("vendor.profile-level.n-level", candidateLevel)` in a **build-time disabled and explicit-opt-in research-only path** before `m_codec->configure()`. Do not hard-code 16 as a validated P7 mode; candidate values require an independent parameter/meaning audit.
- Log the precise injected keys and any configure error, but distinguish MediaFormat injection from actual `OMX_SetParameter` acceptance. Capture only passive native `vdec_status`, vfm and DV output state, not private data.
- Never set global OMX properties as a first experiment and do not patch system libraries or introduce a replacement OMX service.
- If the vendor bridge accepts the parameter but `/dev/amstream_dves_hevc_frame` remains the same, **do not claim FEL is working**. Secondary decoder creation and true residual-aware Dolby output are separate acceptance checks.

### Stop conditions and milestones

1. **Bridge reachability:** verify stagefright configure-time vendor key transport to the exact Amlogic OMX node and that it occurs before the native setup branch.
2. **Vendor semantics:** establish the safe meaning of the Amlogic private `mProfile=0x10` and the correct `n-level`, without equating them to Android Dolby profile enums.
3. **Decoder acceptance:** observe successful P7 setup without system media-service crashes, then **two concurrent VDEC channels**, `dveldec(1)`, DV output.
4. **Actual FEL:** verify residual-sensitive difference vs BL-only output and correct playback, seeking and shutdown. Only then consider a permanent setting/feature.
5. Fail any critical step? Revert/disable the isolated bridge and keep normal P8 and CoreELEC P7 working. Stop instead of reintroducing packet-queue simulations.

## Closest public code bases, by purpose

- [Our Fire OS Kodi fork](https://github.com/angelcode1/xbmc/tree/research/gazelle-fireos-fel-20261019): **best starting base**, because it already selects the OEM Dolby OMX and passes BL/EL/RPU bytes.
- [CoreELEC/xbmc](https://github.com/CoreELEC/xbmc/tree/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video): **closest hardware/Kodi FEL reference**; `DVDVideoCodecAmlogic.cpp` / `AMLCodec.cpp` on the working 5.15 Linux native backend. Its direct decoder and render interfaces are not drop-in Android MediaCodec replacements.
- [koying/SPMC](https://github.com/koying/SPMC/tree/spmc-krypton/xbmc/cores/VideoPlayer/DVDCodecs/Video): **historical Android Kodi + Amlogic bridge reference**, but based on much older Kodi and vendor stack.
- [djnice/vlc-fel-android](https://github.com/djnice/vlc-fel-android): **closest complete demonstrated Android FEL player**, using custom `libdvfelplay`, a kernel module, a second HEVC MediaCodec and GPU composition on S928X/Dune firmware. Major SoC/driver/output changes are necessary before it could run on T7 Fire OS.

**Source/build status:** no Kodi build executed, no APK built/installed, no actual vendor-MediaFormat-key configure test, no second VDEC enabled and no live FEL output shown. This is an engineering design and a concrete API candidate only.
