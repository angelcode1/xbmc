# Gazelle FEL Stage 38 — controlled, redacted VFM provider-graph comparison

**2026-10-20. Stage 37 owner-original offline audit PASS. Stage 38 live capture NOT YET RUN.** Never treat provider names, VFM route counts, or a Dolby badge as FEL pixel reconstruction.

## Confirmed input

Owner-uploaded `stage37-audit-results.txt` shows `GAZELLE_FEL_STAGE37_OFFLINE_PASS` for the exact original `amvdec_h265.ko` and `dovi_vs12.ko`. Five HEVC callback-table relocations, 20 instruction checks, `decoder.h265` provider literal and the original Dolby module registration are verified. **Installed frame-provider alias and the actual P7 aux request remain unverified**.

Independently, Stage 27 original owner-uploaded idle archive `stage27-readonly-20261019-132651.zip` (SHA-256 `761a32df15c8421103b9bf4d0fe87e6999c53e100108219498e147a45d787829`) contained:

```
[02] dvblpath  { dvbldec(0) v4lvideo.0 }
[03] dvelpath  { dveldec(0) dvel }
[04] dvblpath2 { dvbldec2(0) videopip }
[05] dvelpath2 { dveldec2(0) dvel }
provider list:

receiver list:
   ...
```

The **provider list was empty at idle**, and the map contained seven static routes. This does not prove the registered provider remains absent during playback. Stage 28 only retained selected route counters, and did not save the active registered-provider list.

## New Stage 38 read-only discriminant

`tools/gazelle-fel/capture-stage38-provider-graph.py` takes **three samples** in each **manually controlled** phase `idle`, `P8`, `P7` (sequential probes, two-second pause between samples). It reads only:

- `/sys/class/vfm/map`: configured VFM routes **and** any exposed `provider list` / `receiver list` sections;
- `/sys/class/amdolby_vision/dv_provider`: known provider tokens;
- `/sys/class/amdolby_vision/src_format`: coarse first-instance source classification DOVI / HDR10 / SDR / UNKNOWN;
- `/sys/class/vdec/vdec_status`: coarse decoder classification (no vdec, HEVC reported, unknown).

The read commands are restricted to exact sysfs paths, each has a 12-second timeout and bounded raw output. The Mac retains **only allowlisted route names, provider/receiver names, counts, status classifications, timestamps, and read status**; raw sysfs text is discarded in memory. No kernel pointers, filenames, file contents, raw Android logs, device serial or personally identifying data is put in the results. If the sysfs endpoint is missing or the output exceeds the cap, the result is `UNAVAILABLE`, `TIMEOUT`, or `TRUNCATED`, **not** assumed empty.

**No device writes.** No Kodi APK, service stop, root property edits, debugging toggles, procfs kernel symbol probes, `logcat -c`, `dmesg`, sysfs writes, new kernel hooks, direct decoder ioctls, or Magisk changes. User starts/stops playback manually; the collector does not issue Android playback actions.

### Interpretation: evidence gates, not assumptions

- Registered `decoder.h265` in P8/P7 provider section: **HEVC provider name is visible while the user-selected video is playing**. No proof that the Dolby receiver requested that particular provider.
- `dvbldec` on a configured `dvblpath` route and `decoder.h265` simultaneously registered: **coexistence of names**, not a proven alias.
- `decoder.h265` and `dvbldec` in one configured route: **same-route relationship**, not an identity equation or verified forwarding chain.
- No registered name in the provider list: if the section was present and captured fully, reports a **visible empty listing**. This is not proof that no hardware decoder is working; P8 active decoder status is a stronger control.
- A nonzero `dveldec` route count: provider status only; does not prove a separate running EL decode or pixel contribution.
- Missing/garbled status: **fail closed** and treat aliasing as unresolved.

Neither the original kernel module's `decoder.h265` literal nor the public Amlogic source is sufficient to claim the installed Dolby receiver dispatches `VFRAME_EVENT_RECEIVER_GET_AUX_DATA` to this provider on P7. The comparison may improve routing visibility, but **does not execute the event callback or reveal returned aux pointer/length**.

### Original offline baseline replay

The Stage 38 parser passed self-tests against Stage 27-shaped map syntax and a synthetic co-route mapping. A separate offline replay of the user's **actual archived Stage 27 idle VFM map** confirmed: seven recognized routes, zero registered known providers, `dvbldec(0)`, `dveldec(0)` and no same-route evidence. This is **idle-only** and not a new live Stage 38 observation.

## How to run

From a checked out research branch:

```bash
python3 tools/gazelle-fel/capture-stage38-provider-graph.py --selftest
python3 tools/gazelle-fel/capture-stage38-provider-graph.py --capture
```

The companion macOS runner SHA-pins the specific research commit and Git blob of the collector. The owner should follow the three on-screen prompts and upload the **redacted** `~/Downloads/gazelle-fel-stage38-results/stage38-provider-graph-*.zip`. The ZIP includes a sanitized JSON event matrix and a text summary. Nothing private is committed to Git.

## Next Stage 39 gate

Interpret actual P8 and P7 registry/map differences before doing any additional probing. If VFM provides an explicit name mapping, investigate the original receiver's request routing **offline**. If VFM remains ambiguous, return `ORIGINAL_BUILTIN_VF_DISPATCH_AND_PROVIDER_ALIAS=NOT_VERIFIED`; do not escalate to kprobes, eBPF, ptrace, library injection, new APKs or settings changes merely to get an apparent success.

FEL remains unproven until independent P7 metadata processing, running EL decoder, and residual-sensitive output pixels have been demonstrated. Preserve working P8, Kodi, HDMI/audio passthrough, voice satellite, Magisk and UDF/MMBD.
