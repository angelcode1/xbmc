# Stage 2 device playback capture — 2026-10-14 12:17–12:19 AEST

Evidence: user-supplied `gazelle-fel-stage2-results.zip` (SHA-256 `0433b30c045fc77061c9356ea2855b659d23f7cb3bd8a25bfb07cd8ca8872a04`). This archive contains P8/P7 Kodi logs and Dolby state snapshots; raw logs are not checked into the repository.

## Playback findings

| Check | P8 `DV8_TEST.mp4` | P7 `DV FEL Power Rangers Credits Test.mkv` |
| --- | --- | --- |
| Decoder | `OMX.amlogic.dolby-vision.dvhe.decoder` | same |
| Dolby driver `inst1` | `DV FORMAT_DOVI` | `HDR10 FORMAT_HDR10` |
| Instance | mapped=1, valid=1, 3840x2014 | mapped=1, valid=1, 3840x2160 |
| RPU | `profile=8 el_type=unknown fel=false` | `profile=7 el_type=FEL fel=true` |
| Stage 1 per-AU logging | n/a | 48 paired pre/post NAL records |

In the P7 capture, 48 post-conversion records total **384 BL**, **48 RPU**, **501 EL**, VPS/SPS **6 each**, PPS **51**, invalid **0**. Per-unit pre/post counts agree. This is **not** proof that the vendor decoder consumed EL NALs.

## Critical artifact mismatch discovered

Neither log includes **any** of the Stage 2 diagnostic strings:

- `GAZELLE_DOVI_CODEC_SELECTED` — 0
- `GAZELLE_DOVI_MEDIAFORMAT` — 0
- `GAZELLE_P7_INPUT_COPY` — 0

These markers were added to source in `93d13bc` and `599c876`; the reported artifact was installed after an earlier build that accidentally checked out `android-firetv-fel` even when triggered by the `android-firetv-bluray` branch. The corrected workflow is at `86526e2` and its run `38491975738` completed successfully. **The logs strongly indicate the older APK was installed, but an APK file was not provided, so the precise installed artifact SHA cannot be established.** Do not infer Stage 2 failure from absent log markers.

## Gate to unblock further testing

1. Download the **APK** artifact (not logs) from [corrected run 38491975738](https://github.com/angelcode1/xbmc/actions/runs/38491975738).
2. Extract the APK; run `python3 tools/gazelle-fel/verify-stage2-apk.py /path/to/kodiapp-armeabi-v7a-debug.apk`. Require `STAGE2_MARKERS_PASS` before installation.
3. Since the user explicitly prefers fresh Kodi installation, uninstall the existing `org.xbmc.kodi` (deletes its settings and data) and install the verified new APK. The signing secret is **not necessary for a clean install**.
4. Confirm P8 `FORMAT_DOVI` and P7 `FORMAT_HDR10`, plus the new `GAZELLE_DOVI_CODEC_SELECTED`, `GAZELLE_DOVI_MEDIAFORMAT`, and `GAZELLE_P7_INPUT_COPY` markers.
5. If every P7 `equal=true`, move the fault boundary into vendor OMX/kernel. A valid Dolby source format alone does not prove full FEL enhancement-layer reconstruction.

Leave Surface acceleration enabled; do not toggle global H265/Dolby sysfs flags or inject ioctl `0x179` during this validation.
