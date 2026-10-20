# Gazelle FEL Stage 44 — P7-only native stream interface readiness: **NO-GO**

**20 October 2026. Original proprietary Fire OS ARM32 code audited offline.** No device operations, software installation, configuration changes or executable native decoder calls. No private Amazon ELF files were committed. **Profile 7 FEL pixel reconstruction NOT PROVEN.**

## Owner's Stage 43 uploaded report: do not confuse partial with full PASS

The newly uploaded `stage43-audit-results(2).txt` includes:
- `GAZELLE_FEL_STAGE43_SOURCE_SELFTEST_PASS`;
- `ORIGINAL_ELF_CONNECTED_LIST_GATE_PASS` for `decoder_common` (28 instruction gates, eight relocations) and `stream_input` (five instructions, one relocation);
- `GAZELLE_FEL_STAGE43_ORIGINAL_BRIDGE_OFFLINE_PASS`.

But it **ends there**. It lacks `STAGE42_VERIFIED_PHASE`, `GAZELLE_FEL_STAGE43_EVIDENCE_RECONCILIATION_PASS`, and final `GAZELLE_FEL_STAGE43_OFFLINE_PASS`. Therefore **this particular Mac run stopped before completing the Stage 42 capture cross-check**. The cause is not established because the existing Mac runner pipes stdout to `tee` without retaining standard error. A missing/misnamed `stage42-connected-decoder-20261020-064046.zip` in `~/Downloads` is a possible cause, **not a confirmed diagnosis**.

An independently run *earlier complete* Stage43 audit already validated the exact Stage42 ZIP and observed **one connected P7 decoder (1/1) across all three P7 snapshots, as well as one P8 connected decoder**. It is not necessary to repeat Cube capture. Stage44 is independent of the incomplete rerun.

## Original owner vendor inputs

`03-vendor-odm.zip` SHA-256 `63c0aacc8647def650751a17b1fdba7ae6a67fed5ce6de7c88ab834d13e41622` contains the private original `vendor.img` SHA-256 `8021a1ba7956f01fe705b90e0005c377c04570adbec0e2e4399962617ab5553a`. Only two original binaries are extracted privately by the existing Stage30 source-only ext4 parser:

| Original ELF32 ARM library | SHA-256 |
|---|---|
| `libOmxVideo.so` | `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` |
| `libomx_framework_alt.so` | `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba` |

The Stage44 offline audit checked **39 exact Thumb instruction addresses/operands** across these two SHA-pinned ELFs, **six dynamic native symbol identities and sizes**, and the **21 DT_NEEDED dependencies** on the original `libOmxVideo.so`. Marker: `GAZELLE_FEL_STAGE44_ORIGINAL_ABI_OFFLINE_PASS`.

## Distinct native contracts: the missing steps are not interchangeable

| Boundary | Original pinned code evidence | What remains unproved |
|---|---|---|
| OMX component owner flag | Framework owner `+0x10a` is written as 1/0 in different constructor paths (`0x16834/0x16888`); `setParameter` contains an overlapping halfword clear at `0x1a1e0` | Supported **P7-only** setter/index, legal values, timing, confinement to the active `.dvhe` instance |
| Native mode selection | `codec_para_t.decoder_type` **+0x10a0**, `codec_init` `0x58ce6–0x58cec`, selects Dolby HEVC **frame if ==1**, stream otherwise in this tested branch | Safe Kodi-to-vendor per-instance mode selection and all preconditions before `codec_init` |
| Native input write | `codec_write` `0x597d0–0x597d2` loads context FD and branches to low-level write | Correct **HEVC byte-stream packetization**, BL/EL/RPU routing, extradata, short writes, backpressure, parser readiness; this wrapper does not create the stream packet contract |
| Timestamps | `codec_checkin_pts` passes selector `0x10e` through a native ioctl stub; `codec_checkin_pts_us64` invokes a distinct request and handles error | Correct media clock/timebase, 32-bit rollover, PTS/DTS mapping, ordering, underflow and flush/discontinuity behavior |
| Native handle lifetime | `codec_close` conditionally closes auxiliary handles, then primary FD, marking closed handles -1 | Complete ownership/synchronization, init-partial failure recovery, sibling decoder connection and teardown, safe fallback before opening P8 |
| EL metadata | `codec_set_dvmetawithel` writes `codec_para_t+0x12c0` and issues selector `0x179`; previous Stage19/31 audited `0x301` string submission/error masking | Exact call order, actual kernel acceptance, dual-layer metadata parsing/RPU output, EL frames and residual pixels |

The offset **`+0x12c4` is a *minimum accessed memory extent*, not `sizeof(codec_para_t)`**. The inline configuration `config` occupies a 512-byte span `+0x10b4` to `config_len+0x12b4`. Native layout beyond the recovered logger fields remains unverified.

The vendor's 21 shared dependencies include private OMX and Android libraries. Having exported `codec_*` symbols **does not establish that Kodi's 32-bit app process can load them through its linker namespace, nor that SELinux allows decoder device access**. These have not been tested on the Cube.

## Decision: no new native backend, test APK, or mode-changing experiment

**BLOCKED (NO-GO) until all gates below can be verified without jeopardizing the installed configuration:**

1. Full, version-specific native `codec_para_t` allocation/ownership contract, including the actual full struct size.
2. Correct HEVC stream input framing, parameter sets, buffer flow control, PTS units and discontinuity/flush handling validated on the **same Fire OS vendor/kernel build**; CoreELEC's kernel 5.15 path is a *reference*, not a directly compatible Fire OS 5.4 recipe.
3. Demonstrable supported **per-instance** P7-only selector before OMX/native init; no globally scoped `media.omx.stream_mode`, `vendor.media.omx.use_dv_frame` or kernel debug/property toggles.
4. Linker namespace, permissions and exclusive decode-device ownership determined, without changing live Kodi or `media.codec`.
5. Complete positive paired vdec **creation → initialization → connection → live EL frames → metadata/RPU acceptance** with clear, fail-closed error/teardown gates.
6. A controlled **BL-only vs BL+EL residual-sensitive pixel oracle**, with known-good P8 restart/fallback protected, to distinguish real FEL reconstruction from a label change.

No evidence here authorizes a live stream-mode switch, direct raw ioctl `0x179/0x301`, a fabricated native context struct, replacing installed OMX/vendor libraries or installing a speculative Kodi APK. Prior global NAL and metadata-flag experiments destabilized playback; **do not repeat**. The working native P8 path, satellite/HDMI coexistence, UDF/MMBD and Magisk modules remain intact.

## Next Stage 45

Continue with **offline HEVC packet/PTS and native Kodi boundary analysis**, keeping exact Fire OS 5.4 vendor ABI evidence separate from CoreELEC source and generic Amlogic examples. If the per-instance control/feeding contract remains unsupported, stop at a documented design gate rather than generating a runtime test.

Stage44 verifier: `tools/gazelle-fel/audit-stage44-native-abi-readiness.py`. GitHub CI runs source syntax/selftest/safety; the owner original ELFs are checked only offline and not uploaded.
