# Gazelle FEL Stage 57 — exact Kodi queue scheduler and guarded P7 replay epoch

**21 October 2026 · source-only/host-only · no Cube, Kodi APK, vendor ELF or kernel mutations.** Continues [Stage56](gazelle-fel-stage56-cpp-epoch-barrier-reference-20261020.md). Original Kodi source pinned to immutable integrated commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

## Source-level findings: verified from nine original pinned blobs

An independent GitHub connector audit re-read **9/9** original source blobs and matched **37/37** bounded predicates, without modifying source:

| Original Kodi file | Exact Git blob SHA-1 |
|---|---|
| `DVDMessageQueue.cpp` | `f891833a6975e1aa05fc1a3684d7ee261bd68f0f` |
| `DVDMessageQueue.h` | `6a8a03812943b87f81e53a26eb535d4aeee5dbf6` |
| `VideoPlayerVideo.cpp` | `51ca08050efcd32648d20876e7ac1cae9df6e368` |
| `VideoPlayerVideo.h` | `91e4af7b098e6fffb1e9ff563419f6053181f996` |
| `DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |
| `DVDVideoCodecAndroidMediaCodec.h` | `76252f255f0b2bdff43735575c4111c56414f295` |
| `Interface/DemuxPacket.h` | `4cb47b4659a208853788ecff23109424fa714f62` |
| `VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `DVDStreamInfo.cpp` | `3cc705ba6ef1e7002d675d9aaa903b9639d20df0` |

**Queue order:** Original `DVDMessageQueue::Put` stores normal messages in `m_messages` and priority-positive in `m_prioMessages`. Normal `Put` inserts at front and `Get` pops back (FIFO); normal `PutBack` inserts at the read end and can overtake earlier ordinary packets. Priority insert uses `prio <= item.priority`, with a +1 insertion preference for `PutBack`. `Get` selects priority messages before normal messages, and a worker priority floor of 1 can defer normal packets. `Flush(DEMUXER_PACKET)` removes packet messages from both lists; it does not clear codec-internal pending P7 halves.

**Stream change / replay:** `CVideoPlayerVideo` sends `GENERAL_STREAMCHANGE` at priority 0; `VC_FLUSHED` or `VC_REOPEN` re-enqueues replay at priority 10 and resets/reopens afterwards. An older replay message therefore can overtake a queued stream-change. `AddData` backpressure can `PutBack` at normal priority. The old worker may reuse a compatible MediaCodec via `Reconfigure` without clearing `m_doviLayerPackets`; existing pairs are selected by opposite role without verified epoch/PTS/track identity.

## Standalone Stage57 runnable package (private conversation attachment, **not** Kodi integration)

`gazelle-fel-stage57-kodi-queue.zip` SHA-256 `d5f10f8050a0b15260450e73e6da467aff98e0c9274084b241a241dbc53bd20b`, ZIP CRC and SHA256SUMS pass. Contains:

- `stage57_queue_model.cpp`: host C++17 list-order reference and distinct proposed P7-generation guard;
- `audit_stage57_sources.py`: original Git-blob hash-verified 9-file / 37-predicate read-only source verifier, refuses unpinned or modified files;
- `run_stage57_macos.sh`: `--selftest` (no network), `--full` (uses local pinned source or retrieves **public** Kodi source HTTPS), `--sanitize` (host ASan/UBSan);
- README and detailed report.

**Host local tests:** 10 original queue-semantics cases PASS; 5 synthetic P7 admission cases PASS; exhaustive **5,040 permutations** of a bounded seven-action event set PASS. Across enumerated schedules: 8,358 stale packet refusal occurrences before worker acknowledgement, 3,948 after acknowledgement, 3,276 high-priority replay observations before acknowledgement. Occurrence counts are from repeated synthetic permutations, **not Cube activity**. The sanitizer-enabled run passed (ASan/UBSan, not TSan). The complete local Mac `--full` runner replay remains **PENDING** because this isolated execution environment cannot fetch raw GitHub source directly; the nine immutable source hashes and 37 predicates were independently checked through the GitHub connector.

**Test markers:**

- Local offline-only: `GAZELLE_FEL_STAGE57_MODEL_ONLY_PASS schedules=5040 source_replay=pending`.
- Expected only after a full Mac source replay: `GAZELLE_FEL_STAGE57_OFFLINE_PASS schedules=5040 source_gates=37`.

## New design distinction: logical cancellation precedes physical cleanup

Publishing a producer epoch must make any old pending P7 half **ineligible for pairing immediately**, even if the video worker physically clears its list only later at barrier acknowledgement. The toy guard checks both published and worker epochs on every P7 submit, rejects queued replay and in-flight stale packets, clears pending/replay on worker acknowledgement, then requires a newly verified `(demuxer, BL, EL, epoch)` binding. This is not a production synchronization proof: the real Kodi producer/worker/MediaCodec threads do **not** have an established equivalent common atomic commit fence; actual AddData/JNI operations might be in flight.

Synthetic integer PTS equality is not a validated cross-track corrected-timestamp rule. The model's P8 bypass is not an installed P8 regression test. There is still no observed active native EL decoder, accepted residual-sensitive FEL pixels, or demonstrated P7 Dolby output.

**NO-GO** for installed Kodi patch, global OMX/property change, 0x179/0x301 ioctl, disc EL PID 0x1015 exception, native library patches, Magisk/HDMI/satellite/optical changes. Preserve working P8 and optical UDF/MMBD.

**Stage58:** a host-only ownership/acknowledgement model for *in-flight* P7 commit permits, cancellation, worker teardown and reconfiguration under concurrent producers. Do not integrate into Kodi until the real thread/packet lifetime and native BL/EL contract are proven.
