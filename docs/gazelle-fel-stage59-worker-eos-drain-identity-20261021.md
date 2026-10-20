# Gazelle FEL Stage 59 — worker EOS, drain exit, and epoch acknowledgement
**21 October 2026 — host-only; no Cube or Kodi modification.**

This work extends [Stage58](gazelle-fel-stage58-inflight-mediacodec-submission-fence-20261021.md). All original Kodi sources remain pinned at commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

## Distinct terminal states in pinned Kodi source

- `VideoPlayerVideo.cpp:501-520`: The `GENERAL_STREAMCHANGE` worker handler calls `SetCodecControl(DVD_CODEC_CTRL_DRAIN)` and repeats `ProcessDecoderOutput()` until a **boolean false**, then calls `OpenStream`. It has no separate verified hardware-output-drained status check in that handler.
- `VideoPlayerVideo.cpp:656-710`: `ProcessDecoderOutput()` can return false for `VC_BUFFER`, `VC_FLUSHED`, `VC_REOPEN`, `VC_ERROR` and `VC_EOF`; reset/reopen paths can also replay saved packets at priority 10. False is therefore not uniquely attributable to a physically completed output drain.
- `DVDVideoCodecAndroidMediaCodec.cpp:1528-1595`: `GetPicture()` returns `VC_EOF` for `MEDIACODEC_STATE_ERROR` and `MEDIACODEC_STATE_ENDOFSTREAM`; the latter branch may also be entered when `m_state == MEDIACODEC_STATE_WAIT_ENDOFSTREAM`. **A returned `VC_EOF` alone cannot prove native decoder output exhaustion.**
- `DVDVideoCodecAndroidMediaCodec.cpp:1619-1673`: `SignalEndOfStream()` only queues an EOS input when codec state is RUNNING; it can dequeue a separate input buffer, calls `queueInputBuffer(... BUFFER_FLAG_END_OF_STREAM)`, handles JNI exceptions and clears the input-buffer index on successful EOS queueing. EOS *requested*, EOS *input queued*, Android wrapper `VC_EOF`, and native output *drained* remain distinct.
- `DVDVideoCodecAndroidMediaCodec.cpp:1460-1526`: `Reset()` clears the pending P7 BL/EL halves and invalidates input index. Compatible `Reconfigure()` can reuse a codec without clearing the pending halves. These are different lifetime mechanisms.

The new **29/29** Stage59 source predicates were independently verified via the GitHub connector against three original pinned files. The packaged `--audit` requires the 14 original SHA-pinned Kodi sources and 61 Stage55 + 23 Stage57 + 29 Stage58 + 29 Stage59 predicates; the full Mac source audit remains **PENDING**.

## Compiled host reference — not Kodi integration

Downloadable `gazelle-fel-stage59-worker-eos.zip` SHA-256 `8aa156a797519bf8c77a36e1aee6e6e686802238218c6cf84d7d8951b923c637` includes C++17 reference, Bash 3.2-compatible macOS runner, exact source-audit chain, tests, manifest and detailed report.

- **66/66 deterministic assertions passed**, including plain/secure input leases, EOS queued vs ambiguous `VC_EOF`, failure/timeout, old EOS ticket completing after a superseding request, explicit reset disposition, admission close and fresh bind.
- **3,000 threaded model cycles passed** with `ambiguous_vc_eof=3000`, `unresolved_before_reset=3000`, `reset_fallbacks=3000` and `after_ack_violations=0`.
- Normal build and an independent AddressSanitizer/UndefinedBehaviorSanitizer build passed on the available Linux host. A fresh unpack of the package completed a real runner and ZIP output; ZIP CRC and internal SHA manifest verified.
- A real `--offline-audit` with no source cache correctly stopped at `SOURCE_MISSING_OFFLINE DVDMessageQueue.cpp`, not a fabricated source-audit PASS.

In the **reference model**, an in-flight old submission can complete after a request, but an acknowledged barrier waits for all old leases. The model rejects EOS completion from an old ticket as authorization for the new ticket. Importantly, model `ExplicitOutputEOS` is a **synthetic not-yet-validated signal**. Model `WorkerReset` is not evidence that real Kodi JNI, output-buffer and renderer lifetime is safe. The synthetic P8 traffic is not Dolby Vision playback validation. Sanitizer tests are not ThreadSanitizer.

The owner's Stage57 full source audit was verified; an **owner Stage58 full Mac audit result has not yet been provided** in this conversation. Do not assert Stage58/59 complete network-backed Mac source audits.

## Decision

**Runtime P7 FEL patch remains NO-GO.** Actual native EL decoder allocation, common BL/EL corrected timeline and residual-sensitive FEL output are unproven. Preserve existing working P8, HDMI passthrough, voice satellite, optical UDF/MMBD, vendor codecs, Magisk and disc PID 0x1015. No raw OMX/ioctl/device actions were performed.

Next evidence gate: identify a source-/vendor-backed, authenticated output-EOS completion signal or prove a reset/recreate lifetime across JNI input and output resources, then establish actual corrected BL/EL timestamp equivalence; neither is yet done.
