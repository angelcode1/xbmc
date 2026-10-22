# Gazelle FEL — verified Kodi source integration and ARMv7 APK build gate (22 Oct 2026)

**Build preparation only. This does not enable FEL or install an APK.**

## Actual test evidence

The user confirmed on their Mac: `GAZELLE_FEL_P7_PAIRING_HOST_PASS timestamps=true bounds=true device=false FEL_decode=false`.

GitHub Actions **run [39753890492](https://github.com/angelcode1/xbmc/actions/runs/39753890492) completed successfully** for the research branch on commit `d1baeb49ca6f4b33640879aae860a3c30c19fe8d`, proving both BL/EL pairing and hvcC 1/2/3/4-byte length-prefix host tests, and the new `tools/gazelle-fel/verify-kodi-fel-source-integration.py` gate. That gate also verifies the **actual Kodi call sites** instead of relying only on standalone helpers.

The research branch's real full-APK workflow `.github/workflows/android-firetv-bluray.yml` now has a conditional early-source preflight which checks these exact call paths and builds both host tests **before** downloading/compiling Android dependencies. It does not change the normal `android-firetv-unified` workflow behavior; no P7-only APK installation is performed. This full Kodi **Android compile has not yet been run against the FEL research branch**.

A previous full build [run 39140459487](https://github.com/angelcode1/xbmc/actions/runs/39140459487) on **android-firetv-unified** did successfully compile Kodi, make APK and verify UDF/MMBD packaging. It is a baseline **for a different source branch**, not proof the FEL branch compiles.

## Run the full Android build (explicit opt-in)

GitHub web: open <https://github.com/angelcode1/xbmc/actions/workflows/android-firetv-bluray.yml>, choose **Run workflow** → branch `research/gazelle-fireos-fel-20261019` → `build_mode: full-apk` → Run workflow.

Command-line alternative (no local Git checkout; requires GitHub CLI already authenticated):

```bash
gh workflow run android-firetv-bluray.yml \
  --repo angelcode1/xbmc \
  --ref research/gazelle-fireos-fel-20261019 \
  --field build_mode=full-apk

gh run list --repo angelcode1/xbmc \
  --workflow android-firetv-bluray.yml --limit 5
```

Inspect the job for `GAZELLE_FEL_ANDROID_RESEARCH_PREFLIGHT_PASS`, `GAZELLE_DEPENDS_BUILD_PASS`, `GAZELLE_KODI_CORE_BUILD_PASS`, successful `Package APK` and `Verify kernel UDF and MMBD native service packaging`. An output APK is a **build candidate** only.

The build job can take substantial CI resources. It is **not automatically triggered** by research branch pushes; the user must explicitly dispatch it. An individual run can fail for toolchain/network/dependency issues unrelated to P7; use the exact failed step/log. The earlier workflow uses NDK r28c, Android API37 build tools and ARMv7 API28 compiler, independent of user's macOS sdk-28 Java test installation.

## Deployment safety

Do **not** install over the working Kodi merely because a candidate APK exists. The workflow signs with an ephemeral debug key unless a stable `GAZELLE_DEBUG_KEYSTORE_B64` secret is configured; a signature mismatch prevents upgrade. A clean reinstall can delete Kodi app data, change Kodi's UID and invalidate the UDF mount and root MMBD broker, plus the custom optical source tile. Preserve the working APK, broker and Magisk setup; no automatic install/adb/stream-mode/kernel flag write belongs in CI.

This source integration guard prevents the old first-opposite BL/EL match and unbounded/truncated P7 access unit path. It **does not** cause Amazon FireOS to instantiate `dveldec` or safely enable private `enable_fel`. The visual Power Rangers white-credit test and enhanced-layer-only image remain **unmet**.
