# Gazelle FEL Stage 55 — P7 packet provenance, continuity asymmetry and epoch handoff

**20 October 2026 · Source-only; no device or Kodi mutations.** Continues Stage54 commit `a718429ff70e0870402818d78753473fda9c2f04`. All inspection targets immutable integrated Kodi commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

## Original-source pins and evidence

In addition to the eight Stage54 exact original Git blob pins, Stage55 adds six original header pins:

| Original header | Git blob SHA-1 |
|---|---|
| `Interface/DemuxPacket.h` | `4cb47b4659a208853788ecff23109424fa714f62` |
| `DVDMessage.h` | `d619e15bf0c9ce22d3211b66afd9df5f1dbfae30` |
| `VideoPlayerVideo.h` | `91e4af7b098e6fffb1e9ff563419f6053181f996` |
| `DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.h` | `76252f255f0b2bdff43735575c4111c56414f295` |
| `DVDDemuxers/DVDDemuxFFmpeg.h` | `541e2e4efb7283d7891a821ef9c1cae5760b7e70` |
| `VideoPlayer.h` | `58195f8ed824b5e507e0761071ad8cc8245912af` |

All **14** original blob identities were confirmed from the owner's GitHub repository, and an independent source review confirmed **53 positive content checks and 7 scoped negative/positive path checks** (60/60). The complete bundled Stage55 verifier has **61 separately scoped predicates**, but a full original-source replay on the owner's Mac is **pending**, not a claimed PASS.

## New original-source evidence

1. `DemuxPacket` derives from the addon-facing `DEMUX_PACKET` type; the C++ extension has `isDualStream`, `isELPackage`, `m_ptsOffsetCorrection` and a keyframe flag, but **no verified binding epoch**. `CDVDMsgDemuxerPacket` stores a raw `DemuxPacket*` and the worker retains packet-message pointers in `m_packets` for replay. Adding a field to the public addon C ABI would be an unnecessary compatibility risk; a future P7-only metadata mechanism should preserve that ABI.
2. `CVideoPlayer::ReadPacket` applies common `UpdateCorrection(packet,m_offset_pts)` before dispatch. Selected BL packets enter `ProcessVideoData`, which calls `CheckStreamChanges`, `CheckContinuity`, and `UpdateTimestamps`. Unselected `isELPackage` packets enter the video-worker queue directly, **without independently executing those three BL-selected functions**. This is a code-path asymmetry, not proof of diverged P7 timestamps: `UpdateTimestamps` predominantly updates stream tracking, and both paths share the first read-time correction.
3. Normal-message `PutBack` appends to the end read by `Get`; positive-priority replay (priority 10) can preempt a priority-zero stream-change. `Flush()` message-list removal does not itself clear codec-owned `m_doviLayerPackets`.
4. `CDVDVideoCodecAndroidMediaCodec::DolbyLayerPacket` holds bytes, layer role and PTS/DTS, without a verified demuxer/BL/EL/epoch binding. The current opposite-layer selection does not check PTS identity or epoch. `Reconfigure()` can reuse compatible codec hints while leaving the codec queue uncleared; its equality test still compares many profile/Dolby fields.
5. The production app has no demonstrated source-level last-safe-submit synchronization spanning producer epoch publication, worker message dequeue and any in-progress `AddData`/JNI enqueue. A token check performed only at queue insertion or dequeue is **not** by itself an atomic generation fence.

## Reference design and tests (never installed)

The standalone `gazelle-fel-stage55-source-model.zip` contains Python 3.9+ `audit_stage55.py`, `run_stage55_macos.sh`, a README and complete analysis report. The reference model uses a monotonic producer epoch, separately acknowledged worker epoch, verified P7 `(demuxer, BL, EL, epoch)` binding, immutable stamped packets and replay, and conservative rejection of stale and early new-generation data until a barrier and rebind. It covers 12 barrier causes, same-PTS stale packets, priority replay overtaking a barrier, invalid tracks, overflow and P8 bypass.

**Local self-test:** `GAZELLE_FEL_STAGE55_SYNTHETIC_PASS tests=18 schedules=8640` (18 Python unit tests, 8,640 bounded permutations); Python 3.9 syntax and runner shell syntax pass. These are source-only **design tests**, not real C++ thread interleaving, playback lifetime proof, corrected PTS equivalence, an active EL decoder or residual-sensitive FEL output evidence.

**Expected only after owner Mac full audit:** `GAZELLE_FEL_STAGE55_OFFLINE_PASS source_gates=61 tests=18 schedules=8640`. Do not claim this marker has already been produced.

## Decision and next gate

**NO-GO:** do not change installed Kodi, P7 native decoder, optical PID `0x1015`, Magisk, global OMX properties or kernel ioctls `0x179/0x301`. Preserve existing P8, HDMI audio passthrough, voice satellite and UDF/MMBD. Working native EL residual contribution remains unproven.

Stage56 should implement a **standalone host-compiled C++17 reference** of epoch ownership and barrier admission, with controlled thread/interleaving tests and an explicit no-ABI-change boundary. Do not treat such a prototype as an authorized Kodi integration patch without verified synchronization of in-flight codec submissions and a production BL/EL corrected-time contract.
