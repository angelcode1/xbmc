#!/usr/bin/env python3
"""Read-only ABI audit for original Fire TV Cube 3 vendor codecs.

Never calls dlopen, codec_init, ioctl, adb, or device interfaces. This checks
static evidence only. Only the exact pinned Amazon PS7702.4965N ELF set is valid.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PIN = {
    "libOmxVideo.so": "eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77",
    "libomx_framework_alt.so": "fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba",
    "libOmxBase.so": "7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee",
}
EXPORTS = {
    "codec_init": 0x58bdd,
    "codec_write": 0x597d1,
    "codec_close": 0x597dd,
    "codec_checkin_pts": 0x5986f,
    "codec_checkin_pts_us64": 0x59885,
    "codec_set_dvmetawithel": 0x5a1a1,
}
CHECKS = {
    0x58bfe: r"strd\s+r0,\s*r0,\s*\[r8\]",
    0x58c02: r"strd\s+r0,\s*r0,\s*\[r8,\s*#8\]",
    0x58c84: r"ldr\.w\s+r0,\s*\[r8,\s*#0x10\]",
    0x590d0: r"mov\.w\s+r0,\s*#0x10a0\b",
    0x590d8: r"ldr\.w\s+r2,\s*\[r8,\s*r0\]",
    0x58ce6: r"cmp\s+r2,\s*#0x1\b",
    0x58cea: r"moveq\s+r0,\s*r3\b",
    0x597d0: r"ldr\s+r0,\s*\[r0\]",
    0x597d2: r"b\.w\s+0x67dc4\b",
    0x597dc: r"push\s+\{r4,\s*r5,\s*r6,\s*lr\}",
    0x59810: r"ldr\s+r0,\s*\[r4,\s*#0x4\]",
    0x59826: r"ldr\s+r0,\s*\[r4\]",
    0x59830: r"str\s+r1,\s*\[r4\]",
    0x5986e: r"ldr\s+r0,\s*\[r0\]",
    0x59876: r"mov(?:w|\.w)\s+r2,\s*#0x10e\b",
    0x5987a: r"movt\s+r1,\s*#0x4010\b",
    0x5a1a0: r"mov\s+r3,\s*r1\b",
    0x5a1a2: r"mov\.w\s+r1,\s*#0x12c0\b",
    0x5a1a6: r"movw\s+r2,\s*#0x179\b",
    0x5a1aa: r"str\s+r3,\s*\[r0,\s*r1\]",
    0x5a1b0: r"ldr\s+r0,\s*\[r0\]",
    0x5a1b2: r"movt\s+r1,\s*#0x4010\b",
}
LINE = re.compile(
    r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)"
)

def output(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE)

def verify(folder):
    for name, sha in PIN.items():
        path = folder / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing or symlinked private ELF " + name)
        raw = path.read_bytes()
        if raw[:7] != b"\x7fELF\x01\x01\x01" or int.from_bytes(raw[18:20], "little") != 40:
            raise ValueError("expected ARM ELF32 " + name)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("UNSUPPORTED_BUILD " + name)
        print("PINNED_ELF_PASS", name)

    lib = str(folder / "libOmxVideo.so")
    symbols = {}
    for line in output("readelf", "-Ws", lib).splitlines():
        m = re.search(
            r"^\s*\d+:\s+([0-9a-f]+)\s+\d+\s+FUNC\s+GLOBAL\s+DEFAULT\s+\d+\s+(\S+)$",
            line,
        )
        if m and m[2] in EXPORTS:
            symbols[m[2]] = int(m[1], 16)
    if symbols != EXPORTS:
        raise ValueError("native export address mismatch")
    print("NATIVE_THUMB_EXPORTS_PASS", len(EXPORTS))

    deps = re.findall(r"Shared library: \[([^]]+)\]", output("readelf", "-d", lib))
    required = ("libomx_worker_peer_alt.so", "libdatachunkqueue_alt.so",
                "libomx_framework_alt.so", "libOmxBase.so", "libsystemcontrolservice.so")
    if len(deps) != 21 or not all(x in deps for x in required):
        raise ValueError("vendor dependencies changed")
    print("DT_NEEDED_PASS", len(deps))

    instructions = {}
    for line in output("llvm-objdump", "-d", "--triple=thumbv7a-linux-android", lib).splitlines():
        m = LINE.match(line)
        if m:
            instructions[int(m[1], 16)] = m[2] + " " + m[3]
    for addr, pattern in CHECKS.items():
        if not re.search(pattern, instructions.get(addr, "")):
            raise ValueError(f"instruction mismatch at 0x{addr:x}: {instructions.get(addr)}")
    print("ARM_INSTRUCTIONS_PASS", len(CHECKS))
    print("CODEC_CONTEXT_OFFSET_MODE=0x10a0")
    print("CODEC_CONTEXT_OFFSET_META_WITH_EL=0x12c0")
    print("MINIMUM_OBSERVED_CONTEXT_END=0x12c4 (4804 bytes, NOT sizeof)")
    print("EXACT_CONTEXT_LAYOUT=UNKNOWN")
    print("KODI_LINKER_NAMESPACE=UNKNOWN; SELINUX_DECODER_ACCESS=UNKNOWN")
    print("NATIVE_P7_FEL_RECONSTRUCTION=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE17_NATIVE_ABI_PASS")

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path, nargs="?")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        assert len(EXPORTS) == 6 and len(CHECKS) == 22
        assert 0x12c0 + 4 == 4804
        print("GAZELLE_STAGE17_SOURCE_SELFTEST_PASS")
    elif args.directory:
        verify(args.directory.expanduser().resolve())
    else:
        ap.error("Pass original vendor library directory or --selftest")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print("GAZELLE_STAGE17_NATIVE_ABI_FAIL", error, file=sys.stderr)
        sys.exit(1)
