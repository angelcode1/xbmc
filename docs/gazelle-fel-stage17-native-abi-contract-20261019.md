# Gazelle Stage 17 — native Amlogic decoder ABI preflight, not a backend implementation

Date: 2026-10-19 (Australia/Brisbane). Status **OFFLINE_NATIVE_ABI_VERIFIED / KODI_NATIVE_BACKEND_BLOCKED**.

## Source provenance

Offline static verification of the **original** user-supplied PS7702.4965N proprietary ARM32 ELF binaries. The raw ELF files are not committed to Git.

| Binary | SHA256 |
| --- | --- |
| `libOmxVideo.so` | `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` |
| `libomx_framework_alt.so` | `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba` |
| `libOmxBase.so` | `7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee` |

`llvm-objdump` 17, `readelf`, SHA256 and ELF32 little-endian ARM checks were run on the originals. A separate local standalone verification tool checked **22 pinned Thumb instruction patterns**, **six exported function symbol addresses**, and **21 `DT_NEEDED` dependencies**. Result: `GAZELLE_FEL_STAGE17_OFFLINE_NATIVE_ABI_PASS`.

## Proven native exports — exact pinned .so only

These are dynamic `GLOBAL DEFAULT` ARM Thumb function symbols (LSB indicates Thumb), NOT promises of stable SDK ABI:

| Export | Thumb VA | Static implementation evidence |
| --- | --- | --- |
| `codec_init` | `0x58bdd` | Takes native decoder context pointer; initializes first four 32-bit FD slots to `-1` at `0x58bfe/0x58c02`. Reads a mode word at context `+0x10a0`. The DV HEVC open path uses a comparison `mode==1` to choose the **frame** node rather than the **stream** node. |
| `codec_write` | `0x597d1` | At `0x597d0`, loads the first context word as the decoder FD, then branches to the linked low-level write stub. This **does not** itself establish correct stream packetization, input-buffer handling, or PTS sequencing. |
| `codec_close` | `0x597dd` | Closes conditional auxiliary handles and the main FD, overwriting closed context FD slots with `-1`. Proper ownership, error-path and teardown sequencing are not yet established. |
| `codec_checkin_pts` | `0x5986f` | At `0x5986e–0x5987e`, uses first context FD and an AMSTREAM ioctl wrapper with selector `0x10e`; PTS timebase contract remains unverified. |
| `codec_checkin_pts_us64` | `0x59885` | Separate exported 64-bit PTS path; observed existence, not yet validated for Kodi's PTS units. |
| `codec_set_dvmetawithel` | `0x5a1a1` | At `0x5a1a2–0x5a1aa`, **writes the passed flag/value into context offset `+0x12c0`**, and forwards metadata ioctl selector `0x179` using the first FD. This ioctl has prior kernel-side validation; actual P7 invocation remains unmeasured. |

**Critical structure-size finding:** `codec_set_dvmetawithel` unconditionally addresses an actual 32-bit field at **`codec_para_t+0x12c0`**. Thus any ABI-compatible context on this path must contain at least **`0x12c4 = 4,804` bytes**. **This is only a lower bound, NOT `sizeof(codec_para_t)`, a layout prescription, or a safe allocation size.** Exact pointer fields, alignments, version-specific tail fields and constructor/init requirements are not recovered.

## Dependency and execution boundary

The exact `libOmxVideo.so` has **21** `DT_NEEDED` libraries, including vendor-private `libomx_framework_alt.so`, `libomx_worker_peer_alt.so`, `libdatachunkqueue_alt.so`, `libomx_clock_utils_alt.so`, `libsystemcontrolservice.so`, `libge2d.so`, Android `libbinder.so`, `libui.so`, `libion.so`, and libc/libc++. Dynamic export presence **does not** prove that ordinary Kodi's app process can `dlopen` the library via Android linker namespaces, resolve dependencies, or acquire the `/dev/amstream_dves_hevc` device under SELinux.

The SDK-level 2011-era `codec.h` signature for `codec_init(codec_para_t*)` / `codec_write(codec_para_t*,void*,int)` is only a historical API comparison, **not** a layout or ABI source for PS7702.4965N:
https://github.com/Stane1983/amlogic-libplayer/blob/master/amcodec/include/codec.h

CoreELEC 22 Kodi `AMLCodec.cpp` on the separate 5.15 stack selects FEL stream mode **before** codec initialization, arranges stream buffering/extradata/PTS, and separately drives FEL/MEL and NAL policy. Its packet feeding logic is not present in the Android MediaCodec route and cannot be transplanted without validation:
https://github.com/CoreELEC/xbmc/blob/aml-5.15.196-22.0/xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp

## Safety / engineering decision

**Not ready for a P7 native backend APK.** The unverified items are concrete:

1. Recover **exact PS7702-specific `codec_para_t` layout, size, field semantics and ownership**. The `0x12c4` bound must never be misused as a struct size. Do not embed an old `codec_type.h` verbatim.
2. Verify Android **32-bit app process/vendor linker namespace**, all `DT_NEEDED` closure, and **SELinux** permissions for a process capable of opening Amlogic decoder devices. This requires an explicitly authorized, minimal **read-only** device capability probe; no such observation was made here.
3. Validate the native **stream parser packet format**, HEVC BL/EL/RPU ordering, extradata, PTS timebase, decoder buffer thresholds, and error propagation.
4. Prove actual **paired decoder allocation** (`vdec->slave`), the per-instance `0x179` handshake and enhancement decoder activity under a safe isolated lifecycle.
5. Test residual-sensitive **FEL pixel reconstruction**; a Dolby icon, `dveldec(1)`, or valid metadata alone cannot establish native full enhancement reconstruction.
6. Any future P7-only test must be **opt-in/default-off**, isolated from working P8 and Kodi disc/audio/voice integrations, with teardown/rollback for *every* native error. No shared global property writes, process injection, vendor-`.so` replacement, flash, eMMC or incompatible CoreELEC kernel modules.

Reconcile with Stage 12/13: live P7 uses `/dev/amstream_dves_hevc_frame` with `PORT_TYPE_FRAME` and bypasses default slave creation. The alternate stream port offers a **second-vdec allocation attempt**, not guaranteed decoded FEL.

**No device changes, native calls, `dlopen`, ioctl injection, Kodi binary changes, Magisk changes or kernel writes were performed in Stage 17.** Working `android-firetv-unified` remains unchanged.
