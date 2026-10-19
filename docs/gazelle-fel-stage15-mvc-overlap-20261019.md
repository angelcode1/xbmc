# Gazelle Stage 15 — resolve the apparent per-instance OMX stream-mode setter

Date: 2026-10-19. **Static read-only confirmation on original Amazon PS7702.4965N vendor library**, no Cube/Kodi installation, kernel or property changes.

## Input provenance

Owner-supplied original `/vendor/lib/libomx_framework_alt.so`, SHA-256 `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba`. ARM32 little-endian Thumb ELF. All reported VAs here require **that exact SHA**.

Stage 14 noticed a write `0x1a1e0: strh.w r8,[r4,#0x109]` within `OmxVideoDecoder::setParameter()`. The 16-bit store covers both owner `+0x109` and `+0x10a`, the latter read as the frame/stream flag during native decoder setup. This warranted checking whether OMX exposes an instance-scoped control. **The question is now narrowed and the proposed positive setter is disproven.**

## The exact parameter dispatch index

`OmxVideoDecoder::setParameter()` begins its proprietary OMX selector jump table at `0x18e46`. It subtracts `0x7f000102` from the incoming `OMX_INDEXTYPE`, bounds checks 30 entries, then uses `TBH [pc,r0,lsl #1]`. The binary table begins at `0x18e4a`.

- **`0x7f000108`**: table slot 6; halfword resolves to handler **`0x196da`**.
- Control: **`0x7f00010d`**: table slot 11; resolves to the already verified Amlogic profile-level handler **`0x19488`**.

The `0x196da` handler checks size `>=0x10` and an OMX-version-related input byte; it next checks owner `+0x10c` at `0x196f4–0x196fa` before branching into the block at `0x19e60`. The exact handler is **MVC-related**, as proved by its independently resolved string `media.support.mvc` at VA `0x297a3` and nearby log string `mIsMvc is true, mvc must show on video laryer`. The ELF also contains `OMX.amlogic.index.isMvc`, but the direct string-to-index registration was not independently established; avoid asserting an exact exported symbolic enum name solely from proximity.

## The actual write is a zero-only path

From `0x19e60`:

1. `0x19e66: mov.w r8,#0` sets the **source register for the eventual halfword store to ZERO**.
2. At `0x19e6c`, code checks `media.support.mvc` via the property's helper; `0x19e72` can branch directly to the store at `0x1a1e0`.
3. An alternative conditional path checks input `+0x0c`, state fields `+0x604`, `+0x722` and then branches `0x19eac → 0x1a1d8`, which falls through to the same store.
4. `0x1a1e0: strh.w r8,[r4,#0x109]` clears **both owner bytes +0x109 and +0x10a** when reached. The only explicit direct branches to the final block identified within `OmxVideoDecoder::setParameter()` are from `0x19e72` and `0x19eac`.

The instruction **can clear the mode byte** (which might incidentally change what decoder mode is later chosen), but **it is not a general setter that accepts a requested P7 stream-mode value**. Invoking this MVC-related branch as a FEL feature switch is inappropriate.

The known other explicit writes to `owner+0x10a` in the pinned framework are constructor decisions at `0x16834` (1) and `0x16888` (0), chosen using vendor/global decoder configuration such as `media.omx.stream_mode`. These are not a demonstrated supported *per-instance* Kodi control. Indirect/aliased writers elsewhere are not excluded.

## Verification

Standalone offline tool `tools/gazelle-fel/audit-stage15-mvc-index.py` pinned to exact SHA; and an expanded independent local checker `gazelle_fel_stage15_mvc_setter_audit.py`.

Local expanded audit on the owner's original library:

```
PINNED_VENDOR_ELF_PASS
INSTRUCTION_GATE_PASS checked=21
VENDOR_INDEX_DISPATCH_PASS idx=0x7f000108 slot=6 target=0x196da
READ_ONLY_PROPERTY_XREF_PASS at=0x297a3 key=media.support.mvc
MVC_ZERO_WRITE_PATH_PASS branches=0x19e72,0x19eac source_r8=zero
OWNER_BYTES_CLR=0x109,0x10a
GAZELLE_STAGE15_MVC_SETTER_AUDIT_PASS
```

Tampering a copy of the library caused the auditor to refuse the changed SHA (**fail-closed**). The GitHub Actions source-only check exercises Python syntax and mask arithmetic; it does not download or execute proprietary ELF.

## Decision and engineering next gate

**Close the overlapping-write candidate.** Do not send `0x7f000108`, force the MVC flag, patch the owner fields, use global `setprop media.omx.stream_mode`, or inject native ioctls as a FEL trial. Existing P7/P8 live captures show unchanged kernel port types and a frame device for both; this explains skipped default slave allocation but does not imply a safe route to change the selected decoder.

The next useful work is to find a **genuinely supported per-instance** stream decoder mode contract (or an isolated alternative native AML backend) whose input format, decoder allocation, teardown and fallback can be validated without changing global shared media HAL behavior. A Kodi P7-only APK remains unjustified until such a contract is proven. Keep P8, voice satellite, HDMI passthrough, Blu-ray MMBD/UDF and installed Kodi untouched. Native P7 FEL residual reconstruction remains unproven.
