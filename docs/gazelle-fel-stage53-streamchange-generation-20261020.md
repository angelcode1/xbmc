# Gazelle FEL Stage 53 — queued P7 packet epochs across stream changes and codec reuse

**20 October 2026.** Owner's corrected Stage52 Mac report passed 43 synthetic lifetime tests and 39 pinned Kodi source checks. All work in this stage is source-only; no running Cube, installed Kodi, kernel, VFM, Magisk, HDMI passthrough, voice satellite or optical-disc modifications.

## Four exact integrated Kodi C++ inputs

At immutable Kodi commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`:

| File | Git blob SHA-1 |
|---|---|
| `DVDDemuxFFmpeg.cpp` | `4955205e22ba462cff9998b03f9e5143d1ce1ef2` |
| `VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |
| `VideoPlayerVideo.cpp` | `51ca08050efcd32648d20876e7ac1cae9df6e368` |

The *fourth file is newly required* because it implements the actual video-worker packet queue, stream-change handler, decoder reopen and replay behavior. The Mac verifier refuses to claim a full four-file pass if this original Git blob is not present.

## Source-level event ordering

1. `CDVDDemuxFFmpeg::ReadInternal()` handles `IsProgramChange()` by invoking `CreateStreams(m_program)` **before** it returns a special `DMX_SPECIALID_STREAMCHANGE` packet. This is a source-code order, not a guarantee that all previously queued decoder packets have been drained.
2. `CVideoPlayer::ReadPacket()` receives the special packet, rebuilds selection streams and calls `OpenDefaultStreams(false)`. Ordinary BL packets pass through `ProcessVideoData()`, while unselected EL packets use the `isELPackage` fallback into the **same** `CVideoPlayerVideo` queue. No explicit verified BL/EL binding generation is carried on existing `DemuxPacket`.
3. `CVideoPlayerVideo::OpenStream(CDVDStreamInfo)` enqueues a `CDVDMsgVideoCodecChange` with `GENERAL_STREAMCHANGE` and priority zero when the worker queue is running. In the worker's `GENERAL_STREAMCHANGE` handler, it drains decoder output, calls `OpenStream(msg->m_hints, ...)` and releases an old picture buffer. The handler does **not explicitly call `m_pVideoCodec->Reset()`**.
4. The worker's internal `OpenStream(CDVDStreamInfo&,codec)` can **reuse** the existing codec when `m_pVideoCodec->Reconfigure(hint)` succeeds, moving it to the new owner slot. It clears `m_packets` (the convergence/replay list) but has no explicit mechanism to clear a separate P7 BL/EL half-packet queue stored inside MediaCodec.
5. The original `CDVDVideoCodecAndroidMediaCodec::Reconfigure()` compares hints while excluding `COMPARE_ID` and `COMPARE_EXTRADATA`; when that comparison succeeds, it replaces `m_hints` and returns `true`. Its body has **no `m_doviLayerPackets.clear()` or `Reset()`**. Therefore a source-level path *may* preserve an unmatched P7 half across a compatible stream-change codec reuse. **We have not observed such a pending half or actual cross-generation pairing in playback.** A full stream-change may instead replace the codec, whose `Dispose()` clears the queue; the risk is conditional, not universal.
6. `CDVDVideoCodecAndroidMediaCodec::Reset()` clears `m_doviLayerPackets` when its active-codec reset body executes, and `Dispose()` also clears it. `CVideoPlayerVideo` resets codecs on `GENERAL_RESET` and `GENERAL_FLUSH`, and clears its own `m_packets` replay list. But `VC_FLUSHED` and `VC_REOPEN` handling in `ProcessDecoderOutput()` re-enqueues saved replay messages at **priority 10**, before calling codec reset/reopen. There is no proven pair-generation validation on these saved `DemuxPacket` messages.
7. The worker sometimes re-enqueues a packet after `AddData()` backpressure (`SendMessageBack(pMsg)`), and its priority filtering can defer normal queue messages. **Do not assume a simple global FIFO ordering** across priority classes; the required pre/post-stream-change barrier has not been verified.

## Tested design policy (not a Kodi patch)

The self-contained Stage53 Python 3.9+ macOS verifier `audit-stage53-queue-generation.py` has **43 deterministic synthetic generation/queue tests** plus source predicates: **20 gates on the prior three sources**, and **20 additional worker gates** requiring the exact `VideoPlayerVideo.cpp` Git blob for a **full 40-gate pass**. Its independent `ReferenceGenerationGate` metadata-only model requires:

- explicit P7-only (demuxer ID, BL ID, EL ID, verified epoch) binding;
- an epoch barrier on stream changes, codec reuse/reconfigure, reopen, reset, flush, decoder errors, program rebuild, close and pair rebind;
- invalidation of both pending BL/EL halves and saved replay packets on a barrier;
- refusal of foreign tracks, stale packets, invalid/missing PTS and bounded-queue overflow;
- a new verified binding after a barrier; **never silently match old and new epochs**.

The 43 cases and any future source gate pass are **design tests**, not proof of Kodi's runtime queue behavior or native FEL processing. Simplified exact integer timestamp equality in the model is not a validated production timestamp-correction rule. A future C++ implementation would need explicit queue ownership, flush synchronization/priority ordering, a safe atomic stream/codec-generation identity and P8 preservation.

## Reproducibility and limitations

Standalone ZIP: `gazelle-fel-stage53-macos.zip` SHA256 `a56239abeb14665ef6769b337f7d68f1d281c303588c29a73dc3d9a3226f1811`. Verifier SHA256 `5959699306fef708067743e731f8164e9ff9c3a4ed85638943b9447521b85181`, Python 3.9 grammar and 43 synthetic cases checked. ZIP CRC and runner shell syntax passed.

Runner `run-stage53-macos.sh` reuses a prior pinned source directory when available and fetches only the **missing public Kodi C++ source** over HTTPS, including the new worker file. All four files are SHA-1 Git-blob verified before a full audit; a local three-source check prints a **PARTIAL** marker only. The complete Mac output target is `~/Downloads/gazelle-fel-stage53-results/stage53-audit-results.txt`, expected `GAZELLE_FEL_STAGE53_OFFLINE_PASS source_gates=40 regressions=43` *if all new source checks pass*. No original vendor ELF, Blu-ray media, live logs, APK or Cube access is used.

GitHub research branch `research/gazelle-fireos-fel-20261019` also carries a smaller **independent** source-only `stage53-queue-generation-core.py` auditor, with 21 original-source gates and 16 synthetic tests. Those checks are distinct from the full bundled verifier.

**NO-GO:** do not install a decoder patch, relax optical PID `0x1015`, toggle a global OMX property or issue native video ioctls. No additional connected native P7 enhancement decoder was observed in the prior captures. BL/EL input metadata, native packet/PTS contracts, RPU acceptance and residual-sensitive FEL output pixels remain unproven. Working native P8, Magisk, HDMI audio passthrough, voice satellite and optical UDF/MMBD must remain unchanged.

**Stage54 direction:** verify exact `Reconfigure()` equality inputs and the worker message queue's priority/flush arbitration; design a source-only decoder generation barrier that does not assume packet FIFO or PTS equality. A supported, runtime-safe C++ implementation remains blocked until the lifetime and native decoder contracts are established.
