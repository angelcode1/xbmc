# Fire TV Kodi APK signing / safe update procedure

**Issue observed 2026-10-14:** `INSTALL_FAILED_UPDATE_INCOMPATIBLE` when installing the CI `kodiapp-armeabi-v7a-debug.apk` over existing `org.xbmc.kodi`. Android requires identical signer identities for normal package updates. `adb install -r`, `-d`, `-t`, `pm install`, root, or changing the user ID do not make differing signing certificates compatible.

The previous GitHub Actions workflow generated a **fresh random debug keystore on every ephemeral runner**, making artifacts from different runs incompatible. It also checked out the old `android-firetv-fel` branch despite running under `android-firetv-bluray`. Both source and signer problems are addressed in the workflow, with the following limits.

## Safe first step: compare certificate hashes, without modifying device

```bash
ADB=/Applications/adblink.app/Contents/MacOS/adbfiles/adb
APK=$HOME/Downloads/gazelle-fel-stage2-apk/kodiapp-armeabi-v7a-debug.apk
EXISTING=$HOME/Downloads/gazelle-current-installed-base.apk
DEVICE_APK=$("$ADB" shell pm path org.xbmc.kodi | tr -d '\r' | sed -n 's/^package://p' | head -n 1)
"$ADB" pull "$DEVICE_APK" "$EXISTING"

# Requires Android SDK build-tools' apksigner on your Mac (install if missing).
APKSIGNER=$(find "$HOME/Library/Android/sdk/build-tools" -type f -name apksigner -print 2>/dev/null | sort -V | tail -n 1)
"$APKSIGNER" verify --print-certs "$EXISTING" | grep 'SHA-256 digest'
"$APKSIGNER" verify --print-certs "$APK" | grep 'SHA-256 digest'
```

If you have a candidate existing **local private keystore**, compare it using:

```bash
keytool -list -v -keystore "$HOME/.android/debug.keystore" -alias androiddebugkey | grep 'SHA256:'
```

A matching signing-certificate **fingerprint** means the candidate local keystore may be usable. It does **not** mean an installed APK contains a signing key: APKs contain the public certificate only. **Never commit, upload to the chat or disclose the private keystore/password**.

If the original keystore matches the installed app, a correctly rebuilt APK may be re-signed with that same private key using Android SDK `apksigner sign`, and the new certificate fingerprint must be checked before `adb install -r`. If there is no matching private key, a signature-preserving upgrade is not possible via ordinary Android package installation.

## Stable signing on future CI builds

The workflow now accepts repository Actions secret **`GAZELLE_DEBUG_KEYSTORE_B64`** containing the base64 text of a debug keystore with alias `androiddebugkey`, store password `android`, and key password `android`. It restores that keystore in the build runner *before packaging*. Set the secret through **GitHub repository Settings → Secrets and variables → Actions**; do not commit the keystore. The secret must contain a key corresponding to the **installed** signature if the goal is to update the existing installation without uninstalling. Merely generating a new persistent keystore fixes *future* consistency, not upgrades from a different existing signature.

If the secret is absent, CI still works but warns that the APK has a temporary signing certificate and therefore cannot be relied upon for in-place upgrades across different runs.

## If the installed private key has been lost

**Stop before uninstalling.** The official update path cannot accept a different signature; back up both Kodi's application-private data and the external `Android/data/org.xbmc.kodi` tree while Kodi is stopped, then validate archives *off the device*, before any uninstall or data migration. Android's `pm uninstall -k` can retain signing identity and is not a reliable shortcut for installing a differently signed APK. Restoring internal data across a signing change requires attention to app UID, ownership, SELinux context, and any app-/keystore-bound encrypted data. Prefer selectively restoring Kodi's user-level `.kodi` data and validating functionality instead of transplanting package-manager state.

## Source revision safety

For workflows triggered in `angelcode1/xbmc`, checkout is pinned to `github.sha` and immediately compared to `git rev-parse HEAD`. This ensures a successful workflow corresponds to its named commit, rather than an unrelated branch. The reusable workflow retains `android-firetv-fel` as the source branch when invoked by `angelcode1/cube3`; review that cross-repository call independently before merging these build paths.
