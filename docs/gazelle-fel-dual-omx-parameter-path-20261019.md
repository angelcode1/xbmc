# Gazelle native FEL — distinct Dolby Vision vs Amlogic OMX profile parameter paths

Date: 2026-10-19. This report supersedes any implication in the earlier exploratory notes that the vendor index `0x7f00010d` is itself the Dolby Vision profile setter.

## Provenance and scope

Read-only LLVM 17 ARM Thumb disassembly of the **exact private user-supplied Fire TV Cube 3 Gazelle PS7702.4965N** ELF files:

- `/vendor/lib/libomx_framework_alt.so` SHA256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`
- `/vendor/lib/libOmxVideo.so` SHA256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`
- `/vendor/lib/libOmxBase.so` SHA256 `7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee`

No binaries, kernel dumps, logs or proprietary data have been committed. Offline checks require exact hashes and actual instruction matches. **This does not measure runtime profile values or enable FEL decoding.**

## New concrete distinction: two separate handlers in the same `OmxVideoDecoder::setParameter()`

**1. Dolby Vision-specific index `0x7f800001`**

At `0x18fdc` / `0x18fde`, the code constructs `0x7f800001`, compares it to the incoming OMX index at `0x18fe2`, then executes:

| Instruction | Operation |
| --- | --- |
| `0x18fe8: ldr r0,[r5,#0xc]` | Read input field at `+0x0c` |
| `0x18ff2: str.w r0,[r4,#0x36c]` | Store value to decoder component `+0x36c` |
| `0x18ffa: ldr r0,[r5,#0x10]` | Read input field at `+0x10` |
| `0x18ffc: str.w r0,[r4,#0x370]` | Store value to component `+0x370` |

The `0x18fee` instruction's PC-relative string reference resolves exactly to `SetParameter:OMX_IndexParamVideoDolbyVision: profile:%d, level:%d` at `0x29699` in the pinned framework ELF. This strongly establishes the vendor framework's naming and the two profile/level storage fields.

**Decoder-side read:** in `libOmxVideo.so`, `AmlogicVideoDecoder::intitalizeCodec()` retrieves the owning `OmxVideoDecoder` pointer through `decoder+4`, then at `0x1eb6e` loads **owner+0x36c** into `r8`. At `0x1ee5c`, the same function compares this register to `0x400`. Thus `+0x36c` is **not merely a logged field**; it influences a native initialization decision. The exact meaning of the tested value and whether the installed Fire OS actually supplies it for P7 remain unresolved.

**2. Amlogic profile/level index `0x7f00010d`**

The jump-table dispatch documented in `gazelle-fel-omx-owner-parameter-trace-2026-10-14.md` leads to `0x19488`, whose stores are:

| Instruction | Operation |
| --- | --- |
| `0x194a4: str r0,[r4,#0x20]` | Input `+0x0c` → component `+0x20` |
| `0x194a8: str r1,[r4,#0x24]` | Input `+0x10` → component `+0x24` |

An independent `0x1a164` log path loads both from `owner+0x20` and resolves a PC-relative string at `0x29942` containing `OMX_IndexAmlogicProfileLevel %s %d, mProfile:%d, mLevel:%d`. The `OmxVideoDecoder` constructor initializes `+0x20/+0x24` to **zero** at `0x163bc` (via `strd r5,r5,[r4,#32]` with `r5=0`).

The legacy `AmlogicVideoDecoder::setUp()` gate `owner+0x20==0x10`, which optionally appends `dv_duallayer:1;`, pertains to this **different** Amlogic parameter path. Although standard Android Dolby profile enumerations also use numeric `0x10`, the two internal fields have not been proven to share that enumeration. Treating `owner+0x20=0x10` as a native FEL switch is unjustified.

## Stream/frame mode: separate still

`libOmxVideo.so` references `vendor.media.omx.stream_mode` at `0x1ef80` and `media.omx.stream_mode` at `0x1ef8c` during `AmlogicVideoDecoder::intitalizeCodec()`; the surrounding code at `0x1efb6–0x1efd2` selects a decoder mode field based on local flags. **This is not evidence that the properties alone enable FEL.** Previous CoreELEC source comparison documents a coordinated stream-mode, NAL-policy and Dolby-gate lifecycle; do not copy those writes to Fire OS.

## Correlation against previously captured real startup logs

P8 (11:55:52) and P7 (11:56:46) both successfully create `OMX.amlogic.dolby-vision.dvhe.decoder` and Kodi records `has_profile_key=false` in the Android `MediaFormat` for both. There are **no printed `SetParameter:OMX_IndexParamVideoDolbyVision` or `OMX_IndexAmlogicProfileLevel` lines** in those logcat snapshots. Their absence is not proof of no calls; log filtering/verbosity or indirect forwarding may hide them.

P7 retains 501 type-63 EL NAL units and 48 RPU units through 48 Kodi input buffers; kernel recognizes `[0]dv dual layer`, but stable output remains HDR10 and `dveldec(0)`. P8 reliably outputs DOVI. No ELF evidence in this report establishes whether `0x7f800001` is actively invoked or what value is supplied.

## Practical next boundary: upstream OMX parameter caller, not another P7 NAL capture

1. Offline inspect the exact `libstagefright.so`, `libstagefrighthw.so`, `libOmxCore.so`, `libstagefright_omx.so` and `libmedia_omx.so` already identified in the earlier source-matched bridge/Stagefright audits, including indirect parameter forwarding and decoding the relevant OMX extension indices. Verify SHA before using known addresses.
2. Distinguish the **actual caller of `0x7f800001`** from the caller of `0x7f00010d`; neither has been proven with the current three-ELF collection.
3. If later instrumenting live `media.codec`, first specify a reversible trace-only method, isolate audio/voice HAL coexistence, and prove a bounded, non-mutating fallback; no speculative OMX writes or process injection on a working installation.
4. Native FEL acceptance requires evidence that EL residual changes output pixels. P8.1 DV output alone cannot be called FEL.

## Updated reproducible test

The research-branch `tools/gazelle-fel/audit-fireos-profile-boundary.py` now validates separate address windows for the Dolby Vision profile setter, the Amlogic profile setter, and the native Dolby profile reader, in addition to previously verified dual-layer/metadata gates. Its complete binary-backed runtime is **offline**, without device changes. The distinct handlers were independently cross-checked by an additional 17-instruction pinned audit against the user's actual 3-ELF ZIP.
