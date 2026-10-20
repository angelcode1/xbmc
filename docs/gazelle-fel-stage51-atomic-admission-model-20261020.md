# Gazelle FEL Stage51 — atomic BL/EL admission and rollback source model

**20 October 2026 · Python 3.9+ compatible · offline, uninstalled design only.**

## Stage50 owner result

The owner-uploaded `stage50-audit-results(2).txt` ends in `GAZELLE_FEL_STAGE50_OFFLINE_PASS source_gates=26 regressions=25`. All three integrated Kodi original source blobs matched commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`, and the source-level ordering risk was reconfirmed: a registered BL's `hdr_type`, `dovi`, and `isDualStream` can be changed before a newly discovered EL stream with Blu-ray PID `0x1015` reaches `AVDISCARD_ALL` and early return.

These findings apply to *particular source paths*, not demonstrated behavior of the owner's specific P7 playback, input type, or real EL PID.

## Exact original source files

| File | Original pinned Git blob |
|---|---|
| `DVDDemuxFFmpeg.cpp` | `4955205e22ba462cff9998b03f9e5143d1ce1ef2` |
| `VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |

The extended Stage51 verifier checks **29 exact-source contract predicates** including the two candidate-discovery orders, direct BL `hdr_type/dovi/dual` mutations, fallback dovi P7 metadata, conditional Blu-ray PID `0x1015` discard, navigation identity, duplicate suppression, language and default-stream metadata, normal registration, packet role propagation and MediaCodec pairing/capacity behavior.

## Original problem: pre-admission mutation

`CDVDDemuxFFmpeg::AddStream()` has a first-candidate BL/EL discovery block which mutates an already registered BL (or an existing EL when the BL arrives second) **before** the candidate has passed the later, Blu-ray-specific suppression and admission logic. For `HAVE_LIBBLURAY` + `DVDSTREAM_TYPE_BLURAY` + PID `0x1015`, the new EL can be discarded while already-existing stream flags remain changed. A later duplicate disc stream rejection is another reason why a speculative pairing mutation must not precede admission.

This is source evidence of **potential inconsistent metadata**, not proof that Kodi ever sent an actual EL to a secondary original Fire OS decoder.

## Proposed Stage51 admission design (NOT implemented in Kodi)

The standalone Python reference model `AtomicDemuxModel` has immutable `Stream`, `Policy`, and `Proposal` snapshots. It deliberately stores metadata only, no compressed video.

1. **Admission first:** register a candidate video stream independently, preserving its existing PID, language and default attributes. Preserve original disc rules, including PID `0x1015` discard when compiled with Blu-ray support. Do not set dual-stream or EL-role flags during provisional BL/EL discovery.
2. **Identity and scope:** demand an independently verified (demuxer ID, BL stream ID, EL stream ID) binding, distinct roles, HEVC, profile-7 EL, matching demuxer, and a validated common timeline. Source flags and first-candidate search are not themselves sufficient.
3. **Proposal:** capture the current registry revision and continuity epoch. Merely preparing a proposal changes no registered stream metadata.
4. **Atomic publish:** after validating that the exact issued proposal remains current, prepare copies of both BL and EL metadata, then swap the complete dictionary in one model operation; if either copy or any pre-swap test fails, original metadata is untouched.
5. **Rejection and teardown:** unknown/duplicate tracks, invalid or stale proposals, foreign demuxers, disallowed disc EL, missing verification, removed partner, and epoch changes leave no dangling BL/EL paired flag. Reconfiguration requires an advancing epoch.

**Important model boundary:** Python immutable dictionary swap is *not* a drop-in C++ thread-safe transaction. Actual Kodi `m_streams` owns heap-allocated pointers, and a runtime implementation would require lock/ownership and observer contracts across demux and VideoPlayer, a guaranteed commit or rollback site, and tests proving no other consumer saw intermediate state. The synthetic policy's `verified_track_binding`, `verified_timeline`, `confirmed_p7` flags are **supplied test assumptions**, not proven live values or existing Kodi capabilities. The original PID `0x1015` disc filter remains enabled by default in the model.

## Reproducible local Stage51 results

- Bundle: `gazelle-fel-stage51-macos.zip` (SHA256 `a32604f48600fbf957c02716d21098fb3fd38cd9ebd399fd62026ed7245c521b`)
- Full offline verifier: `audit-stage51-atomic-admission.py` (SHA256 `29b0b0b233778fa4d1a23a92473b5f6b95b168173082a9fcc77bfeefc6951a0d`)
- Python 3.9-compatible annotations, Python 3.9 AST grammar verified
- **48/48 synthetic admission/rollback cases**, including failure injection before metadata publication and rejection of proposal-ID tampering
- **29/29** pinned original-source checks
- ZIP CRC OK; shell syntax OK; full runner replay against owner's exact original source bytes passed
- Final `GAZELLE_FEL_STAGE51_OFFLINE_PASS source_gates=29 regressions=48`
- Output: `~/Downloads/gazelle-fel-stage51-results/stage51-audit-results.txt` and sanitized JSON policy summary. No Cube, Kodi binary, vendor ELF, media, ADB, sysfs, Magisk or native codec operation was involved.

The GitHub research branch additionally carries a smaller source-only CI core gate to verify original source ordering and admission invariants, distinct from the full 48-case bundled verifier.

## Decision / next work

**NO-GO** for any installed P7 decoder modification or optical-disc EL-filter exception. To move from model to Kodi code would first require concrete original Blu-ray PID / input-kind evidence, verified BL/EL ownership and common corrected epoch, safe C++ lifetime/locking/rollback, and proof that disc navigation and menu compatibility are unaffected. Stage40–43 showed **only one observed connected P7 decoder**; the original vendor packet/PTS/EL metadata contract and **FEL residual-sensitive output pixels** remain unproven.

Stage52, if pursued, should map the exact `m_streams` ownership/observer lifetimes (including pointer replacement/invalidation under `AddStream`, `Dispose`, `CreateStreams` and program/playlist changes) and seek the earliest actually safe atomic commit point. Continue **source-only**; do not relax PID `0x1015`, flip global OMX properties, install experimental Kodi, or alter working P8, HDMI passthrough, voice satellite, Magisk or optical UDF/MMBD.
