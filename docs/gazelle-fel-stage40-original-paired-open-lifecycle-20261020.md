# Gazelle FEL Stage 40 — original paired-decoder open, failure, init and release contract

**2026-10-20. Owner-supplied Stage 39 PASS. Original owner kernel static code gates independently verified for the critical path; full Stage 40 macOS replay is the next owner checkpoint.** No Cube, Kodi, Magisk, optical, HDMI, voice-satellite, property or driver changes.

## Owner Stage 39 evidence

Uploaded `stage39-audit-results(2).txt` ended with `GAZELLE_FEL_STAGE39_OFFLINE_PASS`. It verified both original kernel ELFs, 44 ARM64 sites, 18 relocations, six provider literals and all eight naming branch combinations. The original HEVC driver deliberately produces `dvbldec`, `dveldec`, `dvbldec2`, `dveldec2`; the P8/P7 Stage 38 provider `dvbldec` does not indicate a missing generic `decoder.h265` provider.

The Stage 38 owner active capture shows P8: DOVI, P7: HDR10. In both, the VFM provider is `dvbldec(1)`, and `dveldec(0)` remains present only as a configured route count, **not a confirmed active EL**. Earlier P7 process FD capture showed `/dev/amstream_dves_hevc_frame` and actual frame-port type `0x1d11`.

## Original SHA-pinned modules

Only the owner archive `gazelle-fel-kernel-readonly-20261019-191050.zip` (SHA-256 `02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44`) was used to inspect the private original files offline:

| Module | SHA-256 |
|---|---|
| `stream_input.ko` | `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c` |
| `decoder_common.ko` | `a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b` |

Original `ports[]` table at `.data+0x5f0` has stride `0x50` and `type` at row `+0x18`. Its read-only initialized values and name relocations give Dolby HEVC stream `0x1911` (index 15) versus Dolby HEVC frame `0x1d11` (index 17). **Live values may be modified**, so static values must be reconciled with the earlier actual Stage 13 port readings. No new live port observation is claimed here.

## A. Pair creation: frame exclusion wins over DUALDEC

The original `amstream_open()` has two independent `vdec_create` calls:

1. `0x160c/0x1610`: **primary** `vdec_create(port,NULL)`, stored into the port's primary pointer at `0x1614`. Null primary takes the failure branch at `0x1618`.
2. `0x161c/0x1620`: read actual `port->type`; if **FRAME bit 10 set**, skip directly to `0x1654`, never entering the second allocation block from that call.
3. `0x1628`: if **DUALDEC bit 12 set** (and FRAME not set), proceed to `0x1638/0x163c` and invoke **secondary** `vdec_create(port,primary)`. If DUALDEC absent, the debug flag at `0x162c/0x1630` can provide a separate entrance; this is a compiled alternate path, not a suggested property change.
4. `0x1644–0x1650`: assign and check `primary->slave` at `+0x40`. Zero branches to cleanup at `0x16d4`.

Thus the initialized frame port `0x1d11` skips paired allocation despite having the DUALDEC bit. The initialized stream port `0x1911` takes the paired creation attempt on the ordinary successful primary-open path.

## B. New fail-closed evidence: attempted second creation cannot silently return a successful open when it returns null

On the secondary allocation path, original `0x164c` reloads `primary->slave`; `0x1650` branches on null to `0x16d4`. That branch calls `vdec_release` on the primary, releases file-private storage via `kfree` at `0x16e0`, emits a `printk` diagnostic at `0x16ec`, and sets `w0=-0xc` at `0x16f0` (Linux **`-ENOMEM`**) before returning via `0x16f4`. The successful common return sets `w0=0` at `0x1694`.

**Conditional inference:** If a future *unchanged, valid stream-mode contract* successfully opens the default `0x1911` device and its type still has DUALDEC but lacks FRAME, then this open path had a **non-null secondary allocation pointer at that checkpoint**. This is materially stronger than 'a second `vdec_create` was attempted'. It still does **not** prove that the linked instance was initialized, remained alive, registered an `dveldec` provider, parsed EL metadata or contributed FEL residual pixels. Do **not** switch the Cube to stream mode just to test this; its buffer/PTS contract differs from frame mode.

The original `decoder_common.ko:vdec_create()` uses `vzalloc` at `0x8a0`; when passed a non-null master it writes `new_vdec->master` at `+0x38` and `master->slave` at `+0x40` (`0x93c–0x948`). Failure paths can return null, as seen at `0x9e4–0x9e8`. Two code sites thus independently establish bidirectional pointer storage and the caller's null check.

## C. The separate initialization gate and conditional release

`amstream_port_init()` calls `vdec_init(primary)` at `0x1f88`; checks its return at `0x1f8c`; checks a port flag and debug path at `0x1f90–0x1fa0`; and has a **separate** `vdec_init(primary->slave)` call at `0x1fa8/0x1fc4`, with a distinct error branch at `0x1fc8`. This is **not** proof the second decoder was initialized during current P7 playback.

`amstream_release()` has two original conditional teardown paths:
- `0x17fc–0x181c` reads `primary->slave` and invokes `vdec_release(primary)`, then `vdec_release(slave)` if non-null;
- `0x18e8–0x1904` has another guarded primary/slave release sequence.

All release, create and initialization callsites are verified by original `R_AARCH64_CALL26` relocation targets; the code does not justify assuming both teardown paths run for one file or that a slave always exists.

## Verification and safety

`tools/gazelle-fel/audit-stage40-pair-open-release.py` verifies original ZIP and both exact private module SHA-256/ELF identities, two initialized port table row types/names, original `amstream_open/release/port_init` and `vdec_create` function identities, exact instruction addresses/operands, 13 relocation-checked callsites, and a synthetic FRAME-before-DUALDEC branch selector.

The key path from the same original modules was separately cross-checked offline. Owner full run should end `GAZELLE_FEL_STAGE40_OFFLINE_PASS`. Proprietary original ELFs must remain off GitHub. GitHub CI runs selftest/source safety only.

No ADB, sysfs/property/debug setting mutation, direct 0x179/0x301 ioctl, library patch, kernel patch, Kodi APK, video playback automation or Magisk changes.

## Stage 41 priority

Find **an existing instance-scoped, passive observation of the actual paired `vdec_s` pointer and life-state** before designing any FEL-only stream path. A mere provider name cannot prove allocation, and open-time allocation cannot prove the instance's subsequent decoded frames or the residual-sensitive pixel output. If the original modules/installed read-only status provide no such observable, record **NOT_OBSERVABLE** and continue static lifecycle proof rather than introducing kprobes/eBPF/ptrace or global debug toggles. Keep working P8, passthrough, satellite, UDF/MMBD protected.
