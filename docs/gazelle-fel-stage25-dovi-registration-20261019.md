# Gazelle FEL Stage 25 — DOVI registration ABI and missing event receiver

**Date:** 2026-10-19 (Australia/Brisbane). **Original kernel offline static PASS; runtime P7 FEL reconstruction NOT PROVEN.** No changes to Fire OS, Kodi, Magisk, HDMI/audio, kernel, or satellite.

## Private pinned inputs

The original owner-supplied PS7702.4965N archive `gazelle-fel-kernel-readonly-20261019-191050.zip` (archive SHA-256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`) holds six ELF64/AArch64 `.ko` modules. The verifier checks all six original SHA pins, including `dovi_vs12.ko` at SHA-256 `7c59782906328a9a524719ac0df18ea5d6395d901ca035e3ad7cfed7a9025224`. No proprietary binaries or verbatim disassembly are committed.

## DOVI function table registration is real

Original `dovi_vs12.ko` DWARF names a **96-byte** `dolby_vision_func_s` table. Its exported instance `DV_func` is an object at `.rodata + 0x18` with size 96. The 12 verified field offsets are:

| Offset | Name |
|---:|---|
| 0 | `version_info` |
| 8 | `metadata_parser_init` |
| 16 | `metadata_parser_reset` |
| 24 | `metadata_parser_process` |
| 32 | `metadata_parser_release` |
| 40 | `control_path` |
| 48 | `tv_control_path` |
| 56 | `multi_control_path` |
| 64 | `multi_mp_init` |
| 72 | `multi_mp_reset` |
| 80 | `multi_mp_process` |
| 88 | `multi_mp_release` |

Original `.rela.rodata.DV_func` entries confirm that function-table slots corresponding to offsets 0x38, 0x40, 0x48, 0x50 and 0x58 from the structure's base bind to `multi_control_path`, `metadata_parser_init`, `metadata_parser_reset`, `metadata_parser_process`, and `metadata_parser_release`, respectively (actual module relocation offsets `0x50` through `0x70` because `DV_func` begins at 0x18).

The `init_module` symbol has a relocation-bound `register_dv_functions(&DV_func)` call at `.init.text + 0xdc`. Its pointer setup is pinned by original register instructions at 0xd4 and 0xd8. `cleanup_module` calls `unregister_dv_functions` at `.exit.text + 0x18`. The corresponding registration symbols are **undefined imports** in this module; no symbol definition for them occurs in any of the six collected modules.

The compiled original additionally exports a distinct `register_dec_event_callback` at `.text + 0x1eb2c` which stores its supplied callback into a parser-context field at `+0x316d8`. This name must **not** be interpreted as proof that HEVC's `vh265_event_cb` reaches the Dolby parser; no such call edge was established by this audit.

## Interpret the boundary correctly

The compiled DOVI module really supplies metadata-parser and control-path callbacks through a function table to an external receiver. A separate HEVC module really exposes per-picture auxiliary pointer/size through a callback (Stage 24). **This archive does not contain a demonstrated link between those two interfaces.** Registration does not imply an active P7 decoder, tag semantic decoding, a functioning EL slave, or FEL residual-sensitive pixels. The handler for `register_dv_functions` may be built into the kernel or supplied by a separate uncollected module; its location is **unknown** from these six binaries.

## Reproduction

Use `tools/gazelle-fel/audit-stage25-dovi-registration.py` on original extracted private modules:

```bash
python3 tools/gazelle-fel/audit-stage25-dovi-registration.py --selftest
python3 tools/gazelle-fel/audit-stage25-dovi-registration.py /path/to/private/modules
```

The offline result checked six SHA hashes, 12 DWARF member offsets, five function-table ABS64 relocations, four registration relocations, nine exact global symbols, nine instruction-and-operand checks, and absence of the registration resolver definition among the six modules. Final marker: `GAZELLE_FEL_STAGE25_OFFLINE_PASS`. Public CI only runs syntax and source selftest.

## Stage 26 — requested bounded evidence, not device modifications

First check the existing public Amlogic kernel sources for the precise `register_dv_functions` implementation and HEVC auxiliary callback path (source-level references must be separately versioned/verified). If still ambiguous, a **separate opt-in read-only** collector can inspect currently loaded module names and bounded symbol listings without setting any properties, injecting ioctls, or changing decoder mode. Keep P8 working. Only use runtime P7 testing once a supported, reversible FEL-only route and residual-sensitive output oracle exist.
