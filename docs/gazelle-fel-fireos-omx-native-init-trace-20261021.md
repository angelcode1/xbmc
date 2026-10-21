# Fire OS native P7 FEL — original OMX component factory and dual-layer setup trace

**21 October 2026 — static analysis only of private owner-provided Fire OS image. No device reads or writes were executed in this checkpoint. Original proprietary binaries and device identifiers not committed.**

## Empirical problem to solve

Earlier read-only captures show Fire OS P7 `dvbldec(1),dveldec(0)` and one 4K HEVC VDEC; CoreELEC on the **same Cube 3** shows `dvbldec(1),dveldec(1)` and **two channels** (3840x2160 BL + 1920x1080 EL, frame counters advancing together). See [active decoder comparison](gazelle-fel-fireos-coreelec-active-decoder-comparison-20261021.md).

## New binary-level evidence (original /vendor/lib/libOmxVideo.so)

The captured ELF is **32-bit ARM Thumb PIC**. This analysis used `readelf`, `llvm-objdump --triple=thumbv7-none-linux-gnueabi`, PC-relative literal reconstruction and matching PLT veneers to `.rel.plt` symbol names. Actual file offsets are distinct from virtual addresses (e.g. `.rodata` file offset + 0x2000).

**1. The registered Dolby Vision component selects the LEGACY decoder class.**

- `/vendor/etc/media_codecs.xml` advertises `OMX.amlogic.dolby-vision.dvhe.decoder`, **not** `OMX.amlogic.dolby-vision.dvhe.decoder.awesome2`.
- In `android::amlpeer::CreatComponent(char const*)`, a comparison with `OMX.amlogic.dolby-vision.dvhe.decoder` at virtual address **0x23200** branches on equality to **0x233e4**.
- The branch allocates the legacy class and calls the veneer at **0x66134**, which resolves via PLT to **`AmlogicVideoDecoderDolbyVision::AmlogicVideoDecoderDolbyVision()`**.
- By contrast, the `.awesome2` component comparison at **0x23088** branches to **0x2339e** and the veneer **0x66124**, which resolves to **`AmlogicVideoDecoder2DolbyVision::AmlogicVideoDecoder2DolbyVision()`**.
- Thus the two apparent Dolby implementations are *not interchangeable*. A decoder selected via the XML advertised dvhe name would enter the legacy class family. It is **not yet proven what actual codec Kodi selects** during the owner's P7 playback.

**2. The legacy family contains an executable `dv_duallayer:1;` config-append branch.**

- In `AmlogicVideoDecoder::setUp()` (symbol at **0x21328**), code at **0x21ac6-0x21acc** fetches the stream's internal format field (`[object+4]+0x20`) and compares it to **0x10**, branching away if different.
- On the matched branch **0x21ad0-0x21afe**, a PC-relative literal at **0x21fd0**, loaded at **0x21ad4** and resolved by `add r2,pc` at **0x21ada**, points **exactly** to the `dv_duallayer:1;` bytes at virtual address **0x6ae9b**. The subsequent code appends the text to the codec's config field and updates its configured length.
- This is a live compiled instruction path, not a naked unused string. **Caveat:** the internal format value 0x10 has not yet been traced all the way from selected Kodi P7 media format and OMX parameters. Public kernel `vformat_e` enum labels are not safe substitutes for this proprietary OMX field without proving the correspondence.
- A static branch/append is **not** proof the live P7 session takes it or that the kernel/firmware accepts the requested paired decoder.

**3. Downstream native kernel capability is present but not activated.**

Earlier original binary disassembly found `stream_input.ko` `amstream_open` conditional second `vdec_create` call (paired with primary), and conditional `vdec_set_dv_metawithel` on both decoder objects. This is architectural consistency, **not a proven userspace-to-kernel call trace**. The global `dolby_meta_with_el=0` cannot be the answer because CoreELEC works with that global value also at zero.

## Precise remaining decision

Trace the **live selected MediaCodec component name**, together with the input stream's recognized profile/extradata and any `mAmlCodecParam->config` log under P7, then compare to P8. The pinned Kodi source has an existing **INFO-level** `CDVDVideoCodecAndroidMediaCodec::Open Testing codec: ...` line and a custom DV profile/codec/mime line, which should allow passive observation without patching Kodi.

- **Case A: P7 selects `video/hevc` / HEVC OMX, not DV OMX.** The missing point is Kodi's profile recognition or DV codec selection; only in this case may a *narrow P7-only userspace selection change* be a viable low-effort prototype.
- **Case B: P7 already selects `OMX.amlogic.dolby-vision.dvhe.decoder`.** Then verify actual internal format 0x10/config append and Android decoder execution. Without that evidence do not assume forcing a second decoder by ioctls is safe.
- **Case C: P7 selects another path (e.g., `.awesome2`, V4L2).** Follow that path separately; the legacy `dv_duallayer` append branch may be bypassed completely.

**NO-GO** for kernel parameters, OMX global modifications, manual ioctl, CoreELEC module transplant, firmware/kernel writes and production Kodi patches. Preserve working P8, HDMI passthrough, Magisk, voice satellite and optical UDF/MMBD. Only one targeted read-only observation is warranted before further implementation.

## Owner P7 Kodi decoder-selection confirmation (16:23, 21 October 2026)

The owner's **real Fire OS P7 playback** Kodi log confirms `CDVDVideoCodecAndroidMediaCodec::Open Using codec: OMX.amlogic.dolby-vision.dvhe.decoder`. Diagnostic values: `profile=7`, `el_present=1`, `mime=video/dolby-vision`, `surface=true`, `capability_filter_profile=0`, `advertised_profiles=16,32,256`, `advertises_p7=false`, `advertises_p8=true`, `has_profile_key=false`, `has_level_key=false`, `csd_source_bytes=797`, `csd_injected_bytes=725`. **Codec selection is not the primary missing step; Case A above is ruled out for this sample.** Missing Android P7 capability advertisement corresponds to 0x80=128; absence does not prove hardware incapability. Selection filter 0 and missing MediaFormat profile are deliberate in the original Kodi source and are not confirmed triggers for the vendor internal `0x10` branch. The 72-byte difference is codec-specific-data conversion output, not proof that FEL is stripped.

**New single decision gate:** the pinned Kodi source logs `GAZELLE_P7_NALS stage=pre` and `stage=post`, including counts of NAL 63 (EL) and NAL 62 (RPU) immediately preceding codec input-buffer copy, as well as `GAZELLE_P7_INPUT_COPY equal=...`. Obtain these **already-existing info logs** for the owner's P7 sample. If `stage=post` includes EL (and RPU as expected) and input bytes are copied intact, focus on native OMX format recognition, `dv_duallayer:1;` and kernel second-decoder creation. If no EL reaches `stage=post`, focus on Kodi BL/EL conversion/pairing and decoder payload. The vendor library also contains existing log message strings `mAmlCodecParam->config=%s`, `AmlogicVideoDecoder::setUp`, `check if is dves`, `es is dves, need use dv decoder` and `dv_duallayer:1;`; test whether Android logcat already exposes these strings without modifying log levels. Missing logs are inconclusive because vendor logging may be disabled or expired.

**Never set Android MediaFormat profile to 128 or kernel controls blindly:** the vendor OMX instance does not advertise P7, and the proprietary format-field `0x10` used by `setUp()` has not been proven equivalent to Android's P7 profile constant. Use passive evidence only until the actual input and driver path is established.
