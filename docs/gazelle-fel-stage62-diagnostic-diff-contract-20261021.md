# Gazelle FEL Stage 62 — P7 diagnostic diff contract and isolated replay

**21 October 2026 — source-only research; no Cube, installed Kodi, Magisk, optical-disc, vendor codec or device writes.**

Follows the [owner-verified Stage61 source audit](gazelle-fel-stage61-output-buffer-lifetime-diagnostic-20261021.md) and the [Stage60 EOS provenance finding](gazelle-fel-stage60-output-eos-provenance-20261021.md).

## Verified inputs and correction

The user's `gazelle-fel-stage61-results.zip`, SHA-256 `505d8f380a15af10fe9eb42536c4132f91bd91744a1e3c3fa84223ec299eed40`, passes ZIP CRC and has 8 expected members, 14 original Kodi source blob SHA pins, **210/210** inherited/new source predicates, 15 targeted lifetime checks, 2,048 bounded synthetic cases, and a complete source-only P7 EOS review diff. Its summary says `source_audited=true` and `kodi_diff_production_compiled=false`.

**Important correction:** the actual generated owner patch consists of **11 hunks, 97 added lines and 1 removed line** across `DVDVideoCodecAndroidMediaCodec.cpp/.h`. Stage61's synthetic test marker `hunks=10` is **not** the hunk count of the owner-generated diff. The one removed line is an `if (xbmc_jnienv()->ExceptionCheck())` line, replaced in the new diff with a local boolean expression and corresponding conditional. No new `return`, `goto`, `break`, `continue` or C++ JNI media-control call was added. These are textual checks and do not guarantee a Kodi build or production-equivalent behavior.

The P7-only instrumentation maintains local `session` and `ticket` counters; those are **not authenticated producer epochs, decoder hardware identities, paired BL/EL stream bindings or output retirement proofs**. Logging and exception-check refactoring can still affect scheduling and require source/ABI/thread reviews. No device was contacted.

## Stage62 standalone offline package

Downloadable conversation artifact `gazelle-fel-stage62-review.zip`, SHA-256 `d449d9ba7cd6cd02b29fb140e010f561632968ec1424bbdb6b52c17a1a8e66a4`. Contains a fail-closed owner Stage61 ZIP auditor, exact source-diff generator dependencies, isolated C++17 scoped semantics model, nine adversarial archive-mutation tests, Mac Bash 3.2-safe runner, original owner-generated **review-only** diff, reports, and SHA-256 manifest.

Verified locally:

- `STAGE62_RESULTS_INTEGRITY_PASS source_pins=14 source_gates=210 stage61_cases=2048`
- `STAGE62_PATCH_SHAPE_PASS files=2 hunks=11 additions=97 removals=1`
- `STAGE62_ADVERSARIAL_ARCHIVE_PASS cases=9 baseline=PASS mutated=REFUSED`
- `STAGE62_DIAGNOSTIC_TICKET_SELFTEST_PASS checks=9`
- `STAGE62_SCOPED_CONTROL_EQUIVALENCE_PASS cases=10240`; 7,680 control cases had P8 or disabled diagnostics; the check uses two independently coded **narrow branch abstractions**, not the real Kodi code or JNI.
- `GAZELLE_FEL_STAGE62_CPP_REFERENCE_PASS runtime_device_test=false kodi_patch_compiled=false`
- Optimized and separate ASan/UBSan builds, Bash and Python syntax, ZIP CRC, SHA manifest, and fresh-unzip runner smoke test passed.

The **full Stage62 `--audit` is still PENDING on the user's Mac**. It must read the owner's already-cached 14 original Kodi source files at immutable commit `a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd`, confirm actual Git blob hashes, regenerate the owner's diff **byte-for-byte**, stage copies of the original codec .cpp/.h in an isolated temporary directory, `git apply --check`, apply, reverse and compare the restored copies. It must not alter the Kodi checkout. The current host has no direct access to these original source files, though the Stage61 owner's Mac full audit already passed.

Run on Mac with `gazelle-fel-stage61-results.zip` and cached original Kodi files retained:

```bash
cd ~/Downloads
unzip gazelle-fel-stage62-review.zip
cd gazelle-fel-stage62-review
bash run_stage62_macos.sh --audit
```

Required full markers include:

```text
STAGE62_DIFF_REGENERATION_PASS original_files=14 match=true
STAGE62_ISOLATED_PATCH_ROUNDTRIP_PASS source_pinned=true kodi_checkout_modified=false
GAZELLE_FEL_STAGE62_HOST_PASS cases=10240 full_diff_roundtrip=true runtime_device_test=false
```

Owner output ZIP is printed as `UPLOAD_FILE=...`.

## Decision and next gate

**NO-GO** for production Kodi compilation/deployment of the diagnostic diff or any P7 FEL runtime behavioral changes yet. After full Stage62 Mac audit, require an independent compilation/ABI/threading review and an explicit read-only runtime data-minimization and rollback plan *before* proposing a device diagnostic. FEL native enhancement-layer decoding and residual-sensitive output pixels remain unverified. Protect known-working P8, voice satellite, HDMI passthrough, Magisk and optical UDF/MMBD.
