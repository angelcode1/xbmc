#!/usr/bin/env python3
"""Read-only, fail-closed Fire OS Stage 19 native config ABI audit.

Requires original SHA-pinned PS7702.4965N libOmxVideo.so; never runs vendor
code or accesses the Cube. These are static source-to-sink checks, not FEL proof.
"""
import argparse
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import sys

SHA = "eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77"
GATES = {
  0x21a74: r"movw\s+r8,\s*#0x10b4",
  0x21a80: r"mov\.w\s+r1,\s*#0x200",
  0x21a86: r"bl\s+0x1e488",
  0x21a8e: r"adds\s+r0,\s*#0x1",
  0x21a90: r"movw\s+r7,\s*#0x12b4",
  0x21a9c: r"str\s+r0,\s*\[r1,\s*r7\]",
  0x21ade: r"movw\s+r1,\s*#0x10b3",
  0x21ae4: r"mov\.w\s+r1,\s*#0xffffffff",
  0x21ae8: r"bl\s+0x1e488",
  0x21afe: r"str\s+r0,\s*\[r1,\s*r7\]",
  0x281e4: r"movw\s+r1,\s*#0x10b4",
  0x281ea: r"mov\.w\s+r1,\s*#0x200",
  0x281f0: r"bl\s+0x1e488",
  0x281fa: r"movw\s+r5,\s*#0x12b4",
  0x2821e: r"movw\s+r1,\s*#0x10b3",
  0x28224: r"mov\.w\s+r1,\s*#0xffffffff",
  0x28228: r"bl\s+0x1e488",
  0x1e490: r"mov\s+r2,\s*r1",
  0x1e496: r"mov\s+r3,\s*r12",
  0x1e4a6: r"movs\s+r1,\s*#0x0",
  0x1e4a8: r"bl\s+0x65ae4",
  0x5aa9e: r"movw\s+r0,\s*#0x12b4",
  0x5aaa6: r"cbz\s+r0,\s*0x5aadc",
  0x5aaaa: r"movw\s+r0,\s*#0x10b4",
  0x5aab4: r"movw\s+r2,\s*#0x301",
  0x5aabe: r"str\s+r0,\s*\[sp\]",
  0x5aac4: r"bl\s+0x67d94",
  0x5aac8: r"cmp\.w\s+r0,\s*#0xffffffff",
  0x5aacc: r"bgt\s+0x5aadc",
  0x5aad8: r"bl\s+0x658b4",
  0x5aadc: r"movs\s+r0,\s*#0x0",
  0x591ac: r"bl\s+0x5aa64",
  0x59406: r"bl\s+0x5aa64",
  0x594ce: r"movw\s+r2,\s*#0x177",
  0x594ea: r"movw\s+r2,\s*#0x111",
}
FORMATS=[
 (0x21fc0,0x21a84,"hevc_double_write_mode:%d;"),
 (0x21fd0,0x21ada,"dv_duallayer:1;"),
 (0x288d8,0x281ee,"hevc_buf_width:%d;hevc_buf_height:%d;hevc_buf_margin:%d;hevc_double_write_mode:%d"),
 (0x288dc,0x2821a,"negative_dv:1;"),
]

def audit(path):
    blob=path.read_bytes()
    if blob[:7]!=b"\x7fELF\x01\x01\x01" or int.from_bytes(blob[18:20],"little")!=40:
        raise ValueError("Expected ARM32 little-endian ELF")
    if hashlib.sha256(blob).hexdigest()!=SHA:
        raise ValueError("Unsupported vendor library SHA")
    dis=subprocess.check_output(["llvm-objdump","-d","--triple=thumbv7a-linux-android",
                                 "--no-show-raw-insn",str(path)],text=True)
    ins={}
    for line in dis.splitlines():
        m=re.match(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)",line)
        if m:ins[int(m[1],16)]=m[2]+" "+m[3]
    for addr,pat in GATES.items():
        if not re.search(pat,ins.get(addr,"")):
            raise ValueError(f"Gate 0x{addr:x}: {ins.get(addr)!r}")
    for literal,add,expected in FORMATS:
        delta=struct.unpack_from("<i",blob,literal-0x2000)[0]
        addr=(add+4+delta)&0xffffffff
        off=addr-0x2000
        end=blob.find(b"\x00",off)
        if off<0 or end<off or blob[off:end].decode("ascii")!=expected:
            raise ValueError("Format string differs at 0x%x"%addr)
    disp=struct.unpack_from("<i",blob,0x65af0-0x2000)[0]
    plt=(0x65aec+8+disp)&0xffffffff
    if plt!=0x1adfc:raise ValueError("Unexpected format veneer/PLT")
    instructions=[struct.unpack_from("<I",blob,plt-0x2000+i*4)[0] for i in range(3)]
    if instructions!=[0xe28fc600,0xe28cca93,0xe5bcf390]:
        raise ValueError("Unexpected format PLT instructions")
    rel=subprocess.check_output(["readelf","-rW",str(path)],text=True)
    if not re.search(r"^000ae194\s+\S+\s+R_ARM_JUMP_SLOT\s+\S+\s+__vsprintf_chk@LIBC",rel,re.M):
        raise ValueError("Unexpected dynamic formatter relocation")
    print("GAZELLE_STAGE19_ELF_SHA_PASS",SHA)
    print("THUMB_CONTROL_FLOW_GATE_PASS",len(GATES))
    print("FORMAT_STRING_XREF_PASS",len(FORMATS))
    print("FORMATTER_PLT_PASS veneer=0x65ae4 symbol=__vsprintf_chk")
    print("CONFIG_IOCTL_SELECTOR=0x301")
    print("INITIAL_FORMAT_BOUND=512; OPTIONAL_APPEND_BOUND=0xffffffff")
    print("CONFIG_IOCTL_ERROR_LOGGED_RETURN_ZERO=yes; RUNTIME_STATUS=unknown")
    print("ACTIVE_LEGACY_BRANCH=unknown; FEL_RESIDUAL=not_proven")
    print("GAZELLE_FEL_STAGE19_CONFIG_LIFECYCLE_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("lib",type=Path,nargs="?")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        assert len(GATES)==35 and len(FORMATS)==4 and 0x12b4-0x10b4==512
        print("GAZELLE_FEL_STAGE19_CONFIG_SELFTEST_PASS")
    elif a.lib:audit(a.lib.expanduser().resolve())
    else:p.error("Specify original libOmxVideo.so or --selftest")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print("GAZELLE_STAGE19_AUDIT_FAIL",error,file=sys.stderr)
        sys.exit(1)
