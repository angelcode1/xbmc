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


## Owner P7 input-byte provenance confirmed (16:23, 21 October 2026)

The owner's pasted Kodi diagnostic (private: not committed) includes **27 post-conversion P7 packet summaries**, 26 visible pre-conversion summaries (a `tail -n 80` excerpt), and **27 copy checks**. All 27 post samples have `el>0` (10–17 NAL-63 units each), `rpu=1`, `bl=8`, `invalid=0`, `fel=true` and `rpu_tested=true`. Across the excerpt: **284 EL NAL units**, **27 RPU**, **216 BL**; total **1,146,264 bytes** in the 27 verified input-buffer copies, all `equal=true`. The FNV hash values are deliberately **not** reproduced.

The trace is from the pinned Kodi `AddData()` **post-conversion, pre-`queueInputBuffer()`** copy path. It demonstrates that BL+EL+RPU NAL bytes are present and copied intact into the MediaCodec input buffer. **It does not prove successful JNI queueing of each sample, driver consumption, actual second decoder creation or FEL residual processing.** The single visible `pre`/ `post` size differences reflect Annex B/length-prefix conversion and cannot be labeled EL stripping.

The immediately following `adb logcat -d -v threadtime -b main -b system` vendor-string filter produced **no matching lines**. This is **inconclusive**, not proof that `AmlogicVideoDecoder::setUp()` or `dv_duallayer:1;` did not execute. Vendor log levels, buffers, or log string construction can suppress output.

**Consequent engineering gate:** codec selection and Kodi byte-copy of EL are demonstrated; the next and last meaningful uncertainty in the native route is whether the *live* vendor OMX session selects internal format `0x10`, appends `dv_duallayer:1;` and causes the Fire OS `stream_input.ko` second-`vdec_create` path to run. The internal format comparison is an OMX private field, **not equivalent by assumption to Android `DolbyVisionProfileDvheDtb=128`**. Do not force MediaFormat profile, private ioctls, sysfs or kernel modules on current evidence. Static C++ factory and driver branches establish code presence, not their actual runtime path.


## Fire OS P7 dmesg confirms hardware dual-layer indication but frame-port secondary creation is guarded (21 October 2026)

The owner's real Fire OS P7 dmesg reports `vdec_create ... total 1`, `vdec_init ... format: 11`, `vf_provider_name = dvbldec`, `port type 0x1d11`, then `[0]dv dual layer` after first decoded frame. No `dveldec` initialization or second simultaneous `vdec_create` appears. This corroborates prior P7 VFM `dveldec(0)` and single vdec_status channel.

**New immutable offline binary disassembly evidence:** Original SHA-256 fingerprints: `amvdec_h265.ko` `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`; `stream_input.ko` `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c`; `decoder_common.ko` `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`. These are **private owner-provided** ELF files; no binary is committed.

1. `amvdec_h265.ko` `vh265_isr_thread_fn`, `.text:0xa164–0xa198` reads hardware register `0x30c4`, tests bit zero after internal-state checks, latches a one-shot byte and logs `dv dual layer\n`. Relocation `.rodata+0x2f07` confirms exact string. This shows a live hardware-side dual-layer indication, **not** secondary VDEC creation. The same string is also referenced by `ammvdec_h265_probe` near `.text:0x0f10`; in this path `get_config_int("dv_duallayer", ...)` loads a software config key. Do not confuse the two distinct uses of the same message text.
2. `stream_input.ko` `amstream_open`: first `vdec_create` at `0x1610`; after success `tbnz w8,#10,0x1654` at `0x1620` **skips** the linked second-decoder path when **port flag bit 10** is set. When bit10 is clear, bit12 at `0x1628` (or separate debug logic) gates second `vdec_create` at `0x163c`, with the first decoder as master. Other initialization checks may still fail; this does not guarantee success if bit flags are different.
3. Original static per-port table, structurally verified as 19 entries of 0x50 bytes, links the exact device name to flag value:
   - `amstream_dves_hevc`: type **0x1911** — bit12 **set**, bit10 **clear**; can reach second constructor.
   - `amstream_dves_hevc_frame`: type **0x1d11** — bit12 **set**, bit10 **set**; second constructor **skipped** in `amstream_open`.
   - These values come from immutable `.data` entries and their `.rela.data.userdata_mutex` name pointers, not a guess about bit labels. Both ports are distinct vendor-defined interfaces.
4. `decoder_common.ko` `vdec_create` at `0x8b8` sets `vdec->port` to the passed port descriptor. `vdec_init` at `0x308c–0x30a8` reads `vdec->port->type` (offset `+0x18`) for the exact logged `port type 0x1d11`. This corroborates the relationship of the live log and the flag gate.
5. Original Fire OS capture shows `media.codec` using `/dev/amstream_dves_hevc_frame`, while `/dev/amstream_dves_hevc` is a separate device. `libmediahal_videodec.so` contains the latter name as an import/interface string, but its use by Kodi is **not demonstrated**.

**Engineering conclusion:** The frame-input port selected for Android MediaCodec has a **structural skip** of the stream-input module's second `vdec_create` path, explaining why `[0]dv dual layer` may coexist with `dveldec(0)`. This is the strongest concrete port-level gap found so far. However, the frame-based V4L/MediaCodec pipeline might have other decoder creation paths, and changing device nodes or flag bits is **not** a safe drop-in solution. The missing part is a compatible frontend for native dual-layer stream input *and* corresponding Android renderer/Dolby output. Retain strict NO-GO for forced ioctls, port flags, `/dev` writes, `dovi.ko` swaps, and installed Kodi patches until tested outside active device and rollback justified.

**Next implementation investigation:** trace exactly how `codec_init` in Android legacy `libOmxVideo.so` chooses frame versus stream interface, and whether a supported vendor API can select stream-based dual layer without bypassing DRM, video-buffer ownership, timing, V4L routing, protected paths, or Dolby policy. Compare to working CoreELEC's stream-based architecture. If no supported interface exists, classify this as a major Android decoder pipeline port, not a Kodi codec-profile fix.


## Native OMX stream/frame selection traced from original Fire OS binary (21 October 2026)

This was verified **offline against the exact owner-provided 32-bit ARM /vendor/lib/libOmxVideo.so**, SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`. No Fire OS settings or live device changed.

**Executable chain, no symbol-name inference necessary:**

1. `AmlogicVideoDecoder::intitalizeCodec(codec_para_t*)`, ARM Thumb `0x1ef7a–0x1efd2`, reads byte `this+0xdc`; **only if it is nonzero**, reads `vendor.media.omx.stream_mode` and then `media.omx.stream_mode` (both default `false`). If neither property is enabled, instruction at `0x1ef9a` sets byte `this+0xdd = 1` (forces frame mode). If either is enabled the instruction is **skipped**. Merely enabling a property does not guarantee clearing a pre-existing frame-mode value and is not a demonstrated per-app switch.
2. `0x1efb6–0x1efd2` populates the input-mode field in `codec_para_t + 0x10a0`: **1 if byte `this+0xdd` is set; else 2 if byte `this+0xdc` is set; else 0**. This demonstrates a real distinction between frame (1) and stream (2) input modes.
3. The bundled `codec_init(codec_para_t*)` at `0x58bdc`, with the Dolby HEVC selection branch `0x590c8–0x590e4`, uses `codec_para_t+0x10a0`. A value of **1** chooses exactly `/dev/amstream_dves_hevc_frame` (PC-relative string address `0x79f22`); other values in this branch choose `/dev/amstream_dves_hevc` (address `0x79f40`). These strings are reached as direct literal references from the executable `codec_init` branch, not just present in rodata. An analogous ordinary HEVC selection exists at `0x595b4–0x595ce`.
4. The owner's existing Fire OS `media.codec` FD observation shows **`/dev/amstream_dves_hevc_frame`**, and `vdec_init` reports corresponding port type **0x1d11**. In `stream_input.ko`, bit10 of 0x1d11 skips the paired decoder constructor, whereas **`/dev/amstream_dves_hevc` type 0x1911** clears bit10 and can reach the master/slave second `vdec_create` call when other conditions hold.
5. The same legacy decoder's `setUp()` appends `dv_duallayer:1;` only when an **unresolved private OMX format field at `[this+4]+0x20` equals `0x10`** (`0x21ac6–0x21afe`). The input mode and dual-layer config are two independent branches. Neither should be treated as proof of the live private format value or successful RPU/EL reconstruction.

**Why this matters:** This is a **real compiled Fire OS entry point for a stream input mode capable of reaching second-decoder construction**, not a hypothetical CoreELEC binary transplant. It is still **not proven compatible with Android MediaCodec surface buffer lifecycle, P7 format identification, timestamps, 4K BL + 1080p EL scheduling, or Dolby output**. CoreELEC already demonstrates both hardware channels on this Cube, but Fire OS 5.4/V4L differs.

**Safe read-only follow-up:** `adb shell getprop vendor.media.omx.stream_mode` and `adb shell getprop media.omx.stream_mode` (note their exact values, including empty). Do not `setprop` yet: these are process-global Android properties, potentially affecting all OMX users; selecting a stream port without adapting packet framing and V4L output could break playback, block the codec service or cause an unsafe driver condition. A sensible subsequent test would require inspecting the object's `this+0xdc` source and a controlled isolated codec session with explicit rollback, not patching installed Kodi.

**Stopping rule:** if an isolated vendor path cannot preserve the Android surface/renderer contract while opening both native decoders, classify Fire OS FEL as a major native player pipeline port and suspend the native approach. No more Kodi packet queue stages.


**Additional constraint on reachability:** The original legacy `AmlogicVideoDecoder` constructor writes zero to byte `this+0xdc` (`0x1de7c`). The `stream_mode` property checks run *only* if that byte is later nonzero. A static search of direct stores to that byte found no straightforward legacy Dolby subclass setter; indirect or framework writes remain possible. Therefore the properties are a **candidate gate**, not a proven working toggle for the active Dolby session. P7's observed frame device cannot by itself establish which assignment produced frame mode. Record actual `getprop` values before considering any changes. Do **not** claim a one-property FEL fix.

## Owner properties unset; inherited Awesome setup sources the input-mode flags

Read-only owner result on Fire OS: `vendor.media.omx.stream_mode` is unset and `media.omx.stream_mode` is unset. These match the default (false) property reads in `AmlogicVideoDecoder::intitalizeCodec()`. **No property writes are authorized or recommended.**

**Correction to initial constructor-only analysis:** the proprietary legacy Dolby decoder constructor calls the `AmlogicVideoDecoderAwesome` constructor (class inherits that implementation); `AmlogicVideoDecoderAwesome::setUp()` has direct instruction sequence at virtual addresses `0x2612a-0x26138` that reads `[this+4]+0x109` and `[this+4]+0x10a` and assigns them respectively to `this+0xdc` and `this+0xdd`. So although base `AmlogicVideoDecoder` constructor clears `this+0xdc` at `0x1de7c`, it **does not establish that the byte is always zero at codec initialization**. The source of the vendor configuration bytes and their actual runtime values in this owner's P7 session remain unverified; the two system properties are gated on these inputs.

The previously traced `intitalizeCodec()` mode-value conversion `this+0xdd=1 => codec_para_t+0x10a0=1` (frame) and otherwise `this+0xdc!=0 => codec_para_t+0x10a0=2` (stream) is supported by instruction sequence `0x1efb6-0x1efd2`; a property alone might leave the existing `this+0xdd` value set and therefore **does not guarantee switching to stream**. The owner has directly observed frame mode in `media.codec` with P7. Only a traced vendor parameter setter or a purpose-built isolated codec experiment could close this gap.

**Updated gate:** investigate who populates `[this+4]+0x109/+0x10a` from OMX/native input-mode requests and whether the legacy Dolby class can use its stream backend with Android surface output. No Kodi queue patches, no global property changes, no module loading or stream-port swaps on these data.


## Framework producer of vendor OMX mode bytes resolved

**New offline finding (owner's original `/vendor/lib/libomx_framework_alt.so`, SHA-256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`):** the previously unresolved private OMX fields `[this+4]+0x109/+0x10a` are authored in the companion **`android::OmxVideoDecoder` constructor**, not solely inside `libOmxVideo.so`. The original ELF retains symbol `android::OmxVideoDecoder::OmxVideoDecoder(char const*, VendorPeerComponent&, ...)` at Thumb `0x162e0`, and executable instructions below were verified with `llvm-objdump`, PC-relative literal addresses resolved to exact strings.

| Producer instruction in `libomx_framework_alt.so` | Direct meaning |
| --- | --- |
| `0x163d4` | Initialize four consecutive mode/config bytes at object `+0x109` to zero |
| `0x16556–0x16572` | Parse `/sys/class/amstream/vcodec_profile` for `mh264:`; when found set `object+0x109=1` |
| `0x16622–0x16650` | Detect `frame_dv` in video codec profile; read **`vendor.media.omx.use_dv_frame`** (default 0), store resulting flag at **`object+0x10b`** |
| `0x166c2–0x16704` | Read `media.omx.multi_mode` and parse decimal override, followed by conditional per-codec multi-mode eligibility at `0x16704–0x16780` |
| `0x16730–0x16780` | Consult `media.omx.single_mode` and sometimes clear `object+0x109` |
| `0x167dc–0x16834` | If multi mode is enabled and codec is among supported family, log **`Use frame mode for multidec.`** and set `object+0x10a=1` |
| `0x16838–0x16888` | Read `media.omx.stream_mode` (already confirmed unset in owner's Fire OS), and under its parsed true condition clear `object+0x10a` |
| `0x1688c–0x16900` | Other properties and framebuffer behavior (`media.omx.min_buf`) |
| `0x2834e → 0x287c0–0x287e4` in `libOmxVideo.so` | **Secondary later branch:** for internal codec format **0xb**, `AmlogicVideoDecoderAwesome::doCodecSpec()` reads **`[this+4]+0x10b`**, resets local `this+0xdd`, then updates `codec_para_t+0x10a0` (1 if flag set, else 2). This is conditional during codec-specific processing; not proven executed in owner's P7 session. |
| `0x2612c–0x26138` in `libOmxVideo.so` | `AmlogicVideoDecoderAwesome::setUp()` copies shared framework mode bytes `+0x109/+0x10a` into native instance `+0xdc/+0xdd`. |
| `0x1ef7a–0x1efd2` in `libOmxVideo.so` | Native `intitalizeCodec()` uses mode bytes plus properties `vendor.media.omx.stream_mode` and `media.omx.stream_mode` to choose stream-vs-frame input parameter. |

### Corrected interpretation

This establishes **the complete source of the initial native mode bits** across two original vendor libraries. In particular, the Android OMX framework itself can force frame mode for multidecoder use; the later native code also reads the mode fields and may force frame mode again when the two previously unset properties are false. The vendor's `frame_dv` profile capability and `vendor.media.omx.use_dv_frame` feed an *additional* byte `+0x10b`, so it is **incorrect** to say the existing two properties are the only relevant controls.

**Important limits:** exact P7 runtime multi-mode flags are still unknown; class constructor branches may be gated on codec type and `vcodec_profile` contents. The exact per-stream object and config chain have **not** been sampled live. The original `libOmxVideo.so` is 32-bit ARM, linked through `libomx_framework_alt.so`; pointer `this+4` is a shared framework-provided configuration object. Executable branches are not proof they were reached in the measured P7 session. The later `+0x10b` path may execute only on a specific parser/reconfiguration event. Replacing device path or globally enabling a property still has unknown input and surface timing implications.

### Minimal read-only owner evidence to resolve remaining flags

```sh
ADB="$(command -v adb)"
for key in vendor.media.omx.use_dv_frame media.omx.multi_mode media.omx.single_mode media.omx.drm_framemode media.omx.stream_mode vendor.media.omx.stream_mode; do
  printf '%s = ' "$key"
  "$ADB" shell getprop "$key" | tr -d '\r'
done
"$ADB" shell "cat /sys/class/amstream/vcodec_profile" 2>&1 | grep -E '(^|[[:space:]])(mh264:|h265|frame_dv|vdec_common|no_single)' | head -n 30
```

The literal properties are **read-only**. Do **not** use `setprop` or `echo > /sys` while the normal MediaCodec stack is in use. If a reversible prototype is ever justified, isolate it from production playback and require confirmed complete rollback and actual BL/EL decoder state. No native FEL function is proven here.


## Owner frame-DV capability and explicit true gate — Dolby subclass reaches Awesome mode branch

Owner read-only Fire OS (2026-10-21) reports:
```text
vendor.media.omx.use_dv_frame = true
media.omx.multi_mode =
media.omx.single_mode =
media.omx.drm_framemode =
vdec_common:vdec;
vdec_input:drm_framemode;
hevc:8k, 8bit, 10bit, dwrite, compressed, frame_dv, fence, v4l-uvm;
h265:8k, 8bit, 10bit, dwrite, compressed, frame_dv, fence, v4l-uvm;
mh265:8k, 8bit, 10bit, dwrite, compressed, frame_dv, fence, v4l-uvm;
```
Other profiles such as `mh264` and `av1` also advertise `frame_dv`; this is a vendor capability token, **not** advertised Profile7 FEL support. Empty properties are unset, not necessarily meaning auto-detected feature flags are disabled.

### Verified vendor code-chain implications

- `libomx_framework_alt.so` `OmxVideoDecoder` constructor at `0x16622–0x16650` checks the string `frame_dv` in `/sys/class/amstream/vcodec_profile`; if found, calls `property_get_bool("vendor.media.omx.use_dv_frame", false)` and stores the result into framework byte **`+0x10b`**. Owner has **`true`** for this property.
- `libOmxVideo.so` `AmlogicVideoDecoderDolbyVision::doCodecSpec()` virtual override at **`0x30948–0x309b0`** delegates via a resolved vendor linker veneer **`0x66b54`** to **`AmlogicVideoDecoderAwesome::doCodecSpec()`** (`0x27f80`) for the normal non-AV1 path. The alternate veneer **`0x66b44`** invokes `AmlogicVideoDecoderAv1::doCodecSpec()` when its AV1 code path is selected. The veneer targets were traced to distinct `.rel.plt` entries (index 321 and 443) and exact exported symbol addresses. This confirms the **registered legacy Dolby decoder genuinely reaches the Awesome HEVC-specific mode branch** when its guards permit, not just inheriting an unrelated unused method.
- In `Awesome::doCodecSpec()`, at **`0x2833c–0x2834e`** additional source/state flags are checked and `codec_para_t+0x18` is compared against **0xb (11)**. For the matching format, control branches to **`0x287c0–0x287e4`**, reading the framework **`+0x10b`** byte and selecting codec input mode **1 (frame)** if nonzero, otherwise **2 (stream)** into `codec_para_t+0x10a0`. The owner's `vdec_init ... format: 11` is consistent with the HEVC case, but does **not independently authenticate the precise user-space guard outcomes**.
- Existing run-time read-only capture showed the actual Fire OS MediaCodec using `/dev/amstream_dves_hevc_frame` and kernel port type **0x1d11**. That port bit10 bypasses the `stream_input.ko` paired decoder constructor. Together, this is a **specific, likely root-cause chain for the missing secondary decoder**.
- The `Awesome::doCodecSpec` route also has checks on session/parser state bytes `+0x35c/+0x35d`; whether the P7 AU encountered those conditions is not verified. This is a **strong static explanation** of observed frame mode, **not proof** that switching the single property results in a functioning native second decoder.
- Previous owner evidence: P7 MediaCodec selects `OMX.amlogic.dolby-vision.dvhe.decoder`, post-conversion NALs include BL, EL and RPU with 27/27 input-copy checks equal; kernel reports dual-layer indication but only one VDEC and HDR10 output. CoreELEC actively runs two synchronized HEVC VDECs. These observations continue to delimit the issue.

### Decision

**Do not globally set `vendor.media.omx.use_dv_frame=false`** or alter `media.omx.stream_mode` on production Fire OS. The property applies across OMX components; changing the frame/stream input protocol without preserving buffer ownership, timing, Surface/V4L, FENCE and Dolby pipeline can break P8 and non-Kodi playback or destabilize media services. A property-only change would also not establish that `dv_duallayer:1` is appended (that separate branch checks an unresolved internal format `0x10`), nor that FEL reconstruction and HDMI output work.

**Next worthwhile work:** offline trace the exact per-session guard flags and the native stream decoder's output and Dolby handoff, followed by an *isolated*, opt-in, reversible codec experiment only if those contracts align. If they cannot be aligned, stop the native Fire OS attempt rather than building more Kodi buffering models.
