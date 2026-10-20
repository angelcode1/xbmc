# Gazelle FEL Stage 58 — in-flight MediaCodec submission-fence design

**21 October 2026 — host-only reference. No device or Kodi runtime modification.**

This checkpoint follows owner-verified [Stage 57](gazelle-fel-stage57-queue-replay-event-scheduler-20261021.md) and continues to pin the original Kodi baseline at commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

## Owner Stage57 results accepted

The uploaded `gazelle-fel-stage57-results.zip` passed ZIP CRC verification. It contains `GAZELLE_FEL_STAGE57_SOURCE_AUDIT_PASS files=14 stage55_gates=61 stage57_gates=23`, plus 12 queue cases, 8 generation guard cases, 7,560 bounded schedules, 14,742 guarded rejections, 2,898 guarded pairs, 1,620 cross-epoch pairs in the **deliberately unguarded model only**, 7,560 P8 controls, and 6,372 replay-before-barrier schedules. The reference marker is `GAZELLE_FEL_STAGE57_CPP_REFERENCE_PASS runtime_device_test=false`; these are not real Cube decoding failures.

## Pinned source findings: the submission region is larger than the message queue

Review of original `VideoPlayerVideo.cpp` and `DVDVideoCodecAndroidMediaCodec.cpp` at the pinned commit reveals:

1. In `VideoPlayerVideo.cpp:544-644`, the video worker consumes `DEMUXER_PACKET`, calls `m_pVideoCodec->AddData(*pPacket)` and can reinsert the same message through `SendMessageBack(pMsg)` on backpressure. The queue lock does not, by itself, protect an already-dequeued packet.
2. `DVDVideoCodecAndroidMediaCodec.cpp:1574-1589`: `GetPicture()` calls `dequeueInputBuffer` and retains `m_indexInputBuffer`. `AddData()` later checks the retained index, pairs/converts P7 BL/EL data, gets the input buffer, copies payload and calls either `queueInputBuffer` or `queueSecureInputBuffer` (`AddData` roughly lines 1174-1454). Admission before `AddData` is not synonymous with completion of that JNI submission.
3. `DVDVideoCodecAndroidMediaCodec.cpp:1619-1673`: **`SignalEndOfStream()` is another `queueInputBuffer` call path**. It is used by `GetPicture` drain and `FlushInternal`. EOS and index lifecycle need explicit accounting beyond the P7 pair queue.
4. `DVDVideoCodecAndroidMediaCodec.cpp:1460-1526`: `Reset()` invalidates `m_indexInputBuffer` and clears pending P7 halves; `Reconfigure()` may reuse compatible hints **without clearing pending P7 halves**. The old generation must not survive a compatible-codec reuse.
5. `DVDVideoCodecAndroidMediaCodec.h:168-175` holds `m_doviLayerPackets` in codec-owned state. The player producer cannot simply manipulate it without a demonstrated ownership/acknowledgement protocol. `CMediaCodecVideoBufferPool` has a separate mutex, which does not establish an epoch fence over this P7 pipeline.

The independent Stage58 source predicate review checked **29/29** predicates against immutable GitHub source. The packaged Mac full auditor is still pending; it checks 14 exact Git blob identities followed by 61 Stage55 + 23 Stage57 + 29 Stage58 source gates. No JNI or device test has been performed.

## Stage58 reference package and results

Standalone `gazelle-fel-stage58-submission-fence.zip` SHA-256 `81a25ca48013356048b304468bd0bbf5daf348af2dd771c805bd6a9aca14e2ee` contains:

- `stage58_submission_fence.cpp`: isolated C++17 mutex/lease model, no Kodi/JNI dependency;
- `run_stage58_macos.sh`: macOS Bash 3.2-safe host compiler, `--selftest`, `--sanitize`, `--audit`, `--offline-audit`;
- `stage58_source_audit.py` plus pinned Stage55/Stage57 Python audit dependencies;
- README, engineering report, SHA-256 file manifest.

On the available Linux host, C++17 `-O2 -Wall -Wextra -Werror -pthread` passes **41 deterministic test assertions and 3,000 threaded barrier cycles**, with zero after-ack epoch violations in the **reference model**. A separate ASan/UBSan run passed. ZIP checksum/CRC, Python compile and Bash syntax passed. Real offline-audit with absent sources properly refused `SOURCE_MISSING_OFFLINE` rather than producing a false PASS. The owner's full Mac 14-file source audit remains **PENDING**.

The synthetic model tests **two-phase** transition semantics:

- `request()` closes new P7 admission, without mutating worker/codec pending halves from the producer.
- Already-admitted JNI leases may finish **after request**, so it is incorrect to claim they were cancelled.
- `acknowledge()` is blocked until all such leases finish, then retires pending halves, advances epoch and keeps admissions closed.
- `bind()` admits the new epoch only after acknowledgment with verified source binding.
- All old packets and stale replay are rejected after acknowledgment, keeping `after_ack_violations=0`; P8 is represented as a logical separate control, **not a runtime performance or playback test**.

The model uses strict integer clock equality only as synthetic test data. **It does not establish common corrected BL/EL timestamps, the actual Kodi producer/worker synchronization, JNI safe cancellation, decoder draining, native EL allocation or residual-sensitive FEL output pixels.**

## NO-GO and next gate

**NO-GO** for any installed Kodi patch, kernel ioctl, OMX property toggle, Blu-ray PID modification, Magisk change or Cube/device write. Preserve working Profile 8, voice satellite, HDMI passthrough and optical UDF/MMBD.

Next source-only gate: verify every real input submission path including EOS/secure and buffered indices; design a nonblocking request/worker-ack ownership protocol with error and close paths; prove corrected BL/EL clock and identity under program changes and navigation. Actual JNI and decoder output remain unverified.
