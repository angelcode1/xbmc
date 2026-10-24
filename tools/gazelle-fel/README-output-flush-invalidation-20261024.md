# Gazelle FEL — output-index invalidation is a returned native-operation boundary

**24 October 2026; Kodi source-only research. No Cube changes, no APK, no decoder hook, FEL disabled.**

## Finding

Review of the merged `GazelleFELOutputGenerationFence.h` revealed a false-positive model path. `RetireStaleWithoutJNI()` previously discarded a renderer-held output ticket whenever the phase was not `Running`. That included `FlushPending` and `FlushInFlight`. The prior host test explicitly accepted retirement while a flush had not returned.

Android's `MediaCodec.flush()` documentation says previously dequeued input/output indices become invalid **upon return**. Seek publication and entry into a potentially blocking native flush are not invalidation acknowledgments. The same holds for decoder close versus a separately acknowledged successful `stop()`.

Documented API: https://developer.android.com/reference/android/media/MediaCodec#flush()

## Narrow correction

- Each original output-ticket record now carries an `invalidated` bit, initially **false**.
- A successful native flush return **without JNI exception** marks only live tickets belonging to the active decoder/generation invalidated. An error poisons the model and confers no invalidation.
- Successful native decoder stop acknowledgment marks output tickets for that decoder invalidated. Merely calling `Close()` does not.
- `RetireStaleWithoutJNI()` rejects every still-valid ticket, even in `FlushPending`, `FlushInFlight`, `Closed`, or `Faulted`. It accepts an invalidated ticket only after an actual modeled renderer return, and never invokes JNI.
- `BeginRelease()` refuses invalidated tickets, protecting against numeric output-index reuse on a new generation/decoder.
- This **does not** convert an output-index invalidation into renderer-reference retirement. `Outstanding() == 0`, explicit `ReportRendererRetired` witness, separate original-packet dispatch completion and independent native-quiescence evidence are still required. No production witness is wired.

## Validation

Standalone source audit rejects **16** altered-host-source patterns; integrated source audit also rejects **2** worker/codec inclusion mutations. C++17 tests cover early seek and flush-in-progress stale discard refusal, JNI flush error refusal, later successful return, decoder stop/reopen with recycled index, input/output debt, and existing concurrency/overflow cases. Validated locally under GCC regular/UBSan and Clang ASan+UBSan. GitHub Actions outcomes must be independently checked for the exact committed SHA; a source-only test is not a full Android build.

## Remaining native gate

This model still cannot establish Amlogic's internal decoder quiescence. An OEM `OMX_CommandFlush`, `onFlushDone` symbol, MediaCodec JNI return or Android first-frame-after-flush log independently cannot prove all asynchronous codec work and Surface/renderer consumers have retired. Actual Kodi code still calls `MediaCodec.flush()` and output buffer releases without generation-aware coupling. The user’s two seek observations show errors around flush, but are insufficient to distinguish stale indices from deeper driver races.

**Operational NO-GO:** Do not enable research FEL, call native decoder from the fence mutex, change vendor OMX binaries or policy, merge into `master`, install a new APK, or alter UDF/MMBD/HDMI/satellite. The target is to preserve this corrected, dormant model on the Gazelle Kodi source branch.