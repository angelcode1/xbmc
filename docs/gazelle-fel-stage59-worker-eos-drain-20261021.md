# Gazelle FEL Stage 59 — worker ownership, EOS enqueue and drain acknowledgement

**21 October 2026 · host/source-only checkpoint · NO runtime Kodi or Cube modification.**

Original Kodi pin: `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`. Continues [Stage58](gazelle-fel-stage58-inflight-mediacodec-submission-fence-20261021.md).

## Stage58 owner-uploaded source audit accepted

The owner uploaded `gazelle-fel-stage58-results(1).zip`; its ZIP CRC and five entries were verified. Full source audit output included:

```
GAZELLE_FEL_STAGE58_SOURCE_AUDIT_PASS files=14 stage55_gates=61 stage57_gates=23 stage58_gates=29
STAGE58_FENCE_SEMANTICS_PASS cases=41
STAGE58_THREADED_FENCE_PASS cycles=3000 worker_attempts=940 admitted_pairs=8 rejected=1864 post_request_commits=2 blocked_ack_retries=8 p8_controls=77 after_ack_violations=0
GAZELLE_FEL_STAGE58_CPP_REFERENCE_PASS runtime_device_test=false
```

The 2 after-request completions were permitted in the isolated model because worker acknowledgement waited for in-flight leases. **Zero after-acknowledgement violations are measured in the host model only**, not in Kodi or JNI.

## Source-level EOS drain finding

- `VideoPlayerVideo.cpp:501-530`: ordinary `GENERAL_STREAMCHANGE` and `VIDEO_DRAIN` loop with `DVD_CODEC_CTRL_DRAIN` and `ProcessDecoderOutput()`. Streamchange then calls `OpenStream()`, which may reuse the old Android codec.
- `DVDVideoCodecAndroidMediaCodec.cpp:1574-1589`: `GetPicture()` obtains and retains `m_indexInputBuffer`; `AddData()` later converts/copies and submits secure or nonsecure input buffers.
- `DVDVideoCodecAndroidMediaCodec.cpp:1630-1673`: **`SignalEndOfStream()` returns `void`**; on an absent input-buffer index, it logs a warning without enqueueing EOS. A JNI exception after attempted enqueue can also produce an error log without a success value returned to its caller.
- `DVDVideoCodecAndroidMediaCodec.cpp:1595-1600`: on the running drain path, **`GetPicture()` still sets `MEDIACODEC_STATE_WAIT_ENDOFSTREAM` immediately after the void `SignalEndOfStream()` call**, irrespective of a proved successful EOS enqueue.
- `DVDVideoCodecAndroidMediaCodec.cpp:1540-1570`: when the state is `WAIT_ENDOFSTREAM`, a subsequent no-picture output poll can lead to `VC_EOF`. This yields a **possible premature EOF source path**, conditional on absent EOS-buffer index and output-poll conditions. It has NOT been witnessed on a real Cube.
- `DVDVideoCodecAndroidMediaCodec.cpp:1619-1625`: `FlushInternal()` also calls `SignalEndOfStream()`, so EOS submission is not limited to ordinary player packet handling.
- Hard `Reset()` clears pending P7 halves and input-buffer index; compatible `Reconfigure()` does not explicitly clear pending halves.

**Source evidence:** independent verification of 29/29 Stage59 bounded predicates on original GitHub source, including the unconditional `WAIT_ENDOFSTREAM` assignment and distinct EOS enqueue branch. The downloadable macOS runner will additionally verify 14 original Git blob SHA identities and all prior 61+23+29 gates; full owner Stage59 source-audit rerun remains pending.

## Isolated C++17 reference model

Standalone private conversation artifact `gazelle-fel-stage59-eos-drain.zip` SHA-256 `19f8a12cb15279c4858a5f88ca6addb2c4d8dc3b5b252eefe7e9399610437023` contains `stage59_eos_reference.cpp`, Bash 3.2-safe `run_stage59_macos.sh`, `stage59_source_audit.py`, Stage55/57/58 audited dependencies, README, report and per-file SHA256SUMS.

The model separates **admission close**, **in-flight packet-commit drain**, **EOS-input-index retry**, **successful EOS enqueue**, **decoder-output EOS**, **worker barrier acknowledgement**, and **new-epoch bind**. `begin_eos(false)` models a missing index as retryable, never as successful EOS enqueue. For graceful streamchange/video-drain, a worker acknowledgement requires `OutputComplete` and zero in-flight submission leases. For hard flush/reset/reopen/error/close it models explicit abandonment after in-flight work completes. Strictly synthetic P8 control remains separate.

Verified on the available host:

- 64 deterministic tests;
- 3,000 concurrent transitions with 1,000 EOS submissions and 1,000 index-absence retries; `after_ack_violations=0`;
- standalone AddressSanitizer and UndefinedBehaviorSanitizer replay passed;
- a source-branch counterexample marker: `STAGE59_HYPOTHETICAL_EOS_WITNESS unsafe_eof_without_enqueue=1 guarded_ack_without_eos=0` (hypothetical, **not real playback**);
- Bash syntax, Python compilation, ZIP CRC, internal checksums passed;
- offline source audit correctly failed closed with `SOURCE_MISSING_OFFLINE` when exact original source was absent.

Host completion markers:

```
STAGE59_WORKER_EOS_SEMANTICS_PASS cases=64
STAGE59_THREADED_WORKER_EOS_PASS cycles=3000 ... eos_submits=1000 eos_retries=1000 ... after_ack_violations=0
GAZELLE_FEL_STAGE59_CPP_REFERENCE_PASS runtime_device_test=false
```

The original Kodi code has **not** been changed to implement this model. Synthetic output-EOS acknowledgement is not proof that actual decoded frames drained. ThreadSanitizer, Android/JNI, native EL, residual-sensitive FEL output and P8 runtime regressions remain untested.

## NO-GO and next gate

**NO-GO for P7 FEL runtime patch.** Do not alter installed Kodi, vendor OMX/driver ioctls `0x179/0x301`, disc PID `0x1015`, Magisk, HDMI passthrough, voice satellite or UDF/MMBD. Do not add a field to Kodi's public addon `DEMUX_PACKET` C ABI.

Proceed only with source-only error/timeout and worker ownership design; require a proven production handoff for in-flight JNI calls, EOS success, codec output drain, queue generation and common corrected BL/EL clock, then real EL/residual pixels before any runtime deployment.
