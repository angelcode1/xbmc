# Gazelle FEL Stage 37 — original provider callback registration, Dolby interface and unresolved alias

**2026-10-20. ORIGINAL AMAZON MODULE OFFLINE AUDIT PASS; no new Cube access.** The owner-uploaded `stage36-audit-results(1).txt` passes exact HEVC `set_aux_data`, `dolby_get_meta` and `vh265_event_cb` checks. **True Profile 7 FEL residual pixel reconstruction remains NOT PROVEN.**

## What changed since Stage 36

Stage 36 validated the export callback's conditional pointer/length implementation but did not prove the callback was **wired into a frame provider's function table**. Stage 37 resolves that module-local wiring and the HEVC provider's name from **two original SHA-pinned Amazon Fire OS PS7702.4965N kernel modules**, not from compatible public sources.

| Original module | SHA-256 |
|---|---|
| `amvdec_h265.ko` | `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040` |
| `dovi_vs12.ko` | `7c59782906328a9a524719ac0df18ea5d6395d901ca035e3ad7cfed7a9025224` |

Both are read privately from `gazelle-fel-kernel-readonly-20261019-191050.zip` (SHA-256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`). No raw modules or proprietary bytes are committed.

## A. Five original frame-provider callback slots

Original `amvdec_h265.ko` declares local `vh265_vf_provider` as a 40-byte object at `.rodata+0x3ba0`. All five original ELF `R_AARCH64_ABS64` relocations resolve to named local functions:

| Provider-table offset | Function name | Original code VA |
|---|---|---|
| `0x3ba0` | `vh265_vf_peek` | `0x15608` |
| `0x3ba8` | `vh265_vf_get` | `0x7b58` |
| `0x3bb0` | `vh265_vf_put` | `0x4ef8` |
| **`0x3bb8`** | **`vh265_event_cb`** | **`0x15708`** |
| `0x3bc0` | `vh265_vf_states` | `0x15938` |

The original `vh265_init` path has a conditional branch at `0x3b98–0x3b9c` and then at `0x3bc0` calls `vf_provider_init`, followed by `vf_reg_provider` at `0x3bc8`. These call destinations and the original `vh265_vf_provider` pointer are validated by `R_AARCH64_CALL26` and `R_AARCH64_ADR_PREL_PG_HI21`/`ADD_ABS_LO12_NC` relocations. **These are compiled conditional paths; this does not establish registration executed during P7.**

## B. Original provider string is decoder.h265 — aliases remain unresolved

The registration code's name pointer resolves to original `.rodata+0x2c2d`, an exact NUL-terminated **`decoder.h265`** literal. The owner's earlier Stage 27–28 kernel-status observation exposed `dvbldec` and `dveldec` names in VFM and Dolby status endpoints.

These are **not necessarily an error or a mismatch**: the Amlogic frame routing/provider layer can use aliases and mappings, and working P8 demonstrates usable Dolby Vision under the same installed driver. The original installed built-in provider-dispatch implementation or alias mapping was **not** byte-inspected in this stage. Do not assume `decoder.h265` and `dvbldec` are identical, disconnected, or simultaneously registered merely from these snippets.

This name relationship is the **next useful read-only discriminator** if the corresponding provider-routing map is exposed. Previous Stage 28 reduced VFM output to provider counts; it did not preserve the entire mapping and registration graph.

## C. Callback's auxiliary-data path and Dolby entrypoint

Original `vh265_event_cb` contains a bit-7 event branch at `0x15748`. In the corresponding guarded path, it initializes its aux pointer and size to zero at `0x157a0/0x157a4`. After valid-picture checks at `0x157b4–0x157c4`, it can return the picture's aux pointer and size at `0x157dc/0x157f0`.

The original `dovi_vs12.ko` contains the expected `DV_func` callback table and `metadata_parser_process` function, and its `0xdc` relocation imports `register_dv_functions`. Stage 27 independently observed the `register_dv_functions` symbol on the installed kernel; Stage 26 provided a **compatible public source** showing a Dolby receiver that uses `VFRAME_EVENT_RECEIVER_GET_AUX_DATA`. Neither static module table nor the public source demonstrates that the **original built-in Fire OS receiver** actually issued this request during the owner's Profile 7 playback.

**We have two independently documented module-side interfaces, NOT a proven runtime end-to-end P7 metadata invocation.**

## Verification and limits

`tools/gazelle-fel/audit-stage37-provider-bridge.py` checks SHA-256 of the original ZIP and both AArch64 ELFs, six exact symbols, five data-function relocations, 20 exact ARM64 instructions, four provider/name-address relocations, the registration call relocations, original `decoder.h265` literal, and the Dolby registration import. The original-module audit succeeded, ending in `GAZELLE_FEL_STAGE37_OFFLINE_PASS`.

No extra runtime probes, ptrace, kprobes, eBPF, log clearing, device-setting changes, global decoder/stream-mode flags, direct kernel ioctls, Kodi installs or patches were needed. Both binaries remain local-only. GitHub Actions can run source-only syntax/selftests and cannot validate the private ELF unless the owner supplies it offline.

## Stage 38 decision

**Prefer a genuinely discriminating read-only provider-graph discovery** before asking for any new P7 test. Check whether existing non-mutating interfaces expose a mapping from `dvbldec` to `decoder.h265` and whether the provider receiving the Dolby auxiliary request is registered. If the installed frame-routing implementation cannot expose that state without instrumentation, return `NOT_OBSERVABLE`, rather than writing debugfs, inserting hooks or altering the working P8 decoder.

To prove true FEL, still require positive P7 metadata parsing, separate active EL decoder and **residual-sensitive output pixel evidence**, not only registration symbols and an HDR/Dolby label.
