# Gazelle FEL Stage 16 — offline OMX mode contract, no live switches

Date: 2026-10-19. **Original vendor ELF only; no changes to Cube, installed Kodi, Magisk, kernel or shared audio HAL.** The exact supplied proprietary ELFs remain private.

## Input pins

- `libomx_framework_alt.so` SHA256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`
- `libOmxVideo.so` SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`

Both ELF32 ARM little-endian binaries passed hash, ABI and exact instruction verification in a local offline audit.

## Source-to-sink contract

| ARM address | Verified operation |
| --- | --- |
| OMX constructor `0x163d4` | Initializes component mode bytes, including `owner+0x10a` |
| OMX constructor `0x16834` / `0x16888` | Explicitly writes `owner+0x10a=1` and `=0` in different configuration paths |
| OMX MVC `setParameter` `0x19e66` / `0x1a1e0` | Sets source `r8=0`, then conditionally clears a halfword covering `+0x109` and `+0x10a` |
| Native Awesome `setUp()` `0x2612c–0x26138` | Copies owner `+0x109/+0x10a` to decoder `+0xdc/+0xdd` |
| Native Awesome `setUp()` `0x26172/0x26178/0x26192` | Conditionally overrides decoder frame-mode byte `+0xdd=1` when internal format is `0x0c` and owner format/profile-like field is `0x400`; this special case is **not proven to apply to active .dvhe HEVC** |
| `AmlogicVideoDecoder::intitalizeCodec()` `0x1efd2` | Stores selected input-mode integer into codec parameter at `+0x10a0`; Stage 10 linked that value to `/dev/amstream_dves_hevc_frame` vs `/dev/amstream_dves_hevc` |

**New bounded negative finding:** `OmxVideoDecoder::setConfig()` over exact function code range `0x1b574–0x1b9f8`, **411 disassembled instruction lines**, has **no direct `[r4,#0x109]` or `[r4,#0x10a]` store**. The function does write the adjacent **`+0x108` byte**, which is not the selector. An indirect/aliased setter elsewhere has not been excluded; this is **not** an absence proof for every private API.

In the original framework, the named vendor extension strings include `is-mvc`, `profile-level`, `low-latency`, `save-mem` and `renderByOmx`. The existence of these names is grounded in the ELF. No supported per-instance `stream-mode` extension has been identified in the audited source; this is not a proof that none exists elsewhere. The MVC-related `0x7f000108` parameter from Stage 15 is a zero-only overlapping store, not a safe or arbitrary stream-mode selector.

## A backend requires a different feeding contract, not just a device path

CoreELEC 22's actual `AMLCodec.cpp` selects stream mode **before** native `codec_init` and uses a stream-buffer-specific `AddData` code path (buffer readiness/thresholds, codec extradata, `write_av_packet` data and PTS handling). Compare https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp . This is an independent *different OS/kernel* source comparison. Kodi's current Android MediaCodec route does not implement that direct packet feed. CoreELEC also configures NAL/FEL policy and Dolby gates as a coordinated decoder lifecycle; none should be copied blindly to Fire OS.

## Decision

- Stage 13 P7/P8 live capture: both use frame Dolby HEVC node; port flags stable at `0x1d11` (frame) and `0x1911` (stream). The frame node skips the **default** slave allocation; stream node is eligible to **attempt** a slave, but EL and true FEL pixels remain unproven.
- **No verified per-instance mode control** from Kodi to original Fire OS OMX has been found. Avoid global `media.omx.stream_mode`, `vendor.media.omx.stream_mode`, `vendor.media.omx.use_dv_frame`, and speculative raw OMX indices.
- A future isolated P7-only backend needs independently proved mode selection, stream input packetization/PTS, EL pairing, metadata ioctl lifecycle, graceful decoder restart/fallback, and FEL residual-sensitive visual verification. Do **not** produce or install a speculative APK yet.
- P8 playback, integrated Kodi, voice satellite, HDMI passthrough, UDF and MMBD must remain unchanged.

## Reproducible verification

`tools/gazelle-fel/audit-stage16-omx-mode-contract.py` is read-only and fails closed on ELF hashes, checks twelve exact ARM instruction patterns, 411 `setConfig()` instructions for direct writes to the mode field, and selected vendor-extension strings. Local original-binary run completed with:

```
GAZELLE_FEL_STAGE16_OFFLINE_CONTRACT_PASS
```

GitHub CI only runs syntax and `--selftest` because proprietary ELFs must not be uploaded to GitHub. Neither of these checks claims native FEL reconstruction.
