# Gazelle FEL Stage 36 — original HEVC metadata assembly and callback export, no direct flag linkage

**20 October 2026. Original Amazon ELF offline audit PASS. Actual P7 metadata consumption, enhancement decoding and FEL pixels NOT PROVEN.**

## Owner-supplied Stage 35 checkpoint

`stage35-audit-results(2).txt` confirms `GAZELLE_FEL_STAGE35_ORIGINAL_HEVC_OFFLINE_PASS`, including six correct DWARF fields, 30 instruction checks, four relocations and two confirmed false short-offset aliases. Specifically:
- `hevc_state_s.discard_dv_data` at **+0x10a88** is the original `negative_dv` probe key's destination;
- `hevc_state_s.dv_duallayer` at **+0x10a74** is the separate dual-layer probe key's destination;
- ISR's `x25+0x25c` near `0xa548` is **ip_mode**, not discard_dv_data;
- similarly `last_pts+0xa74` and `shift_byte_count_lo+0xa88` are not dual-layer/discard fields.

This correction is a prerequisite for Stage 36; **never infer identical structure fields solely from the same relative register offset**.

## Input and offline verification

Original Amazon Fire OS PS7702.4965N `amvdec_h265.ko` SHA256:

`0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`

Privately extracted from original `gazelle-fel-kernel-readonly-20261019-191050.zip`, SHA256:

`02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`

The new `tools/gazelle-fel/audit-stage36-meta-export-gates.py` runs only offline disassembly and original symbol/relocation inspection. It verifies **50 exact AArch64 instruction operands**, **three local function identities and sizes**, **three actual call relocations**, and conducts an **explicit bounded direct-offset census** in the complete three named function bodies. Proprietary kernel binaries are private, never committed to Git. Stage 36 does not execute the module.

| Original function | Symbol range | Instructions inspected in full | Discriminating finding |
|---|---|---:|---|
| `set_aux_data` | `0xcee0–0xd318` (1,080 B) | 270 | DMA/tag select, allocate/copy, clear on failure; no direct instruction operand naming either corrected flag offset |
| `dolby_get_meta` | `0xdc10–0xdcf8` (232 B) | 58 | Current buffer vs master/current tag-selector split using `vdec_s.dolby_meta_with_el` and master/slave links |
| `vh265_event_cb` | `0x15708–0x15938` (560 B) | 140 | Sets caller aux pointer and length to zero before conditional valid-picture lookup; only on successful lookup exports the picture's aux pointer and size |

### Connection 1 — Dolby role-aware metadata selection

In `dolby_get_meta`:
- `0xdc60–0xdc6c` reads `vdec_s.dolby_meta_with_el` at **+0x11db9**;
- `0xdc70–0xdc74` checks `vdec_s.slave` at **+0x40**;
- `0xdc78–0xdc88` uses the current buffer and selector **0**, when the metadata-with-EL bit is set or a slave exists;
- otherwise `0xdc9c–0xdcc0` checks `vdec_s.master` at **+0x38** and calls the local `set_aux_data` for the master's buffer with selector **1**; `0xdcc4–0xdcd4` then sends the current buffer with selector **2**.

Relocations at **0xdc88** and **0xdcc0** directly target local `.text+0xcee0`. This proves compiled call linkage, not calls happening during P7 playback. As Stage 23 independently established, selectors **1** and **2** select tag-1 entries and other valid tags respectively. These are metadata entries, **not** proven base-layer pixels or FEL residuals.

### Connection 2 — assembled aux output may be empty

`set_aux_data` uses the original HEVC DMA auxiliary address at **+0x8f0**, a tag selector and original `vzalloc` relocation at **0xd0cc**. The null-buffer guard exits early, and allocation failure reaches **0xd2f4/d2f8** to clear the destination pointer/length. The output is therefore **not guaranteed populated** merely because metadata assembly was requested.

The event export `vh265_event_cb` at **0x157a0/0x157a4** zeros its caller's pointer and size before validating the per-picture reference. The `0x157b4–0x157c4` picture-index and null checks precede **0x157d0/0x157dc** (aux pointer) and **0x157ec/0x157f0** (aux length). This is positive evidence for a **conditional callback contract**: event invocations can return no auxiliary payload.

### What Stage 36 does *not* prove

The 468 instructions across these three function bodies do not contain a direct `[register,#0x248/#0x25c/#0x10a74/#0x10a88]` memory operand, validated against the full symbol bounds. Those offsets mean different things under different register bases, and indirect aliases, helper calls, firmware, pre-assembly filtering, and other consumers **are not excluded**. In particular:

- **Not proven:** `discard_dv_data` or `dv_duallayer` controls exported payloads or their absence during current P7 playback;
- **Not observed:** a non-empty P7 auxiliary payload reaching the receiver, RPU processing by the registered Dolby parser, master/slave EL allocation, the ELF vendor 0x301 outcome, or visible EL residual reconstruction;
- **Not justified:** modifying global `negative_dv`, `dv_duallayer`, `parm_v4l_metadata_config_flag`, stream-mode properties, `dolby_meta_with_el`, or raw `0x179/0x301` ioctls.

Stage 28 measured active P8 as DOVI and P7 as HDR10 with `dveldec(0)`. Stage 32's passive filtered logging found no explicit 0x301 or parser failure, which is **inconclusive** because the actual ioctl return wasn't recorded. Nothing in Stage 36 overturns those observations.

## Reproduce on Mac

The standalone macOS ZIP verifies its downloader source against an exact Git blob SHA; it verifies the original owner module archive and extracts **only** `amvdec_h265.ko` to a private local folder; it runs `--selftest` and the full offline audit.

Alternatively, with locally extracted original module:

```bash
python3 tools/gazelle-fel/audit-stage36-meta-export-gates.py --selftest
python3 tools/gazelle-fel/audit-stage36-meta-export-gates.py /private/path/amvdec_h265.ko
```

Expected marker: `GAZELLE_FEL_STAGE36_ORIGINAL_HEVC_OFFLINE_PASS`. GitHub CI checks only source syntax/selftest; it does **not** publish or download Amazon's private ELF.

## Next decision — Stage 37

Since static flag→metadata causation remains unverified, prioritize a **non-mutating, instance-scoped active callback/aux-data observation design**, or continue inspecting an independently verified receiver's dataflow if runtime observation is unsafe or unsupported. In particular, test whether an actual P7 `VFRAME_EVENT_RECEIVER_GET_AUX_DATA` request delivers a **non-empty buffer**, and distinguish that from the separate absence of an EL vdec. Do not add runtime hooks, ptrace/eBPF instrumentation, kernel probes, decoder-property writes or Kodi APK patches without a separate explicit safety review and an opt-in test plan. Only a residual-sensitive BL-vs-BL+EL pixel oracle could prove actual FEL reconstruction.

Known-good P8, HDMI passthrough, Kodi, Magisk, optical UDF/MMBD and voice satellite remain untouched.
