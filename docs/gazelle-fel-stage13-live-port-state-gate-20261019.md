# Gazelle FEL Stage 13 — verify *live* amstream pairing flags without changing kernel state

Date: 2026-10-19. Original Fire OS PS7702.4965N (5.4.125-ab27) private kernel module `stream_input.ko`, SHA256 `fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c`. Proprietary kernel binary stays out of GitHub.

## New finding: an existing read-only sysfs endpoint

The original relocatable ELF exports a class named **`amstream`**, with a class attribute named **`ports`**. The class/attribute identities were independently verified via `.rela.data.userdata_mutex` `R_AARCH64_ABS64` relocation targets into `.rodata`:

| Original .data address | Relocation | Target |
| --- | --- | --- |
| `0x4f8` | class name | `.rodata+0x12c5` → `amstream` |
| `0x5d0` | attribute name | `.rodata+0xef2` → `ports` |
| `0x5e0` | show function | `.text+0xcac` → `ports_show` |

The `class_attr_ports` structure contains mode **`0x124`, octal 0444**, meaning read-only access for all users under normal sysfs semantics. `ports_show()` reads each current `stream_port_s.type` field at `0xda8` using the verified 0x18 offset. The expected path on a running module is **`/sys/class/amstream/ports`**, assuming the class is registered normally; if absent/inaccessible, the collector reports it rather than changing device state.

The original `amstream_open()` code also includes conditional **mutations** of type flags (not just its initial `ports[]` table):
- `0x142c–0x1434` reads `port->type`, ORs `0x1000` (`PORT_TYPE_DUALDEC`), writes it back, under an earlier condition involving a global flag.
- `0x16f8–0x1710` reads `port->type`, ORs `0x400` (`PORT_TYPE_FRAME`), writes it back, on another exceptional branch.
- `0x161c/0x1620/0x1628` reads the current `port->type` and uses FRAME before DUALDEC to determine whether it enters the secondary `vdec_create()` path.

Therefore **initial table values are not always live values**. Although the default DV HEVC frame port `0x1d11` blocks secondary allocation and the default stream port `0x1911` attempts it, a stream port modified to include `PORT_TYPE_FRAME` may also skip the second decoder.

The standalone local `gazelle_fel_stage13_sysfs_audit.py` checked the exact binary SHA, ELF class/attribute name relocations, `0444` mode, and 12 ARM64 instructions. Result: **`GAZELLE_FEL_STAGE13_READONLY_SYSFS_AUDIT_PASS`**. This is static code proof; **no live port-type value has yet been read**.

## New lightweight observational P7/P8 comparison

Host capture tool:
`tools/gazelle-fel/capture-stage13-live-ports.sh`

On macOS, run P7, then P8 as separate processes:

```bash
bash tools/gazelle-fel/capture-stage13-live-ports.sh P7
bash tools/gazelle-fel/capture-stage13-live-ports.sh P8
```

For each run, stop Kodi playback and press Enter to capture baseline; then play the indicated sample, leave video visibly moving, and press Enter to capture two active snapshots three seconds apart. It reads:
- `/sys/class/amstream/ports` (primary new evidence; may reveal live per-port type flags and status)
- `/sys/class/vfm/map`, `/sys/class/vdec/vdec_status` (established read-only decoder controls)
- symbolic links for the active `media.codec` process's `/dev/amstream*` file descriptors

The script does **not** clear logs, change properties, force-stop apps, restart services, inject ioctls, write sysfs, reboot or install anything. If the endpoint is absent, that is recorded and the capture remains useful for decoder/FD correlation.

## Intended decision gate

1. Read the actual `amstream_dves_hevc_frame` and `amstream_dves_hevc` port types from before/active snapshots, and see if either changes during P7 or P8.
2. Confirm which `/dev/amstream*` FD the active OMX decoder actually owns.
3. If P7 remains on the frame node, it is still a **known default no-slave path**; do not install a test APK until the native Fire OS stream-mode prerequisites and HAL coexistence are reviewed.
4. If the stream node becomes active in a future *explicitly opt-in* experiment, look for master/slave creation, active `dveldec`, valid Dolby metadata, and a residual-sensitive FEL output test. A dual-decoder allocation attempt is **necessary but not sufficient**.
5. Do not try global `media.omx.stream_mode`, `nal_skip_policy`, `dolby_meta_with_el`, raw metadata `0x179` ioctl, or CoreELEC 5.15 modules on Fire OS 5.4.

No new APK, Kodi fork merge, Magisk change, kernel property write, satellite/audio modification or optical-UDF/MMBD change was made.
