# Gazelle FEL Stage 20 — original kernel 0x301 config receiver and slave gap

**Date:** 2026-10-19. **Status:** SHA-PINNED_STATIC_VERIFIED; active native FEL residual **NOT PROVEN**.

This report follows the owner-provided `gazelle-fel-kernel-readonly-20261019-191050.zip` offline (Fire OS PS7702.4965N, Linux 5.4.125-ab27). Original private ELF modules are not committed or published.

| Original module | SHA256 |
| --- | --- |
| `stream_input.ko` | `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` |
| `decoder_common.ko` | `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b` |
| `amvdec_h265.ko` | `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040` |

## User-to-kernel configuration path

`stream_input.ko:amstream_do_ioctl_new`, `0x24bc`, processes **AMSTREAM_SET_PTR_CONFIGS = 0x301** separately from `amstream_ioctl_set()`'s scalar `0x179` metadata command. This is a key distinction from Stage 11.

- `0x29ec–0x29fc`: copies a fixed **16-byte descriptor** from userspace; `0x2a14/0x2a18` branches on descriptor command `0x301` to `0x2c64`.
- `0x2c64/0x2c68`: requires video capability on the port; `0x2c6c/0x2c70`: requires a non-null user data pointer.
- `0x2c74–0x2c80`: checks `length-1 <= 0xfff`, accepting **1–4096 bytes**. Zero and excessive length take common invalid argument handling.
- `0x2c84–0x2c94`: computes `vdec_s + 0x10db1`, and `0x2ca0` calls `__check_object_size`.
- `0x2cb0`: calls a local `__copy_from_user` wrapper at `0x7710`; wrapper in turn invokes `__arch_copy_from_user` at `0x7814`, independently checked by ARM64 call relocations. A failed copy branches to invalid argument handling at `0x2cb4`, without committing the configuration length.
- `0x2cb8–0x2ccc`: on successful copy, stores `config_len` at `vdec_s + 0x11db4`; then proceeds to common success handling.

The module's original **DWARF** establishes `vdec_s::config` at offset `0x10db1` as `char[4096]`, `config_len` at `0x11db4`, and `dolby_meta_with_el` at `0x11db9`. The three bytes between the 4096-byte array end and length field are alignment padding. This is the **kernel structure**, and is different from the vendor native userspace `codec_para_t` fields at `+0x10b4` (`config`, **512** bytes) and `+0x12b4` (`config_len`) established in Stage 18–19.

**Important:** the kernel's 4096-byte bound does not establish NUL termination for a 4096-byte input. It is not a bound for unsafe appending in the smaller userspace buffer. Kernel copy success is not equivalent to correct decoder-option parsing.

## HEVC consumes decoder-instance-specific configuration

`amvdec_h265.ko:ammvdec_h265_probe()`:

- `0x9c4/0x9c8` retrieves the associated vdec instance.
- `0xd44/0xd48` checks the instance `config_len`; zero bypasses the option parser.
- `0xd4c–0xd54` calculates the instance's `config[]` address `+0x10db1`.
- `0xd80–0xd88` passes that pointer to `get_config_int`. **16** ARM64 `R_AARCH64_CALL26` relocations to `get_config_int` exist between `0xd88` and `0x100c`. This proves actual parsing of instance-local configuration settings, not necessarily any particular Dolby key.

The previous active P7 capture's `[0]dv dual layer` log remains evidence of recognizing dual-layer signalling; it does not prove `dv_duallayer:1;` was accepted or that an enhancement decoder reconstructed FEL pixels.

## Master/slave configuration handoff still unresolved

Stage 11 proved the kernel can create a second vdec and attach `master/slave` pointers. Stage 12–13 show the P7 Dolby **frame** node typically prevents that initial creation. The 0x301 handler above writes **one vdec object's** buffer and length. It does not directly address `vdec->slave` at this code site.

Another observed path, `decoder_common.ko:vdec_init()` at `0x2ecc–0x2ee0`, conditionally calls `memcpy(slave + 0x50, master + 0x50, 0xf8)`. This **248-byte** early-structure transfer cannot transfer the later `config[]` at `+0x10db1`. It does **not** rule out other secondary configuration copies in other functions.

Therefore the **secondary vdec's effective `config_len` and metadata-with-EL state are unverified**, even if a stream device succeeds in creating it. Stage 21 should investigate whether subsequent initialization or the HEVC driver independently transfers the configuration to the enhancement-layer decoder.

## Error semantics

Stage 19 identified that Amazon userspace `set_video_codec_info()` can log but conceal the error status returned by ioctl `0x301`. Stage 20 shows the kernel does return errors for invalid length/pointer and copy failure. A future P7-only native backend must independently verify effective configuration and cannot assume `codec_init()==0` proves successful kernel option transfer.

## Reproducibility and safety

Offline Python audit `gazelle_fel_stage20_config_receiver_audit.py` passed on the original private modules, testing **37 addressed AArch64 instructions, seven call relocations, three DWARF offsets, the 4096-byte config array, and 16 HEVC parser calls**.

The full audit, results, and this technical report are supplied as a separate **nonproprietary** bundle. GitHub source-only CI must not download the vendor binaries.

**No device actions were made.** Do not write global stream/FEL properties, inject `0x301` or `0x179`, patch OMX or the kernel, or build a speculative APK. The integrated `android-firetv-unified`, working P8, HDMI passthrough, satellite, UDF and MMBD remain unchanged. Actual P7 FEL residual reconstruction is **not yet demonstrated**.
