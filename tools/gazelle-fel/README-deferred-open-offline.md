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

## Source-lifetime restrictions

- The video worker can receive `MSGQ_TIMEOUT` and call `ProcessDecoderOutput` even before any packet. Pending mode must guard this path before a null `m_pVideoCodec` dereference. The optional branch currently waits up to 500 ms and then uses stock; this is **not an owner-approved timing parameter** or a production latency claim.
- `GENERAL_RESET` and `GENERAL_FLUSH` must exit pending mode safely; the helper creates the stock decoder and preserves the existing queue reset. Video stream changes drain the existing decoder, then replace it or enter disabled pending state.
- `DEMUXER_PACKET` is still the original queue `shared_ptr` that owns `DemuxPacket*` and frees it exactly once. The code has **no packet-copy, no libdovi RPU inspection and no file/optical special-case injection**.
- Stock decoder behavior must be compared in a full native Kodi CI/build. The source checker is not enough: build all relevant Android targets, inspect warnings, then perform non-device lifecycle/packet-queue tests on the actual Kodi types and all stream-change paths. Only after those gates can a separately reviewed libdovi first-NAL probe be considered.
- **Do not** install the APK on the live Cube, enable the switch, change Magisk/vendor files, restart `media.codec`, alter SELinux, Kodi UDF/MMBD, HDMI, P8/HDR10 or satellite. Independent recovery R0 remains NO-GO.

## Exact current disposition

**Isolated source branch: created and source guard verified.** No full Kodi build, Clang target compile, Kodi lifecycle test, live libdovi pre-create parser or FEL output. Existing branch untouched. The next step is verifying full Kodi target compilation plus testable stream-change worker sequencing on an isolated build host; absent that, this branch is a **non-deployable scaffold**.
