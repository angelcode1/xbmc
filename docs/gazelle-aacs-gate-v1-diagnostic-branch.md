# Gazelle AACS gate v1 — isolated Kodi diagnostic branch

**This branch is not production, not an installed Kodi APK, and not a Blu-ray decryption fix.** It was created from the exact previously installed Kodi core commit `1b95bc1bbe42de0714947fabbafee266682b089c` on 2026-10-14 to stage five phase markers in libbluray 1.5.0. The existing production/fel branch and Cube3's working optical and root services are unchanged.

## Reason

Live FireTV Cube3 physical UDF source, Blu-ray playlist enumeration and Kodi menu selection work. Kodi AACS initialization has two distinct failure modes: with no root broker the helper exits 3 and AACS returns -6; with an authenticated root broker, a real ARMhf MakeMKV session starts but AACS may wait until the external 150-second broker timeout. We need a boundary marker to establish whether the delay is inside MakeMKV context creation or the following `aacs_open_device` autodiscovery.

## Source selection

- Base Kodi commit: `1b95bc1bbe42de0714947fabbafee266682b089c`.
- Kodi `tools/depends/target/libbluray/LIBBLURAY-VERSION`: libbluray 1.5.0 archive SHA512 `32725c8490479b134f2fc9ec72e77a6f57a85b3de33a4a3ad2c82575b7045c0d31a997c0dd05f1dc175628cd2ce61f58573f58a7b799057ec4d6984616b0e732`.
- Original `src/libbluray/disc/aacs.c` SHA256 `74936b808fd5d236af3b6f3f73ef4e711fbf1ea23e3f9dac57051134ded5a3ce`.
- Staged five-marker `aacs.c` SHA256 `76c64d58fa109108eda0958cd314df185f2542327f883995ba3a55b653b6357d`.
- The private Cube3 source gate previously passed actual pinned archive checksum, staging, synthetic tests and C syntax verification. CI must separately pass Android ARMv7 object and complete downstream Kodi core build before any artifacts are considered usable.

## Build integration

`tools/depends/target/libbluray/Makefile` applies existing Android libmmbd unversioned loader patch first. Only on Android in this separate diagnostic branch, it then invokes `gazelle-aacs-gate-v1.py` on the unpacked source, refuses a changed SHA256, checks staged SHA256, writes a diagnostic-only define at the top of the build-tree `aacs.c`, and compiles the original libbluray 1.5.0 with these extra stage markers. Nothing is patched in checked-in third-party vendor code or other platform builds.

Marker names (no sensitive buffers, key bytes, callback paths, or drive identities):

```text
GAZELLE_AACS_GATE_V1 phase=context_begin
GAZELLE_AACS_GATE_V1 phase=context_end ok=0|1
GAZELLE_AACS_GATE_V1 phase=callback_set
GAZELLE_AACS_GATE_V1 phase=open_begin device_null=0|1
GAZELLE_AACS_GATE_V1 phase=open_end rc=N
```

CI `gazelle-aacs-diag-source.yml` checks only the exact source branch, original archive SHA512, Android loader patch, stage tool and host compile syntax. Public Android FireTV Blu-ray workflow on this branch is forced into `routing-core` mode: **no private Cube3 helper, VFS/optical addon, or root broker is bundled**. Its output is **NOT DEPLOYABLE** on the Cube until a separate private integration, signed APK verification and rollback are explicitly completed.

## Evidence interpretation

- `context_begin` without `context_end`: MakeMKV startup or InitMMBD context phase did not return. Inspect broker/client handshake, not autodiscovery yet.
- `context_end ok=0`: no usable context; inspect broker state and actual helper exit code.
- `context_end ok=1` and `open_begin device_null=1` without `open_end`: investigation can narrow to MakeMKV 2.0.0 `mmbd_open_autodiscover` (drive scan / callback metadata comparison / OpenMMBD).
- `open_end rc!=0`: an explicit error, not a still-pending open. Do not conflate it with backend timeout.
- Even `open_end rc=0` is **not** verified protected playback; bus encryption, usable disc key and decoded audio/video remain independent gates.

## Non-negotiable safety

Do not load or mount kernel UDF (`udf.ko` causes watchdog lock on Cube3), broaden SELinux permissions, restart the known-working LF/pread64 optical root service without a failed gate, bypass physical-drive identity checks, patch the production Kodi branch, dump IPC payloads or keys, or deploy this public routing-core APK directly.
