# Gazelle FEL Stage 63 — EOS ticket attribution and diagnostic P8 isolation

**21 October 2026 — original Stage61 diff inspection and host-only reference. No changes to the Cube, Kodi installation, Magisk, satellite, HDMI passthrough or optical UDF/MMBD.**

Continues [Stage62](gazelle-fel-stage62-diagnostic-diff-contract-20261021.md) without claiming that its full Mac original-source roundtrip has completed. Original Kodi commit is pinned to `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`. Owner Stage61 source audit and generated 11-hunk diagnostic diff passed the Stage61 14-file / 210-source-gate review.

## Two blocking attribution issues in the **review-only** diagnostic diff

1. **Output-EOS input-ticket identity is not established.** Stage61 increments `m_gazelleEosDiagTicket` for each eligible EOS *input* attempt. When `GetOutputPicture()` observes the EOS flag in an *output* buffer, its added code sets `m_gazelleEosDiagOutputObserved=true` and logs the **current** `m_gazelleEosDiagTicket`. The output buffer does **not** carry a provenance-verified matching input ticket in this code path. A hypothetical older output arriving after another input attempt is indistinguishable by these markers. Therefore `local_ticket` on `phase=output_flag` is **not proof of EOS pairing**. This is a correctness limitation of the *diagnostic interpretation*, not evidence of a real Cube race.
2. **P8 isolation needs an explicit lifecycle contract.** At `Open()`, added instrumentation sets `m_gazelleEosDiagSession` only when profile=7 and does not explicitly set it to zero for a non-P7 open. If the very same codec C++ instance could later execute `Open()` on a non-P7 stream, its old P7 session remains enabled and the additional EOS diagnostic log guards could run. Whether that reuse occurs on the real system is **not demonstrated**. The needed gate is proof of object nonreuse or deterministic diagnostic reset on any non-P7 open and at other lifetime boundaries.

A separate observation remains valid: Kodi's release operation can log a JNI exception while local buffer state is invalidated. Stage61 separately tracks observed EOS flag and `release_ok`, but successful JNI invocation alone does not prove complete native/renderer resource retirement.

## Host-only bounded reference and package

Downloadable ZIP `gazelle-fel-stage63-provenance.zip`, SHA-256 `b54061622425c6120e80ae0f8dbcd3b09d4f32b3f914d3af43321acb6890a264`. Contains `stage63_ticket_reference.cpp`, `audit_stage63.py`, `test_stage63_roundtrip.py`, the existing exact Stage61 generated diff, pinned original-source verification dependencies, Mac Bash 3.2-safe runner, README, report and internal file SHA manifest.

Locally verified:

```text
STAGE63_TARGETED_ATTRIBUTION_PASS checks=13
STAGE63_ATTRIBUTION_MATRIX_PASS combinations=240 potentially_misattributed=150 hypothetical_foreign_origin=120 conditional_p8_session_persistence=60
STAGE63_SYNTHETIC_PATCH_ROUNDTRIP_PASS files=2 no_original_sources_used=true
STAGE63_PATCH_MUTATION_REFUSAL_PASS cases=5
STAGE63_OWNER_STAGE61_AUDIT_PASS source_pins=14 inherited_gates=210
STAGE63_DIAGNOSTIC_ATTRIBUTION_RISKS_CONFIRMED checks=11 patch_hunks=11
STAGE63_OFFLINE_AUDIT_PASS source_roundtrip=false runtime_device_test=false
GAZELLE_FEL_STAGE63_HOST_PASS cases=240 source_roundtrip=false runtime_device_test=false
```

The 240 matrix combinations are **constructed model states, not frequency measurements**: 150 include unknown/foreign hypothetical output provenance while a P7 session is enabled, 120 have a specified but mismatched hypothetical input ticket, and 60 assume a reused object has reached P8 while retaining an earlier P7 session. None prove actual invocation/order on Kodi.

Separate optimized C++17 and ASan/UBSan reference executions passed. Five mutated diagnostic diffs were refused, and a **synthetic** fixture reconstructed from the original 11 patch hunks was applied and reversed in temporary files. Bash/Python syntax, manifest and ZIP CRC passed. A direct missing-original-source audit was independently checked to stop with `STAGE63_REVIEW_REFUSED SOURCE_MISSING_OFFLINE DVDMessageQueue.cpp`.

## Pending full owner Mac check

```bash
cd ~/Downloads
unzip gazelle-fel-stage63-provenance.zip
cd gazelle-fel-stage63-provenance
bash run_stage63_macos.sh --audit
```

This verifies all 14 original Git SHA blob pins, regenerates the diff byte-for-byte from the pinned sources, then applies and reverses it **only in a temporary directory**, verifying both original files are restored. Required markers:

```text
STAGE63_DIFF_REGENERATION_PASS original_files=14 match=true
STAGE63_ISOLATED_PATCH_ROUNDTRIP_PASS original_restored=true checkout_modified=false
GAZELLE_FEL_STAGE63_HOST_PASS cases=240 source_roundtrip=true runtime_device_test=false
```

**The full pinned-source roundtrip and a real Kodi build are pending.** This Stage63 test does not install or run any instrumented decoder.

## Decision

**Do not deploy the Stage61 diagnostic diff as written.** A better diagnostic should separate `input_eos_attempt`, `input_eos_queued` and `output_eos_observed` and label their relation **unattributed** until verified output-origin identity. Establish profile lifetime/reset semantics and ensure P8 logging is provably off before a future read-only build. Native Profile7 EL decoding, corrected BL/EL timeline and residual-sensitive FEL output remain unproven. Runtime P7 FEL implementation stays **NO-GO**.
