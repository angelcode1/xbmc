# Gazelle FEL Stage 34 — original HEVC register-base correction and DWARF resolution

**Date:** 2026-10-20. **Original Amazon ELF offline audit PASSED; Stage 33 ISR flag alias CORRECTED.** No device changes. Real Profile 7 FEL residual composition remains **NOT PROVEN**.

## Why the correction matters

The owner-uploaded Stage 33 output **passed** 3 key names, 23 instructions, and 9 relocations, but its descriptive name **NEGATIVE_DV_FLAG_LATER_READ** equated two `[x25,#0x25c]` operations in different functions without tracking how `x25` was constructed. Stage 34 traced the register definitions and compared **absolute offsets from the actual original `hevc_state_s` struct**, named in DWARF. Thus the byte read in the interrupt is a *different field* from the byte written in the probe. An earlier assertion that the same flag was later rewritten was also unsupported because `x25` was rebased in the interrupt handler.

## Original private modules and verification

Both modules came from the owner's original `gazelle-fel-kernel-readonly-20261019-191050.zip` SHA-256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`.

- `amvdec_h265.ko`: `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`;
- `decoder_common.ko`: `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`.

All original ELF binaries remain private and are not committed to the repo.

## Reconstructed absolute offsets — actual original DWARF field names

| Executing scope | Register definition | Relative access | Absolute structure address | DWARF name |
| --- | --- | --- | --- | --- |
| `ammvdec_h265_probe` | `0xa1c: x25 = HEVC + 0x1082c` | `0xeec`, `0xfc0`: `+0x25c` | `0x10a88` | **`hevc_state_s.discard_dv_data`** |
| `ammvdec_h265_probe` | same register base | `0xf28`, `0xfc4`, `0xfe0`: `+0x248` | `0x10a74` | **`hevc_state_s.dv_duallayer`** |
| `ammvdec_h265_probe` | same register base | `0xfbc`: `+0x2c8` | `0x10af4` | **`hevc_state_s.metadata_config_flag`** |
| `vh265_isr_thread_fn` early path | `0x9fa0–0x9fb0: x25 = HEVC + 0x107fc` | `0xa548`: `+0x25c` | `0x10a58` | **`hevc_state_s.ip_mode`** |
| `vh265_isr_thread_fn` later path | `0xb190: adrp x25` | `0xc568`: `+0x25c` | **Not the established instance field** | `x25` is rebound to a page-relocated `.bss+0x50` target |

The `b190` `R_AARCH64_ADR_PREL_PG_HI21` relocation is verified as `.bss + 50`; do not treat the page-relative expression as an exact symbol address without the remaining relocation and path. **In no case does simply reusing `#0x25c` prove the same instance field.**

The original `decoder_common.ko` also independently confirms the `vdec_s` structure fields `master+0x38` and `slave+0x40`. ISR `0xc554/0xc55c` reads those pointer offsets from `x22`, which is sourced earlier at `0x9f14` by loading a decoder-context pointer. Its adjacent branches are conditional, not proof an EL slave was created on P7.

## What remains established

- The original HEVC probe recognizes the independent `negative_dv` and `dv_duallayer` keys; **`negative_dv` writes the field actually named `discard_dv_data`**.
- If successfully parsed, `parm_v4l_metadata_config_flag` can override both probe fields: bit 1 maps to `discard_dv_data`, bit 0 maps to `dv_duallayer`.
- The original ISR gate at `0xa548–0xa54c` branches based on `ip_mode`, **not** the probe's `discard_dv_data`.
- The later `0xc568` store is not sufficiently linked to the probe instance flag to conclude a runtime override. Other writes or indirect reads of `discard_dv_data` are not ruled out by this audit.
- Stage 28's P8 DOVI vs P7 HDR10 and `dveldec(0)` runtime boundary is unchanged. Nothing here proves actual P7 RPU parsing, paired EL decoding or FEL residual-sensitive pixels.

## Reproduction and audit boundaries

`tools/gazelle-fel/audit-stage34-hevc-register-bases.py` validates two owner-original SHA-256 modules, six original DWARF field offsets, **26 exact ARM64 instructions**, **seven direct `[x25,#offset]` sites across the complete `.text`**, and the `.bss` rebasing relocation. It rejects changed binaries/opcodes, and never reads a live kernel or device.

```bash
python3 tools/gazelle-fel/audit-stage34-hevc-register-bases.py --selftest
python3 tools/gazelle-fel/audit-stage34-hevc-register-bases.py /private/original-modules
```

Expected final marker: `GAZELLE_FEL_STAGE34_OFFLINE_PASS`. Public GitHub CI can run source-only selftests but not owner's proprietary kernel ELFs.

## Next: Stage 35

Use the **corrected, DWARF-named** `discard_dv_data`, `dv_duallayer` and `ip_mode` identities to inspect the full HEVC decoder for consumers using other register bases or indirect helpers. Avoid falsely asserting absence from an exact `[x25,#imm]` search. The goal remains an independently observable, instance-scoped P7 metadata and EL-pairing path—not a generic mode toggle. **No** system-property, sysfs, `0x301` or `0x179` writes, firmware/kernel patches or installed Kodi modifications.
