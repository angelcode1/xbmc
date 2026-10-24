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

## 24 October 2026 — REAL libdovi 3.3.2 host ABI gate PASS

**Verified GitHub Actions:** [run 40058234002](https://github.com/angelcode1/xbmc/actions/runs/40058234002) completed **success** in BOTH `source-only` and `real-libdovi-abi` jobs.

The dedicated container uses `debian:forky` and installs **libdovi-dev 3.3.2-3+b1**, checks `RPU_PARSER_MAJOR/MINOR/PATCH=3.3.2`, verifies that `/usr/include/libdovi/rpu_parser.h` is a complete header (over 10 KiB with `dovi_parse_unspec62_nalu` declaration), and compiles/links/runs `tests/TestGazelleFELRealLibdovi.cpp` against the **actual libdovi shared library**. Observed markers:

```text
libdovi-dev=3.3.2-3+b1
GAZELLE_FEL_REAL_LIBDOVI_ABI_PASS version=3.3.2 linked_real_library=true invalid_input_unknown=true no_authenticated_FEL_fixture=true kodi_android_build=false no_device=true
GAZELLE_REAL_LIBDOVI_HOST_ABI_GATE_PASS full_kodi_build=false real_FEL_fixture=false no_device=true
```

Earlier real-library attempts revealed **two distinct findings**:

1. The original `DoviRpuOpaque`/`DoviRpuDataHeader` type spellings in this branch's new probe **and existing `BitstreamConverter.cpp`** did not match the pinned real libdovi 3.3.2 API. The isolated branch now uses `auto*`/`const auto*` deduced from the `dovi_*` functions. This was required to make the production probe compile with its actual header, not just with the synthetic FFI stub. The base/working Kodi branch was not modified.
2. Ubuntu resolute's `libdovi-dev 3.3.2-3` package has a **truncated 281-byte** `rpu_parser.h` exposing only version macros, while the shared library exports `dovi_*`. The CI initially failed before source compilation. This corresponds to Debian [bug 1124682](https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1124682) about a truncated generated header; Debian's `3.3.2-3+b1` rebuild supplies a complete header. CI now refuses a truncated header rather than misdiagnosing missing declarations as a Kodi defect.

**Scope limit:** this is genuine runtime execution of real libdovi with *intentionally invalid, synthetic* NAL62 payload, proving the ABI links and returns Unknown without failure. It does **not** prove a valid FEL versus MEL RPU produces the correct classification, that the full `VideoPlayerVideo.cpp`/existing late converter compiles with Android's target dependencies, or that any EL residual decoding works. The first-open Kodi codec remains synchronous, and the source feature is **hard-disabled**. No APK was generated or installed; R0 recovery remains unverified.

**Next actionable gates:** compile the full Android Kodi worker and late converter on an isolated build host, then test against independently validated clear-content FEL and MEL metadata (no private disc assets committed). Only then review initial-stream pre-create lifetime and native decoder requirements.

## 24 October 2026 — authentic upstream FEL/MEL RPU classifications PASS

Verified CI [run 40059636961](https://github.com/angelcode1/xbmc/actions/runs/40059636961) completed **SUCCESS** in both source-only and real-libdovi ABI jobs. The latter executed the production `GazelleFELPrecreateProbe.h` against **genuine libdovi 3.3.2** and pinned, upstream `quietvoid/dovi_tool` `libdovi-3.3.2` public RPU fixtures. It downloaded files only in the ephemeral CI container, did **not** check them into our repositories or upload them as artifacts, and verified original Git blob hashes:

- `assets/tests/fel_orig.bin` (384 bytes), blob `a7926febb39043d938ebc49dce0a4c043b5b32f0`, independently identified by upstream `tests/rpu/info.rs` as **Profile 7 FEL**.
- `assets/tests/mel_orig.bin` (183 bytes), blob `09b8963ddaee4e2c5554b9682987a72278edf53c`, sourced from upstream MEL metadata.

The first attempt **correctly failed**: the upstream `.bin` file stores `0x00000001` followed by **raw 0x19-prefixed RPU data**, *not* a complete `0x7c01` HEVC NAL62 as Kodi sees in its stream. The test adapter was fixed to strip only the Annex B start code and prepend `0x7c 0x01` to the **unchanged RPU payload**; the production classifier was not weakened. Real libdovi then correctly returned FEL and MEL; both were independently passed through the production in-band first-AU scanner by wrapping them with **synthetic** BL and EL NALs, checking protected fallback and duplicate-RPU rejection.

Observed CI marker:

```text
GAZELLE_REAL_FEL_MEL_RPU_CLASSIFICATION_PASS libdovi=3.3.2 authentic_upstream_metadata=true synthetic_bl_el_transport=true codec_selection=disabled actual_fel_decode=false android_kodi_compile=false no_device=true
```

**Meaning:** the isolated read-only classifier genuinely distinguishes these two test-vector RPUs. **Not** a genuine disc BL/EL stream, Kodi initial-stream lifetime proof, native decoder proof or residual playback. The experiment remains compile-time **OFF**, stock-only and non-deployable.

## 24 October 2026 — independent Android ARMv7 two-translation-unit job initiated

Added `.github/workflows/gazelle-fel-android-two-tu-build.yml` and `tools/gazelle-fel/compile-android-kodi-tus.py`. Job [40059389926](https://github.com/angelcode1/xbmc/actions/runs/40059389926) uses the original Android build's pinned NDK r28c/SDK and `tools/depends` build, configures `CMAKE_EXPORT_COMPILE_COMMANDS=ON`, then compiles **exactly** `xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp` and `xbmc/utils/BitstreamConverter.cpp` using the genuine Android-generated compiler commands. The runner rejects commands outside the checkout and compiler paths outside `ANDROID_NDK_HOME`. It does **not** sign, build or upload an APK, fetch signing secrets, modify Kodi on the device, or publish binary outputs.

**At this checkpoint the build job was still in `Build Android depends` (NOT a compile pass).** Its eventual compiler status must be checked independently in the GitHub Actions run; there is no honest claim of successful Android compilation yet. Dependencies/downloads may fail before either translation unit is reached.

Next after the exact target build: make the real initial-open packet handoff use the proven parser, with bounded original-message ownership and seek/timeout/flush safety; test full Kodi lifecycle before any device test. No on-device activation while independent recovery R0 is unverified.

## 24 October 2026 — Android two-TU compile-command validation (source CI PASS, target build pending)

The Android ARMv7 build-only workflow is now live, following the base Kodi `android-firetv-bluray.yml` bootstrap and pinned NDK r28c. It does **not** produce/sign/upload an APK, use signing secrets or contact a Cube. It compiles only `VideoPlayerVideo.cpp` and `BitstreamConverter.cpp` using CMake's generated `compile_commands.json`. These translation units have **NOT YET PASSED** actual Android compilation at the most recent check; dependencies are still compiling.

Review found an important potential false-positive in the runner: a `compile_commands.json` `file` field could name the target while the command itself compiled an unrelated file. This is now fail-closed in `tools/gazelle-fel/compile-android-kodi-tus.py`: require **exactly one** source path matching the claimed file, `-c`, an ARMv7 target, `-o` pointing to a `.o`, and a compiler under `ANDROID_NDK_HOME`. CMake-generated commands are executed with `subprocess.run(argv)`, never shell.

Added `tests/TestGazelleCompileCommands.py`, exercising six negative cases using a dummy compiler; this does **not** compile Android Kodi. [CI run 40060808504](https://github.com/angelcode1/xbmc/actions/runs/40060808504) completed **SUCCESS** for both `source-only` and `real-libdovi-abi`. Source CI printed:

```text
GAZELLE_ANDROID_COMPILE_COMMANDS_SOURCE_SELFTEST_PASS negative=6 exact_tus=true armv7_only=true real_android_compilation=false no_device=true
```

Two isolated Android compile-only runs may coexist after improving the runner: [original run 40059389926](https://github.com/angelcode1/xbmc/actions/runs/40059389926) uses the earlier runner and [revised run 40060758989](https://github.com/angelcode1/xbmc/actions/runs/40060758989) uses the stricter runner; both were still in initial build/dependency setup at the latest check. **Do not claim Android compilation from the source-mock selftest or running workflow.** A final target compile pass requires `GAZELLE_ANDROID_ARMV7_TWO_TU_COMPILE_PASS` from the actual Android job after CMake generates the database, for BOTH source files. Even then that would not demonstrate a full Kodi link or real device runtime.

The experimental runtime policy remains `kDeferredStockResearchEnabled=false` protected by a `static_assert`. Existing UDF/MMBD, satellite, HDMI and the six Magisk modules remain untouched.

## 24 October 2026 — first Android ARMv7 compilation reached actual Clang; missing internal FFmpeg prerequisite

The **first** compile-only run [40059389926](https://github.com/angelcode1/xbmc/actions/runs/40059389926) finished **FAILURE**, but it made useful progress: Android SDK/NDK r28c installation PASS, all `tools/depends` PASS and Kodi CMake configure PASS. Direct compilation of `VideoPlayerVideo.cpp` then failed **before reaching the Gazelle changes**, because an existing Kodi header required `libavutil/pixfmt.h`:

```text
GAZELLE_ANDROID_ARMV7_TU_START path=xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp
xbmc/cores/VideoPlayer/Buffers/VideoBuffer.h:21:10: fatal error: 'libavutil/pixfmt.h' file not found
GAZELLE_ANDROID_TU_COMPILE_REFUSED GAZELLE_ANDROID_ARMV7_TU_FAIL xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp exit=1
```

**Root cause:** `cmake/modules/FindFFMPEG.cmake` configures **internal FFmpeg**, which is a Kodi CMake `ExternalProject` target named `build-ffmpeg` from `cmake/scripts/common/ModuleHelpers.cmake`. CMake generates a compile database without first building that target, and a bare `clang++ -c` command from the compile database does not express/exert the required dependency ordering. CMake's configure report had `LIBDOVI enabled: Yes`, but that is not proof of other generated headers.

**Fix on this isolated research branch:** `.github/workflows/gazelle-fel-android-two-tu-build.yml` now performs `cmake --build "$BUILD_DIR" --target build-ffmpeg --parallel 2` after configure, fails closed on any FFmpeg build problem and checks that generated `libavutil/pixfmt.h` exists before attempting the two requested Kodi TUs. This does not touch Kodi runtime, proprietary binaries, APK signing or the Cube.

The new [compile-only run 40060990150](https://github.com/angelcode1/xbmc/actions/runs/40060990150) was **in progress** when this text was written. Its final FFmpeg, `VideoPlayerVideo.cpp` and `BitstreamConverter.cpp` results must be checked independently; do not claim an actual target compile pass until both translation units print their exact `GAZELLE_ANDROID_ARMV7_TU_PASS` markers. Another runner, [40060758989](https://github.com/angelcode1/xbmc/actions/runs/40060758989), had already started before this prerequisite fix and may produce the same missing-header error.

**Next**: distinguish Kodi build/dependency failures from genuine Gazelle source compile errors. Do not enable `kDeferredStockResearchEnabled=false` or install an APK; R0 rollback, first normal stream precreate integration and native FEL residual decoding remain NOT IMPLEMENTED.

## Source-lifetime restrictions

- The video worker can receive `MSGQ_TIMEOUT` and call `ProcessDecoderOutput` even before any packet. Pending mode must guard this path before a null `m_pVideoCodec` dereference. The optional branch currently waits up to 500 ms and then uses stock; this is **not an owner-approved timing parameter** or a production latency claim.
- `GENERAL_RESET` and `GENERAL_FLUSH` must exit pending mode safely; the helper creates the stock decoder and preserves the existing queue reset. Video stream changes drain the existing decoder, then replace it or enter disabled pending state.
- `DEMUXER_PACKET` is still the original queue `shared_ptr` that owns `DemuxPacket*` and frees it exactly once. The code has **no packet-copy, no libdovi RPU inspection and no file/optical special-case injection**.
- Stock decoder behavior must be compared in a full native Kodi CI/build. The source checker is not enough: build all relevant Android targets, inspect warnings, then perform non-device lifecycle/packet-queue tests on the actual Kodi types and all stream-change paths. Only after those gates can a separately reviewed libdovi first-NAL probe be considered.
- **Do not** install the APK on the live Cube, enable the switch, change Magisk/vendor files, restart `media.codec`, alter SELinux, Kodi UDF/MMBD, HDMI, P8/HDR10 or satellite. Independent recovery R0 remains NO-GO.

## Exact current disposition

**Isolated source branch: created and source guard verified.** No full Kodi build, Clang target compile, Kodi lifecycle test, live libdovi pre-create parser or FEL output. Existing branch untouched. The next step is verifying full Kodi target compilation plus testable stream-change worker sequencing on an isolated build host; absent that, this branch is a **non-deployable scaffold**.
