# Current Gazelle Android APK build

The workflow at
[android-firetv-bluray.yml](../.github/workflows/android-firetv-bluray.yml)
runs on the `android-firetv-unified` branch. It checks out only the
triggering XBMC repository SHA. It bundles kernel-UDF and MMBD addons,
LibMMBD, the compiled ARMv7 PIE helper and existing AACS/FEL changes.
It does not fetch external optical artifacts or private repositories.
See [current build contract](gazelle-kernel-udf-self-contained-build.md).
