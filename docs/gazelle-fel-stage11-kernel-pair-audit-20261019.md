# Gazelle FEL Stage 11 — exact Fire OS kernel paired-decoder evidence (2026-10-19)

This report covers a **read-only offline** audit of the user's `gazelle-fel-kernel-readonly-20261019-191050.zip` (SHA256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`). All six pulled `.ko` files pass their SHA256 manifest, AArch64 ELF and DWARF checks. Platform: Fire OS `PS7702.4965N`, Linux `5.4.125-ab27`. The raw proprietary kernel modules are **not** published.

## Decisive new result: kernel has a real secondary-decoder allocation path

`stream_input.ko` SHA256 `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c`: `amstream_open` at `0x1320`.

- `0x1610`: primary `vdec_create(port, NULL)`; exact symbol established by `R_AARCH64_CALL26` relocation.
- `0x1620`: if bit 10 (`0x400`) in **`port->type`** is set, skip the secondary-decoder path.
- `0x1628`: bit 12 (`0x1000`) in **`port->type`** takes the second-decoder path.
- Otherwise `0x162c` calls `vdec_get_debug_flags`, and `0x1630` checks bit 8 (`0x100`) for a possible alternative entrance.
- `0x163c`: second call to `vdec_create(port, primary)`; `0x1644` writes the pointer to `primary+0x40`; `0x1650` checks it for null.
- **These are checks on `port->type`, not on `vdec->port_flag`. The symbolic meanings are not established by this exact ELF, and neither bit is verified as a FEL switch.** Which branch active P7 takes is unmeasured.

`decoder_common.ko` SHA256 `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`: `vdec_create()` at `0x824` assigns `new->master=primary` at `0x944`, `primary->slave=new` at `0x948`, and marks master-state at `0x94c` when supplied a master pointer. Independently the original `struct vdec_s` **DWARF** describes `master` at `0x38` (56), `slave` at `0x40` (64). This confirms paired *creation* can occur, beyond the mere presence of struct fields.

## Metadata-with-EL is truly per-instance and slave-aware

`stream_input.ko:amstream_ioctl_set()` uses `R_AARCH64_CALL26` relocations to call `vdec_set_dv_metawithel` at `0x7454` for the primary, and conditionally at `0x7480` for `primary->slave` (loaded from offset `0x40` at `0x7474`). The second call requires a non-null slave and passes additional flags/debug gates; it is **not** unconditional.

`decoder_common.ko:vdec_set_dv_metawithel()` at `0x4ac` writes a Boolean byte to `vdec+0x11db9` at `0x4e4`. The original `vdec_s` DWARF names this field **`dolby_meta_with_el`** at `0x11db9`.

`amvdec_h265.ko` SHA256 `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`: `dolby_get_meta()` at `0xdc10` reads this per-instance field at `0xdc68`, and consults `vdec->slave` at `0xdc70` and `vdec->master` at `0xdc9c`. The HEVC module also contains BL/EL-specific state and strings `dv_enhance_exist`, `To decode el (poc ...)`, `Clear bl ... dv_enhance_exist flag`. Their presence alone does not establish active residual reconstruction.

`dovi_vs12.ko` identifies its module name as `dovi` via `.modinfo`, matching the loaded `dovi` in `proc-modules.txt`; no mismatch is implied by the on-disk file name.

## What this changes and what it does not

**Resolved:** Fire OS's 5.4 kernel has an actual conditional second-vdec creation path, real master/slave relationships, per-instance EL metadata control, and HEVC BL/EL metadata logic. This narrows the failure investigation to the creation/configuration **conditions** and later decode/metadata processing, rather than an absolute absence of kernel support code.

**Not resolved:** whether the active Kodi P7 playback sets the relevant port flags, creates a slave decoder, invokes `0x179` with suitable values, or reconstructs an FEL residual. Earlier P7 evidence has `[0]dv dual layer` but active `dveldec(0)` and `HDR10 FORMAT_HDR10`; P8 correctly yields DOVI. Previous `vdec->port_flag` log values `0x102` and `0x10b` are **not comparable to these `port->type` checks**; they are different fields. The debug flag alternative is likewise unmeasured. Do not force bits/properties/decoder ioctls based on this static information.

## Reproducibility and next gate

The standalone local `gazelle_fel_stage11_kernel_audit.py` validated all **6** SHA-pinned ELF64 AArch64 modules, **24** exact ARM64 instruction patterns, **6** relocation targets, **3** original DWARF offsets and **5** HEVC EL-related markers. It completed `GAZELLE_FEL_STAGE11_OFFLINE_PASS instruction_checks=24`. Its audit output and script were delivered privately; the raw modules were not committed.

**Next:** statically trace which port-type bits are set by the **frame** and **stream** Dolby HEVC amstream opens and how those flags reach the conditional second `vdec_create()`. A suitable hypothesis test should compare P7 vs P8 **at the open/port flags boundary**, not just Docker/Kodi packet counts. Avoid live `media.codec` injection, a speculative stream-mode property toggle, `nal_skip_policy`/`dolby_meta_with_el` sysfs writes, external `0x179` injection, or transplanting CoreELEC kernel modules. Preserve P8 playback, satellite, passthrough and optical UDF/MMBD.
