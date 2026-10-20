# Gazelle FEL Stage 47 — Kodi demux timestamps, BL/EL selection and continuity asymmetry

**20 October 2026. Source-only investigation. No Cube, Kodi, vendor ELF, stream-mode or Magisk changes.** Stage46 owner rerun PASSED: `GAZELLE_FEL_STAGE46_OFFLINE_PASS`, **26/26 synthetic cases**, 15/15 source checks. Owner-provided `stage46-source-model-report.json` explicitly confirms no device access, no Kodi modifications, no measured P7 mispair/truncation, and no FEL pixel proof.

## Exact integrated Kodi source at commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`

The Stage47 verifier pins Git blobs for three unchanged files (refuses alternate content):

| File | Original Git blob SHA-1 |
|---|---|
| `xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp` | `4955205e22ba462cff9998b03f9e5143d1ce1ef2` |
| `xbmc/cores/VideoPlayer/VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |

All findings below are from these exact source files and do **not** claim a measured runtime failure.

## 1. Timestamps share Kodi units but are not guaranteed equal

- Demux `ReadInternal()` assigns packet PTS and DTS using `ConvertTimestamp(av_packet_pts/dts, stream->time_base.den, stream->time_base.num)`. Each original stream time base is used, then the helper returns `timestamp * DVD_TIME_BASE`.
- `ConvertTimestamp()` preserves unknown timestamps as `DVD_NOPTS_VALUE`; uses `double` arithmetic and subtracts the common demux origin/starttime under specified conditions. Common units **do not** establish equal valid PTS in every source, B-frame, damaged packet or discontinuity.
- The demuxer flags `CDemuxStreamVideo.isDualStream` / `isELStream` and copies them onto each packet's `isDualStream` / `isELPackage`. The stream detection searches for the first qualifying Dolby/non-Dolby video stream rather than storing an independently verified BL/EL pair identity.
- `CVideoPlayer::OpenDefaultStreams()` skips selecting the EL as a separate picture stream; `ProcessPacket()` sends packets marked `isELPackage` directly to the video decoder queue when they are not selected streams. This fallback branch checks the EL flag, **not an explicit pairing key with the currently selected BL stream**.

## 2. Selected BL and EL take different clock-correction paths

- For the current selected BL, `CVideoPlayer::ProcessPacket()` calls `ProcessVideoData()`, which checks continuity and calls `UpdateTimestamps()`.
- An unselected EL packet instead enters the `else if (pPacket->isELPackage)` branch and directly calls `m_VideoPlayerVideo->SendMessage(...)`, bypassing `ProcessVideoData()`.
- `CVideoPlayer::CheckContinuity()` can call `UpdateCorrection(pPacket, correction)` and in exceptional ambiguity set `pPacket->pts = DVD_NOPTS_VALUE`. Thus there is a source-level path where selected BL PTS can be altered/invalidated without applying that *same selected-stream routine* to EL PTS.
- The final `CDVDVideoCodecAndroidMediaCodec::AddData()` pairing predicate simply takes the **first pending opposite layer**, without checking PTS, DTS, stream ID or discontinuity generation. The Stage46 reference model's strict matching of **identical integer PTS** cannot be adopted into production without resolving the upstream asymmetry.

**Careful interpretation:** A conditional code path is not a captured device event. There is **no positive evidence from Stage41–46 that a real P7 timestamp correction, missing timestamp, cross-stream match or input truncation actually occurred.**

## 3. Synthetic counterexamples and scoped engineering decisions

The Stage47 verifier `tools/gazelle-fel/audit-stage47-demux-contract.py` checks 16 bounded source predicates and runs 12 host-only synthetic counterexamples illustrating:
- nominal common time-base normalization from different raw units;
- BL(PTS100), BL(PTS200), EL(PTS200) selecting BL100 in the current first-opposite predicate;
- an upstream BL-only continuity correction defeating exact PTS matching;
- equal PTS across unrelated stream identities not proving an actual BL/EL pair;
- missing PTS; packet reorder; selected video identity distinct from a boolean `isELPackage`.

They are **regression/specification demonstrations, not an installed Kodi patch, actual stream data or a FEL output test**. The current packet queue is limited to 8 entries with oldest-drop, while the MediaCodec path can truncate an oversized access unit. Stage46 already separately audited these and verified 26 corresponding reference-model tests.

### Stage47 policy gate

A future P7-only pairing change must first define/verify:
1. **Explicit BL↔EL track identity**, demuxer/lifecycle identity and selected current video association; prevent unrelated EL forwarding.
2. **Timestamp identity after corrections**: missing PTS, DTS fallback, two source timebases, rounding tolerance, B-frame order, discontinuity and reset generation.
3. **Whole-access-unit delivery:** no silent clipping on MediaCodec capacity, clean error/fallback handling, bounded queue/memory and no encryption-path regressions.
4. **P7-only default-off scope** with all P8, native Dolby, optical-UDF/MMBD, voice satellite, passthrough and Magisk paths unchanged.
5. Distinguish improvements to Kodi demux input from the larger blocker: current P7 captures show one connected decoder, **no observed enhancement decoder**, unverified native stream packet/PTS/EL metadata contract, and **no FEL residual-sensitive output pixels**.

**No compiled P7 source patch authorized yet.** Proceed to Stage48 only with a supported pair-identity/timestamp contract (or another offline proof that reduces these ambiguities), not by blindly using exact PTS equality or changing global OMX properties.

## Reproduction

`tools/gazelle-fel/run-stage47-macos.sh` downloads the verifier at immutable source commit `00715ebdab98f3aa1605884d5eaa178d97b8dd46` (Git blob `97a50d0cf4145fd57a035a578687f182f5fcfd3c`), verifies that Git blob before running any code, then downloads the three pinned Kodi source-only files at the immutable integration commit and verifies their content within the tool. All three are non-proprietary C++ source. No native vendor ELF, raw stream data or device logs are requested or distributed. The report is `~/Downloads/gazelle-fel-stage47-results/stage47-audit-results.txt`; successful full marker: `GAZELLE_FEL_STAGE47_OFFLINE_PASS`.
