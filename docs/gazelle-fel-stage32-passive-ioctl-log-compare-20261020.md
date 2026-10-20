# Gazelle FEL Stage 32 — passive P8/P7 ioctl and Dolby metadata log boundary

**2026-10-20 — source-only collector ready. No Stage 32 Cube capture has yet been executed.**

## Prior original-device and vendor evidence

The owner-uploaded `stage31-audit-results(2).txt` confirms `GAZELLE_FEL_STAGE31_OFFLINE_PASS`: the original Fire OS `libOmxVideo.so` matched SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` and passed 37 exact instruction checks. Verified compiled branches show `AmlogicVideoDecoderAwesome::doCodecSpec` requires subtype 0x0b and decoder flag +0xdc nonzero, while native `set_video_codec_info` can log an `AMSTREAM_SET_PTR_CONFIGS (0x301)` ioctl error but return zero. **This is NOT evidence that the ioctl fails for P7.**

Stage 28's original nine samples showed active P8 `DV FORMAT_DOVI` versus P7 `HDR10 FORMAT_HDR10`, both with `dvbldec(1)` but no observed `dveldec` activity. Those measurements are not a residual-sensitive FEL reconstruction test.

One exact diagnostic string found in the owner's original pinned `libOmxVideo.so` is **`kernel not support AMSTREAM_SET_PTR_CONFIGS`**. It is a useful existing logging candidate, not proof of kernel incompatibility unless captured.

## New Stage 32 opt-in read-only collector

`tools/gazelle-fel/capture-stage32-log-gates.py` uses a Mac-host ADB client, requires exactly one authorized connected device, and executes **only**:
- `adb logcat -b main -b system -T 1 -v epoch` (passive ongoing read; never clears log buffers or changes verbosity)
- optionally a read-only `su -c 'cat /sys/class/amdolby_vision/src_format'` once per active playback phase

User manually starts P8 then P7 playback. For each phase, the script starts reading logcat **before** the user starts playback; the owner presses Enter when video is visibly playing. Event collection is bounded (75 seconds maximum, 200000 lines maximum, 120 retained matched event labels). Host UTC and parsed Android epoch timestamps allow phase comparison but do not make the reads atomic.

Crucially, **it never writes raw log messages to disk**. It retains only whitelisted event *category labels* and timestamps, coarse Dolby source classification, line counts and truncation indicators. No message text, Kodi filename, Android file paths, PIDs, USB serial, device identifiers or raw logcat content are saved. Results go to a private local ZIP, and no proprietary binary is included.

Detected categories distinguish:
- exact **CONFIG_301_UNSUPPORTED** (`kernel not support AMSTREAM_SET_PTR_CONFIGS`);
- a more explicit **CONFIG_301_IOCTL_FAILURE** log that actually mentions command or subcommand 0x301;
- an **unspecified** native ioctl failure (not automatically attributed to 0x301);
- Dolby metadata parser failure messages;
- presence-only HEVC configuration strings, Dolby HEVC component, EL or frame-mode mentions, and prior Kodi diagnostic markers.

**Do not equate a log candidate with confirmed failing ioctl return.** If stock log verbosity suppresses a category, the observation is `NO_DIRECT_ERROR_SEEN_SUCCESS_UNKNOWN`, not evidence of successful configuration. If logcat exits, truncates, produces no parseable lines or overflows the retained events, status is `INCOMPLETE`.

No global property/sysfs writes, `logcat -c`, `dmesg` dumps, Magisk changes, Kodi installation, process restarts, injection, raw ioctl or audio/HDMI/voice satellite changes. Collection stops only the **host adb client**, not any Android media process.

## Reproduce

Mac bundle runner downloads the **exact SHA-pinned** script from this research branch, verifies its Git blob SHA, executes `--selftest`, then starts `--capture`. Or run directly from a checked-out repository:

```sh
python3 tools/gazelle-fel/capture-stage32-log-gates.py --selftest
python3 tools/gazelle-fel/capture-stage32-log-gates.py --capture
```

Output: `~/Downloads/gazelle-fel-stage32-results/stage32-log-compare-*.zip`, containing a redacted JSON event timeline and text summary. **Only upload the ZIP privately**, not any original device log.

## Next gate / non-goals

Compare P8 and P7 event categories and source classifications. If there is an exact native `0x301` failure during P7 but not P8, that warrants *additional provenance verification*, not immediately changing stream properties. If the logs lack a direct 0x301 outcome, record **UNKNOWN** and continue offline original-binary analysis. Neither a vendor log, Dolby badge, provider count nor RPU message can prove enhancement-layer residual contribution to displayed pixels.

Preserve known-working Profile 8, integrated Kodi, HDMI passthrough, optical UDF/MMBD and satellite coexistence. Stage 32 is strictly diagnostic.
