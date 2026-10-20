# Gazelle FEL Stage 46 — source-pinned P7 BL/EL pairing and whole-buffer contract

**20 October 2026. Uploaded Stage45 combined offline audit PASSED. Stage46 source audit and 26 deterministic synthetic regressions PASSED.** Source-only research branch, **no Kodi or Cube changes**, no original-vendor binaries redistributed.

## Stage45 handoff: owner originals and exact Kodi source

Owner's uploaded `stage45-audit-results.txt` contains `GAZELLE_FEL_STAGE45_OFFLINE_PASS`, original `libOmxVideo.so` identity, 24 native Thumb instruction checks and four native exports; the **exact integrated Kodi input-source check passed 14 gates**. Owner also uploaded the actual `DVDVideoCodecAndroidMediaCodec.cpp` SHA256 `5fdaad4937baef11f769cdcc706d55769bd06608e5c0797eb5a9f59fa270fdac`; independently verified Git blob SHA1 `1a313fdc297db69607b2a3f0e82069def4b198f3`, pinned Kodi commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

Stage44/45 original native codec checks remain relevant: native `codec_write()` is a raw-FD write wrapper, distinct from Android `queueInputBuffer()`; native 32-bit PTS `0x10e` and 64-bit `0x40045395` ioctls are separate and their required timebase/ordering are **not verified**. P7 fallback currently has no observed connected second `vdec`. Stage46 does not claim to solve this hardware path.

## New checked observations in the owner's exact Kodi C++ source

`tools/gazelle-fel/audit-stage46-p7-input-guards.py` rejects any source blob other than the pinned integrated `DVDVideoCodecAndroidMediaCodec.cpp` and checks **15** source-location patterns scoped to the actual `AddData()` / `Reset()` bodies. Unlike the previous Stage45 check, this audit explicitly includes queue overflow and reset behavior.

| Source operation | Verified original behavior | Distinct potential risk |
|---|---|---|
| `std::find_if(...)` dual-stream lambda | Only `return pending.isEL != packet.isELPackage;` | Opposite layer can match a different frame's PTS if inputs interleave |
| Pending packet | Stores PTS, DTS, isEL and payload | Timestamps are available but unused in the match predicate |
| Pending queue | Maximum eight; silently `pop_front()` oldest on overflow | One half of a frame can be discarded while another remains |
| `CBitstreamConverter::Convert(blData, blSize, elData, elSize)` | Combines paired BL/EL payloads | Input matching correctness is an independent prerequisite |
| MediaCodec input capacity | `if (iSize > out_size) iSize = out_size;` | Potential shortened access unit, including a partial NAL |
| `Reset()` | Clears `m_doviLayerPackets` | This is already a correct reset containment action |
| Timestamp handoff | `presentationTimeUs = pts - m_dtsShift`, falling back to DTS | Distinct from original Fire OS native ioctl timebase |

The "wrong-frame" counterexample is **synthetic but follows the verified source predicate**: a pending BL at PTS 100 and a newer BL at PTS 200, followed by EL at PTS 200, would select the first pending opposite-layer BL (PTS 100). This shows a *reachable logic concern if such packet ordering occurs*, not evidence the owner's real P7 stream generated that sequence. The prior 48/48 MediaCodec copy hashes only show bytes copied intact **after** any possible input-length shortening.

## Stage46 reference policy — no compiled decoder patch

`ReferencePairer` in the same source-only Python file is an **independent proposal, not the algorithm currently running in Kodi**:

1. Require an explicitly known integer timestamp identity for both BL and EL, within one generation. **This is an assumption to validate** against Kodi's actual demux stream timebase, missing PTS, B-frame reordering and discontinuity behavior, not an adopted production requirement.
2. Pair only opposite-layer samples with **equal timestamps**, whichever arrives first; avoid pairing unrelated interleaved frames.
3. Reject missing/duplicate timestamps, invalid layer/size, or queues exceeding an **illustrative** eight-packet/8 MiB pending policy. Drop the whole pending generation on error rather than retaining a potentially mismatched half-pair.
4. Clear pending halves on explicit reset or generation change.
5. Reject a whole oversize encoded access unit instead of silently truncating it to destination-buffer capacity; return a distinct failure state for caller-controlled flush/fallback. Actual MediaCodec input-buffer handling and error policy still require review.
6. Reject overflow beyond a signed 32-bit payload-size range. Never allocate actual video payloads in the tests.

**26 regression cases passed** on the independent model, including BL-first/EL-first, two interleaving orders, mismatched PTS, missing/float/duplicate timestamps, bounded queue overflow, byte-budget overflow, flush/discontinuity, invalid lengths, sum overflow, exact buffer fit, oversize refusal and model-level P8 isolation. The example time and memory limits are **not validated production constants**.

## Reproducible source-only results

- Verifier file: `tools/gazelle-fel/audit-stage46-p7-input-guards.py`
- Mac runner: `tools/gazelle-fel/run-stage46-macos.sh`
- SHA-256 of bundled verifier: `ba942beda9cad95e6f9da043705305bf1a8d4673b380339064fa163ab15cb931`
- Git blob SHA1 of verified source: `83d5cd4059ecb7fd16efd3778b55d2d215b6fb87`
- Offline result: `GAZELLE_FEL_STAGE46_OFFLINE_PASS`; `GAZELLE_FEL_STAGE46_SYNTHETIC_REGRESSIONS_PASS cases=26`, `GAZELLE_FEL_STAGE46_EXACT_SOURCE_GATES_PASS checks=15`.

Mac bundle contains only the source verifier, runner and README. The runner looks for the previously downloaded Kodi C++ file under `~/Downloads/gazelle-fel-stage45-results/` or `~/Downloads/`, or fetches its immutable, exact blob from public GitHub. It checks local SHA, runs 26 regressions and the exact source audit, saves a sanitized TXT plus JSON under `~/Downloads/gazelle-fel-stage46-results/`, and performs **zero ADB calls or device changes**. No private original ELF or stream payload is packaged.

## No-go criteria and Stage47 direction

**Nothing in Stage46 proves** that actual P7 PTS mismatches or MediaCodec buffer clipping occurred, that a correct native HEVC BL/EL/RPU bitstream has been constructed, that Kodi can access the proprietary native codec with a complete context ABI, or that a second connected EL decoder contributes residual-sensitive output pixels. FEL **remains unproven**.

**Stage47:** an isolated source-only proposal, preferably a minimal unit-tested helper (not installed Kodi modification), must first validate actual Kodi demux PTS equivalence, handling of missing PTS/reordered BL/EL and overflow, atomic access unit capacity/failure paths, before any optional P7-only compiled patch. Keep P8, HDMI/audio passthrough, voice satellite, UDF/MMBD and Magisk unchanged. Never flip global OMX stream properties or issue speculative device ioctls solely because this model passes.
