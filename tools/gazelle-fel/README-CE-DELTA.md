# Pinned CoreELEC vs Fire OS first FEL decoder-init audit

This tool establishes only a **source-code comparison**, not FEL playback, private Android ELF equivalence, or the owner's exact installed CoreELEC build identity.

Pinned CoreELEC packages (as selected by public `coreelec-22` package metadata at the time of this analysis):

- Kodi `884eab3a40712e7a853db68eb114d712e9600fc2` (`DVDVideoCodecAmlogic.cpp`, `AMLCodec.cpp`).
- `media_modules-aml` `c15aebb1ac93028d0aceadf8f35dda2204d33424` (`amstream.c`).

`--verify-upstream` retrieves three public code files over HTTPS, enforces their exact pinned Git **blob** SHA-1 and audits the FEL-before-decoder-open, stream-mode-before-codec_init, global CE Dolby control, `video10` and conditional slave VDEC contracts. It never connects to the Cube. This external network step can fail due to GitHub availability; do not treat that as a codec regression.

`--kodi-root .` verifies the **local** Android Kodi fork still keeps initial factory deferral hard disabled; if that changes, refuse. It does not infer which native port the real media service opened—that was verified separately by the owner. `--selftest` uses synthetic source snippets with negative mutation rejection, not a full Kodi/Android test.

From the repository root:

```sh
python3 -S tools/gazelle-fel/audit-coreelec-first-init.py --selftest --kodi-root .
python3 -S tools/gazelle-fel/audit-coreelec-first-init.py --verify-upstream --kodi-root .
```

See [`docs/GAZELLE_FEL_ANDROID_MASTER_PLAN.md`](../../docs/GAZELLE_FEL_ANDROID_MASTER_PLAN.md) for the only active technical path and stop conditions. Do not deploy scripts/plugins, set system properties or modify vendor/kernel/boot partitions.