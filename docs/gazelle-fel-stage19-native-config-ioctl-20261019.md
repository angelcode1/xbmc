# Gazelle Stage 19 — native codec configuration and kernel ioctl boundary

**Date:** 2026-10-19. **Scope:** offline read-only analysis of the user-owned original Amazon Fire OS `PS7702.4965N` `/vendor/lib/libOmxVideo.so` (SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`). Proprietary ELF remains private. Native FEL reconstruction is **not** established.

## Verified config context and kernel submission

Stage 18 identified the original vendor field labels in `dump_codec_param()`:

- `codec_para_t + 0x10b4` = **inline** `config` buffer;
- `+0x12b4` = `config_len`;
- `+0x10a0` = `decoder_type`;
- `+0x12b8` = reset-related value (ioctl `0x177`);
- `+0x12c0` = per-instance metadata-with-EL value (ioctl `0x179`).

The vendor's own `.gnu_debugdata` names the native helper at `0x5aa65` **`set_video_codec_info`**. In `libOmxVideo.so`:

- `0x5aa9e–0x5aaa8` loads `config_len` and bypasses the configuration ioctl if it is zero;
- `0x5aaaa–0x5aabe` constructs a pointer to the inline string at `+0x10b4` and pairs it with `config_len` on the stack;
- `0x5aab4/0x5aac4` sends selector `0x301`, **`AMSTREAM_SET_PTR_CONFIGS`**, through ioctl `0x401053c6`, consistent with the separately published [A311D2 amstream.h](https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/include/linux/amlogic/media/utils/amstream.h);
- `codec_init` calls the helper at `0x591ac` and `0x59406` on different paths before its subsequent reset (`0x177`) and port-init (`0x111`) phases.

**Error propagation caution:** `0x5aac8–0x5aacc` checks the configuration ioctl return. On an error (return at most `-1`), it logs; both successful and logged-error branches converge on `0x5aadc: movs r0,#0`. Thus a **config ioctl error can be logged but not propagated by this helper**. There is no runtime proof this occurred during P7 playback.

## Confirmed string construction and formatting boundary

The original formatter helper `0x1e488` resolves via the Thumb/ARM veneer `0x65ae4`, PLT entry `0x1adfc` and GOT relocation `0xae194` to **`__vsprintf_chk@LIBC`**. The caller supplies its destination object-size argument; it is not automatically derived from the remaining inline-buffer capacity.

**Legacy `AmlogicVideoDecoder::setUp()`:**
- At `0x21a74–0x21a9c`, formats `hevc_double_write_mode:%d;` into `config+0`, with a **512-byte bound**, then records the string length **including the terminator**.
- If its separate HEVC/OMX gates hold, at `0x21ad4–0x21afe` appends `dv_duallayer:1;` at `config + config_len - 1`, passing **`0xffffffff`** as the formatter's bound; then increments `config_len` by the appended character count.
- This is a **legacy** function. The active `.dvhe` wrapper's exact dispatch and inheritance remain relevant; presence of this block does **not** establish it executed during P7 playback.

**`AmlogicVideoDecoderAwesome::doCodecSpec()`:**
- At `0x281e4–0x281fe`, formats `hevc_buf_width:%d;hevc_buf_height:%d;hevc_buf_margin:%d;hevc_double_write_mode:%d` using the same **512-byte bound** and records length including NUL.
- A condition at `0x28210–0x28234` optionally appends `negative_dv:1;` at the prior NUL using **`0xffffffff`**. This append is **not** the legacy `dv_duallayer:1;` path.

The inline `config` span ends where `config_len` starts: exactly **512 bytes**. The inspected append paths do not demonstrate a remaining-buffer bound, although **no overrun was observed or asserted**. A future implementation must validate lengths/NUL handling and the full ABI. The previously recovered 4,804-byte minimum context extent is **not** `sizeof(codec_para_t)`.

## Audited result and decision

A local original-binary audit checked **35 Thumb instruction patterns**, four exact PC-relative format-string xrefs, and the actual formatting PLT/GOT relocation. It returned `GAZELLE_FEL_STAGE19_CONFIG_LIFECYCLE_PASS`. Source-only GitHub CI cannot run on proprietary user binaries.

**Next:** trace the exact kernel receiver for `AMSTREAM_SET_PTR_CONFIGS` and its error semantics, then correlate native configuration acceptance with P7 enhancement decoder allocation. Do **not** force global stream-mode properties, inject ioctl `0x301`/`0x179`, hot-patch OMX, or build a native P7 Kodi APK based only on this static evidence. P8, HDMI passthrough, satellite and optical UDF/MMBD remain untouched.
