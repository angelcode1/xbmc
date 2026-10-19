# Gazelle FEL Stage 27 result and Stage 28 controlled P8/P7 runtime comparison

**2026-10-19, Australia/Brisbane.** Stage 27 owner-uploaded read-only snapshot **CAPTURED**; Stage 28 is an **opt-in collector**, not yet executed on the Cube. No kernel, sysfs, Kodi, Magisk, audio, video, optical or satellite configuration changes.

## Stage 27 private input

Owner-uploaded `stage27-readonly-20261019-132651.zip`, containing a compact text and JSON snapshot taken at `2026-10-19T13:26:51Z`. Source remains in the owner's private conversation; only these non-sensitive conclusions are documented here. Original source reports `DEVICE_WRITES=NONE` and `ROOT_READ_ACCESS=YES`.

| Observation | Meaning and limitation |
|---|---|
| Kernel `5.4.125-ab27` | Matches the original PS7702.4965N target kernel release; not proof of byte-identical built-in kernel code |
| Loaded `dovi`, `amvdec_h265`, `decoder_common`, `stream_input` | Verifies modules loaded at snapshot; not evidence of active paired decoder |
| `register_dv_functions` and `unregister_dv_functions` symbols, type `T`, no bracketed module | Installed kernel exposes registration entry points; no module name does **not** by itself prove built-in implementation |
| `parse_sei_and_meta_ext`, `is_dovi_dual_layer_frame` symbols visible | Compatible names exist in installed symbol table; no byte-level comparison with public source |
| `vh265_event_cb` symbol type `t` in `amvdec_h265` | Confirms event callback exists in loaded original driver; not proof it is called |
| `decoder_do_aux_data_check` and `vdec_set_dv_metawithel` in `decoder_common` | Metadata helper symbols resolve; no runtime invocation proof |
| `dvbldec dvbldec2` named in Dolby provider node | Potential upstream provider names, not evidence of active decoded pictures |
| `dveldec(0)` and `dveldec2(0)` in VFM map | Named EL paths have observed zero counts; not an active EL frame |
| `/sys/class/vdec/vdec_status` reads `No vdec.` | No active vdec reported at this sample |
| `amstream_hevc_frame` and `amstream_dves_hevc_frame` report `flag:267( Used )`; corresponding stream port unused | Flag remains set despite `No vdec.`. Do not equate Used port with currently decoding video |
| Dolby source-format node says `inst1: DV FORMAT_DOVI`, while instance status says `valid 0` and `core on 0` | Residual/stale status can outlive active pictures; not sufficient to claim working playback |

**Stage 27 conclusion:** installed registration and parser-related symbol names are now confirmed present. Active Profile 7 pairing, FEL extraction, P7 Dolby rendering and enhancement-layer pixel contribution remain **NOT PROVEN**. Static presence and counters are orthogonal to active decoder state.

## Why Stage 28 is necessary

Stage 27 is a single, non-atomic status snapshot with no controlled playback phase. This can explain apparently contradictory flags, but cannot distinguish persistent port ownership from active hardware decode or discriminate P7 vs working P8. Repeating Stage 27 without synchronized content phases is unlikely to help.

## Stage 28 collector contract

`tools/gazelle-fel/capture-stage28-active-comparison.py` runs on the **Mac**, never installs code on the Cube. After checking exactly one authorized ADB target and root **read** permission, it prompts the owner to manually control video playback:

1. **idle:** stop Kodi video and press Enter;
2. **P8:** start a *known-working* Profile 8 video, press Enter while visibly playing;
3. **P7:** stop P8, start the Profile 7 FEL test, press Enter while visibly playing.

For each phase, take **three** sequential read-only samples, spaced two seconds apart. Read only `/sys/class/amstream/ports`, `/sys/class/vdec/vdec_status`, `/sys/class/vfm/map`, and four existing `/sys/class/amdolby_vision/` status nodes (`src_format`, `dv_inst_status`, `dv_provider`, `dv_mode`). Parse and save only bounded, semantic statuses (port type, flags, format; VFM provider counters; coarse vdec classifier; instance validity, output mode). Each ADB call has a 12-second timeout. No logs, kernel addresses, video samples, arbitrary sysfs paths or device identifiers are retained.

The collector cannot guarantee atomicity across seven nodes, nor that the user-selected file really is P7 or P8. The displayed host UTC start/end times delimit each sample. It makes **no device-side writes**, changes no codec flags/properties, injects no ioctls, does not kill or restart services, and does not alter playback automatically.

## Interpret without overclaiming

- **Good discriminant:** when a P8 *visibly playing* phase yields different `vdec_status`, Dolby core state, provider counts or port flags from idle, evidence of active observable state increases.
- **P7-specific discriminant:** repeated P7 samples showing live vdec and distinct stream-vs-frame ports, and nonzero EL-path provider state, would motivate a closer ELF/metadata gate. No such result can be inferred before running the collector.
- **Fail-closed:** empty/missing endpoints or `No vdec.` during user-stated playback are evidence of limited diagnostic visibility, possible time-of-read effects or disabled status—not proof that hardware lacks support.
- **Never sufficient alone:** P7 `FORMAT_DOVI`, a Dolby badge, `[0]dv dual layer`, nonzero EL map counters, port `Used` flags or module registration are not independent proofs of FEL residual reconstruction.

Run:

```bash
python3 tools/gazelle-fel/capture-stage28-active-comparison.py --selftest
python3 tools/gazelle-fel/capture-stage28-active-comparison.py --capture
```

Output: `~/Downloads/gazelle-fel-stage28-results/stage28-active-comparison-*.zip`, with one text summary and structured JSON. Keep the ZIP private and upload it for review. No Play Store, ADB installation, privileged writes or global `media.omx.stream_mode`, `enable_fel`, `dolby_meta_with_el` or `nal_skip_policy` changes are permitted.

**Next decision after results:** investigate only a demonstrably different active runtime branch; otherwise prefer further original-module static research to speculative Kodi playback patches. Residual-sensitive BL-vs-BL+EL output evidence is still mandatory.
