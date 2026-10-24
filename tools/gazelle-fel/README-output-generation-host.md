# Gazelle FEL output-generation / renderer-return fence — host-only checkpoint

**24 October 2026.** **Feature OFF. No live Kodi integration. No Cube action. No APK.**

## Evidence that motivated the model

The user-supplied 24 October captures documented 11 explicit `OMX_CommandFlush` in the second seek observation, 25 Kodi `CMediaCodecVideoBuffer::ReleaseOutputBuffer` errors, and a decoder instance recreation between the fourth and fifth explicit flush. An earlier seek capture reported eight flushes with output-release errors. The 29 private binary/config captures matched their SHA-256 manifest. The Amlogic native modules expose `doFlushPort`, `flushInput`, `flushOutput` and `onFlushDone` functions, **but no proven end-to-end quiescence acknowledgment**.

Kodi's `CDVDVideoCodecAndroidMediaCodec::Reset()` directly calls `m_codec->flush()`; `CMediaCodecVideoBufferPool::Return()` independently calls `ReleaseOutputBuffer(false,0)`. Android invalidates previously dequeued MediaCodec input/output indices when flush returns. Therefore packet-lease `Finish(token)` and `MediaCodec.flush()` returning are different obligations from renderer-owner retirement. Error logs alone do not prove continued hardware work after flush.

Source: `angelcode1/xbmc`, `xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp`, and repo's existing `GazelleFELNativeQuiescenceGate.h`.

## What the new model establishes (synthetic host only)

`GazelleFELOutputGenerationFence.h` is **standalone C++17** and intentionally excluded from real `VideoPlayerVideo.cpp` and the JNI codec. It adds:

- A stable `(decoder incarnation, output generation, ticket serial, native output index)` handle; buffer index alone is not identity.
- Bounded 64-record outstanding renderer holds, with no clearing of old owners at seek or recreation.
- A two-step JNI release permit (`BeginRelease`/`FinishRelease`), enabling external blocking JNI calls **outside** the fence's own mutex.
- Seek publication that immediately freezes new JNI release permits; flush cannot begin while existing JNI release operations remain in flight.
- Flush permit and explicit success/exception outcome; once flush is requested, later returns are retired without calling native `releaseOutputBuffer` on stale indices.
- Barrier acknowledgment only after a successful modeled flush return **plus** zero held output tickets **plus** a separate synthetic pool/renderer-retirement witness. Both input lease and independent native-quiescence proof remain **additional** requirements; see composite test.
- Decoder close/reopen identity increments, so a recycled numeric index cannot pass the old incarnation check. Native close overlapping a running JNI operation permanently refuses reopening this fence.
- Refusal of duplicate releases, repeated or out-of-order seeks, capacity overrun, wrapped counters, JNI errors and false renderer witnesses.

Host test prints `GAZELLE_OUTPUT_GENERATION_HOST_PASS` and source mutation test prints `GAZELLE_OUTPUT_GENERATION_SOURCE_PASS negative=12` in the standalone package, or negative=14 when run in full Kodi research checkout. Tested with GCC and Clang, plus UBSan and ASan+UBSan. This is not a JNI runtime test, Kodi Android build, or native decoder quiescence proof.

## Limitations and NO-GO boundaries

1. `ReportRendererRetired(..., true, true)` is **caller-supplied synthetic evidence**; existing Kodi code cannot truthfully issue it. No fake callback may be wired into the live worker.
2. New `RequestFlush` does not make the separate `NativeQuiescenceGate` or real `SeekFence` callable from Kodi. The three barriers must remain independent. No atomic cross-fence commit or real Kodi producer fairness has been demonstrated.
3. No actual native `ReleaseOutputBuffer` start/end timestamp or OMX completion token is emitted by this model. A pending native call can remain blocked indefinitely; model refuses rather than forcing progress.
4. The output pool may have additional Surface/BufferQueue references that cannot be inferred from tracked output indices; a complete real output retirement witness needs more instrumentation.
5. Even a clean MediaCodec flush and renderer retirement would not establish that an original demux input buffer is no longer used by native decoder hardware or that Dolby FEL residual decoding works.
6. A successful host test does not authorize enabling `kDeferredStockResearchEnabled`, installing an APK, changing the working Kodi branch, vendor libraries, Magisk, passthrough or satellite.

## Next gate

Source-only instrumentation design (still OFF): record codec incarnation, JNI `Reset()` call begin/return and exception, output index acquisition, release begin/return + status, renderer reference counts and explicit pool retirement under a single monotonic generation schema. Prove ordering under actual Kodi VideoPlayer worker/renderer threads on a separate test build. Only after independent native decoder input and output work can be proven quiescent should a seek barrier be considered for real wiring.