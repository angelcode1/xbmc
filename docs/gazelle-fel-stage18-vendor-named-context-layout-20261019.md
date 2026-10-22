# Gazelle FEL Stage 18 — recovered vendor `codec_para_t` field map

**Status:** offline ABI *partial* layout verified; full native decoder struct and FEL backend are **not** proven.

Source: original Fire OS PS7702.4965N `/vendor/lib/libOmxVideo.so`, SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`. ARM32 Thumb disassembly using `llvm-objdump` and the original ELF `.rodata` addresses; no proprietary binaries committed.

## New method — original vendor's own field labels

`dump_codec_param()` (Thumb `0x588ad`, size 816 bytes) emits 40 log messages of the form `dump_codec_param: FIELD=%...`. For each message, the read-only audit resolves the PC-relative log format address, then verifies the corresponding ARM load of the field from the `codec_para_t` pointer (`r4`). This independently connects field **names, locations, and code**, without importing an incompatible public Amlogic struct.

Audit result `GAZELLE_FEL_STAGE18_NATIVE_LAYOUT_PASS`: **40/40 logger calls and fields**, plus six separately verified native initialization/EL metadata instructions. A copy with an incorrect ELF hash is rejected.

### Recovered field map (selected, full JSON provided separately)

| Offset | Field / meaning | Evidence |
| --- | --- | --- |
| `+0x00` | `handle` | 32-bit field, later main decoder FD |
| `+0x04` / `+0x08` / `+0x0c` | `cntl_handle` / `sub_handle` / `audio_utils_handle` | 32-bit fields |
| `+0x10` | `stream_type` | Named logging field; distinct from `decoder_type` |
| `+0x14`, bits 0–3 | `has_video` / `has_audio` / `has_sub` / `noblock` | Vendor bit extraction, not four separate words |
| `+0x18` | `video_type` | 32-bit field |
| `+0x1c` | `audio_type` | 32-bit field |
| `+0x40` through `+0x58` | `am_sysinfo.format`, `.width`, `.height`, `.rate`, `.extra`, `.status`, `.ratio` | seven 32-bit named fields |
| `+0x60` | `am_sysinfo.ratio64` | 64-bit load (`ldrd`) |
| `+0x1084` | `packet_size` | Named 32-bit field |
| `+0x1088` | `avsync_threshold` | Named 32-bit field |
| `+0x1090` | `SessionID` | Named 32-bit field |
| `+0x1094` / `+0x1098` / `+0x109c` | `dspdec_not_supported` / `switch_audio_flag` / `automute_flag` | Named 32-bit fields |
| **`+0x10a0`** | **`decoder_type`** | Native `codec_init()` selects DV HEVC frame device if this word equals `1`; stream device otherwise in that branch |
| `+0x10a4` | `dves_type` | Named 32-bit field, independently referenced in `codec_init()` |
| `+0x10a8` | `drmmode` | Named 32-bit field |
| `+0x10ac` | `video_path` | Named 32-bit field |
| `+0x10b0` | `receive_id` | Named 32-bit field |
| **`+0x10b4`** | **`config`** | Inline character data address passed to the logger as `%s` |
| **`+0x12b4`** | **`config_len`** | Neighboring length word; **512-byte (`0x200`) span** between start of `config` and start of `config_len` |
| `+0x12b8` | Reset-related value | Native `codec_init()` reads it at `0x594d2`, passes it through ioctl selector `0x177` |
| `+0x12c0` | Dolby EL metadata flag | `codec_set_dvmetawithel()` writes this word before invoking ioctl selector `0x179` |

The ioctl selector names `AMSTREAM_SET_IS_RESET` (`0x177`) and `AMSTREAM_SET_DV_META_WITH_EL` (`0x179`) are corroborated by a **separate public A311D2 `amstream.h`**. The actual values and call addresses were recovered from the Amazon vendor ELF, not inferred from that source.

Original source reference: https://github.com/TCLOpenSource/a311d2/blob/24a1e36b68d5319f7c4e94a2d6d1badf9f92ba7f/include/linux/amlogic/media/utils/amstream.h

## Practical new implications

1. **`decoder_type` has a recovered name**, not merely a numeric unknown: `codec_init()` accesses the same field at `+0x10a0` that the logger identifies. In the verified DV HEVC branch, `== 1` selects the frame device; other values select the stream device. Other decoder formats may interpret the enum differently.
2. The native decoder's **configuration string is in-line** at `+0x10b4`, not a pointer to some arbitrary external allocation. The `config_len` field is at `+0x12b4`, with a 512-byte span between them. The verified vendor `dv_duallayer:1;` append must be understood together with bounds checks before any new backend attempts to construct configuration.
3. The per-instance **metadata-with-EL flag at `+0x12c0` and its ioctl are distinct** from the ordinary decoder configuration string. `codec_init()` also reads the reset-related word at `+0x12b8`, passes ioctl `0x177`, then issues the regular port-init selector `0x111` in its completion path. These are different kernel operations.
4. The mapped last field gives a **minimum observed context memory extent `0x12c4` (4,804 bytes)**, **NOT** the complete `sizeof(codec_para_t)`. The logger omits other fields and vendor code may access higher addresses or nested structures. Some fields in the 4KB region around `+0x84` remain unidentified.
5. `.gnu_debugdata` decompresses to a mini-ELF with `.debug_frame` and symbols, but **no `.debug_info` type structures**. It cannot supply a trustworthy full struct layout. The field names and offsets above come from executable logger instructions instead.

## Engineering decision

**Do not allocate or pass a made-up 4,804-byte C structure to `codec_init`.** We have a reliable **partial named layout**, not the full ABI; initialization preconditions, complete size, linker visibility, SELinux decoder permissions, stream HEVC packet/PTS contracts, paired-EL allocation and residual pixel reconstruction still need separate validation.

No Kodi builds or APKs were modified; no device files, sysfs, properties, kernel modules, Magisk setup, satellite/passthrough or optical-disc support were touched.

Offline reproducibility:

```bash
python3 tools/gazelle-fel/audit-stage18-native-layout.py --selftest
python3 tools/gazelle-fel/audit-stage18-native-layout.py /private/path/libOmxVideo.so --json /tmp/gazelle-fel-stage18-layout.json
```

**Next gate:** audit all writes/reads around `config`/`config_len` and the codec initialization order, then reconcile the original vendor constructor and packet feeding structures with the native codec context. Keep any P7-only stream backend on a separate experimental branch, default off, until those exact ABI conditions and teardown can be proved.

## 22 October 2026 correction — constructor's exact 0x12c8 allocation proven

The original Stage18 conclusion that the largest accessed field at `+0x12c0` establishes only a **minimum extent `0x12c4`** was correct at that time. New SHA-verified analysis of the **same original** `libOmxVideo.so` (SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77`) has now resolved the actual original **`AmlogicVideoDecoder::AmlogicVideoDecoder()` allocation**:

- `0x1ddd0`: loads 0x12c8 (4,808 bytes); `0x1dde8` BL via veneer `0x65934` / PLT calls `_Znwj` (C++ operator new unsigned int);
- `0x1ddec`: stores pointer in native decoder `+0x190`;
- `0x1ddfa–0x1ddfe`: loads the same 0x12c8 and invokes `__aeabi_memclr` via veneer `0x65944`;
- destructor `0x1e13e–0x1e15a`: null-checks the stored pointer, conditionally calls `codec_close` (veneer `0x659d4`), invokes `_ZdlPv` (operator delete, veneer `0x659e4`) and clears decoder `+0x190`.

This **supersedes only the unknown total allocation size**. The original 40 logger-derived field names and offsets remain intact. The 4,808 bytes are the real allocation/clear size inside this vendor constructor, not an invitation to fabricate an external `codec_para_t` C struct, bypass its constructor, or call `codec_init` from Kodi. Nested allocations, proper parameters, output Surface/V4L/UVM/fence ownership, independent stream-mode selection, dual BL/EL decoding and FEL residual pixels remain unresolved. No owner Cube actions or binaries committed.

Source-only exact audit: `angelcode1/cube3/tools/fel_codec_context_owner_audit.py` on `research/gazelle-fel-no-fork-observer-20261021`; validates **16 Thumb opcode witnesses and four BL→veneer→PLT→relocation symbol edges**, passes with unchanged original ELF and refuses altered SHA. Details in `docs/gazelle-fel-codec-context-allocation-ownership-20261022.md` in that repository. Implementation remains OFF on Fire OS.
