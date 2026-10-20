# Gazelle FEL Stage 39 — original Dolby provider name selection resolved

**2026-10-20. Owner's Stage38 9-sample runtime ZIP verified; original Amazon kernel provider naming audit PASSED. P7 FEL reconstruction NOT PROVEN.**

## Owner Stage 38 capture — private primary runtime evidence

Owner-uploaded `stage38-provider-graph-20261020-034700.zip` SHA256:

`ce556f193feb62c8b617046517c292ad7795f0aadc6e720b89a5cf9856d625da`

The ZIP archive integrity check succeeded. The owner-submitted `gazelle-fel-stage38-v1` JSON contains exactly three phases `idle/P8/P7`, each with three sequenced samples, all four read-only sysfs probes reporting `OK`. `DEVICE_WRITES=NONE` in the source audit; the capture collector did not retain raw sysfs strings.

| Live signal | Idle, all 3 | Working P8, all 3 | P7 test, all 3 |
|---|---|---|---|
| Dolby source inst1 | HDR10 label, **inactive/stale** | DOVI | HDR10 |
| vdec status parser | NO_VDEC | NONEMPTY_UNCLASSIFIED | NONEMPTY_UNCLASSIFIED |
| VFM registered providers | Empty | **dvbldec** | **dvbldec** |
| `dvblpath` route count | 0 | 1 | 1 |
| `dvelpath` route count | 0 | 0 | 0 |
| `decoder.h265` registered | No | No | No |
| VFM route count / provider section | 7 / present | 7 / present | 7 / present |

All phases retain the same configured VFM routes, receiver-list entries, and `dv_provider` known tokens `dvbldec/dvbldec2`. This is not an actual alias mapping; those tokens may be configuration. The Stage 38 `vdec_status` coarse parser classified active statuses `NONEMPTY_UNCLASSIFIED` (not `HEVC_REPORT`), so do not claim Stage 38 alone proved the active codec type. Stages 13/28 independently measured HEVC decoder behavior.

**Stage 38 discrimination:** the active provider registry and route counts are **the same for P8 and P7**; only Dolby source classification differs (DOVI vs HDR10). There is no evidence here of a P7-specific missing BL provider. Absence of registered `dveldec` and zero dvelpath counts means no visible EL provider, but is not alone a hardware memory/decoder-pointer proof. True FEL pixel reconstruction remains unproved.

## Original Amazon binary names, not merely a public-source analogy

Original owner archive `gazelle-fel-kernel-readonly-20261019-191050.zip`, SHA256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`:

- `amvdec_h265.ko`, SHA256 `0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040`;
- `decoder_common.ko`, SHA256 `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b`.

Original `amvdec_h265.ko:ammvdec_h265_probe` composes the instance provider name in a 16-byte field at **vdec+0x10c98**; code at `0x1268–0x126c` calls `snprintf` after selecting the format pointer. The exact literal addresses and compiled relocations establish these four names:

| Name | Original `.rodata` offset | Selection role |
|---|---|---|
| `dvbldec` | `0x0a9d` | BL-named branch without stream multi |
| `dveldec` | `0x2eff` | EL-named branch without stream multi |
| `dvbldec2` | `0x1f3c` | BL-named branch with multi |
| `dveldec2` | `0x06c4` | EL-named branch with multi |

Separate original literals are `decoder.h265` at `.rodata+0x2c2d` and `vdec.h265.%02x` at `.rodata+0x1539`. The generic `decoder.h265` name is supplied to the different `vh265_init()->vf_provider_init()` path, while the four Dolby provider names are selected **inside** `ammvdec_h265_probe()`. The earlier Stage37 appearance of a provider-name mismatch is therefore explained in the original build, **without asserting that the two names are runtime aliases of an identical registration object**.

### Exact compiled three-predicate naming gate

The original executable code reads:

1. `0x108c–0x109c`: **`hevc_state_s.is_stream_mode_dv_multi`** at absolute field `+0x138b0` (named independently by original DWARF);
2. `0x1094–0x10a0`: **`dv_toggle_prov_name`** at original module `.bss+0x90` (symbol independently named by its original ELF symbol table); and
3. `0x10a4`: **`vdec_s.master`** at `+0x38` (original `decoder_common.ko` DWARF).

The decision at `0x10b4–0x10d4` / `0x124c–0x126c` selects one of the four strings. Its exact conditional AArch64 instructions plus all eight named-literal relocations were checked.

| HEVC instance multi flag | master pointer absent, toggle=0 | master pointer present, toggle=0 |
|---|---|---|
| 0 | `dvbldec` | `dveldec` |
| 1 | `dvbldec2` | `dveldec2` |

Setting `dv_toggle_prov_name` to **nonzero reverses** the BL/EL-named assignment within either row. Its current runtime value was **not captured**; this is a read-only observation of compiled alternative branches, **not a recommendation to change the parameter**. The original `master` field being non-null is distinct from proof that the linked decoder actively decodes FEL residual.

An original `snprintf` relocation at `0x1084` separately uses `vdec.h265.%02x` for a different naming route. The generic provider `vh265_init` contains separate `vf_provider_init` / `vf_reg_provider` calls as established by Stage37.

## Reproducible verifier and honest limits

`tools/gazelle-fel/audit-stage39-provider-names.py` rejects any archive/module SHA mismatch, verifies original ELF64 AArch64 identity, 2 named DWARF fields, 1 original module symbol, **44 exact instructions**, 6 exact strings, **18 relevant relocations**, and all 8 synthetic predicate/name combinations. Private proprietary ELF modules remain off GitHub.

Local offline result: `GAZELLE_FEL_STAGE39_OFFLINE_PASS`. GitHub CI checks source syntax/self-test only.

**Not shown:** runtime P7 instance `is_stream_mode_dv_multi`, runtime module `dv_toggle_prov_name`, actual vdec master/slave pointer state, original Fire OS Dolby receiver's auxiliary request and parser return, linked EL decoder, or residual-sensitive BL+EL output pixels. The Stage38 dynamic `dvbldec` registration is consistent with the compiled provider name route; it does not allow deduction of the three runtime predicate values individually.

## Engineering decision

The Stage37–38 **provider-naming discrepancy is resolved at the original-module source level**. Do not repeat the same VFM counts or change `dv_toggle_prov_name`, `is_stream_mode_dv_multi`, global stream_mode, `negative_dv`, `dolby_meta_with_el`, direct ioctls `0x179/0x301`, or Kodi just to alter the visible provider name.

**Stage40 priority:** Investigate **real paired-instance allocation and decoder lifetime** in the exact installed `stream_input.ko/decoder_common.ko` paths, correlated with the already observed use of the Dolby frame device and the observed absence of EL providers. Consider original offline evidence and/or a genuinely new passive read-only device signal with a demonstrated predicate. Pixel proof remains a separate final gate.

No changes to the Cube, Kodi, Magisk, passthrough, voice satellite or optical UDF/MMBD.
