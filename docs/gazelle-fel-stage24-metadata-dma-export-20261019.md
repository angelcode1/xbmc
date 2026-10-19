# Gazelle FEL Stage 24 — HEVC auxiliary DMA origin and callback export

**2026-10-19, Australia/Brisbane. Result: OFFLINE STATIC PASS; actual P7 FEL residual reconstruction NOT PROVEN.** The only inputs are owner-supplied original Amazon PS7702.4965N kernel modules. No device, kernel, Magisk, Kodi, SELinux, audio, HDMI, optical or voice-satellite settings changed.

## Original binaries (private, never upload to public Git)

| Module | SHA-256 |
| --- | --- |
| `amvdec_h265.ko` | `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040` |
| `decoder_common.ko` | `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b` |
| `stream_input.ko` | `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` |

## A. Where tag-bearing metadata starts

Original HEVC DWARF identifies private instance members `prefix_aux_size` at `+0x8e4`, `suffix_aux_size` at `+0x8e8`, and `aux_addr` at `+0x8f0`.

`vh265_local_init()`, `0x9804–0x9830`, rounds sizes up to 16-byte boundaries, allocates the combined auxiliary DMA region with a relocation-confirmed `dma_alloc_attrs` at `0x982c`, stores its virtual address in `aux_addr`, and places the address output at private-state `+0x908`. `hevc_local_uninit()` later uses relocation-confirmed `dma_free_attrs` at `0x3e98`.

`vh265_prot_init()`, `0x8a58–0x8a84`, writes the DMA/bus address to HEVC decoder register `0x30d5` and size configuration to `0x30d6`, through `aml_write_dosbus` (original call relocations checked).

`set_aux_data()` at `0xcf64` reads this `aux_addr`, selects prefix/suffix region, reads 16-bit tagged entries and extracts tag byte with shift-by-eight at `0xd124–0xd128`. Stage 23 proved selector arguments 0/1/2 choose all valid / only tag-1 / other valid tags.

**Supported boundary:** a dedicated, register-configured HEVC DMA auxiliary buffer is the input. Which decoder firmware/hardware unit actually writes each tag and whether P7 enhancement data appears there are still **unknown**.

## B. Where the assembled metadata goes

DWARF names per-picture `aux_data_buf` at `+0x1f448` and `aux_data_size` at `+0x1f450`. The HEVC `vh265_event_cb()` path at `0x15708`, guarded by event bits and a valid picture lookup, loads those fields at `0x157c8–0x157f0` and stores their pointer and size to its caller-supplied event argument at offsets `+0x10` and `+0x18`.

This **exports a pointer and length to a callback caller**. It does not prove the caller invokes Dolby RPU parsing, mixes the EL into BL pixels, or ever executes this branch during active P7.

An independent `post_video_frame()` path at `0x7210–0x7228` passes the same fields to the externally linked `decoder_do_aux_data_check` (verified call relocation). `vh265_vf_get()` contains a debug read; restore/uninit paths reference and release auxiliary storage. Such references are not themselves proof of pixel composition.

## C. Offline reproducibility and next boundary

Run `tools/gazelle-fel/audit-stage24-metadata-path.py` offline. Against the pinned original modules, the verifier passed **3 SHA checks, 71 ARM64 instruction+operand checks, 3 original local function symbol checks, 5 ELF call relocations, and 5 named DWARF member-offset checks**:

```sh
python3 tools/gazelle-fel/audit-stage24-metadata-path.py --selftest
python3 tools/gazelle-fel/audit-stage24-metadata-path.py /path/to/private/extracted/modules
```

Final marker: `GAZELLE_FEL_STAGE24_OFFLINE_PASS`. GitHub CI only checks source syntax/selftest; the proprietary modules are not committed.

**Stage 25 next:** audit the owner-supplied `dovi_vs12.ko` or other relevant pinned original kernel module to identify the external receiver of HEVC auxiliary event data, its event-argument contract and tag interpretation. Trace this entirely offline before any proposed FEL-only runtime test. Preserve working P8; avoid global `media.omx.stream_mode`, `nal_skip_policy`, `dolby_meta_with_el`, speculative Kodi builds, kernel flags or direct `0x179/0x301` ioctls.