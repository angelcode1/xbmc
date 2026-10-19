# Gazelle FEL Stage 8: why a zero Dolby OMX profile does not prove P7 failure

Date: 2026-10-19. **Strictly offline**, using eight original SHA-pinned Amazon Fire TV Cube 3 (PS7702.4965N) ARM32 ELF shared libraries supplied by the device owner. No device changes and no proprietary ELF redistribution.

## Static findings (verified with 19 ARM instruction checks)

1. The OMX base constructor initializes owner `+0x36c` (Dolby profile) to zero through a NEON fill starting at `+0x360`. `libomx_framework_alt.so:0x18ff2` is the **only explicit direct register-relative store to `+0x36c`** in that library's disassembled instructions. That is the `0x7f800001` Dolby Vision `setParameter` receiver; indirect/aliased writers are not excluded.
2. `libOmxVideo.so:0x1eb6e` reads that profile; `0x1ee5c` compares it against `0x400`. **However, this comparison is conditional.**
3. When constructing the component whose name ends `.dvhe`, `libomx_framework_alt.so:0x164c8–0x164ca` writes a separate subtype value **`owner+0x3dc = 0x0b`**. This value is not the Dolby profile at `+0x36c`.
4. In native `AmlogicVideoDecoder::intitalizeCodec()`: `0x1eda8–0x1edaa` reads owner `+0x3dc`; `0x1edb2` compares it with `0x0b`; `0x1edb4` jumps **to** the `0x1ee5c` Dolby profile comparison only if the subtype is **not** `0x0b`. If subtype **is** `0x0b`, the HEVC branch continues and `0x1edce` jumps to `0x1ef1c`, **bypassing** the profile compare.
5. Therefore prior research suggesting that the Dolby profile's zero initialization might explain Profile 7 FEL fallback was **not proven and is now weakened**. In a .dvhe HEVC instance taking this branch, zero at `+0x36c` alone is insufficient to establish failure. Neither the live subtype nor the live profile was measured.
6. Full-image scans of all **eight** supplied libraries found **zero raw little-endian `0x7f800001` literals**. The vendor framework constructs that index from `movs #1; movt #0x7f80` at `0x18fdc–0x18fde` in its *receiver*. The eighteen `movt #0x7f80` occurrences in `libstagefright.so` each have a nearby same-register `movw #0x7f81`, the unrelated colour arithmetic constant `0x7f807f81`. Neither scan proves absence of indirect forwarding or runtime setter calls.
7. The raw P7/P8 device captures remain decisive at the decoder-output boundary: Kodi passes BL/RPU/EL NALs to JNI (48/48 verified copies); the kernel reports `[0]dv dual layer` but settles at HDR10 with `dveldec(0)` for P7; P8 reaches DOVI. Native Fire OS FEL reconstruction is **not** established.

## Reproducibility

The separate full eight-library offline audit `gazelle_fel_stage8_producer_audit.py` verified original SHA-256 hashes, 19 addressed ARM instructions, single explicit field writer, index-construction/false-positive pairs. Final marker:

`GAZELLE_STAGE8_OFFLINE_PRODUCER_GATE_PASS instructions=19 binaries=8`

The research-branch `tools/gazelle-fel/audit-fireos-profile-boundary.py` also carries the new subtype/branch semantic checks. CI performs source-only syntax/self-tests; it **does not** run the full proprietary-binary audit.

## Next engineering target

The next missing evidence is **which decoder initialization branch, stream/frame mode, and instance-local metadata/EL control run during active P7**. The true-FEL hypothesis should center on creating and connecting an EL decoder, not forcing standard Android `MediaFormat.profile=128`, raw proprietary `OMX_SetParameter`, global `nal_skip_policy`, `dolby_meta_with_el`, or a CoreELEC 5.15 module on the Fire OS 5.4 kernel.

No changes to the integrated Kodi branch, installed Cube, voice satellite, passthrough, UDF or MMBD were made.
