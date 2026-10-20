> **CORRECTION — Stage 34, 2026-10-20:** The original HEVC DWARF and address-base audit established that Stage 33's `negative_dv` configuration write targets the field actually named `hevc_state_s.discard_dv_data` at offset `0x10a88`. The cited ISR read at `0xa548` uses a *different register base* and reads `hevc_state_s.ip_mode` at `0x10a58`. Furthermore, `x25` is rebased to a `.bss` relocation on a later ISR path; the `0xc568` write cannot be equated with the probe's `discard_dv_data` write. **Withdraw the Stage 33 claim that the same private flag is read/written at these ISR sites.** The three key names, bit override and probe writes remain verified. See [Stage 34](gazelle-fel-stage34-hevc-register-base-correction-20261020.md).

# Gazelle FEL Stage 33 — original HEVC configuration keys and override precedence

**2026-10-20. Original Amazon module static audit: PASS. Runtime P7 cause and FEL pixels: NOT PROVEN.**

## Stage 32 private evidence and decision

Original owner-uploaded `stage32-log-compare-20261020-014627.zip`, SHA256 `aa72082c2aa6d4e51a535a59bbd6292dd7d7e715632679daa0b09e0967736d75`, has two bounded, redacted phases and no raw Android log payload.

| Field | P8 | P7 |
|---|---:|---:|
| Dolby source-format node | DOVI | HDR10 |
| Log lines examined | 2,767 | 880 |
| `DVHE_COMPONENT` category | 41 | 41 |
| `KODI_FEL_MARKER` category | 1 | 1 |
| `CONFIG_301_UNSUPPORTED` category | 0 | 0 |
| `CONFIG_301_IOCTL_FAILURE` category | 0 | 0 |
| Dolby metadata parser failure category | 0 | 0 |
| Collector verdict | `NO_DIRECT_ERROR_SEEN_SUCCESS_UNKNOWN` | `NO_DIRECT_ERROR_SEEN_SUCCESS_UNKNOWN` |

Both report `reader_ok=true`, no truncation or overflow, but the raw messages were discarded by design. Distinct total line counts reflect a different amount of unrelated logging and do not prove 41 identical vendor transitions. Absence of a matching log message **does not establish successful ioctl 0x301, metadata parser execution or FEL decoding**. Do not repeat unchanged broad log captures.

## Original owner module and offline verification

Private original Fire OS PS7702.4965N ELF64 AArch64 `amvdec_h265.ko`:

`0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`

Retained outside Git, extracted read-only from the owner's original `gazelle-fel-kernel-readonly-20261019-191050.zip` (archive SHA256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`). Offline script `tools/gazelle-fel/audit-stage33-original-hevc-config.py` passes exact module hash, 23 AArch64 instruction/operand gates, three `get_config_int` call relocations, six string-pointer relocations, and three exact NUL-terminated named keys in original `.rodata`.

## New evidence from actual original kernel binary

| Key in HEVC probe | Original ELF evidence | What it proves |
|---|---|---|
| `negative_dv` | `.rodata + 0xed8`; `get_config_int` at `0xec8`; success branch `0xecc` then `0xeec` writes `x25+0x25c` | Separately parsed Boolean/private HEVC flag |
| `dv_duallayer` | `.rodata + 0x2448`; `get_config_int` at `0xf04`; success branch `0xf08` then `0xf28` writes `x25+0x248` | Independently parsed Boolean/private HEVC flag |
| `parm_v4l_metadata_config_flag` | `.rodata + 0x1573`; `get_config_int` at `0xfa8`; `0xfac` checks success; `0xfb4/0xfb8` extracts bits; `0xfc0/0xfc4` stores them | **When this third key parses successfully, its bit 1 overwrites `negative_dv` state and bit 0 overwrites `dv_duallayer` state** |

A later `vh265_isr_thread_fn` loads the former flag at `0xa548` and branches on it at `0xa54c`. That function also writes the flag at `0xc568` under a separate later condition. The flag is **mutable after the probe**. These references do not prove how it affects the current P7's RPU processing or output.

**Important separate input contracts:** The original userspace Awesome path *may* append `negative_dv:1;`, while the distinct older Amlogic setup path *may* append `dv_duallayer:1;` (Stage 30). The original kernel recognizes both names, but no captured runtime data demonstrates that either native path submitted either key in actual P7 playback, let alone which setting survived later `parm_v4l_metadata_config_flag` or ISR changes.

This resolves a *static name-to-register field* ambiguity, not the HDR10 root cause. Do **not** infer that writing `negative_dv`, `dv_duallayer` or `parm_v4l_metadata_config_flag` will enable FEL. These are unsafe globally applied runtime experiments without a validated instance-scoped protocol and rollback. Continue to avoid stream-mode property toggles, direct ioctls 0x301/0x179, kernel parameter writes, vendor patches and speculative Kodi APKs.

## Reproducibility

The companion offline macOS ZIP contains the exact audited Python source, SHA-verified runner, and instructions. The runner uses the original owner kernel ZIP in `~/Downloads`, extracts only the matching original HEVC module to a **private local folder**, and invokes the verifier. It requires LLVM objdump and GNU readelf, but **no ADB and no device access**.

```sh
python3 tools/gazelle-fel/audit-stage33-original-hevc-config.py --selftest
python3 tools/gazelle-fel/audit-stage33-original-hevc-config.py /private/original/amvdec_h265.ko
```

Local final marker: `GAZELLE_FEL_STAGE33_ORIGINAL_HEVC_OFFLINE_PASS`. GitHub CI runs **only** syntax and selftest; private Amazon ELFs must not be added to CI or Git.

## Next bounded question — Stage 34

Trace **downstream consumption of original HEVC private flags** (`+0x25c` and `+0x248`) and any independent Dolby/RPU predicate in the original ELF, while preserving conditional branches and avoiding claims about the P7 runtime values. If static analysis cannot prove a necessary gate, ask for a narrowly scoped read-only observable that distinguishes active P7 from working P8. The acceptance bar for true FEL remains independently reconstructed EL residuals changing visible output pixels, not just a recognized profile, provider name or Dolby indicator.
