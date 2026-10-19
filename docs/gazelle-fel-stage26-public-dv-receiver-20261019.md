# Gazelle FEL Stage 26 — public receiver route and Dolby metadata tag ABI

**Date:** 2026-10-19 (Australia/Brisbane). **Public kernel source pathway located; installed Fire OS receiver and FEL pixel reconstruction NOT VERIFIED.** Stage 25 original-module audit passed separately on the owner's private PS7702.4965N kernel. This stage makes **no** device changes and does not redistribute Amazon binaries.

## Revision-pinned independent public source

The following upstream references are all to Git commit `24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f` in `TCLOpenSource/a311d2`, **not** a reconstructed copy of the Cube's installed Amazon kernel:

| File | Git blob SHA-1 |
|---|---|
| [amdolby_vision.c](https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/drivers/amlogic/media/enhancement/amdolby_vision/amdolby_vision.c) | `ee5e4f6b4c90926321daf167c7559e6e0f259f1c` |
| [amdolby_vision.h](https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/drivers/amlogic/media/enhancement/amdolby_vision/amdolby_vision.h) | `97751b206ec7cbd93f1ff0d19615040bfa2d3820` |
| [dolby_vision.h](https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/include/linux/amlogic/media/amdolbyvision/dolby_vision.h) | `8afd173cf769443301c76efa5c48d7dfb04d111e` |

## New findings in this public implementation

1. **The missing registration symbol has a public implementation.** `register_dv_functions` verifies probe readiness and SoC compatibility, then assigns `p_funcs_stb = func` or `p_funcs_tv = func` depending on exported callbacks. It is exported as `EXPORT_SYMBOL(register_dv_functions)`. This is a concrete implementation of the **external** registration interface imported by the original `dovi_vs12.ko`. It is not verified to be byte-for-byte the Cube's actual receiver.

2. **A named video-frame callback retrieves HEVC auxiliary data.** Public `is_dovi_frame` sends `VFRAME_EVENT_RECEIVER_GET_AUX_DATA` to the default `dvbldec` provider, then inspects `provider_aux_req_s.aux_buf`, `aux_size` and `dv_enhance_exist`. Provider choice and signal-format guards matter. In Stage 24, original Amazon HEVC `vh265_event_cb` was shown separately to output a picture's auxiliary pointer/size.

3. **Metadata has a concrete public wire type.** The pinned public `dolby_vision.h` defines `DV_SEI = 0x01000000`. Public `is_dovi_frame` recognizes `type == DV_SEI`. Stage 23's original `set_aux_data` builds a record with one leading type/tag byte and its selector 1 retains tag-1 records; the **formats align**, providing evidence consistent with the tag-1 records being Dolby RPU/SEI metadata in this compatible implementation. Not proof that all tags in the Cube are equivalent or that a tag contains an FEL residual.

4. **The exported buffer reaches the registered parser in public source.** `parse_sei_and_meta` passes `req->aux_buf` and `req->aux_size` to `parse_sei_and_meta_ext`, which invokes `p_funcs_stb->metadata_parser_process` (or the TV variant). This is a source-level path from provider metadata to the registered Dolby parser.

5. **Separate EL pairing is still conditional.** `is_dovi_dual_layer_frame` explicitly returns false when `enable_fel` is false, checks `dv_enhance_exist` via the provider event, and the public processing path checks for a matching `dveldec` provider and PTS. Source also contains MEL/FEL handling and disabling gates. This strongly reinforces why metadata or a Dolby indicator is not evidence of EL reconstruction.

## Evidence boundary

- **Original Amazon, independently verified:** Stage 23 metadata selector, Stage 24 HEVC auxiliary DMA origin/export, Stage 25 external callback registration import in `dovi_vs12.ko`; all original module SHA checks passed. Stages 13–25 still show active P7 frame-mode and `dveldec(0)`.
- **Public compatible kernel only:** `register_dv_functions` receiver implementation, `dvbldec` auxiliary request, `DV_SEI` type, `parse_sei_and_meta_ext` to `metadata_parser_process`, EL gate and `dveldec` frame matching.
- **Not established on Cube:** whether Amazon's installed receiver matches this revision, whether the callbacks fire during P7, what controls `enable_fel`, valid EL residual decoding and BL+EL pixel contribution.

## Reproduce without device access

`tools/gazelle-fel/audit-stage26-public-dv-receiver.py` verifies **three exact pinned Git blob hashes** and **six bounded receiver functions**. Download only the three public source files to a temporary checkout and run:

```sh
python3 tools/gazelle-fel/audit-stage26-public-dv-receiver.py --selftest
python3 tools/gazelle-fel/audit-stage26-public-dv-receiver.py /path/to/public/kernel/repo
```

Final expected marker: `GAZELLE_FEL_STAGE26_PUBLIC_SOURCE_PASS`. The source-only selftest does not by itself establish that all three public files were downloaded and inspected. CI will fetch revision-pinned source and verify it, but never obtains private Amazon binaries.

## Next stage

**Stage 27:** collect a strictly read-only, bounded snapshot of the **installed kernel's available** `register_dv_functions` and `amdolby_vision` symbol/provider context, if exports are accessible, and compare it with original static evidence. No live codec flags, `dolby_meta_with_el` writes, `media.omx.stream_mode` toggles, raw ioctl injections, Magisk changes or Kodi replacement. A complete FEL claim still requires a running paired EL decoder, correct metadata, and a residual-sensitive pixel comparison.
