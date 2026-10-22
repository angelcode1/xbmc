# Gazelle FEL Kodi dual-layer HEVC converter: hvcC widths and RPU source-cursor fix

22 October 2026. This is **actual Kodi C++ decoder code integrated in the research branch**, plus host-tested allocation-free parsing. **Not a compiled Android Kodi APK and not working FEL on Cube.**

## Original defects fixed

1. Kodi's dual-track `CBitstreamConverter::Convert(uint8_t* pData_bl,..., uint8_t* pData_el,...)` used `AV_RB32(buf)` and `buf += 4` for both NAL loops regardless of the `lengthSizeMinusOne` value in HEVC hvcC configuration. `BitstreamConvertInitHEVC()` already parses the real `m_sps_pps_context.length_size`, allowing **1, 2, 3 or 4**. The P7 BL+EL assembler failed on valid non-four-byte packet prefixes, potentially generating corrupt partial AUs.
2. It silently exited on a bad length but could report a partially assembled AU as success.
3. In the EL loop, when `processDoviRpu()` produced rewritten output with a different `rpu_data->len`, the old code overwrote `size` then executed `buf += size`. The next **input** NAL cursor was incorrectly computed from the **new output length**. This could skip, overlap or misidentify remaining EL NALs.

## Changes committed to xbmc research branch

- `xbmc/utils/GazelleFELNalReader.h`: no heap allocations, bounds-checked HEVC NAL reader with 1–4-byte prefix support, rejects length zero/one, truncated headers, overclaims and incomplete trailing NALs, requires at least one well-formed NAL.
- `xbmc/utils/BitstreamConverter.cpp`: obtains width from hvcC when input is length-prefixed; retains four-byte width when local Annex-B→length conversion was used. Validates **both BL and EL in full before any output is assembled**. Actual BL and EL construction loops now use `LengthPrefixedReader::Next()` to get source spans. The RPU output data may be transformed by libdovi, but the source reader advances independently based on original input NAL lengths. Preserves original BL-first, NAL 62 RPU, and NAL 63 EL wrapper ordering; no driver IO.
- `tests/TestGazelleFELNalReader.cpp` tests prefix widths, malformed data, and a changed-length RPU followed by another original NAL; `.github/workflows/gazelle-fel-pairing-host.yml` runs host gate on these new paths.

Source-only no-Git user ZIP `gazelle-fel-nal-guard-20261022.zip` contains header, equivalent standalone test, and Clang host/sanitizer runner. Locally tested optimized and ASan/UBSan:

```text
GAZELLE_FEL_NAL_READER_HOST_PASS prefixes=1,2,3,4 malformed_rejected=true no_device=true
```

This proves just the standalone reader's boundary behaviour. It does **not** independently compile the full `BitstreamConverter.cpp` because the Android Kodi+FFmpeg build toolchain is not present in this execution environment. The full Kodi build, GitHub Actions outcome, actual P7 device output, RPU bitstream semantic acceptance, and FEL video composition remain unverified.

## Existing separate fixes retained

`GazelleFELPairing.h` matches dual-track BL/EL packets using DTS/PTS, rejects unbounded mismatches, and refuses truncated Profile 7 MediaCodec submissions. The user confirmed the companion host test `GAZELLE_FEL_P7_PAIRING_HOST_PASS`. None of these input integrity fixes creates the missing native EL VDEC or proves the Dolby composition path.

Known device evidence: Fire TV Cube 3rd Gen FireOS7 API28; the original Amazon kernel has compiled `enable_fel` policy paths, but live `decoder_common.debugflags=0`, `enable_stream_mode_multi_dec=0`, stock P7 playback had `dvbldec(1),dveldec(0)`, and no-Surface Main10 output returned **8-bit YUV_420_888**. The target remains actual FEL residual reconstruction (Power Rangers credits white, woman visible). Do not toggle global VFM/Dolby/kernel options or change installed Kodi/Magisk UDF/MMBD, HDMI passthrough, satellite based solely on these host results.
