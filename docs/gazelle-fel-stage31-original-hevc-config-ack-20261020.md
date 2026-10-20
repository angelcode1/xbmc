# Gazelle FEL Stage 31 — original native HEVC configuration gating and ioctl error propagation

**Date: 2026-10-20.** Owner-supplied Stage 30 result `GAZELLE_FEL_STAGE30_OFFLINE_PASS` received. **Stage 31 original vendor offline audit PASS** (37 original Thumb instruction-and-operand gates, one original ELF SHA pin, five synthetic branch-selector assertions). P7 FEL residual pixels remain **NOT PROVEN**. No Cube, Fire OS, Kodi, Magisk, HDMI/audio/optical or satellite modifications.

## Input and reproducibility

Original Amazon Fire OS PS7702.4965N `libOmxVideo.so` extracted privately from the owner’s SHA-pinned `03-vendor-odm.zip`, not committed:

`eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`

The checked source lives at `tools/gazelle-fel/audit-stage31-config-ack.py`. Its audit verifies SHA-256, ELF32 little-endian ARM, **37 exact Thumb instruction addresses/operands** and the specific branch destinations in the original compiled code. It never loads/executes the shared library.

```sh
python3 tools/gazelle-fel/audit-stage31-config-ack.py --selftest
python3 tools/gazelle-fel/audit-stage31-config-ack.py \
  ~/Downloads/gazelle-fel-stage30-results/private-original-vendor-libraries/libOmxVideo.so
```

On macOS install LLVM if needed: `brew install llvm` and include `$(brew --prefix llvm)/bin` in PATH.

## Finding A: Awesome HEVC configuration has a distinct enable predicate

`AmlogicVideoDecoderAwesome::doCodecSpec` at **0x281c4–0x281d0** performs:

- the format comparison against **0x0b**; a nonmatch branches elsewhere;
- reads the decoder's **+0xdc** byte; a zero value takes the alternate path at **0x284a2**;
- only on this inspected nonzero path is the main HEVC parameter string constructed with a 512-byte destination argument (`0x281e4/0x281ea`), storing `codec_para_t.config_len` at offset **+0x12b4**.

Earlier work separately mapped native decoder `+0xdc` to owner `+0x109`. Do not confuse this condition with the neighboring native frame-mode byte `+0xdd`. Neither value was measured in the Stage 28 runtime capture.

The **optional** `negative_dv:1;` append is selected by the conditional at **0x28202–0x2820e**: owner component byte **+0x35d nonzero**, or if zero, native decoder word **+0x13c not equal to 0x0c**. The append uses `0xffffffff` as its formatting destination-bound argument at **0x28224**, not verified remaining inline capacity. **These predicates are not known to be true for actual P7 playback.** The older `dv_duallayer:1;` append has a distinct legacy Amlogic profile gate (Stage 30).

## Finding B: kernel configuration ioctl error is masked by the helper

The original native helper at **0x5aa64** (previously independently named `set_video_codec_info` from `.gnu_debugdata` at Stage 19) reads `config_len` at **0x5aa9e–0x5aaa6**. If zero, it branches directly to returning **0**.

For nonzero `config_len`, the helper builds the pointer/length record from inline `config` (**+0x10b4**), uses selector **0x301**, Linux ioctl request **0x401053c6** (**0x5aaaa–0x5aac4**), and compares ioctl return against **-1** (**0x5aac8**). On errors it logs; both the successful and logged-error paths converge at **0x5aadc: movs r0, #0x0** followed by the common epilogue. Thus **a failed configuration ioctl can be logged yet the helper still reports success**.

`codec_init` explicitly checks the helper result at **0x591ac–0x591b6** and, on another path, **0x59406–0x59410**. Those caller-side checks **cannot detect the configuration-ioctl failure if it has already been turned into success by the helper**. This is an exact offline error-propagation finding, **not** proof that the ioctl fails during P7.

## Runtime reconciliation: what we still cannot conclude

The active Stage 28 comparison independently showed **P8 `DV FORMAT_DOVI`**, **P7 `HDR10 FORMAT_HDR10`**, both with `dvbldec(1)`, no observed EL provider (`dveldec(0)`), and unchanged frame-mode ports.

The following remain **unobserved**: P7's actual +0xdc/+0x35d/+0x13c values, which config string (if any) was submitted, the return code of ioctl 0x301, whether a Dolby RPU parsed, EL decoder allocation, and any residual contribution to pixels. Do not claim the masked error caused P7's HDR10 classification. Nor can a successful decoder open or config helper return establish correct initialization.

## Next discriminating evidence — Stage 32 design

Use **passive, time-correlated, bounded and opt-in log collection** during user-selected P8 and P7 playback to look for existing vendor configuration-ioctl errors, Dolby parser outcomes, and native class/mode logs. Protect private metadata and limit output to relevant lines; do **not** clear logcat, elevate logging, instrument `media.codec`, set codec properties, inject ioctls, change `enable_fel`, `dolby_meta_with_el`, `nal_skip_policy`, install a test APK or reload modules. If stock logging cannot expose this boundary, return **UNKNOWN** and continue original ELF analysis rather than trying writes.

Working P8, PTT/voice satellite, HDMI passthrough, UDF and MMBD/optical modules remain protected.
