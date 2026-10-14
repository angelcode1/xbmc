#!/usr/bin/env python3
"""Read-only verification of the pinned Gazelle ARM32 OMX decoder gates.

This tests static instructions, NOT runtime instance state or true FEL decoding.
Requires llvm-objdump. Does not connect to a device or modify the input binary.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED_SHA = "eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77"
GATES = {
    "legacy_setup": (0x21a62, 0x21af0, {
        0x21a68: r"cmp\s+r1,\s*#0xb\b",
        0x21ac8: r"ldr\s+r0,\s*\[r0,\s*#0x20\]",
        0x21aca: r"cmp\s+r0,\s*#0x10\b",
        0x21ad4: r"ldr\.w\s+r2,\s*\[pc,",
        0x21ada: r"add\s+r2,\s*pc\b",
    }),
    "legacy_init": (0x1ec0c, 0x1ec34, {
        0x1ec12: r"ldr\s+r0,\s*\[r0,\s*#0x20\]",
        0x1ec14: r"cmp\s+r0,\s*#0x10\b",
        0x1ec2c: r"orr\s+r0,\s*r0,\s*#0x40\b",
    }),
    "alternate_setup": (0x3b682, 0x3b7d0, {
        0x3b694: r"ldr\s+r0,\s*\[r0,\s*#0x20\]",
        0x3b69c: r"cmp\s+r0,\s*#0x10\b",
        0x3b69e: r"beq\s+0x3b734\b",
        0x3b746: r"movs\s+r6,\s*#0xb\b",
        0x3b7c8: r"str\.w\s+r6,\s*\[r5,\s*#0x150\]",
    }),
    "dolby_codec_spec": (0x30952, 0x30970, {
        0x30958: r"ldr\s+r2,\s*\[r1,\s*#0x20\]",
        0x3095a: r"cmp\.w\s+r2,\s*#0x400\b",
    }),
    "dvmeta_wrapper": (0x5a1a0, 0x5a1ba, {
        0x5a1a6: r"movw\s+r2,\s*#0x179\b",
    }),
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    if not args.library.is_file():
        parser.error("Cannot find vendor shared library")
    digest = hashlib.sha256(args.library.read_bytes()).hexdigest()
    print("SHA256=" + digest)
    if digest != EXPECTED_SHA:
        print("UNSUPPORTED_BINARY: known addresses are version-specific")
        return 2
    objdump = shutil.which("llvm-objdump")
    if not objdump:
        print("llvm-objdump is required", file=sys.stderr)
        return 2
    problems = []
    for name, (start, stop, checks) in GATES.items():
        result = subprocess.check_output(
            [objdump, "-d", "--triple=thumbv7a-linux-android",
             f"--start-address=0x{start:x}", f"--stop-address=0x{stop:x}",
             str(args.library)], text=True)
        insns = {}
        for line in result.splitlines():
            found = re.match(
                r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)",
                line)
            if found:
                insns[int(found.group(1), 16)] = found.group(2) + " " + found.group(3)
        good = True
        for addr, expression in checks.items():
            actual = insns.get(addr, "")
            if not re.search(expression, actual):
                problems.append(f"{name} 0x{addr:x}: expected /{expression}/; actual {actual!r}")
                good = False
        print(name + ": " + ("PASS" if good else "FAIL"))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("OFFLINE_GATE_PASS")
    print("Peer+0x20 value 0x10 selects HEVC format 0xb in alternate decoder.")
    print("Legacy decoder uses the same value to gate dv_duallayer:1;.")
    print("Neither test proves the runtime peer value, EL processing or FEL output.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
