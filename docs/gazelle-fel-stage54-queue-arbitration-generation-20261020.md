# Gazelle FEL Stage 54 — pinned Kodi queue arbitration and generation safety

**20 October 2026 · source-only research checkpoint · no Cube or installed Kodi modification.**

## Inputs and verification boundaries

At integrated Kodi commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`, the four Stage53 originals plus `DVDMessageQueue.cpp/.h` and `DVDStreamInfo.cpp/.h` were inspected. The owner Stage53 report passed 40 pinned source gates and 43 synthetic lifetime tests. The subsequent owner-captured evidence archive passed its manifest audit with 197 collected files. Runtime P8 was classified DOVI; P7 continued to classify HDR10 with no active EL provider demonstrated. The observed P7 post-seek counter reset is **not** proof of a codec reconfigure/reuse or stream-change epoch.

The Stage54 independent source review matched **45/45** bounded predicates against all eight original GitHub source files. A standalone host-only package has **51/51** deterministic Python reference-model tests and a Mac runner that retrieves only public Kodi source after verifying Git blob SHA-1; the complete owner Mac replay remains **PENDING**, not a claimed runtime pass.

## Additional immutable blob SHA-1 pins

| File | Blob SHA-1 |
|---|---|
| `DVDMessageQueue.cpp` | `f891833a6975e1aa05fc1a3684d7ee261bd68f0f` |
| `DVDMessageQueue.h` | `6a8a03812943b87f81e53a26eb535d4aeee5dbf6` |
| `DVDStreamInfo.cpp` | `3cc705ba6ef1e7002d675d9aaa903b9639d20df0` |
| `DVDStreamInfo.h` | `dc8836ba7d4540fe6c31f846d94a588cf4605907` |

The Stage53 four original file pins are unchanged.

## New source-level conclusions

1. **Two queues, not a global FIFO:** `CDVDMessageQueue::Put` stores priority-positive messages in `m_prioMessages`, ordered for highest-priority `Get` pop from the back. `Get` selects this list whenever it is nonempty, before normal priority-zero packets. A priority-10 replay enqueued by the video worker can overtake an already-queued priority-zero `GENERAL_STREAMCHANGE`. This depends on the producer and callback ordering and is not a measured cross-generation pairing.
2. **Normal `PutBack` can advance a packet:** at priority zero, `PutBack` appends to the read end of `m_messages`; `Get` pops from that end. Under AddData backpressure, this is intentionally not strict arrival FIFO.
3. **Filtered queue flush is not codec queue reset:** `DVDMessageQueue::Flush()` removes chosen message types from both queues, defaulting to `DEMUXER_PACKET`. It does not clear `CDVDVideoCodecAndroidMediaCodec::m_doviLayerPackets` inside the active codec.
4. **Conditional codec reuse:** Android `Reconfigure` compares `CDVDStreamInfo` hints using `COMPARE_ALL & ~(COMPARE_ID | COMPARE_EXTRADATA)`. `Equal` still checks flags, Dolby configuration record, profile, HDR type and other properties. Reuse is possible only when the remaining fields compare equal. Its true branch replaces hints but does not explicitly clear pending P7 halves.
5. **Worker replays lack proven epoch guards:** `VC_FLUSHED` and `VC_REOPEN` enqueue saved `m_packets` at priority 10. Their reset/reopen happens after enqueue. Ordinary streamchange drains and may reuse the existing codec while clearing worker replay, without an explicit codec pending-half barrier in that handler.
6. **Pair selection is insufficient:** existing MediaCodec AddData chooses the first opposite-layer pending half, without checking the two tracks' verified binding, stream epoch or corrected presentation timestamp. A queue cap of eight limits memory but is not a packet-generation guard.

## Reference design only — not a patch

For P7 alone, require a verified identity `(demuxer, BL stream ID, EL stream ID, epoch)` on both halves and all saved replay. A stream/program change, pair rebind, seek, codec reuse/reconfigure, reset, flush, reopen, error or close advances the epoch, revokes stale halves and saved replay, synchronizes queue arbitration and requires re-verification. Refuse unknown/foreign tracks, missing timestamps, stale epochs and unbounded queues. Strict integer PTS equality in the synthetic verifier is **not** a validated production timestamp rule. A real implementation must first prove demux/worker/codec thread ownership, in-flight dequeues, atomicity and correct clock normalization; a Python reference model proves none of these.

**Decision: NO-GO for runtime implementation.** No global stream-mode toggles, raw ioctl 0x179/0x301, changes to disc EL PID 0x1015, installed Kodi/native libraries or Magisk. Retain working P8, HDMI audio passthrough, voice satellite and optical UDF/MMBD. Native EL decoder pairing and residual-sensitive FEL output remain unproven.

## Next owner checkpoint

Run the standalone Stage54 host-only Mac bundle's `run_stage54_macos.sh`, require exact original SHA pins and final `GAZELLE_FEL_STAGE54_OFFLINE_PASS source_gates=45 regressions=51`, then inspect the sanitized ZIP. A future source-only C++ barrier plan should test concurrent producers, replay priority, codec reconfigure, demux observer versioning and navigation/P8 regressions before considering code changes.
