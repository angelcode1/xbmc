# Gazelle Fire OS FEL — user-uploaded exact vendor ELF re-analysis (2026-10-19)

## Input and status

User-supplied private archive `gazelle-fel-vendor-private.zip`, SHA-256 `ea1cf7cadfcea0c4d9dc0daa4994ba613d495c4fd5dbeda1fba19d8b722d9ddf`, contains **only** the three vendor libraries listed below. Raw ELF payloads remain private and have **not** been pushed to GitHub.

| Binary | SHA-256 | Verification |
| --- | --- | --- |
| `libOmxVideo.so` | `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` | ELF32 ARM LSB, hash matched |
| `libomx_framework_alt.so` | `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba` | ELF32 ARM LSB, hash matched |
| `libOmxBase.so` | `7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee` | ELF32 ARM LSB, hash matched |

The user's initial host report was empty because `audit-fireos-profile-boundary.py` had **not been downloaded to the working directory**; Python produced `can't open file`. That error is unrelated to the ELF contents. The same code was then executed offline on the uploaded files using `llvm-objdump` 17.0.0: 9 target disassembly windows opened successfully, and the improved script matched 11 specific ARM instruction semantics.

## Confirmed static instruction behavior

1. `libomx_framework_alt.so`:
   - `0x194a4`: `str r0,[r4,#0x20]` — vendor OMX `OmxVideoDecoder::setParameter` writes the owning component's `+0x20` field from its input structure.
   - `0x194a8`: `str r1,[r4,#0x24]` — writes `+0x24` field.
   - `0x1db6e`: `VendorPeerComponent::setOwner` writes the owner pointer at peer `+0x4`.
2. `libOmxVideo.so`:
   - `0x21a68`: HEVC format comparison against `0xb`, and `0x21aca`: owner field comparison against `0x10` before a branch that loads/appends the literal `dv_duallayer:1;`.
   - Alternate decoder `AmlogicVideoDecoder2::setUp()` tests owner `+0x20 == 0x10` at `0x3b69c` and selects kernel HEVC format 11 at `0x3b746`.
   - Dolby decoder `doCodecSpec()` tests owner `+0x20 == 0x400` at `0x3095a`; the alternate Dolby2 decoder uses the same comparison at `0x43014`.
   - `codec_set_dvmetawithel()` exports an ioctl wrapper using selector `0x179`, proven by instruction at `0x5a1a6`. The full `libOmxVideo.so` disassembly contained **no direct BL/BLX call target** to `0x5a1a0`. An indirect path or other ioctl site is not excluded.

These are **static** instructions for exact pinned binaries. The legacy gate's `0x10` check is *not* proved to be a P7/FEL-enable setting; proprietary component-owner field semantics remain unresolved. Standard AOSP Dolby profile enumerators sharing values 0x10, 0x80 or 0x400 cannot be assumed to map onto these vendor offsets.

## Remaining unknowns and next boundary

- The actual `owner+0x20` value for P7 versus P8 was **not measured**.
- The actual caller and runtime input of vendor `setParameter` index `0x7f00010d` remain unidentified.
- Neither the presence nor absence of the per-decoder `0x179` ioctl was proven by this direct-call scan.
- Kodi's 48/48 P7 copy proof, kernel `[0]dv dual layer`, stable P7 HDR10 and `dveldec(0)` remain consistent with a downstream Fire OS vendor decoder configuration limitation, but do not isolate a particular failing branch.
- No verified native FEL residual reconstruction under Fire OS.

A useful next research step is an **offline, bounded call/data-flow** from the vendor index `0x7f00010d` handler to component construction and active Dolby peer allocation. New runtime hooks, raw ioctl injection, changing decoder-mode globals, or patching `media.codec` would be premature, especially given working P8 playback and voice/audio HAL coexistence.

## Reproduction on macOS

Use the **script, not the prior empty tee output**:

```bash
cd "$HOME/Desktop/gazelle-fel-vendor-private" || exit 1
curl -fLsS --retry 2 \
  https://raw.githubusercontent.com/angelcode1/xbmc/research/gazelle-fireos-fel-20261019/tools/gazelle-fel/audit-fireos-profile-boundary.py \
  -o audit-fireos-profile-boundary.py
test -s audit-fireos-profile-boundary.py || exit 1
export PATH="$(brew --prefix llvm)/bin:$PATH"
set -o pipefail
python3 audit-fireos-profile-boundary.py . | tee "$HOME/Desktop/gazelle-fel-omx-static-report.txt"
```

The updated script confirms SHA-pinned binary matches and **actual expected ARM instructions**, rather than counting nonempty disassembly windows alone. All 11 checked instructions passed offline. Its source-only GitHub Actions syntax/selftest gate also passed. No new Kodi APK or changes to the Cube were required.
