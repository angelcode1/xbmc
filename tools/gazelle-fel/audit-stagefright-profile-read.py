#!/usr/bin/env python3
"""Verify the exact Fire OS 7 Stagefright HEVC profile-read gate, read-only.

Firmware: PS7702.4965N. This verifies instruction bytes, not execution or
vendor OMX parameter values. Requires only Python's standard library.
"""
import argparse
import hashlib
import sys
from pathlib import Path

SHA256 = "4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e"
TEXT_FILE_OFFSET_DELTA = 0x5000
EXPECTED = {
    0x53f8c: "b349",             # ldr r1, PC-relative literal, profile key
    0x53f94: "79f056f9",         # call AMessage::findInt32 helper
    0x53f9a: "58d0",             # beq: profile absent -> skip HEVC check
    0x53fa0: "bbf5805f",         # compare against HEVC profile 0x1000
    0x53fa6: "bbf1020f",         # compare against HEVC profile 0x2
    0x53fd8: "cf69",             # read getParameter vtable slot
    0x53fda: "0f21c0f20061",     # synthesize index 0x0600000f
    0x53fe0: "b847",             # blx r7
}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("libstagefright", type=Path)
    args = p.parse_args()
    if not args.libstagefright.is_file():
        p.error("library missing")
    data = args.libstagefright.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != SHA256:
        print("UNSUPPORTED_BINARY: SHA256=" + actual, file=sys.stderr)
        return 2
    for vaddr, hexstr in EXPECTED.items():
        expected = bytes.fromhex(hexstr)
        offset = vaddr - TEXT_FILE_OFFSET_DELTA
        if data[offset:offset + len(expected)] != expected:
            print(f"INSTRUCTION_FAIL at {vaddr:#x}", file=sys.stderr)
            return 1
        print(f"INSTRUCTION_PASS {vaddr:#x}")
    if data[0xd7e39 - TEXT_FILE_OFFSET_DELTA:0xd7e41 - TEXT_FILE_OFFSET_DELTA] != b"profile\x00":
        print("PROFILE_KEY_FAIL", file=sys.stderr)
        return 1
    print("PROFILE_LITERAL_PASS 0xd7e39")
    print("STAGEFRIGHT_HEVC_PROFILE_READ_PASS")
    print("This does not prove OMX index 0x7f00010d was set or EL was decoded.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
