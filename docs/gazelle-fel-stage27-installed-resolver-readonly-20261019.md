# Gazelle FEL Stage 27 — opt-in read-only installed-kernel resolver snapshot

**Date:** 2026-10-19. **Status:** safe *host source* and synthetic parsing checks, no live Cube evidence until the owner runs the collector. Stage 26 independently passed original public-source revision and function gates; original proprietary kernel-module audit passed at Stage 25. Active FEL is still **NOT PROVEN**.

## Why this is the next gate

The owner’s Fire OS `dovi_vs12.ko` uses `register_dv_functions` as an imported external symbol. Stage 26 identified one pinned public Amlogic implementation that stores the callback table and requests `VFRAME_EVENT_RECEIVER_GET_AUX_DATA` from `dvbldec`, then calls `metadata_parser_process`. That public code is not the installed Amazon implementation. We need a non-invasive inventory before assuming it matches.

## What Stage 27 reads

The optional Python host collector `tools/gazelle-fel/capture-stage27-readonly.py` uses only fixed, explicitly allowlisted **ADB shell read commands**:

- `uname -r`, `getprop ro.build.version.incremental`;
- `su -c 'id'` solely to test whether read-only root access is available;
- `cat /proc/modules`, retaining **only video / Dolby module names**;
- a remotely filtered `grep -E` on `/proc/kallsyms`, retaining **only twelve requested symbol names, type letters and owning module names**, never raw kernel addresses;
- read-only `cat` of these optional sysfs nodes: `/sys/class/amdolby_vision/src_format`, `dv_inst_status`, `dv_provider`, `dv_mode`; `/sys/class/vfm/map`; `/sys/class/vdec/vdec_status`; `/sys/class/amstream/ports`.

Each individual call is bounded by a 15-second timeout. Fields are truncated to 12,000 characters; kernel-like addresses are masked. The script requires **exactly one connected, authorized ADB device** and creates text, JSON, and ZIP reports **on the Mac only** under `~/Downloads/gazelle-fel-stage27-results`. No writes, installs, restarts, property changes, shell redirections to device paths, module loading, log clearing, kernel memory dumps, or raw ioctls.

You do not need to start or stop video, unplug any hardware, or install an APK. This is a baseline status snapshot; it does not prove current P7 decode state.

## How to interpret a report

- A `register_dv_functions` symbol entry would show that **some kernel symbol table visibility exists**, not that a Dolby callback was registered or called during playback.
- A `dovi` module entry indicates a module may be loaded, not successful `metadata_parser_process` execution.
- Absence in `/proc/kallsyms` is **not evidence of absence**; kernel symbol visibility can be restricted or symbols may be omitted.
- A named `dvbldec` or `dveldec` provider in sysfs alone does not prove an active EL picture. In particular, `dveldec(0)` is not an active enhancement decoder.
- If root access is unavailable, the report marks root-dependent probes unavailable instead of declaring the receiver absent.

**Non-goals:** no speculative codec mode toggles, no `enable_fel` write, no `dolby_meta_with_el` write, no `media.omx.stream_mode` change, no raw `0x179/0x301` ioctls, no Kodi replacement, no satellite/HDMI/optical/Magisk changes.

## Local macOS usage

With `adb` installed and the Cube connected, from the research checkout run:

```bash
python3 tools/gazelle-fel/capture-stage27-readonly.py --selftest
python3 tools/gazelle-fel/capture-stage27-readonly.py --capture
```

Use `ADB=/path/to/adb` if needed; the existing adblink fallback is also supported. Archive name is printed as `UPLOAD_FILE=...`. Upload the generated ZIP to continue; avoid publishing it in the public repository, because sysfs values may still include device state.

The source-only CI runs compile/selftest but cannot validate the actual Cube without the owner's explicit run.

## What would count as progress after upload

Correlate visible installed-kernel symbol names with original-module imports and public ABI, then identify whether a **separate strictly read-only** runtime capture can distinguish a populated `dveldec` from a registered-but-inactive interface. A credible FEL claim still requires an active paired EL decoder, valid RPU metadata, and a genuinely residual-sensitive BL-vs-BL+EL output oracle.
