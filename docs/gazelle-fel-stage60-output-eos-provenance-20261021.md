# Gazelle FEL Stage 60 — output EOS flag provenance versus wrapper VC_EOF

**21 October 2026 — offline original Kodi source analysis and C++ reference only. No runtime/device modifications.**

This checkpoint follows [Stage59](gazelle-fel-stage59-worker-eos-drain-identity-20261021.md). All original Kodi source pins remain at immutable commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`.

## Owner's Stage59 full Mac audit: accepted

The owner uploaded `gazelle-fel-stage59-results(1).zip`, independently checked for ZIP integrity (archive SHA-256 `58fb1ca9b08afb63ff6f36c8fdf212551d6b1ced6ae4f27748729928c842aec8`). The included source-audit log reported all 14 original source SHA pins and `GAZELLE_FEL_STAGE59_SOURCE_AUDIT_PASS files=14 stage55_gates=61 stage57_gates=23 stage58_gates=29 stage59_gates=29`. The C++ reference reported 66 deterministic cases, 3,000 worker-model transitions, zero post-ack epoch violations, and `runtime_device_test=false`. This verifies host/source checks **only**; no real decoder output EOS or native FEL evidence was collected.

## New source-backed finding — a useful output-side signal already exists

`xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp`:

1. **Lines 1910–1928:** `GetOutputPicture()` calls `dequeueOutputBuffer(bufferInfo, timeout_us)`. A JNI exception yields `-2`.
2. **Lines 1930–1972:** For a valid output index, the `DVD_CODEC_CTRL_DROP` branch releases and returns `-2` *before checking EOS flags*. Otherwise `bufferInfo.flags()` is checked for `CJNIMediaCodec::BUFFER_FLAG_END_OF_STREAM`. When set, output-buffer release is attempted and `GetOutputPicture()` returns `-1`. The code logs release exceptions **but still returns -1 even if release fails**, so observed flag and successful output-buffer retirement are separate facts.
3. **Lines 1528–1570:** `GetPicture()` maps either `retgp == -1` **or** the mere current state `MEDIACODEC_STATE_WAIT_ENDOFSTREAM` to `VC_EOF`. If the output dequeue returned `0` (try again), then WAIT state can still produce `VC_EOF`, even without the output EOS flag. If the output dequeue returned `-2` in WAIT state, the wrapper marks ERROR and also returns `VC_EOF`. Thus `VC_EOF` alone loses the output-flag provenance.
4. **Lines 1619–1673:** `SignalEndOfStream()` queues an *input-side* `BUFFER_FLAG_END_OF_STREAM` buffer; this does **not** attest that the output EOS flag was observed.
5. **VideoPlayerVideo.cpp lines 501–520:** `GENERAL_STREAMCHANGE` stops its drain loop on a generic `ProcessDecoderOutput()` false and then opens a stream; it cannot distinguish flag-observed EOS from other exit conditions.
6. Reset clears P7 pending halves while compatible reconfigure need not. Retain Stage55–59 generation/replay protections in any future proposal.

**Correction to Stage59 interpretation:** there is a source-visible, concrete Android output-EOS flag observation. Stage59's caution about using `VC_EOF` remains valid, but the missing piece is preserving/validating the signal across decoder identity, EOS-ticket generation, release success and worker transition—not inventing another output EOS mechanism.

These are statements about original source control flow, **not a claim of actual P7 hardware EOS or FEL playback**. Independent GitHub connector reinspection of the two original source blobs matched 33 relevant content/branch checks; the bundled Stage60 auditor contains 37 scoped checks and 61+23+29+29 inherited gates requiring owner Mac replay.

## Stage60 host-only package

Conversation artifact: `gazelle-fel-stage60-eos-provenance.zip`, SHA-256 `00d04aa89084601cfd721872ee369d6dfe5e88539bf1d5d2886a5c2e1d99928d`.

Contents: C++17 finite-state classifier, macOS Bash 3.2-compatible runner, pinned 14-file source-audit chain, README, report and internal SHA-256 manifest. It makes **no device, APK, ioctl, media or kernel changes**.

Actual local host output:

```text
STAGE60_DISTINCT_EOS_CASES_PASS cases=14
STAGE60_BOUNDED_EOS_PROVENANCE_PASS cases=640 source_vc_eof=480 strong_evidence=1 ambiguous_source_eof=479 stale_tickets=320 drop_masked=64 wait_tryagain_eof=32 wait_jni_eof=32
GAZELLE_FEL_STAGE60_CPP_REFERENCE_PASS runtime_device_test=false
GAZELLE_FEL_STAGE60_HOST_PASS cases=640 source_audited=false
```

The **640 bounded cases are synthetic combinations**, not 640 device measurements or measured failure rates. The stricter reference model accepts output EOS only with a synthetic current generation ticket, successful output-buffer release, no in-flight lease, and acknowledged input EOS. These are **new design requirements not yet implemented in Kodi**; the test's single accepted combination and 479 ambiguous wrapper-EOF combinations do not represent the Cube's probability of any result.

C++17 optimized host and separate ASan/UBSan runs passed. Bash and Python static checks, archive CRC/internal SHA verification passed. An intentionally missing offline source cache yielded `STAGE60_SOURCE_AUDIT_REFUSED SOURCE_MISSING_OFFLINE DVDMessageQueue.cpp`, not a false PASS.

### Owner Mac run

```bash
cd ~/Downloads
unzip gazelle-fel-stage60-eos-provenance.zip
cd gazelle-fel-stage60-eos-provenance
bash run_stage60_macos.sh --audit
```

Full expected marker, **not yet claimed from the owner's Mac**:

`GAZELLE_FEL_STAGE60_SOURCE_AUDIT_PASS files=14 stage55_gates=61 stage57_gates=23 stage58_gates=29 stage59_gates=29 stage60_gates=37`.

## Next evidence gate and scope

A future source-only, optional **P7-only rate-limited diagnostic diff** could log decoder-instance/generation, EOS input submission, true output-buffer EOS flags, release failure and wrapper EOF reason. It must not collect PTS, private media, pixel content, protected logs or device addresses. No such change is installed or approved for runtime here.

Further native FEL progress still requires separately proving active enhancement decoder/path, BL/EL corrected clock agreement and residual-sensitive output pixels. Preserve P8, voice satellite, HDMI passthrough, optical UDF/MMBD and Magisk.

**Engineering decision: P7 FEL runtime patch remains NO-GO.**
