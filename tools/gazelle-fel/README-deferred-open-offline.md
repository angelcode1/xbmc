# Gazelle FEL — disabled Kodi worker deferred-open experiment

**Research branch:** `research/gazelle-fel-deferred-open-offline-20261024`
**Base:** `research/gazelle-fireos-fel-20261019`
**24 October 2026 — source-only, not installed, not a working FEL decoder.**

The original owner first-AU, Kodi precreate epoch and demux message-ownership **host tests** passed, but they did not touch actual Kodi factory/queue control. This branch stages the *first actual source changes* for a worker-thread deferred factory without touching the working base branch.

## Files modified

- `xbmc/cores/VideoPlayer/VideoPlayerVideo.h`: private worker pending-state flag/deadline plus helper.
- `xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp`: fixed OFF switch, strict clear-profile-7 candidate filter, stream-change event flag, deferred stock-only factory helper, packet path guard, timeout fallback (500 ms), reset/flush cancellation to stock and worker thread cleanup.
- `tools/gazelle-fel/verify-deferred-open-source.py`: static source regression checks with five negative-mutation selftests.

## Safety gate

```cpp
constexpr bool kGazelleDeferredStockResearchEnabled = false;
```

The **existing initial OpenStream still calls the stock codec factory synchronously**. The staged worker path exists only for an *already-started video worker stream-change* and is never selected with the switch OFF. Even if someone deliberately changes the switch in a future research build, the helper calls only `CDVDFactoryCodec::CreateVideoCodec` with fallback; it contains **no actual libdovi first-AU call or research OMX alias selection**. It is **not** safe to switch ON: no real first RPU, no parallel BL/EL decoder, no Dolby FEL residual reconstruction, no registry-native OMX component, no proven rollback.

Source-only tests (from a full checkout):

```sh
python3 -S tools/gazelle-fel/verify-deferred-open-source.py --selftest
python3 -S tools/gazelle-fel/verify-deferred-open-source.py
```

These tests **do not compile Kodi** and do not prove Android thread correctness. They inspect source structure and fail closed if the disabled feature changes, the timeout or first-packet ordering guard disappears, source references to a research alias are introduced or stock creation is removed. Their expected final line includes `target_compile=NOT_TESTED on_device=NOT_TESTED`.

## 24 October 2026 — CI compilation of shared policy (not full Kodi)

Created `xbmc/cores/VideoPlayer/GazelleDeferredOpenPolicy.h`, compiled as part of the existing `VideoPlayerVideo.cpp` source include and directly as the *same header* in `tests/TestGazelleDeferredStockPolicy.cpp`. The C++17 policy is **hard-disabled via constant and static_assert**, verifies an HEVC/P7/EL/unprotected/worker-stream-change *candidate* only, and refuses eight missing or unsuitable eligibility properties. **It is not an FEL/MEL parser.**

A new `.github/workflows/gazelle-fel-deferred-open-offline.yml` runs only on this isolated research branch and performs the source-regression script (nine negative mutations), GCC C++17 `-Wall -Wextra -Werror -pedantic` compilation, UBSan runtime, and explicit no-device/not-full-Kodi-build markers. Previous workflow passes: https://github.com/angelcode1/xbmc/actions/runs/40055043588 and https://github.com/angelcode1/xbmc/actions/runs/40055084723. The source checker must still **not** be described as compiling Kodi's entire `VideoPlayerVideo.cpp`: that translation unit depends on Android/Kodi/FFmpeg libraries and has **not** been built with the target toolchain here.

A local exact GitHub-blob-matched copy of the shared header and source test compiled with both GCC and Clang+UBSan. Clang caught and led to a correction of an unused test counter; reruns passed. The candidate decision still cannot be enabled, cannot select a research OMX alias, and cannot establish genuine FEL.

The staged worker's stock-factory failure branch formerly called `StopThread()` from the video worker; corrected to set `m_bStop = true` and send `PLAYER_ABORT`, allowing the external thread owner to handle joins. A new source regression condition refuses any self-join in `GazelleEnsureDeferredStockCodec`. This is a **non-deployable fail-closed safety correction**, not a demonstrated Android runtime recovery path.

## 24 October 2026 — read-only first-AU RPU probe staged in actual Kodi source

Added `xbmc/utils/GazelleFELPrecreateProbe.h` (no NAL rewrites): the source checks first-AU length-prefixed HEVC framing (≤16 MiB, ≤512 NAL, ≤64 KiB RPU), requires base VCL, EL NAL type 63 and **one** RPU NAL 62, enforces valid HEVC headers, rejects protected or malformed data, and then uses `dovi_parse_unspec62_nalu` / `dovi_rpu_get_header` under `HAVE_LIBDOVI`. It returns FEL only when the parsed header has **guessed_profile=7** and **el_type="FEL"**; similarly MEL. Header and RPU receive independent libdovi frees, exactly matching the connected upstream C ABI ownership implementation. If built without libdovi, unknown is returned.

The actual disabled path in `VideoPlayerVideo.cpp` now calls this header on the **original message-owned `DemuxPacket`**, before `GazelleEnsureDeferredStockCodec()`. It does not allocate, copy or edit the packet and never uses the classified type to choose a decoder; the compile-time policy still fixes `kDeferredStockResearchEnabled=false`, so no live execution is possible in this checkpoint. **This staged seam currently covers stream changes in an already running worker, not the initial stream's first codec open.** Even a true libdovi FEL result would not prove any native EL/residual output.

Added `tests/TestGazelleFELPrecreateProbe.cpp` and `tests/stubs/libdovi/rpu_parser.h` with an **EXPLICITLY FAKE libdovi ABI double**, not a genuine library. The host test checks 10 malformed/unsafe AU cases, FEL/MEL/unknown/profile/P8 branching, separate header/RPU frees, protected fallback, and AU size limit. The source audit now requires correct probe→stock factory→ordinary packet ordering, and rejects 10 source mutations.

**Successful GitHub Actions:** [40056672402](https://github.com/angelcode1/xbmc/actions/runs/40056672402). Its completed successful steps included source audit, shared production policy compile, policy UBSan, fake libdovi probe compile/run and probe UBSan. Earlier two CI runs failed because the static checker still expected the *old* direct packet guard text; the checker was corrected to verify the new read-only probe ordering and rerun successfully. The pass does **NOT** include: libdovi 3.3.2 real runtime parsing, Android ARMv7 Kodi `VideoPlayerVideo.cpp` target compilation, actual queue/thread timing, a working P7 decoder or FEL visual output.

The repo's `tools/depends/target/libdovi/LIBDOVI-VERSION` pins **3.3.2**; its `BitstreamConverter.cpp` already calls the same C-API on NAL62 after codec creation. The new precreate classifier is separately scoped and keeps every uncertain result on stock. Do not enable/ship, alter Magisk, replace an OMX ELF or run on the Cube. Full Kodi Android compile and genuine clean in-process parsing are still required; R0 independently bootable recovery remains NO-GO.

## Source-lifetime restrictions

- The video worker can receive `MSGQ_TIMEOUT` and call `ProcessDecoderOutput` even before any packet. Pending mode must guard this path before a null `m_pVideoCodec` dereference. The optional branch currently waits up to 500 ms and then uses stock; this is **not an owner-approved timing parameter** or a production latency claim.
- `GENERAL_RESET` and `GENERAL_FLUSH` must exit pending mode safely; the helper creates the stock decoder and preserves the existing queue reset. Video stream changes drain the existing decoder, then replace it or enter disabled pending state.
- `DEMUXER_PACKET` is still the original queue `shared_ptr` that owns `DemuxPacket*` and frees it exactly once. The code has **no packet-copy, no libdovi RPU inspection and no file/optical special-case injection**.
- Stock decoder behavior must be compared in a full native Kodi CI/build. The source checker is not enough: build all relevant Android targets, inspect warnings, then perform non-device lifecycle/packet-queue tests on the actual Kodi types and all stream-change paths. Only after those gates can a separately reviewed libdovi first-NAL probe be considered.
- **Do not** install the APK on the live Cube, enable the switch, change Magisk/vendor files, restart `media.codec`, alter SELinux, Kodi UDF/MMBD, HDMI, P8/HDR10 or satellite. Independent recovery R0 remains NO-GO.

## Exact current disposition

**Isolated source branch: created and source guard verified.** No full Kodi build, Clang target compile, Kodi lifecycle test, live libdovi pre-create parser or FEL output. Existing branch untouched. The next step is verifying full Kodi target compilation plus testable stream-change worker sequencing on an isolated build host; absent that, this branch is a **non-deployable scaffold**.
