# Gazelle OMX bridge library follow-up

The active P8/P7 captures on 2026-10-14 show the same OMX decoder, frame mode, HEVC kernel format, port flags and working output path, yet P7 is parsed as HDR10 and never activates `dveldec`. Neither session prints effective `dv_duallayer:1;` configuration or the `AMSTREAM_SET_DV_META_WITH_EL` ioctl (`0x179`). These absences alone do **not** prove the operations were not executed. The Android `DynamicANWBuffer` warning occurs for working P8 as well as failing P7.

The next offline audit should resolve where the vendor OMX decoder's component-field `+0x20 == 0x10` is assigned and how it affects `AmlogicVideoDecoder::setUp()`. The previous six OMX companions had no direct dynamic import/relocation to `codec_set_dvmetawithel`. Additional mapped bridge candidates include `libOmxCore.so`, `libamavutils.so`, `libmediahal_resman.so`, `libstagefrighthw.so`.

While a P7 sample plays, run the **read-only** `tools/gazelle-fel/collect-omx-bridge-libs.sh` script on macOS. It copies only those bridge libraries plus the original `libOmxVideo.so` for version consistency, and saves maps and build properties. It does not change device state. Keep proprietary libraries out of public Git; analyze them offline.

See [validated active vendor differential](gazelle-fel-active-vendor-diff-2026-10-14.md). No native FEL fix is claimed.
