# Gazelle Stage 14 — P7-only stream-mode preflight, no device writes

Date: 2026-10-19. **DESIGN / STATIC EVIDENCE ONLY — NO NEW APK AND NO ACTIVE MODE CHANGE.**

## Source-backed findings from Stage 13

See `docs/gazelle-fel-stage13-live-capture-results-20261019.md` for the read-only P7/P8 live capture SHA and data. In all six port snapshots, the stream port is `0x1911`, while the actively opened Dolby HEVC frame port remains `0x1d11`. No `port->type`/flag/Vformat changes occurred in the sampled 19-entry tables; the P7 instance had an active `/dev/amstream_dves_hevc_frame` FD, `dvbldec(1)`, `dveldec(0)`, and advancing frame counts. The port `Used` flag was already present without an active decoder and cannot be used to infer live slave allocation.

Exact pinned Amazon `stream_input.ko` ELF disassembly from Stage 12 shows that initial FRAME-bit `0x400` prevents its default paired-vdec call, even though the frame port also carries DUALDEC bit `0x1000`. The alternative `/dev/amstream_dves_hevc` stream port has DUALDEC without FRAME. This explains the default paired-vdec allocation eligibility, **not** FEL pixel reconstruction.

## Integrated Kodi source inspection

The unchanged integration branch `android-firetv-unified` at **`a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`**, `xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp`, creates an Android Dolby Vision MediaCodec, builds a `MediaFormat`, sets ordinary color/HDR/CSD fields, calls `configure()`, and then `start()`. Existing `GAZELLE_DOVI_MEDIAFORMAT` diagnostic records that `profile` and `level` are normally absent. There is **no demonstrated supported per-instance stream/frame decoder-mode API used by Kodi**.

Reference: https://github.com/angelcode1/xbmc/blob/android-firetv-unified/xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp

## Additional static vendor search: do not mislabel setter absence

Re-scanned exact original `libomx_framework_alt.so` SHA256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba` and `libOmxVideo.so` SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` using full `llvm-objdump` Thumb disassembly:

- The framework `OmxVideoDecoder` constructor has two explicit **byte** writes to owner `+0x10a`: `0x16834` writes `1`, `0x16888` writes `0`, under its mode/property branches.
- **Important exception:** `OmxVideoDecoder::setParameter()` also contains `0x1a1e0: strh.w r8,[r4,#0x109]`. As an aligned little-endian **halfword** store it overlaps **both `+0x109` and `+0x10a`**. Therefore a naive search for `strb [owner,#0x10a]` alone would **falsely conclude the mode byte is constructor-only**. This generic setter path needs exact index/conditions and runtime timing analysis; it is not yet a demonstrated safe or P7-scoped frame/stream control.
- In the native `libOmxVideo.so`, `AmlogicVideoDecoderAwesome::setUp()` at `0x26134–0x26138` copies owner `+0x10a` into decoder `+0xdd`, and subsequent code propagates decoder mode to the video device. Other decoder subclasses have additional writes to their own `+0xdd` fields, so name/class scope matters.

Conclusion: **There may be a generic per-component setter that touches an overlapping field, but no validated, documented P7-only switch.** Do not derive an OMX index from this one store, or write the field in a running `media.codec` process.

## Required preflight gates before proposing a test APK

1. Resolve which **specific OMX index** reaches the overlapping `0x1a1e0` store, source parameter type, legal values, timing and whether `+0x10a` is then consumed before native codec initialization. An untrusted speculative index is insufficient.
2. Find a supported **per-instance** mode selection or a separate isolated backend. **Do not globally set** `media.omx.stream_mode` / `vendor.media.omx.stream_mode` / `vendor.media.omx.use_dv_frame`.
3. Any possible P7 FEL test must be opt-in and disabled by default, preserve working P8, leave audio/satellite passthrough undisturbed, stop if OMX start errors occur and return to the known-good decoder on fresh reinitialization. Do not attempt to hot-switch a live decoder.
4. Verify both actual slave allocation and metadata-with-EL handshake, then native Dolby output and EL residual-sensitive pixels. `PORT_TYPE_DUALDEC`, `dveldec(1)` or a Dolby badge alone cannot prove full FEL reconstruction.
5. Keep experimental Kodi work on a **new isolated implementation branch** based on frozen integration HEAD; never merge/replace the installed APK until independently verified.

Current status: **live frame-port root cause narrowed; no proven safe per-instance change; native FEL still unproven**. No device/kernel/OMX/MediaCodec/property writes performed.
