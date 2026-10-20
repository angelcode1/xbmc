# Gazelle FEL Stage 48 — explicit BL/EL identity and validated-timeline contract (offline)

**20 October 2026. Stage47 owner capture and all three uploaded Kodi source files VERIFIED. Stage48 extended local source-only model: 36/36 synthetic cases, 19/19 original source gates. Installed Kodi/Cube UNCHANGED.**

## Source provenance and completed Stage47 checkpoint

Uploaded `stage47-audit-results.txt` ends `GAZELLE_FEL_STAGE47_OFFLINE_PASS` (12 synthetic counterexamples, 16 exact-source gates, no device actions). The three owner-uploaded original integration-source bytes exactly match Kodi integrated commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`:

| Source file | Verified Git blob SHA1 |
|---|---|
| `DVDDemuxFFmpeg.cpp` | `4955205e22ba462cff9998b03f9e5143d1ce1ef2` |
| `VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |

## Original Kodi code constraints

1. Demux converts per-stream PTS/DTS into the common `DVD_TIME_BASE` via `ConvertTimestamp()`. It preserves missing PTS as `DVD_NOPTS_VALUE`, and per-stream raw timebase values need not be numerically equal.
2. `CDVDDemuxFFmpeg::AddStream()` selects first Dolby/non-Dolby video candidates and tags `isDualStream`/`isELStream`; `ReadInternal()` copies flags to packets. No persistent independently validated BL/EL identity binding is proved by those flags alone.
3. Selected BL packets go through `ProcessVideoData()` → `CheckContinuity()`, which can correct or invalidate PTS; unselected EL packets are forwarded by the separate `isELPackage` branch in `ProcessPacket()`, bypassing this same continuity step.
4. `CDVDVideoCodecAndroidMediaCodec::AddData()` pairs only on opposite layer, chooses first such pending packet, drops oldest pending after eight and conditionally truncates `iSize` to a MediaCodec input buffer's capacity. `Reset()` clears the pending queue. Existing 48/48 JNI copies do **not** measure all upstream pairing/timestamp/capacity situations.

Thus simply replacing the existing opposite-layer predicate with **exact original PTS equality** is not safe to ship. There is no measured P7 mismatch or buffer truncation in the user capture, and the source does not prove a runtime enhancement decoder.

## Extended Stage48 reference contract

The standalone, host-only `stage48-pairing-contract.py` delivered in the conversation ZIP is deliberately **not a Kodi patch**. It source-SHA-pins the exact three files and runs **19 original-source gates** and **36 deterministic synthetic policy tests**. The synthetic contract includes:

- **Explicit binding:** same demuxer, a uniquely selected BL stream ID and distinct EL stream ID; boolean `isELPackage` by itself is insufficient.
- **Per-stream, externally validated common timeline mapping:** each track needs a proven timebase numerator/denominator, origin and continuity adjustment, scoped to an explicit generation/epoch. The model uses Python exact rational `Fraction` arithmetic, **unlike Kodi's production `double`**, so the model is neither a drop-in implementation nor proof that exact timestamps will always be pairable.
- **Fail-closed ambiguous data:** missing/float timestamps, unverified map, foreign tracks/demuxers, invalid/stale epochs, duplicate layer/time and unsupported layer flags must not be guessed into pairs.
- **No cross-epoch reuse:** pending halves are cleared at rebind/flush. BL-before-EL, EL-before-BL, interleaved frames, different underlying track timebases and explicit offset corrections have independent tests.
- **Whole access-unit policy:** never submit a shortened combined access unit; reject oversize or signed-int overflow. Eight pending packets and 8 MiB are **illustrative** limits, not production constants. The model stores sizes, not encoded video bytes.
- **Scope:** a non-P7 binding bypasses this model. This synthetic assertion does **not** measure installed P8 regressions.

Local markers:

```text
GAZELLE_FEL_STAGE48_SYNTHETIC_POLICY_PASS cases=36
GAZELLE_FEL_STAGE48_EXACT_SOURCE_GATES_PASS checks=19
GAZELLE_FEL_STAGE48_OFFLINE_PASS source_gates=19 regressions=36
```

Full verifier SHA256: `2a65f1e0e60b3dcb7086b2bb58ae3ca01235ff569361d025122f1b764cd9d583`.

The Mac bundle contains a readable standalone Python verifier, SHA-verified shell runner and instructions. It reuses the Stage47 pinned source directory when present, otherwise downloads **only exact Kodi C++ source text** at the immutable Kodi commit, and fails if the three Git blob hashes differ. No runtime equipment or proprietary modules are accessed; output: `~/Downloads/gazelle-fel-stage48-results/stage48-audit-results.txt`.

## Engineering conclusion — NO-GO for installed P7 stream backend

This is a specification/proof-of-constraints, **not a live diagnostic or buildable FEL backend**. Kodi's current packet handoff carries demuxer and stream identifiers but **not a validated explicit pair binding plus per-track continuity-epoch mapping**. That information must be established from a common upstream ownership and clock-correction point before any production pairing helper can safely consume it.

Even a correct input-pair policy cannot resolve the separate native blocker from Stages40–43: sampled P7 playback has **only one connected decoder**, while the original frame-mode path skips ordinary secondary creation. Native stream packetization, PTS ioctl timebase, proprietary ABI, EL metadata/RPU handshake and **actual residual-sensitive FEL pixels** remain unverified.

**Stage49, if continued:** locate the lowest Kodi source layer that simultaneously owns BL and EL track identity *and* a common pre/post-continuity timeline; design a default-off, P7-only data-flow interface (not installable patch) for that point. If neither exists, document the missing contract rather than changing mode, setting properties, patching firmware or running invasive probes. Protect working P8, Magisk, passthrough, voice satellite and optical UDF/MMBD.
