# Gazelle FEL Stage 57 — exact queue ordering and stale replay reference
**21 October 2026 — source-only; no Cube, Kodi APK, Magisk or vendor changes.**

This checkpoint follows [Stage56](gazelle-fel-stage56-cpp-epoch-barrier-reference-20261020.md) and pins its source baseline to integrated Kodi commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`. The Stage57 standalone downloadable package is `gazelle-fel-stage57-queue-scheduler.zip` (SHA-256 `4e9fee101ff8ec7cee5f4ee5f1d3f09480b76c18c8632161bb2704a43cef813f`); package and host runner are delivered in the conversation, not committed as a Kodi production patch.

## Owner-submitted Stage56 evidence accepted

Uploaded `gazelle-fel-stage56-results.zip` SHA-256 `d508b5ce1a58caded9ce15121e1907e9302be333762e0cb7eed92e31edb248ff` passed ZIP CRC validation and has three bounded results. Reported markers: `STAGE56_SINGLE_THREAD_TESTS_PASS cases=4`, `STAGE56_THREADED_REFERENCE_PASS barriers=2000 stale_attempts=6780 p8_calls=40457`, and `GAZELLE_FEL_STAGE56_CPP_REFERENCE_PASS runtime_device_test=false`. No native EL/FEL proof or device-access claim follows from this test log.

## Stage57 additional exact source findings

Original `DVDMessageQueue.cpp` implements two distinct message lists. `Put` with priority >0 inserts into `m_prioMessages` using `prio <= item.priority` and increments comparison `prio` on `PutBack`. Normal `Put` inserts at front, normal `PutBack` at back; `Get` pops the back of a selected list and chooses `m_prioMessages` while nonempty. Thus reinserted normal packets can overtake queued normal stream-change messages, and positive priority replay can overtake normal messages. Filtered `Flush` does not itself purge codec-owned P7 halves.

`CVideoPlayerVideo::OpenStream` sends `GENERAL_STREAMCHANGE` at priority 0; the worker replays packets on `VC_FLUSHED` and `VC_REOPEN` at priority 10 and requeues decoder-backpressure packets via `SendMessageBack`. Compatible Android `Reconfigure` does not explicitly clear `m_doviLayerPackets`; P7 pairing finds the first opposite layer without a source-verified generation, identity or corrected-timeline equality check.

These are source-level lifetime and arbitration risks. **No Kodi runtime cross-generation mispair has been observed.** The 23 Stage57 source predicates matched original GitHub source responses (23/23); 14 original SHA pins and Stage55 61 baseline gates are included in the packaged full `--audit` runner, which has **not** been run here in network-enabled full mode.

## New isolated C++17 result

A host-only two-list scheduler reproduces the pinned relevant insertion and dequeue semantics and compares (a) a deliberately unguarded first-opposite-layer pairing anti-example with (b) producer+worker epoch admission checks. A *hypothetical* old BL / new EL PutBack-over-streamchange ordering yielded one cross-epoch pair in the anti-example and zero in the guarded model.

Independent local results:
- `STAGE57_QUEUE_SEMANTICS_PASS cases=12`
- `STAGE57_GENERATION_GUARD_PASS cases=8`
- `STAGE57_ADVERSARIAL_WITNESS_PASS unsafe_cross_epoch=1 guarded_cross_epoch=0`
- `STAGE57_BOUNDED_SCHEDULER_PASS schedules=7560 guarded_rejections=14742 guarded_pairs=2898 unsafe_cross_epoch=1620 p8_controls=7560 replay_before_barrier=6372`
- `GAZELLE_FEL_STAGE57_CPP_REFERENCE_PASS runtime_device_test=false`

C++17 -Wall -Wextra -Werror builds passed, including ASan/UBSan and runner/ZIP CRC validation. Model schedules are **atomic abstract events**, not exhaustive Kodi concurrency, input buffer/JNI linearization or actual playback. P8 probes are logical noninterference checks only. The equal integer PTS rule is synthetic; actual BL/EL corrected clock agreement is unproven.

**Decision: NO-GO** for installed decoder patch. Preserve P8, voice satellite, HDMI passthrough, optical UDF/MMBD and existing Magisk. No global OMX toggles, raw ioctls or Blu-ray PID modifications. Native P7 residual reconstruction, active EL provider and output pixels remain unproven.

**Stage58 next**: source-only ownership and clock normalization proof with an explicit in-flight JNI/MediaCodec submission fence. No production integration until that, safe producer/worker/barrier thread ownership and exact pair-binding provenance have been verified.

## Stage57 v2 macOS runner repair (owner results, 21 October 2026)

Owner's first `bash run_stage57_macos.sh --audit` produced all scheduler PASS markers, then failed before the source audit with `run_stage57_macos.sh: line 29: EXTRAS[@]: unbound variable`. **Root cause:** on macOS system Bash 3.2, `set -u` can treat a defined-but-empty `EXTRAS=()` expansion as unbound. This is a *host runner argument expansion bug*, not a C++ scheduler failure or a source audit failure.

The corrected downloadable `gazelle-fel-stage57-queue-scheduler-v2.zip` has SHA-256 `1372ffa0d494683e450794a3a7be460d0930d2202394ef5440359628ee491c4f`. The runner now uses explicit `--audit` and `--offline-audit` branches instead of an empty Bash array. The original scheduler C++ and pinned source-audit Python files are byte-identical to Stage57 v1.

Verified on the available host:
- `bash -n`, Python compilation, internal file SHA-256 manifest, ZIP CRC: PASS;
- real C++17 default runner and 7,560 bounded schedules: PASS, ZIP output valid;
- real `--offline-audit` with deliberately missing sources: **reaches** Python source gate (`SOURCE_MISSING_OFFLINE DVDMessageQueue.cpp`), without the shell error;
- both audit argument paths and resulting ZIP packaging: PASS **using a local mocked source-auditor** strictly for branch-routing tests. Mocked markers are not an original-source audit;
- independently recorded original Kodi source gates from GitHub remain 23/23; full 14-file downloaded SHA-pinned Mac audit and actual macOS Bash 3.2 execution remain **PENDING**.

Run a fresh unzip into `~/Downloads/gazelle-fel-stage57-queue-scheduler-v2/`, then `bash run_stage57_macos.sh --audit`. Required successful final messages: `GAZELLE_FEL_STAGE57_SOURCE_AUDIT_PASS files=14 stage55_gates=61 stage57_gates=23` and `GAZELLE_FEL_STAGE57_HOST_PASS schedules=7560 source_audited=true`. No device writes or Kodi patch were made. Runtime native P7 FEL output remains unproven.
