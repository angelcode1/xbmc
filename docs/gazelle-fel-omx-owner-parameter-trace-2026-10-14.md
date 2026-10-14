# Gazelle OMX peer-owner field trace — 14 October 2026

## Binary provenance

Input ZIP `gazelle-omx-two-libs-20261014-141513.zip` SHA-256 `eda4b421150e75878f069e50b33c0f6db3f962fc784b2fc729a15305a9d83351`. Contents match included SHA256SUMS:

| ELF | SHA-256 |
| --- | --- |
| `libomx_framework_alt.so` | `fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba` |
| `libOmxBase.so` | `7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee` |

Cross-referenced the already uploaded `libOmxVideo.so` SHA-256 `eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77` (PS7702.4965N). All are 32-bit ARM Android ELF. Nothing was installed or modified on the device.

## Verified static dataflow

1. `libomx_framework_alt.so`, `VendorPeerComponent::setOwner(OmxComponent&)`, address `0x1db68–0x1db70`, stores the pointer to the **owning OMX component** at peer offset `+4` (`str r1,[r0,#4]`, address `0x1db6e`).
2. In `libOmxVideo.so`, `AmlogicVideoDecoderDolbyVision::doCodecSpec()`, address `0x30956`, loads `[decoder+4]` as the owner pointer. At `0x30958/0x3095a`, it compares **owner+0x20** to `0x400`; otherwise at `0x30960–0x3096c` it compares **owner+0x3dc** to `0x7f100001`. Therefore the previously called `peer+0x20`/`peer+0x3dc` fields are more accurately **fields of the owning `OmxVideoDecoder` component, accessed through the peer's saved owner pointer**.
3. In `libomx_framework_alt.so`, `OmxVideoDecoder::OmxVideoDecoder(name, ...)`, the component name is passed in `r9`. The `.dvhe` suffix comparison (`0x164b6–0x164be`) conditionally writes `0x0b` to **owner+0x3dc** (`0x164c8–0x164ca`). The `.dav1` comparison (`0x164d8–0x164e0`) conditionally writes `0x7f100001` to the same field (`0x164ea–0x164f0`). These are mutually exclusive suffix-specific paths in this constructor; subsequent writes by other code are not excluded by this test.
4. `OmxVideoDecoder::setParameter()` dispatches custom/vendor index **`0x7f00010d`** to case `0x19488`: an ARM Thumb `tbh` table at `0x18e4a` maps index entry 11 to that address (`0x7f000102 + 11`). It validates the supplied structure's size (`>=0x18`) and version byte, then loads input offsets `+0x0c` and `+0x10` and **writes owner+0x20 and owner+0x24** respectively at `0x194a4` and `0x194a8`. It checks component coding `+0x604 == 0x0b` and selected profile values `0x1000` or `0x2` for a following HEVC-specific branch. The exact symbolic name of `0x7f00010d` and exact profile enumeration remain unverified.
5. Separate legacy decoder `setUp()` at `0x21ac8/0x21aca` checks **owner+0x20 == 0x10** before appending `dv_duallayer:1;`. Its `0x10` is therefore a value tested on a component field that the framework can also set via a vendor parameter; it is **not established to be a profile-7/FEL toggle**.
6. `libOmxBase.so` contains `AmlogicPeer` and buffer-wrapper methods and depends on `libomx_framework_alt.so`. Neither of these two uploaded ELFs has a matching named dynamic import of `codec_set_dvmetawithel`; absence of a direct symbol reference does not exclude direct `ioctl` or indirect dispatch.

## Practical consequence

For the `.dvhe` decoder, constructor-created `owner+0x3dc=0xb` does **not** match the Dolby subclass's alternate `0x7f100001` condition. Consequently, unless that field is subsequently changed, Dolby-specific `doCodecSpec` / `prepareEsData` branches require **owner+0x20 == 0x400**. The observed status P8 `FORMAT_DOVI` and P7 `FORMAT_HDR10` does not establish the actual runtime value of this field. Previous Kodi capability-filter values `P8=256`, `P7=0` are different-layer diagnostics; they cannot be substituted for the vendor owner-field values.

All six pinned static checks passed, including the table-dispatch calculation and independent Dolby subclass pointer loads. This completes the *static assignment-path trace* for these fields, not the runtime value audit. Next useful work is to establish whether Android's OMX setup passes vendor index `0x7f00010d` and what payload it supplies for P7 versus P8, preferably from existing logs or a narrowly scoped non-mutating diagnostic. A speculative `MediaFormat` override or bare `0x179` ioctl would not be supported by this evidence. Proving actual FEL pixels remains mandatory.

## Offline reproduction

```sh
python3 tools/gazelle-fel/audit-omx-peer-fields.py /path/to/folder-with-libOmxBase-libomx_framework_alt-libOmxVideo
# OMX_PEER_OWNER_DATAFLOW_PASS
```

This verifier pins the exact three library hashes and checks literal suffixes, owner pointer instructions, vendor parameter dispatcher and decoder subclass tests. It reads only the supplied files.