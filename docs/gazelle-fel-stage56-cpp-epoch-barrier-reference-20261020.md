# Gazelle FEL Stage 56 — standalone C++17 epoch barrier reference

**20 October 2026. Host-only compiled reference; not a Kodi patch or live decoder experiment.** Extends [Stage55](gazelle-fel-stage55-packet-provenance-epoch-handoff-20261020.md). Original Kodi source remains pinned at `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`; no user/device configuration was modified.

## New implementation and test

A standalone source package `gazelle-fel-stage56-cpp-reference.zip` includes:

- `stage56_epoch_reference.cpp`: C++17 owner/worker epoch model, no Android or vendor dependency;
- `run_stage56_macos.sh`: Mac-host compile, selftest, 2,000-cycle threaded stress and ZIP result writer;
- README and full Stage56 analysis.

The reference uses a **single shared mutex** for the metadata pairing transition, an explicit producer-published monotonic epoch, separately acknowledged worker epoch, P7-only verified binding `(epoch,demuxer,BL,EL)`, immutable packet identities and replay, an admit/commit revalidation point, a strict small pending buffer and a direct P8 bypass. A barrier revokes prior binding and clears pending halves and replay. Priority-10 stale replay can overtake a priority-0 barrier in the *abstract scenario*, but is rejected if its epoch disagrees with the producer's already-published authority. The code does **not** implement the actual Kodi message queue or attempt JNI/MediaCodec calls.

### Local host verification

- C++17 compiled with `-Wall -Wextra -Werror -pthread`.
- Four single-thread test groups passed.
- A host run exercised 2,000 monotonic barrier publications and worker acknowledgements, concurrent stale-epoch BL/EL submissions and concurrent P8 bypass attempts, preserving the model's pair invariants.
- A separate `-fsanitize=address,undefined` build completed the same stress and passed. **This is not ThreadSanitizer and is not proof of absence of races in Kodi.**
- `run_stage56_macos.sh` was replayed locally and emitted the expected host-only marker and a ZIP containing a sanitized log and JSON. No network, ADB, vendor binary, disc media or running Kodi was involved.

Markers: `GAZELLE_FEL_STAGE56_REFERENCE_SELFTEST_PASS` and `GAZELLE_FEL_STAGE56_CPP_REFERENCE_PASS runtime_device_test=false`.

## Boundaries and source-level lessons

1. An initial `prepare()` validation is not durable: epoch publication may invalidate a packet before a worker's next commit. An **actual production safe point** must be established before irreversible codec submission; a per-packet token alone is insufficient if AddData/JNI can still be in progress.
2. The toy mutex linearizes producer/barrier/pairing state, but Kodi has separate demux/player/video-worker owners and a codec-owned pending-half queue. The present source has **no verified equivalent mutex or atomic fence**. Simply copying this lock risks blocking JNI calls, deadlock and P8 regressions.
3. Real corrected BL/EL presentation-time agreement has not been established. The reference model's equal integer PTS rule is a deterministic placeholder, **not** a production pairing algorithm.
4. A P8 bypass here is only a reference-model noninterference check; native P8 correctness must be regression-tested independently.
5. Actual P7 EL decoder allocation, RPU acceptance and FEL residual-sensitive output pixels remain **unproven**. The owner Stage53 runtime evidence continued to show P7 HDR10 and no active EL provider.

**NO-GO:** no installed Kodi patch, P7 stream-mode toggle, global OMX changes, raw native ioctls `0x179/0x301`, Blu-ray PID `0x1015` filter modification, Magisk/satellite/HDMI/optical changes. Preserve known-working P8.

**Stage57 direction:** source-only isolated event-scheduler prototype reflecting exact `DVDMessageQueue` priority and `PutBack` semantics, with in-flight commit/replay assertions and no installed binary. Production Kodi integration remains blocked on correct thread ownership, verified P7 BL/EL pair identity/timeline, and native EL/residual output evidence.
