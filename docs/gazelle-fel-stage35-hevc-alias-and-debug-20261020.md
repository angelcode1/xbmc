# Gazelle FEL Stage 35 — original HEVC name/offset aliases and bounded dual-layer diagnostic consumer

**2026-10-20.** Owner Stage 34 audit passed unchanged (original `amvdec_h265.ko` and `decoder_common.ko`, six DWARF fields, 26 ARM64 instruction checks, seven reference sites, one relocation). **Original Stage 35 HEVC offline audit passed separately on the original HEVC module.** P7 runtime cause and FEL reconstruction remain **NOT PROVEN**.

## Stage 34 correction carried forward

The HEVC probe's `negative_dv` configuration key populates `hevc_state_s.discard_dv_data` at absolute offset `0x10a88`. `dv_duallayer` populates distinct `hevc_state_s.dv_duallayer` at `0x10a74`. The third configuration key `parm_v4l_metadata_config_flag`, when parsed, can overwrite these two flags with bits 1 and 0 respectively.

An earlier claim that ISR `0xa548` reads `discard_dv_data` was **wrong**: ISR's different `x25` base resolves the read as `hevc_state_s.ip_mode` at `0x10a58`. The later store at `0xc568` follows a `.bss` register rebase and is not the probe flag. Stage 34 corrected the Stage 33 doc.

## New Stage 35 original DWARF evidence

Original SHA-pinned Amazon Fire OS PS7702.4965N `amvdec_h265.ko`:

`0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`

| Offset from actual `hevc_state_s` base | Original DWARF field | Access example | Alias interpretation |
|---|---|---|---|
| `0x0a74` | `last_pts` | `post_video_frame:0x5860/0x5888` via `x20` | Timestamp accounting; **not** `dv_duallayer` |
| `0x0a88` | `shift_byte_count_lo` | `vh265_isr_thread_fn:0xa324` via `x19` | Bitstream offset accounting; **not** `discard_dv_data` |
| `0x10a58` | `ip_mode` | `ISR:0xa548`, derived via `x25=HEVC+0x107fc` | Previous Stage 34 correction |
| `0x10a74` | `dv_duallayer` | `probe:0xf28/0xfc4/0xfe0`, derived via `x25=HEVC+0x1082c` | Original Dolby dual-layer option |
| `0x10a88` | `discard_dv_data` | `probe:0xeec/0xfc0`, same `+0x1082c` base | Original `negative_dv` target |
| `0x10af4` | `metadata_config_flag` | `probe:0xfbc` | Later bit override source |

The `0xa74` and `0xa88` values are not partial references to the larger `0x10a74`/`0x10a88` addresses. These are **distinct original DWARF members**. Unlike substring-based greps, the verified instruction reads use different loaded base pointers and full offsets.

## New Stage 35 direct dual-layer read: diagnostic, not an EL allocator

In `ammvdec_h265_probe`, `0xfe0: ldrb w8,[x25,#0x248]` reads the **correct** `dv_duallayer` field; `0xfe4: cbz w8,0xffc` skips the next block when false. When nonzero, `0xfe8/0xfec` set up a pointer to exactly **`dv_duallayer\n`**, pinned in the original `.rodata+0x25fa` by two relocations. `0xff0` passes the decoder context, `0xff4` selects log parameters, and `0xff8` calls the original module's `hevc_print` function in `.text+0x138` (verified relocation).

**The inspected `0xfe0–0xffc` branch is a diagnostic print route, not a demonstrated device, EL decoder allocation or FEL residual reconstruction call.** The same module has other conditional Dolby gates and possible indirect/accessor consumers; the check does **not** prove no code path consumes `dv_duallayer` or `discard_dv_data` elsewhere.

The exact complete direct-reference census for `[x25,#0x248]` (three sites) and `[x25,#0x25c]` (four sites) was checked across the complete original `.text`, but **register/offset matching is not whole-program pointer-alias analysis**. It must not be extrapolated to other registers, pointer aliases, writes via `memcpy`, or firmware behavior.

## Verification, reproducibility and safety

`tools/gazelle-fel/audit-stage35-hevc-alias-consumers.py` verifies exact original SHA, ELF64 ARM64, **six original DWARF field names/offsets**, **30 exact machine-instruction sites**, **seven x25 direct-reference sites**, four relocation identities (including `.bss` rebase), and the literal `dv_duallayer\n` string in original `.rodata`.

Local original-binary marker: `GAZELLE_FEL_STAGE35_ORIGINAL_HEVC_OFFLINE_PASS`.

For a Mac with original `gazelle-fel-kernel-readonly-20261019-191050.zip` under Downloads, the companion ZIP contains a SHA-pinned offline runner to extract and audit only the original `amvdec_h265.ko`. GitHub CI is **source-only**; no proprietary Amazon modules are uploaded or committed.

**Safety:** no ADB, codec property/ioctl experiments, kernel sysfs writes, firmware/decoder patch, Kodi install, Magisk modification, or changes to working Profile 8, passthrough, PTT satellite or optical UDF/MMBD.

## Stage 36 priority

Do not repeat broad logcat scans or try `negative_dv:1;` as a magic FEL switch. Audit the original HEVC **auxiliary metadata event path** `set_aux_data` and `vh265_event_cb` against the installed Dolby receiver interface and separate EL/master-slave lifecycle. In particular, inspect whether `discard_dv_data` affects per-picture auxiliary records in a provable code path, using true absolute structure addresses and verified call edges. If unsupported, mark the link unresolved; true FEL still requires a running EL decoder and residual-sensitive output proof.
