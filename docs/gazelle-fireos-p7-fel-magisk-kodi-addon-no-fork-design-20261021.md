# Gazelle Fire OS P7 FEL: no-fork Kodi add-on + Magisk module architecture

**21 Oct 2026 | research architecture only | no Magisk module or Kodi add-on built or installed in this change.** The user's existing Blu-ray pipeline is a Kodi UI/library integration plus root Magisk-managed read-only kernel UDF and MMBD broker. Do **not** modify those optical systems, the working P8 player, passthrough audio, Magisk root or the satellite service.

## Answer

A **Kodi add-on for preflight and playback intent plus a Kodi-app-scoped Magisk Zygisk hook for MediaCodec configuration** is technically plausible and requires no permanent Kodi fork if the hook can safely alter `MediaFormat` **before** the exact `MediaCodec.configure()` call. A normal Python add-on **cannot** intercept Kodi's native built-in decoder directly. A Magisk module by itself provides packaging/scripts/mounts; it does **not** confer such interception without explicit in-process instrumentation.

Zygisk runs code in zygote-forked app processes (including a potential Kodi process), **not generally in independently spawned native `media.codec` or vendor codec services**. Root service companion IPC and process matching are separate features. A correct implementation must handle Fire OS's **32-bit userspace ABI** and should not assume another installed hook runtime (LSPosed etc.). Reference: https://github.com/topjohnwu/zygisk-module-sample and https://github.com/topjohnwu/Magisk/blob/master/native/src/core/zygisk/api.hpp .

## Proposed components

```
Kodi UI add-on (launcher/context menu) --- dedicated local IPC ---> Magisk module session arbiter
      |                                                            |
      +--- P7 FEL test file / title prep, explicit opt-in           +-- session-bound, expiring authorization
      |                                                            |
      +--- Kodi plays normal title --------------------------------+-- Zygisk library in org.xbmc.kodi
                                                                       intercept exactly one MediaCodec configure
                                                                          |
                                                                     mime=video/dolby-vision
                                                                     selected OMX.amlogic.dolby-vision.dvhe.decoder
                                                                          |
                                                                  MediaFormat vendor.* keys (if validated)
                                                                          |
                                                                  original Android Stagefright/vendor OMX
                                                                          |
                                                                  Fire OS native decoder and DV output
```

- **UI side:** Python add-on can show a context-menu action and pass an explicit title intent. P7 profile + enhancement layer presence alone does **not** identify FEL (MEL also has an EL). Full FEL must be classified using real RPU data **before configure**, not inferred from Kodi's later `GetDoviIsFEL()` signal in `AddData()`. For physical Blu-ray playlists, exact title/stream pairing may need existing MMBD/UDF exposure; avoid normal library automatic interception for v1. Kodi's event notification after playback starts may be too late. No automatic modification for unmatched titles.
- **Root coordination:** Magisk module holds a short-lived, opt-in capability scoped to process/package, title fingerprint and a single expected decoder creation. Validate credentials over a local IPC mechanism without exposing a world-writable root control socket; never trust package-name text alone for authorization. Never persist global property changes.
- **Kodi-app process hook:** native JNI or an explicit Java-method hook intercepts the `android.media.MediaCodec.configure(MediaFormat, Surface, MediaCrypto, flags)` call for the selected codec instance. Only exact `video/dolby-vision` / OEM DV component and an authorized P7 FEL title are eligible. Pass all other configure calls byte-for-byte unchanged. Instrumentation must be compatible with Kodi's actual JNI MediaCodec wrapper and Fire OS Android 9/32-bit runtime. Beware that `MediaCodec.configure` and `MediaCodec.setParameters` are not equivalent.
- **Vendor-configuration bridge:** offline Fire OS reverse engineering found vendor Android extension `profile-level` with `n-profile` and `n-level`, which Stagefright can convey as `vendor.profile-level.n-profile`, `vendor.profile-level.n-level` to the Amlogic framework's OMX index `0x7f00010d`. The current framework's private `mProfile == 0x10` condition appends `dv_duallayer:1;`. This is a **candidate** and **0x10 must not be blindly enabled**: vendor semantics and ordering still need to be verified; Android P7 profile=128 is a different enum. Testing injection must be explicit, disabled by default and bound to an instance.
- **Distinct native-port gate:** current Fire OS P7 opens `/dev/amstream_dves_hevc_frame` (port 0x1d11, bit10 skips paired decoder constructor), while another stream port `/dev/amstream_dves_hevc` (0x1911) can reach paired creation. Firmware reports `vendor.media.omx.use_dv_frame=true`. Changing this **global** property is **not** an acceptable deployment strategy. The Magisk app-side hook has not yet been shown to provide a *per-instance* frame/stream control; if none exists, the module would need a substantial and risky vendor pipeline adapter and the simple no-fork architecture stops here.
- **Output gate:** even two concurrently initialized HEVC channels, `dveldec(1)` and Dolby output classification are **necessary but insufficient** to prove actual FEL residual contribution. Need residual-sensitive video comparison, seeking/EOF, frame pairing, HDMI passthrough and system stability.

## Why not simply a standard Kodi add-on?

The Kodi video-codec binary add-on API documentation in the pinned fork at `xbmc/addons/kodi-dev-kit/include/kodi/addon-instance/VideoCodec.h` explicitly says video-codec add-ons currently only work *together with inputstream add-ons*, **not** as independent codec replacements for arbitrary Kodi library files. The `AddonVideoCodec.cpp` output bridge handles Kodi's own video-buffer semantics, not proven Android MediaCodec Surface ownership. Implementing an inputstream/video-codec duo is essentially creating a separate playback stack. Kodi's normal Python add-ons cannot set per-codec MediaFormat keys in the built-in decoder.

## Milestones, failure rules

1. Offline verify full vendor extension mapping and Stagefright **configure-time** order in the *owner's exact ROM*, plus `MediaCodec.configure` hook coverage in Kodi app; verify no cross-app injection or global property mutation.
2. Build an **inert observation-only**, opt-in, ABI-matched Zygisk hook, with no media mutation and robust boot-safe disable/rollback path. A Zygisk delivery or ART hook crash is unacceptable on the production Fire OS environment.
3. After semantics are proven, a separate opt-in v1 injects **only validated** `vendor.profile-level.*` values for the exact bound known FEL session; must observe actual vendor setConfig/OMX parameter acceptance. Missing logs or successful configure alone aren't proof.
4. If the observed frame port remains active or a second VDEC does not appear, **stop** the simple Magisk hook path; do not enable global `use_dv_frame=false` or replace system OMX/Stagefright binaries. Substituting a stream port requires different buffering, output and synchronization contract.
5. If two VDEC channels arise, independently verify actual residual contribution (CoreELEC is the positive reference), frame/EL sync, pause, seek, teardown, no harm to P8 and no conflicts with UDF/MMBD/HDMI/satellite. Without residual proof status is **NOT FEL PROVEN**.
6. The module must have a no-op default, an instant *disable toggle* with **no decoder-service reboot**, and a clean uninstallation path, leaving the existing Kodi and modules unchanged.

## Comparison to other projects

- **Current angelcode1/xbmc**: validated input and exact MediaCodec behavior; use as **research/reference source**, not as a required deployed fork.
- **CoreELEC/xbmc**: native T7 5.15 BL/EL implementation; best positive device decoder reference but direct Linux renderer is not drop-in Fire OS Android.
- **koying/SPMC**: historical Amlogic/Android Kodi integration reference only.
- **djnice/vlc-fel-android**: separate Android FEL pipeline on S928X, with native kernel module and GPU reconstruction; major port, not compatible out of box.
- **Zygisk sample**: process-scoped module packaging/injection example, **does not provide a ready-to-use Java/ART hook**.

**Current verdict:** feasible as an **architecture candidate**, not evidence of a working module or simple switch. Primary complexity remains (i) safe per-session JNI/MediaCodec hook with early FEL identification; (ii) private vendor profile semantics and configure ordering; (iii) **per-session stream mode while preserving Android surface/Dolby output**. Do not invest in addon menus or packaging until (iii) has a plausible implementation contract.
