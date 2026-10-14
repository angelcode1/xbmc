#!/usr/bin/env python3
"""Read-only disassembly checks for the pinned Gazelle Dolby OMX component gates."""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

SHA256 = "eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77"
TESTS = (
    ("legacy dual-layer config", 0x21ac6, 0x21ae0, {
        0x21ac8: r"ldr\s+r0,\s*\[r0,\s*#0x20\]",
        0x21aca: r"cmp\s+r0,\s*#0x10\b",
        0x21acc: r"bne\.w\s+0x21d82\b",
        0x21ad4: r"ldr\.w\s+r2,\s*\[pc,",
    }),
    ("legacy Dolby codec spec", 0x30954, 0x30974, {
        0x30958: r"ldr\s+r2,\s*\[r1,\s*#0x20\]",
        0x3095a: r"cmp\.w\s+r2,\s*#0x400\b",
        0x30960: r"ldr\.w\s+r1,\s*\[r1,\s*#0x3dc\]",
        0x30966: r"movt\s+r2,\s*#0x7f10\b",
        0x3096a: r"cmp\s+r1,\s*r2\b",
    }),
    ("legacy Dolby ES preparation", 0x309b2, 0x309d6, {
        0x309b6: r"ldr\.w\s+r3,\s*\[r12,\s*#0x20\]",
        0x309ba: r"cmp\.w\s+r3,\s*#0x400\b",
        0x309c0: r"ldr\.w\s+r12,\s*\[r12,\s*#0x3dc\]",
        0x309c6: r"movt\s+r3,\s*#0x7f10\b",
    }),
    ("alternate Dolby codec spec", 0x4300c, 0x4302a, {
        0x43012: r"ldr\s+r2,\s*\[r1,\s*#0x20\]",
        0x43014: r"cmp\.w\s+r2,\s*#0x400\b",
        0x4301a: r"ldr\.w\s+r1,\s*\[r1,\s*#0x3dc\]",
        0x43020: r"movt\s+r2,\s*#0x7f10\b",
        0x43024: r"cmp\s+r1,\s*r2\b",
    }),
    ("alternate Dolby ES preparation", 0x4306e, 0x4309c, {
        0x43072: r"ldr\.w\s+lr,\s*\[r12,\s*#0x20\]",
        0x43076: r"cmp\.w\s+lr,\s*#0x400\b",
        0x4307c: r"ldr\.w\s+r12,\s*\[r12,\s*#0x3dc\]",
        0x43084: r"movt\s+lr,\s*#0x7f10\b",
        0x43088: r"cmp\s+r12,\s*lr\b",
    }),
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    if not args.library.is_file():
        parser.error("vendor library file not found")
    digest = hashlib.sha256(args.library.read_bytes()).hexdigest()
    print("SHA256=" + digest)
    if digest != SHA256:
        print("UNSUPPORTED_BINARY: address checks only apply to the pinned ELF")
        return 2
    objdump = shutil.which("llvm-objdump")
    if not objdump:
        print("llvm-objdump unavailable", file=sys.stderr)
        return 2
    missing = []
    for name, start, stop, assertions in TESTS:
        output = subprocess.check_output(
            [objdump, "-d", "--triple=thumbv7a-linux-android",
             f"--start-address=0x{start:x}", f"--stop-address=0x{stop:x}",
             str(args.library)], text=True)
        instructions = {}
        for line in output.splitlines():
            match = re.match(
                r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)",
                line)
            if match:
                instructions[int(match[1], 16)] = match[2] + " " + match[3]
        failed = False
        for address, pattern in assertions.items():
            actual = instructions.get(address, "")
            if not re.search(pattern, actual):
                failed = True
                missing.append(f"{name} at 0x{address:x}: expected {pattern}; got {actual}")
        print(f"{name}: {'FAIL' if failed else 'PASS'}")
    if missing:
        print("\n".join(missing), file=sys.stderr)
        return 1
    print("OMX_DOLBY_CODEC_GATE_PASS")
    print("The runtime peer-field values and EL processing are NOT established.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
