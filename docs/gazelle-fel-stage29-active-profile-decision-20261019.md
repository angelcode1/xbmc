# Gazelle FEL Stage 29 — controlled P8/P7 source-format gate, active decoder evidence

**2026-10-19, Australia/Brisbane. Result: NINE-SAMPLE READ-ONLY RUNTIME COMPARISON VERIFIED. P7 FEL residual reconstruction NOT PROVEN.** This is a *diagnostic result*, not a request to modify video/kernel/Magisk/Kodi/HDMI/optical/satellite settings.

## Owner-supplied primary evidence (private)

`stage28-active-comparison-20261019-134212.zip` SHA-256:

`2daf20404ec38b5eb3a86d6d44b8ec0b7f4abe641aa9ecb574dbbf05198b3e5d`

Two archive members: original text summary and structured `gazelle-fel-stage28-v1` JSON, with nine non-atomic samples; manual playback selection: three idle, three working Profile 8, three Profile 7. Owner's collector reports `DEVICE_WRITES=NONE`. All seven probes returned `status=ok` in every sample. Raw capture is intentionally **not committed** to the repository.

| Signal | Idle 3/3 | P8 active 3/3 | P7 active 3/3 |
| --- | --- | --- | --- |
| `vdec_status` classifier | `No vdec.` | nonempty HEVC | nonempty HEVC |
| `dv_source.inst1` | `DV FORMAT_DOVI` (retained, not active) | **`DV FORMAT_DOVI`** | **`HDR10 FORMAT_HDR10`** |
| `dv_inst_status.inst1_valid` | 0 | 1 | 1 |
| `dv_inst_status.core1a_on` | 0 | 1 | 1 |
| VFM `dvbldec` count | 0 | 1 | 1 |
| VFM `dveldec` / `dveldec2` counts | 0 / 0 | 0 / 0 | 0 / 0 |
| `amstream_dves_hevc` stream-port flag | 0 | 0 | 0 |
| `amstream_dves_hevc_frame` frame-port flag | 267 / Used | 267 / Used | 267 / Used |
| Dolby output mode node | `IPT_TUNNEL` | `IPT_TUNNEL` | `IPT_TUNNEL` |

Additional measured details: `amstream_dves_hevc` retains type `6417 = 0x1911`; frame port retains `7441 = 0x1d11`. `Vformat` remains `-1` for the stream port and `11` for frame. These **port values are invariant** across all nine samples, including idle. This reconfirms the Stage 13 finding that the persistent `Used` flag is **not a decoder allocation signal**. Previous Stage 13 active process-FD collection separately observed `media.codec` opening `/dev/amstream_dves_hevc_frame` for both files; Stage 28 did not itself read file descriptors.

Host timestamp window in this capture is approximately `2026-10-19T13:41:28Z` through `13:42:12Z`; probes are sequential and non-atomic. Do not infer precise decoder timing or hardware-pixel behavior from these time-bounded samples. The visible input labels reflect the owner's choices; the collector did not rehash media files or certify their Dolby profiles.

## Discriminating conclusion

- The P8 control demonstrates that the *same installed Kodi and kernel* can show an active HEVC decoder, live `dvbldec(1)`, valid Dolby instance/core and `FORMAT_DOVI`, with a single-layer stream.
- The P7 playback independently shows an active HEVC decoder and `dvbldec(1)` but the active Dolby source is consistently **`HDR10 FORMAT_HDR10`**, *not* DOVI. No enhancement provider is observed: `dveldec(0)`, `dveldec2(0)`.
- The idle capture retains a DOVI source label even with `No vdec.`, valid 0 and core off. Source format **must be interpreted with the active instance/core evidence**, not alone.
- Stage 12 original kernel code shows the frame-type bit checks before dual-decoder allocation in `amstream_open()`. Stage 13 demonstrated actual frame-node FDs. Stage 28 agrees with the absence of observed EL provider state but does not directly inspect `vdec->slave`.

**Working hypothesis, not proved causation:** the P7 path does not complete the necessary mode/decoder/EL metadata handshake, leading to HDR10 classification. Stage 28 cannot establish whether the HDR10 classification is *caused by* the missing slave, metadata parsing, device mode or another vendor policy gate; these require targeted original-vendor static dataflow.

## Safe next engineering decision

**Prioritize offline original Fire OS OMX and native Dolby profile/dataflow investigation**, not another symbol inventory or a global switch. Earlier Stages 9–16 identified a private `AmlogicVideoDecoderAwesome` frame-mode word (`owner+0x10a` -> native `+0xdd` -> `codec_para_t+0x10a0`), while the only overlapping OMX setter identified in Stage 15 is MVC-specific and zero-only. The original native `codec_init` opens `/dev/amstream_dves_hevc_frame` for mode word 1; stream mode is a different feeding and lifecycle contract, not a simple property flip.

Next precise questions:
1. Under what **source-format/RPU and EL state conditions** does the installed native Dolby path classify a P7 input as HDR10 while the same decoder reports P8 as DOVI?
2. Is there an **instance-scoped, validated** HEVC stream mode + packet/PTS pathway reachable from Kodi without changing shared system properties or audio/video services?
3. Which runtime evidence can prove connected master/slave decoding and residual-sensitive output *before* claiming FEL?

**No speculative Kodi APK, direct 0x179/0x301 ioctl, forced `enable_fel`, `dolby_meta_with_el` or `nal_skip_policy`, or global stream-mode property** should be applied on the evidence so far. Preserve working P8, Fire TV HDMI passthrough, voice satellite, UDF and optical MMBD.

## Reproducibility

`tools/gazelle-fel/audit-stage29-live-gates.py` reads only the original Stage 28 ZIP **on the host**, rejects malformed schemas, unexpected archive members, missing probe data, reordered or missing phases, invalid timestamps/provider counts or ambiguous statuses. It prints phase-level gates and explicitly states that no pixel/FEL proof follows.

```bash
python3 tools/gazelle-fel/audit-stage29-live-gates.py --selftest
python3 tools/gazelle-fel/audit-stage29-live-gates.py \
  ~/Downloads/stage28-active-comparison-20261019-134212.zip \
  --output ~/Downloads/gazelle-fel-stage29-results.txt
```

GitHub CI executes syntax and source selftest only because the owner's runtime ZIP is private. A separate independent comparison against the nine uploaded JSON samples also passed, with marker `GAZELLE_FEL_STAGE29_P7_HDR10_GATE_OBSERVED_PASS`. CI success is not the same as private-capture validation. Both statuses must be reported distinctly.
