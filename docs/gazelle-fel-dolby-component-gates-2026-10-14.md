# Fire Cube 3 OMX Dolby component gates: static contrast

Date: 2026-10-14; firmware PS7702.4965N. This investigation uses `/vendor/lib/libOmxVideo.so` with SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`, previously collected from the running `media.codec` process. No proprietary ELF is included in Git.

## New independently verified control-flow distinction

| Class/method | Address | Observed branch |
| --- | --- | --- |
| `AmlogicVideoDecoder::setUp()` | `0x21ac6–0x21ad4` | Reads `peer+0x20`, checks **0x10**, then loads/appends the `dv_duallayer:1;` string |
| `AmlogicVideoDecoderDolbyVision::doCodecSpec()` | `0x30956–0x3096c` | Accepts `peer+0x20 == 0x400` or alternate `peer+0x3dc == 0x7f100001` for a Dolby-specific path |
| `AmlogicVideoDecoderDolbyVision::prepareEsData()` | `0x309b2–0x309ce` | Same **0x400 or 0x7f100001** conditions |
| `AmlogicVideoDecoder2DolbyVision::doCodecSpec()` | `0x43010–0x43026` | Same **0x400 or 0x7f100001** conditions |
| `AmlogicVideoDecoder2DolbyVision::prepareEsData()` | `0x4306e–0x4308a` | Same **0x400 or 0x7f100001** conditions |

The `0x7f100001` value is constructed by `movs ... #1` plus `movt ... #0x7f10`. Distinguish these internal vendor peer/codec values from Kodi's **MediaCodec capability-filter profile**, which was `256` for P8 and `0` for P7. They refer to different fields.

An earlier independently verified alternate-decoder instruction sequence maps `peer+0x20 == 0x10` to HEVC kernel format **11**. That implies `0x10` is associated with HEVC coding selection rather than directly indicating FEL. The Dolby subclass separately recognizes **0x400**, so it is plausible that the selected Dolby component does **not** satisfy the legacy `0x10` append gate. **This is a hypothesis, not a measured runtime peer value.** Different vendor paths may set or override the field.

## Reproducible and bounded check

The read-only tool [audit-dolby-codec-gates.py](../tools/gazelle-fel/audit-dolby-codec-gates.py) checks all five instruction groups, refuses binaries that do not match the pinned SHA, and requires `llvm-objdump`. Expected result on the exact uploaded vendor library: `OMX_DOLBY_CODEC_GATE_PASS`. The check does **not** execute vendor code or assert native FEL reconstruction.

## Follow-up for companion libraries

The user's `media.codec` mappings identify:

- `/vendor/lib/libomx_framework_alt.so`
- `/vendor/lib/libOmxBase.so`

The missing evidence is where `VendorPeerComponent` (or an adjacent OMX struct) **assigns peer+0x20 and peer+0x3dc** while registering/initializing `OMX.amlogic.dolby-vision.dvhe.decoder`, and what configuration actually reaches `AmlogicVideoDecoder::setUp()`. Obtain those two exact ELF files via `adb pull`, inspect their symbols and field-writing paths offline, and correlate them with Dolby component registration and `OMX_SetParameter`. Keep the ELF binaries private, outside Git.

Prior controls remain unchanged: Kodi preserved BL/RPU/EL counts and passed 48/48 exact JNI input-copy checks; P8 produced `FORMAT_DOVI`, and actively decoding P7 produced `FORMAT_HDR10` with `dveldec(0)`. Neither this static code nor those labels demonstrate FEL pixel contribution. Do not force a speculative key or inject ioctl `0x179`.
