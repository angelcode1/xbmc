# Gazelle FEL Stage 21 — separate primary/slave init and EL metadata reset

**Date:** 2026-10-19. **Status:** original Amazon kernel `STATIC_VERIFIED`; active P7 FEL reconstruction **NOT PROVEN**.

This audit uses the six original user-supplied Fire OS PS7702.4965N kernel modules from `gazelle-fel-kernel-readonly-20261019-191050.zip`; the three directly relevant modules are:

| Original ELF64 AArch64 kernel module | SHA-256 |
| --- | --- |
| `stream_input.ko` | `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` |
| `decoder_common.ko` | `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b` |
| `amvdec_h265.ko` | `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040` |

All proprietary kernel binaries remain private. No device/system/SELinux/Magisk/Kodi changes.

## Stage 21 result 1 — newly created slave has separate initial state

`decoder_common.ko:vdec_create` uses a `vzalloc` relocation at **`0x8a0`**, passing its newly allocated vdec pointer to `vdec_input_init` at **`0x920`**. A newly allocated `vdec_s` therefore starts with zero-initialized storage rather than being allocated as a byte-for-byte clone of the primary.

When a primary pointer is supplied, `0x944` stores it in `new_vdec->master` (`+0x38`) and `0x948` writes `new_vdec` to `primary->slave` (`+0x40`). Both offsets were previously confirmed by the original DWARF.

The original `decoder_common.ko:vdec_init()` performs the **conditional** copy at `0x2ecc–0x2ee0`: `memcpy(slave+0x50, master+0x50, 0xf8)`. The copied interval is `[0x50,0x148)`, far below the instance's `config[4096]` at `0x10db1`, `config_len` at `0x11db4` and `dolby_meta_with_el` at `0x11db9`. **That one copy does not transfer any of the latter fields.** Other transfer mechanisms remain possible.

## Stage 21 result 2 — separate calls to initialize primary and slave

`stream_input.ko:amstream_port_init()`:

- `0x1ab4` initially loads primary/port pointers.
- `0x1f6c/0x1f88` calls `vdec_init(primary,...)` on one normal video initialization route.
- `0x1f90–0x1fa0` checks the relevant port state and conditionally allows secondary initialization.
- `0x1fa8/0x1fc4` explicitly loads **`primary->slave`** from `+0x40` and calls `vdec_init(slave,...)`. The call is conditional, not guaranteed on every open.
- A third `vdec_init()` call at `0x1df4` covers another initialization route. These three sites were cross-checked against `R_AARCH64_CALL26` relocations.

Thus paired allocation, primary initialization and slave initialization are **separate gates**. It is incorrect to assume that attaching the slave automatically configures or initializes it for FEL.

## Stage 21 result 3 — the 0x301 handler and HEVC probe use an instance-local config

`stream_input.ko:amstream_do_ioctl_new()`, in its verified `0x301` branch:

- `0x2c84` selects the **port's primary vdec pointer** (`[x20]`).
- `0x2c88–0x2c94` addresses its `config[]` at offset `0x10db1`.
- `0x2ccc` stores `config_len` at offset `0x11db4` in that same vdec. This handler contains **no direct `primary->slave` config write**.

In `amvdec_h265.ko:ammvdec_h265_probe()`, `0x9c4/0x9c8` gets its associated vdec instance. `0xd44` checks **that instance's** `config_len`, and `0xd48` skips the config parser if the length is zero. `0xd4c–0xd88` computes **that instance's** config pointer at `+0x10db1` and passes it to `get_config_int()` otherwise.

This is strong evidence that a freshly allocated slave needs a **separate configuration transfer if its HEVC probe relies on options**. It does *not* prove that the slave must parse the same configuration as the master, nor that another path does not supply it.

## Stage 21 result 4 — native EL metadata flag may be reset during decoder init

`decoder_common.ko:vdec_set_dv_metawithel()` uses `0x4cc–0x4e4` to write a Boolean at **`vdec->dolby_meta_with_el`** (`+0x11db9`). In the distinct `vdec_init()` path `0x2f88–0x2fd0`, conditional branches converge on `0x2fc4` which **writes zero to the same field** at `0x2fd0`. Other branches skip that clear (for instance conditional departures toward `0x30cc` or `0x31d4`).

`stream_input.ko:amstream_ioctl_set()` calls `vdec_set_dv_metawithel(primary)` at `0x7454`, then, on certain driver-port or debug conditions and only when the pointer is non-null, calls **`vdec_set_dv_metawithel(slave)`** at `0x7480`. Both calls are independently bound by ARM64 relocation entries. A hypothetical metadata write **before** a later clearing initialization could be lost. Actual runtime ordering in P7 was not recorded; do not claim this happened.

## Interpretation and next gate

**Proved statically:** the Amazon kernel can create a zero-initialized secondary instance, explicitly initialize that secondary instance, parse instance-specific HEVC configuration and set/reset instance-specific metadata-with-EL. Neither the 248-byte master-to-slave copy nor the `0x301` receiver transfers the config to the slave.

**Not proved:** which initialisation branches execute on actual P7, whether another path populates the slave config, whether `0x179` runs after the final `vdec_init`, whether both HEVC instances become connected/running, and whether a residual-sensitive FEL output differs from BL-only output.

The full **offline-only** Stage 21 verifier checked **43 original AArch64 instruction patterns and seven call relocations**, all three exact module hashes, and ended with `GAZELLE_FEL_STAGE21_PAIR_LIFECYCLE_PASS`. Source-only CI cannot include user proprietary modules.

**Next:** examine HEVC probe and its master/slave-specific branches and kernel option-parser behavior, then devise a **read-only** live check if it genuinely adds evidence. Avoid global decoder-mode toggles, changing `nal_skip_policy`, raw `0x301` or `0x179` injection, installing an unproven Kodi native backend, or changing any shared audio/voice/optical setup. Preserve working P8 and integrated Kodi.
