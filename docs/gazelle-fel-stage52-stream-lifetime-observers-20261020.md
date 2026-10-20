# Gazelle FEL Stage52 — raw stream lifetime, replacement and observer notification gate

**20 October 2026.** Owner's uploaded Stage51 result ended in `GAZELLE_FEL_STAGE51_OFFLINE_PASS source_gates=29 regressions=48`. Stage52 was completed **source-only** against the same three exact integrated Kodi files; no Kodi, Cube, Magisk, native decoder or optical drive was changed.

## Exact original Kodi source

Integrated `angelcode1/xbmc` commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`; exact Git blob identities:

- `DVDDemuxFFmpeg.cpp`: `4955205e22ba462cff9998b03f9e5143d1ce1ef2`
- `VideoPlayer.cpp`: `8b5cf1e6e2862936d2b3e58fe8997972d988c298`
- `DVDVideoCodecAndroidMediaCodec.cpp`: `1a313fdc297db69607b2a3f0e82069def4b198f3`

The additional original header `DVDDemuxFFmpeg.h`, Git blob `541e2e4efb7283d7891a821ef9c1cae5760b7e70`, declares `std::map<int, CDemuxStream*> m_streams`. `VideoPlayer.h`, Git blob `58195f8ed824b5e507e0761071ad8cc8245912af`, declares `CCurrentStream::stream` as `void*` (an identity token), alongside its `changes` counter. These headers were inspected independently and are *context*, not part of the three-file 39-check SHA-pinned macOS audit.

## Confirmed ownership and destruction paths

1. **The demux map owns raw pointers.** `CDVDDemuxFFmpeg::GetStream()` returns the stored `CDemuxStream*` and `GetStreams()` returns a vector of raw pointers. `DisposeStreams()` deletes every `m_streams` value, clears the map and clears `m_parsers`; `Dispose()` calls that after closing the FFmpeg input; `Reset()` calls `Dispose()` then `Open()`.
2. **Replacement invalidates the old object address.** `AddStream(int, CDemuxStream*)` inserts or, on an existing key, sets `stream->changes = old->changes + 1`, `delete old`, then assigns the new raw pointer. Therefore an existing raw identity **must not be treated as a live object** after replacement. This is a lifecycle warning, **not evidence of a runtime use-after-free**.
3. **Program rebuild invalidates all previous stream objects.** `CreateStreams()` snapshots per-index `changes`, calls `DisposeStreams()`, repopulates the map, and applies `prevChanges[streamIdx]+1`. `ReadInternal()` can call this after `IsProgramChange()` and emits a `DMX_SPECIALID_STREAMCHANGE` packet; other `ReadInternal()` paths can replace a stream when its `pPrivate`, codec, dimensions or audio properties change.
4. **The player stores an identity value, not an owned stream reference.** `CVideoPlayer::OpenStream()` snapshots `current.stream=(void*)stream`, `current.changes=stream->changes`, and stream hints. `CheckStreamChanges()` compares the *current* incoming demux pointer and `changes` to those stored values. Only if one differs does it check `CDVDStreamInfo(*stream,true)` for a possible reopen. The reviewed `CheckStreamChanges()` body compares the old pointer value, **not dereferences it**; it would be inaccurate to claim a proven UAF from this code alone.
5. **Critical metadata notification gap.** `CDVDDemuxFFmpeg::AddStream(int)` can mutate a previously registered BL's `hdr_type`, `dovi`, `isDualStream` or a registered EL's flags while finding the opposite track. That discovery body contains **no `->changes` increment**, so `CheckStreamChanges()` can see unchanged pointer+counter and bypass the updated hints. A source-level notification gap is proven; occurrence of a bad playback transition is **not measured**.
6. **Flush is not a stream-map destruction.** `CDVDDemuxFFmpeg::Flush()` resets FFmpeg packet/read state and timestamps but does not call `DisposeStreams()`. Nevertheless, pending BL/EL halves and timeline generation would require a well-defined paired-stream epoch boundary at discontinuity/seek; no such validated production contract is demonstrated by this audit. The current `MediaCodec::Reset()` explicitly clears `m_doviLayerPackets`.

## Stage52 policy model: minimum future stream-observer contract

The **extended, host-only** `ReferenceLifetime` Python model treats an observer token as `(stream ID, object generation, changes, epoch)`, **never a reusable address**. It demands independently verified pairing, and stages both metadata changes for publication. A discarded or replaced EL, program rebuild, stream removal, explicit flush/epoch change or injected prepublication failure revokes/refuses the proposal and does not leave a BL marked paired. **Revoking an already published pair must increment a surviving partner's notification version**, because simply clearing a pairing flag can be invisible to existing observers.

This is an explicit desired future protocol, **not the current Kodi C++ ownership/locking implementation**. Real implementation would need demux thread/worker observer rules, C++ pointer ownership/copy discipline, event ordering, no intermediate metadata visibility, accurate common corrected BL/EL clock, and P8/BD/navigation regression protection. A Python dictionary swap neither proves C++ atomicity nor establishes Kodi's actual thread scheduling.

## Verified offline artifacts

- `gazelle-fel-stage52-macos.zip`: ZIP SHA-256 `a09f8d9ace5c1bb484c9f1bd6cea6309e4115359376ade83b2bf3ad30e48eea7`; 3 safe source-only members; ZIP CRC passed.
- Extended `audit-stage52-lifetime.py` SHA-256 `a129bdbda030ed2b471c1eab532bf3d937da16e9eb66db476c6b9948a5eb75d0`; Python 3.9 AST grammar validated.
- All **39 original Kodi source gates** and **43 synthetic lifetime/version/epoch tests** passed.
- Exact final marker: `GAZELLE_FEL_STAGE52_OFFLINE_PASS source_gates=39 regressions=43`.
- The Mac runner passed a full replay using the owner's existing source files and saves sanitized text at `~/Downloads/gazelle-fel-stage52-results/stage52-audit-results.txt`. It reuses Stage47/48 pinned source, or downloads only public Kodi C++ source at the immutable integration commit. No vendor binaries or live device access.
- GitHub research branch additionally contains the smaller independent `tools/gazelle-fel/stage52-stream-lifetime-core.py` source and synthetic gate, tested by Actions against the pinned source. It is not identical to the extended bundled verifier.

## Decision: safe publication point NOT established in installed Kodi

A correct future design would require a **demux-owned two-stream identity+generation snapshot** and a **player-visible versioned commit after complete admission**, not an in-place mutation of an existing raw-pointer object. A safe C++ owner/observer/lifetime/locking contract has not been demonstrated. Do not ship an EL-admission exception or default-off P7 native-mode patch merely on this source-level evidence.

Separately, Stage40–43 captures saw **one connected P7 decoder**, not an observed second connected EL decoder; native stream packet/PTS and EL metadata requirements and residual-sensitive FEL reconstruction remain unproven.

**Stage53 direction:** offline map `ReadInternal()` stream-change event ordering to `OpenDefaultStreams()`, `CheckStreamChanges()` and `CVideoPlayerVideo` worker queued packets; investigate how a future pair version/epoch notification can be sequenced without stale half-packets. Preserve currently working P8, HDMI/audio passthrough, voice satellite, Magisk and UDF/MMBD.
