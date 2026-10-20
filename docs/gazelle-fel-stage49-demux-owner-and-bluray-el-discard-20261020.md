# Gazelle FEL Stage 49 — authoritative BL/EL ownership and conditional Blu-ray EL discard

**20 October 2026 · Original integrated Kodi source audit passed (22 gates, 20 synthetic cases). Source-only work. No Cube or installed Kodi modifications.**

## Stage48 checkpoint

The previous Stage48 original-source audit passed `GAZELLE_FEL_STAGE48_OFFLINE_PASS source_gates=19 regressions=36`. Its reference pairing policy required an explicit BL/EL track binding, common epoch and corrected timeline, and whole-access-unit delivery. These were specification assumptions, **not fields already supplied by the installed Kodi decoder**. Existing P7 runtime measurements showed only one connected kernel decoder; residual-sensitive Dolby Vision FEL pixels remain unproven.

## New Stage49 original source findings

All three user-supplied sources were SHA-pinned to Kodi integrated commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`:

| Original file | Git blob |
|---|---|
| `DVDDemuxFFmpeg.cpp` | `4955205e22ba462cff9998b03f9e5143d1ce1ef2` |
| `VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |

### 1. A separate optical-disc EL discard gate, before packets reach Kodi's decoder

In `CDVDDemuxFFmpeg::AddStream()`, after a first-candidate BL/EL pairing routine, the code contains the following **conditional** block:

```cpp
#ifdef HAVE_LIBBLURAY
if (m_pInput->IsStreamType(DVDSTREAM_TYPE_BLURAY))
{
  if (pStream->id == 0x1015)
  {
    pStream->discard = AVDISCARD_ALL;
    delete stream;
    return nullptr;
  }
  // ...
}
#endif
```

The original comment identifies PID `0x1015` as a Dolby Vision enhancement stream. The original pairing code **appears earlier in the function** and can assign `bl->isDualStream=true` and `st->isELStream=true`, before a later `0x1015` stream is discarded. Therefore, **depending on the order and Dolby metadata of the streams**, a BL can be left marked as a dual-track video while the disc EL stream is discarded. This is a source-level potential inconsistency, not proof that every disc or the owner's earlier P7 content took that branch.

This is a **separate issue from the frame-mode kernel secondary decoder**. Fixing source-level packet ordering alone cannot yield FEL from an enhancement stream the demuxer does not expose; preserving EL alone also cannot create the original Fire OS native EL decoder and residual processing.

**Scope is strict:** `HAVE_LIBBLURAY` must be compiled, `m_pInput` must have `DVDSTREAM_TYPE_BLURAY`, and `pStream->id` must equal `0x1015`. The original test medium (disc vs remux) and actual incoming EL PID were not established from Stage48's synthetic tests. Do **not** treat this gate as evidence of the cause of the owner's HDR10 fallback.

### 2. Lowest source ownership points: demux track selection vs player clock

- `DVDDemuxFFmpeg::AddStream()` knows the demux streams, `uniqueId`s, Dolby side data, and provisional BL/EL roles. But its candidate search uses the **first** qualifying opposite-stream candidate, not a stored pair identity with a supported validity epoch.
- `CDVDDemuxFFmpeg::ReadInternal()` copies only video role flags `isDualStream` and `isELStream` to the outgoing `DemuxPacket`.
- `CVideoPlayer::OpenDefaultStreams()` deliberately skips selecting the EL as a second picture.
- `CVideoPlayer::ReadPacket()` applies the common `m_offset_pts` correction to each ordinary demux packet **before stream resolution and routing**.
- Selected BL packets then go through `ProcessVideoData()` → `CheckContinuity(m_CurrentVideo, pPacket)`, which may apply **another** per-packet correction or invalidate PTS/DTS.
- Unselected EL packets enter `ProcessPacket()`'s `else if (pPacket->isELPackage)` branch and are sent to the video worker without that selected-BL continuity step. The branch does not independently check a bound demuxer and expected EL unique ID against the selected BL.
- `CDVDVideoCodecAndroidMediaCodec::AddData()` searches only for the **first opposite-layer pending packet** and does not validate stream identity or timestamp in the predicate.

The global `m_offset_pts` does apply to both packets at read time; earlier notes that said EL receives *no* continuity correction would be too broad. The precise asymmetry is the **additional selected-video continuity correction after the common read-time adjustment** and potential correction/epoch changes while packets are queued.

### 3. Remote-stream disable callsite is not equivalent to an EL discard

`OpenDefaultStreams()` also has a conditional remote-item `EnableStream(...,false)` call for unselected tracks, but the `CDVDDemux` base implementation is a no-op and the pinned `CDVDDemuxFFmpeg.h` declares no specific override. This callsite alone does **not** prove the FFmpeg demuxer dropped EL. The guarded Blu-ray PID `0x1015` / `AVDISCARD_ALL` branch above is the concrete source-level discard gate.

## Architectural outcome: a cross-layer contract, not a one-line Kodi fix

No one existing layer simultaneously owns *authoritative, stable* BL/EL track binding **and** the post-continuity timestamp relationship used for pairing.

The appropriate proposed **future** interface would require demux-owned `(demuxerId, blUniqueId, elUniqueId, generation)` with exact Dolby metadata and stream-selection validity, plus player-owned normalized timeline/epoch updates applied consistently to both packet halves. A P7-only handler should reject stale/foreign tracks, missing or divergent timestamps, orphaned EL, incomplete access units and queue overflows. These interfaces do **not exist as a verified production contract** today.

Disc handling needs an **additional gate**: if an EL track is needed for P7 FEL, it must survive disc stream discovery, while preserving all existing disc-menu, audio, optical UDF/MMBD and profile-8 paths. Merely deleting the `pStream->discard` code without testing Kodi's Blu-ray ownership semantics is not authorized.

## Reproducible Stage49 offline audit

The self-contained conversation ZIP `gazelle-fel-stage49-macos.zip` carries full readable Python script `audit-stage49-p7-ownership.py`, SHA-256 `aa096c8fb0d4a3ae068788472ed23a42ea4f66c95bf1093d4210b4920a37e96c`, Mac runner, and README. Local original-source audit passed **22 bounded source checks** and **20 synthetic topology cases**, ending:

`GAZELLE_FEL_STAGE49_OFFLINE_PASS source_gates=22 regressions=20`.

The bundled runner was executed successfully in a host-only test, and ZIP CRC verified. It reuses immutable Kodi source already saved in Stage47/48, or downloads only exact public C++ source text at the pinned commit; outputs `~/Downloads/gazelle-fel-stage49-results/stage49-audit-results.txt`. No ADB, sysfs, native video, secrets or binaries.

The research branch also contains a smaller independently source-pinned repository gate `tools/gazelle-fel/stage49-disc-track-gate.py`, with CI source safety, original source hashes and conditional BD discard checks.

## Next Stage50 gate

1. Determine whether the owner's actual P7 use case is a `bluray://` disc path, a dual-track MKV/file, or both, using existing metadata rather than intrusive playback.
2. Study FFmpeg's `AVDISCARD_ALL` and Kodi Blu-ray `pStream->id` mapping for this exact integration, and identify an **unambiguous P7-only exception test** if warranted (source-only, default-off until validated).
3. Design a way to surface a verified BL/EL binding and shared corrected epoch at the Kodi demux→player boundary. Do not switch decoder mode or build/install an unverified native backend.
4. Require native pair creation, EL decoding, RPU metadata and **residual-sensitive pixel evidence** before calling P7 FEL working.

Existing P8 Dolby path, Magisk, HDMI/audio passthrough, voice satellite, UDF/MMBD and installed Kodi stay unchanged.

## Stage49 macOS Python 3.9 compatibility correction

The first user-run `gazelle-fel-stage49-macos.zip` terminated before tests with `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` at `dvd_pid:int|None`. That is a Python annotation syntax/runtime compatibility issue (PEP 604 unions need Python 3.10+), **not a kernel, Kodi, or original-source audit failure**.

The corrected **standalone conversation ZIP** is `gazelle-fel-stage49-macos-py39-fixed.zip`, SHA-256 `6e3fd626a64e76e0b69c48c1ff784d12c02284ee09560bbacc7c7f935206b937`. Its source replaces the three annotations with `typing.Optional[int]` or `typing.Optional[Track]`. Source SHA-256 is `7c716b966f1bf7354f8395275f13dca52500c5c3829186b8cb0299041dd4604e` and the bundled runner verifies that updated SHA before execution.

The corrected source passed Python 3.9 grammar parsing, 20 synthetic regression tests, 22 exact pinned-Kodi-source checks, ZIP CRC, shell syntax, and a full offline runner replay. The exact original Kodi Git blob pins and all FEL interpretation limits are unchanged. The original research-branch repository gate `stage49-disc-track-gate.py` is independent of the bundle's extended Python script and passed source-only GitHub CI.

Owner Mac instructions:

```bash
cd ~/Downloads
unzip -o gazelle-fel-stage49-macos-py39-fixed.zip -d ~/Downloads
bash ~/Downloads/gazelle-fel-stage49-macos/run-stage49-macos.sh
```

Expected `GAZELLE_FEL_STAGE49_OFFLINE_PASS source_gates=22 regressions=20`. No Cube access.
