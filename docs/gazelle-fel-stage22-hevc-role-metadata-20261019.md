# Gazelle FEL Stage 22 — zero-config HEVC probe and role-aware Dolby metadata

Date: 2026-10-19, Australia/Brisbane. **Result: OFFLINE SHA-PINNED STATIC PASS; runtime P7 FEL unproven.** No kernel, Kodi, Magisk, audio, optical or device configuration changes.

## Original Amazon evidence, never redistribute raw binaries

The owner-supplied PS7702.4965N / Linux 5.4.125-ab27 module archive `gazelle-fel-kernel-readonly-20261019-191050.zip`, verified offline:

| Module | SHA256 |
| --- | --- |
| `amvdec_h265.ko` | `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040` |
| `decoder_common.ko` | `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b` |
| `stream_input.ko` | `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` |

Original ARM64 disassembly and ELF symbol table identify `amvdec_h265.ko:ammvdec_h265_probe` at `0x098c`, `dolby_get_meta` at `0xdc10` and `set_aux_data` at `0xcee0`. The original `R_AARCH64_CALL26` relocations at `0xdc88` and `0xdcc0` both resolve to local `set_aux_data`, **not** just adjacent textual references.

## Question 1: does a newly allocated slave need nonzero config_len to initialize?

**No unconditional failure from a zero config length is visible in the original HEVC probe:**

- `0x09c4–0x09c8` retrieves the vdec instance associated with this HEVC probe.
- `0x0d44–0x0d48` reads the **current instance's** `config_len` (reached via base `+0x10c98+0x111c`) and, if zero, branches to `0x1024`, **skipping the `get_config_int` option-parsing block**.
- On that alternative route, `0x1024–0x1050` checks an **independent pointer at vdec+0x208**, optionally copies a small parameter block into the HEVC private structure, and then branches to common probe setup at `0x10e4`. If the pointer is absent, `0x10d8–0x10e4` establishes an alternative default and continues.
- Thus `config_len==0` means no parsing of the instance's explicit option string. It is **not an immediate decoder-probe failure**. Whether the resulting defaults suffice for EL decoding remains an open question.
- HEVC has additional **role-aware state handling** in the probe: `0x1270–0x127c` records whether the current vdec has a master; `0x1280–0x12a4` can select the counterpart (`master` or `slave`) and copy a word from its private-state field `+0xa88`. That is **not** a copy of the kernel `config[4096]` string.

Earlier Stage 21 analysis still stands: a new slave starts from zeroed `vdec_s`, the documented 248-byte master-to-slave copy excludes `config[]`, and `0x301` writes the port-selected primary's config. But the new HEVC code **weakens the assumption** that the slave must receive a duplicate string to initialize.

## Question 2: how does HEVC metadata actually consider master and slave?

`amvdec_h265.ko:dolby_get_meta()` at `0xdc10`:

1. `0xdc28–0xdc34` obtains the **current** HEVC private state's vdec pointer.
2. `0xdc60–0xdc68` reads **that vdec's `dolby_meta_with_el`** byte at offset `0x11db9`.
3. If the byte is nonzero (`0xdc6c`), or the current vdec has a non-null **slave** (`0xdc70–0xdc74`), it takes a direct `set_aux_data(current buffer, ..., mode=0)` path at `0xdc78–0xdc88`.
4. Otherwise, `0xdc9c` checks the current vdec's **master**. With a master present, `0xdca4–0xdcbc` retrieves the master's HEVC private-state pointer via offset `0x11e40` and its metadata buffer at `+0xa28`; `0xdcc0` invokes `set_aux_data` with an argument value `1`. The function then invokes `set_aux_data` again with the **current** instance's buffer and argument value `2` at `0xdcc4–0xdcd4`.
5. Without either link, `0xdcd8–0xdcf4` contains a separate conditional single-decoder fallback.

The constants 0/1/2 above are **actual argument values**. Their exact public semantic names and the internal behavior of `set_aux_data` have not been established; do not label them conclusive BL/EL pixel reconstruction.

**Important:** a zero `dolby_meta_with_el` on a slave does **not** categorically disable Dolby metadata processing. The master-linked branch has a dual-buffer path. Conversely, these paths do **not** prove that the slave's metadata and residual are correctly interpreted on the installed Fire OS build.

## Runtime boundary, and revised next priority

Observed active P7 in Stage 13 still uses `/dev/amstream_dves_hevc_frame`, `port->type=0x1d11`, `dveldec(0)`; P8 uses the same frame port and yields working Dolby Vision. The frame port's `PORT_TYPE_FRAME` bit skips the **default** second `vdec_create` branch, whereas the initial Dolby HEVC stream port `0x1911` is eligible to attempt paired creation. No stream-mode test was performed here.

Stages 20–22 together distinguish:
- **Port/decoder allocation**: demonstrated conditionally, not active for current frame path.
- **HEVC probe with empty config**: continues through fallback, so no automatic failure on that fact alone.
- **Metadata propagation**: current instance has role-aware master/slave paths and a 0/1/2 argument contract, but its callee's option flags and data behavior need another bounded audit.
- **FEL reconstruction**: still requires an actual running paired decoder, valid metadata and independent residual-sensitive output, not a Dolby badge or `[0]dv dual layer` message.

**Stage 23:** follow `set_aux_data(0xcee0)` and its exact mode 0/1/2 argument handling, frame/metadata buffer provenance, length and error cases, then decide whether a read-only runtime diagnostic could add new evidence. Continue to avoid global `media.omx.stream_mode`, `nal_skip_policy` and `dolby_meta_with_el` changes, direct 0x179/0x301 injection, or a speculative Kodi APK.

## Reproducibility

`tools/gazelle-fel/audit-stage22-hevc-role.py` fails closed on **three exact kernel SHA pins** and ELF64/AArch64 identity, checks **53 instruction patterns**, three original local function symbol VAs and **three relocations**, then emits:

`GAZELLE_FEL_STAGE22_HEVC_ROLE_PASS`

GitHub CI performs only the source syntax/selftest. The full audit ran offline against original owner-provided private modules. This does **not** demonstrate live FEL residual processing.
