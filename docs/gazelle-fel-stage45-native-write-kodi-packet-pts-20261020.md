# Gazelle FEL Stage 45 — Native HEVC write/PTS vs Kodi P7 MediaCodec input contract

**20 October 2026. Original private vendor offline audit PASSED; exact Kodi source content inspected via the linked GitHub repository. Owner's complete Stage45 macOS replay is still required for a combined PASS.** NO device operations, library loading, APK installation or modifications to working P8/voice/audio/optical/Magisk.

## Owner Stage44 result: final checkpoint verified

Uploaded `stage44-audit-results.txt` ended with `GAZELLE_FEL_STAGE44_ORIGINAL_ABI_OFFLINE_PASS`: two owner SHA-pinned ARM32 original vendor binaries, **34 + 5 original Thumb checks**, six native exports, 21 dependencies. The findings include the native context decoder mode at `+0x10a0`, conditional Dolby HEVC frame vs stream device, and separate raw write, PTS and metadata-with-EL interfaces. Native stream packet and PTS semantics remain unknown, and P7 FEL pixels are unproven.

## New Stage45 exact original-vendor ARM32 ABI checks

The original owner-private `libOmxVideo.so`, SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`, was extracted offline from the original vendor archive with the checksum-pinned Stage30 ext4 parser; no vendor bytes are committed. `tools/gazelle-fel/audit-stage45-input-contract.py` independently confirms **24 exact original Thumb instruction locations and four native export identities**, returning `GAZELLE_FEL_STAGE45_VENDOR_ONLY_PASS` in a local audit.

| Fire OS native boundary | Original verified behavior | Readiness limitation |
|---|---|---|
| `codec_init` `0x58ce6–0x58cec` | Context `decoder_type+0x10a0 == 1` selects Dolby HEVC **frame** device; alternate branch selects **stream** | Not a supported Android MediaCodec per-instance setter, nor stream-feed validation |
| `codec_write` `0x597d0–0x597d2` | Loads native decoder FD from context and branches to write wrapper | **No stream packetization or PTS handling inside this six-byte function body**; does not establish the rest of library never packetizes |
| `codec_checkin_pts` `0x5986e–0x5987e` | Separate 32-bit PTS path, selector `0x10e` and ioctl request `0x401053c2` | Timestamp units and rollover conversion not established from exports |
| `codec_checkin_pts_us64` `0x59884–0x598a6` | Separate 64-bit PTS path, ioctl request **`0x40045395`** | Do not assume this interface expects the Android MediaCodec presentationTimeUs representation |
| `codec_set_dvmetawithel` `0x5a1a2–0x5a1aa` | Separate native context flag at `+0x12c0`, selector `0x179` | No confirmed P7 live call/order/acceptance |

The native `codec_para_t` full size and field ownership remain unknown; **`0x12c4` is only a minimum accessed memory extent**.

## New source-specific Kodi comparison

The current integrated Android implementation is the **unchanged** `android-firetv-unified` branch, commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`, with file `xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp` and exact Git blob SHA-1 **`1a313fdc297db69607b2a3f0e82069def4b198f3`**. Stage45's comparator **refuses a modified or different commit** instead of inferring equivalent behavior.

### A. Pairing predicate is by opposite layer, not timestamp identity

At `CDVDVideoCodecAndroidMediaCodec::AddData`, the dual-stream handling (around source lines 1236–1306) searches the pending queue with the lambda:

```cpp
return pending.isEL != packet.isELPackage;
```

The selected lambda **does not compare `pending.pts`/`packet.pts` or DTS**. The queue is bounded to eight, dropping its oldest element on overflow. After finding an opposite-layer packet, the code calls `m_bitstream->Convert(blData, blSize, elData, elSize)` and forwards the resulting access unit.

**Interpretation:** opposite-layer pairing is implemented, **but this search predicate alone does not establish time-aligned BL/EL samples** in out-of-order/interleaved scenarios. This is a correctness gate for a prospective native FEL path, **NOT a claim that mispairing occurred in the owner's P7 playback**. The earlier 48/48 packet-copy observations show certain samples reached JNI intact; they are not proof of all pair timestamps or FEL residual output.

### B. JNI buffer capacity can reduce submitted payload size

In `AddData`, the MediaCodec input-buffer capacity check (around lines 1328–1343) executes `iSize = out_size` when an access unit is larger than `getInputBuffer().capacity()`. The subsequent default codec path calls `memcpy(dst_ptr, pData, iSize)` and eventually `queueInputBuffer(..., iSize, presentationTimeUs, ...)`.

**Interpretation:** the code has a conditional input-truncation path, which the source comparator verifies. **No evidence proves it was taken during the owner's P7 test**, and the checksum logging after the length change alone would not establish the full pre-capacity payload was consumed.

### C. MediaCodec timestamps do not automatically satisfy native PTS ioctl

The integrated Kodi Android class produces `presentationTimeUs` from PTS (or fallback DTS) relative to `m_dtsShift` and passes this to `queueInputBuffer`. This is Android's MediaCodec feed API. The native Fire OS `codec_write` and the separate 32-bit/64-bit PTS ioctls are different interfaces; **the correct native packet ordering, timebase conversion, extradata, EOS/drain, buffer backpressure and discontinuity/flush handling have not been established**.

This audit does not infer that changing the OMX mode selector alone can bridge these distinct contracts.

## Verifiers, privacy and reproducibility

- `tools/gazelle-fel/audit-stage45-input-contract.py --selftest`: source-only structural checks.
- `--vendor-only --original PRIVATE_LIB`: original Amazon ARM32/ELF SHA and 24 instruction + four export checks; verified locally.
- `--kodi-only --kodi FILE`: exact pinned integrated Git blob, bounded pairing/capacity/PTS checks.
- `--original PRIVATE_LIB --kodi FILE`: full combined gate and `GAZELLE_FEL_STAGE45_OFFLINE_PASS`.

The Stage45 macOS ZIP **contains only source/runner and instructions**. It uses the owner's already-recovered `~/Downloads/gazelle-fel-recovered-private/libOmxVideo.so`, and downloads only the pinned Kodi **C++ source text** over HTTPS, SHA-verifying the file before audit. A local source-file override is supported. The runner writes `~/Downloads/gazelle-fel-stage45-results/stage45-audit-results.txt`; no proprietary ELF or raw logs are part of the report.

GitHub Actions checks the source-only comparator and pinned Kodi source via public repository checkout/fetch. The original vendor binary is intentionally not available to CI. No ADB, kernel/module action, native library load, direct ioctl or streaming changes are performed.

## Decision and next gate

**P7-native backend remains NO-GO** pending (1) supported P7-only mode selection, (2) exact original stream packetization and BL/EL/RPU ordering with strict timestamp matching, (3) native PTS units and ownership/backpressure/flush behavior, (4) independently confirmed native context ABI and permissions, (5) slave allocation/connection/metadata parsing, and (6) residual-sensitive pixel comparison.

**Stage46, if owner full Stage45 passes:** focus on an **offline, format-safe BL/EL pairing and bounded buffer-handling contract specification and regression tests**; do not change the installed Kodi or turn on native stream mode. Protect existing P8, audio passthrough, PTT satellite, Magisk and optical-disc code.
