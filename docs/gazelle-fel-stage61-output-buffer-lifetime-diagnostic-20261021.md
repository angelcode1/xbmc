# Gazelle FEL Stage 61 — output-buffer ownership and P7 EOS diagnostics (source-only)

**21 October 2026. Research stage. No device, installed Kodi, Magisk, HDMI passthrough, optical-disc or firmware modifications.**

Follows [Stage60](gazelle-fel-stage60-output-eos-provenance-20261021.md), at pinned integrated Kodi commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`. Stage59's Mac full source audit was accepted; Stage60 and Stage61 full 14-file Mac source audits remain **pending**.

## Newly verified original Kodi source findings

The `DVDVideoCodecAndroidMediaCodec.cpp`, `.h`, and `VideoPlayerVideo.cpp` exact blob SHA pins matched original GitHub sources. The Stage61 independent review matched **31/31** new source predicates.

1. `CMediaCodecVideoBuffer::ReleaseOutputBuffer` performs the release JNI operation, **sets `m_bufferId=-1` before checking any JNI exception**. This means a locally invalidated buffer index alone cannot prove hardware-resource release succeeded. A JNI exception also does not on its own prove native buffers were retained.
2. `CMediaCodecVideoBufferPool::Return` releases the renderer-held buffer then puts its pool index on `m_freeBuffers`. `ReleaseMediaCodecBuffers` releases its buffer collection. `ResetMediaCodec` calls the release path, then clears its shared codec pointer. These are distinct from explicit proof of generation-bound output retirement. The pool has a critical section; its existence is not proof of a generation fence, and source inspection alone is insufficient to claim a deadlock.
3. An EOS flag in `GetOutputPicture` returns `-1` even when `releaseOutputBuffer(index,false)` throws. Dropping buffers can bypass the EOS-flag check. `GetPicture` also reports `VC_EOF` on `WAIT_ENDOFSTREAM` without requiring observed output EOS. `SignalEndOfStream` queues **input** EOS, not output EOS.
4. The worker's stream-change handler drains until generic false, then calls `OpenStream`; it cannot authenticate a complete, generation-matched native drain from that boolean alone.
5. Ordinary returned `CMediaCodecVideoBuffer` objects can carry surface/renderer-held output references separately from an EOS output buffer. A putative transition proof must account for them and possible JNI release failures.

## Stage61 host model and optional review-only diagnostic diff

Standalone artifact `gazelle-fel-stage61-eos-diagnostics.zip` SHA256 `83541d26bef7566a7125f0e121225490feacad1ab363a946ed956240a071683a`, provided in the conversation.

- C++17 host reference **15 targeted assertions PASS**; bounded 11-bit matrix **2,048 synthetic cases PASS**.
- Matrix counts: `wrapper_eof_without_complete_evidence=510`, `local_eos_evidence_complete=4`, `release_unresolved=64`, `non_p7_bypass=1024`. **These are synthetic states, not device observations, frequencies, production EOS success rates, or FEL proof.**
- Normal and ASan/UBSan reference runs passed; Bash syntax, Python syntax, internal SHA manifest, ZIP CRC and fresh-unzip runner passed.
- Deliberately absent offline source cache correctly refused with `STAGE61_SOURCE_AUDIT_REFUSED SOURCE_MISSING_OFFLINE DVDMessageQueue.cpp`.
- A fail-closed `stage61_diagnostic_diff.py` generator, after all **14 exact Git blob pins** verify, emits a **P7-only review diff** to `DVDVideoCodecAndroidMediaCodec.cpp/.h` in a separate results directory. It adds local session/ticket and `GAZELLE_P7_EOS_DIAG` markers for input attempts, successful input queueing, output EOS flag, release outcome, wrapper EOF reason, reset and compatible reconfigure. No timestamps, media bytes, private paths, device IDs, stream IDs or buffer indexes are recorded by these new diagnostic markers. Only synthetic matching-context transformation tests have run here; the actual pinned-source generated diff and Kodi build are **pending**.
- Local session/ticket counters are **not** authenticated producer epochs, decoder hardware IDs, renderer retirement proofs, or BL/EL binding evidence.
- No APK/source checkout is overwritten, no Kodi executable is built or deployed, and no Cube is contacted. Only generate/read the diff; do **not** install it without separate code review, full build, explicit approval and rollback plan.

Host markers:
```text
STAGE61_TARGETED_LIFETIME_PASS cases=15
STAGE61_BOUNDED_RELEASE_PROVENANCE_PASS cases=2048 wrapper_eof_without_complete_evidence=510 local_eos_evidence_complete=4 release_unresolved=64 non_p7_bypass=1024
GAZELLE_FEL_STAGE61_CPP_REFERENCE_PASS runtime_device_test=false kodi_patch_compiled=false
GAZELLE_FEL_STAGE61_HOST_PASS cases=2048 source_audited=false
```

Owner Mac command:
```bash
unzip gazelle-fel-stage61-eos-diagnostics.zip
cd gazelle-fel-stage61-eos-diagnostics
bash run_stage61_macos.sh --audit
```

Expected **only after a real network-backed source audit**:
`GAZELLE_FEL_STAGE61_SOURCE_AUDIT_PASS files=14 stage55_gates=61 stage57_gates=23 stage58_gates=29 stage59_gates=29 stage60_gates=37 stage61_gates=31` and `GAZELLE_FEL_STAGE61_HOST_PASS cases=2048 source_audited=true`.

## Decision

**Runtime FEL implementation remains NO-GO.** Native P7 enhancement-layer decoder and residual contribution, BL/EL corrected timeline, authenticated codec/renderer retirement and playback safety remain unproven. Keep working P8, HDMI audio passthrough, voice satellite and UDF/MMBD unchanged. A source-only diagnostic diff is not a tested or authorized Kodi patch.
