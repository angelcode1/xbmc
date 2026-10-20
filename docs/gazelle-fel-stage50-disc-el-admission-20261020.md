# Gazelle FEL Stage 50 — Blu-ray EL admission order and fail-closed exception design

**2026-10-20 · Original Kodi source only · Installed Cube and Kodi unchanged.** Stage49 owner-uploaded corrected audit `stage49-audit-results(2).txt` **passed**: 20 synthetic cases, 22 source checks, all three original Git blob hashes, final marker `GAZELLE_FEL_STAGE49_OFFLINE_PASS`.

## Pinned integrated Kodi version

Source comes from the owner's original integrated `angelcode1/xbmc` commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`:

| File | Original Git blob SHA1 |
|---|---|
| `DVDDemuxFFmpeg.cpp` | `4955205e22ba462cff9998b03f9e5143d1ce1ef2` |
| `VideoPlayer.cpp` | `8b5cf1e6e2862936d2b3e58fe8997972d988c298` |
| `DVDVideoCodecAndroidMediaCodec.cpp` | `1a313fdc297db69607b2a3f0e82069def4b198f3` |

The extended owner-replay audit checks these exact source bytes and refuses any other file content. It passed locally with **26 exact source checks and 25 synthetic topology tests**, including an entire command-runner replay. Final marker `GAZELLE_FEL_STAGE50_OFFLINE_PASS source_gates=26 regressions=25`.

## New source-level finding: premature BL metadata mutation

In `CDVDDemuxFFmpeg::AddStream()`, the original two-way BL/EL discovery can mutate an *already registered* base-layer entry before the newly discovered EL candidate is finally admitted. This includes assigning `bl->hdr_type = HDR_TYPE_DOLBYVISION`, `bl->isDualStream = true`, `st->isDualStream = true`, and `st->isELStream = true`. The **later** guarded Blu-ray stream block:

- is compiled only under `HAVE_LIBBLURAY`;
- executes only for `m_pInput->IsStreamType(DVDSTREAM_TYPE_BLURAY)`;
- checks `pStream->id == 0x1015`;
- then sets the original FFmpeg stream's discard to `AVDISCARD_ALL`, deletes the temporary Kodi stream, and returns `nullptr`;
- runs **before** normal `AddStream(stream->uniqueId, stream)` final registration.

A scenario is therefore possible where the previously registered BL retained `isDualStream` (and its Dolby metadata), even though the matching newly discovered EL was rejected by the disc filter. This is a **source-level ordering inconsistency under conditional stream discovery**. It has not been observed in the owner's playback and is not evidence that a native enhancement decoder was allocated.

The Blu-ray branch additionally establishes important existing contracts: `dvdNavId = pStream->id`, duplicate Blu-ray stream suppression, `GetStreamInfo()` language mapping, and `IsDefaultStream()` selection. An EL exception that skips any of these or otherwise disrupts disc navigation is unsafe.

An EL packet's eventual `isELPackage` is obtained from an **admitted** stream's `isELStream`. Existing Kodi then skips choosing an EL as a separate default picture, forwards unmatched `isELPackage` packets to the video queue, and MediaCodec pairing still selects the first opposite-layer packet without confirming its BL/EL identity or presentation timestamp.

## Decision: do not patch the disc filter yet

The standalone Stage50 reference policy distinguishes `NOT_THIS_DISC_EL_BRANCH`, missing P7 profile confirmation, missing BL/EL identity, stale epoch, unresolved disc-menu compatibility, missing native EL decoder contract, and missing residual-sensitive pixel oracle. Even when synthetic conditions are supplied as valid, the model returns **`DESIGN_ELIGIBLE_ONLY_NOT_AUTHORIZE_RUNTIME`**, not permission to alter the decoder or stream discard setting.

The current user capture does **not** establish whether the P7 test entered the guarded `DVDSTREAM_TYPE_BLURAY` path, whether the actual EL PID was `0x1015`, or whether any source-level premature metadata mutation occurred. Do not infer those from a P7 title, an HDR10 source-format result or configured VFM provider names.

### Reproducibility

The **standalone verified** macOS bundle `gazelle-fel-stage50-macos.zip` contains:
- `audit-stage50-bluray-admission.py` — readable Python **3.9+** offline verifier;
- `run-stage50-macos.sh` — SHA-256 pins the bundled verifier and then reuses earlier pinned Kodi source files, otherwise retrieves only the three exact public C++ files from immutable commit;
- `README.md`.

Bundle SHA256 `8fdedf0c8839b376eac4519c3ed323d6f0a03d6f201a63d3f6f6cf132b4e0baf`; verifier SHA256 `a3949936d6ed44cc43448eaef8d7a7bb93d79a2a3262cb9bbc5034934aacfb9b`. Complete host-only runner replay and ZIP CRC passed. Output: `~/Downloads/gazelle-fel-stage50-results/stage50-audit-results.txt`. No owner private modules, media, secrets, ADB or runtime calls.

The GitHub research branch has a smaller **independent** source-only gate `tools/gazelle-fel/stage50-bluray-el-admission-gate.py`; the extended 26/25 verifier is self-contained in the ZIP and is not identical to the smaller repository gate. The independent gate checks original source-pin, branch ordering, disc navigation invariants and synthetic fail-closed cases. CI only runs non-device source work.

## Stage 51 decision

Before a P7-specific Blu-ray source policy is considered for default-off build testing, establish: (1) specific physical-disc vs remux/file input type and verified original EL PID; (2) authoritative BL/EL selection and `DVDSTREAM_TYPE_BLURAY` navigation compatibility; (3) atomic metadata commit *after* both tracks are admitted; (4) synchronized corrected PTS/epoch; (5) a valid separate native EL decoder instance, metadata/RPU acceptance and **residual-sensitive pixel output oracle**.

A contained, testable **source-only atomic discovery/rollback model** is a reasonable Stage51 task. Changing global OMX mode, probing invasive ioctls, installing modified Kodi, or relaxing the Blu-ray PID filter is **not** authorized by Stage50 evidence. Preserve P8, Magisk, voice satellite, HDMI/audio passthrough and optical UDF/MMBD functionality.
