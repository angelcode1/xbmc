#!/usr/bin/env python3
"""Read-only, SHA-pinned audit of the MVC OMX handler's overlapping mode-byte store.

Only a static contract audit. Does not call Android, mutate ELF, or enable FEL.
"""
import argparse
import hashlib
import re
import struct
import subprocess
import sys
from pathlib import Path

PIN="fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba"
# These addresses apply ONLY to the exact pinned Fire OS vendor library.
GATES={
  0x18e38:r"sub\.w\s+r0,\s*r6,\s*#0x7f000000",
  0x18e3c:r"sub\.w\s+r0,\s*r0,\s*#0x102",
  0x18e46:r"tbh\s+\[pc,\s*r0,\s*lsl\s*#1\]",
  0x196e6:r"cmp\s+r0,\s*#0x10\b",
  0x196f4:r"ldrb\.w\s+r0,\s*\[r4,\s*#0x10c\]",
  0x196fa:r"beq\.w\s+0x19e60\b",
  0x19e60:r"ldr\.w\s+r0,\s*\[pc,",
  0x19e66:r"mov\.w\s+r8,\s*#0x0\b",
  0x19e6a:r"add\s+r0,\s*pc",
  0x19e72:r"beq\.w\s+0x1a1e0\b",
  0x19e76:r"ldr\s+r0,\s*\[r5,\s*#0xc\]",
  0x19e84:r"ldr\.w\s+r1,\s*\[r4,\s*#0x604\]",
  0x19e88:r"cmp\s+r1,\s*#0x7\b",
  0x19eac:r"beq\.w\s+0x1a1d8\b",
  0x1a1dc:r"strb\.w\s+r0,\s*\[r4,\s*#0x721\]",
  0x1a1e0:r"strh\.w\s+r8,\s*\[r4,\s*#0x109\]",
  0x16834:r"strb\.w\s+r0,\s*\[r4,\s*#0x10a\]",
  0x16888:r"strb\.w\s+r0,\s*\[r4,\s*#0x10a\]",
}

def evaluate(path):
    blob=path.read_bytes()
    if blob[:7]!=b"\x7fELF\x01\x01\x01" or int.from_bytes(blob[18:20],"little")!=40:
        raise ValueError("expected little-endian ARM32 ELF")
    got=hashlib.sha256(blob).hexdigest()
    if got!=PIN:
        raise ValueError("unsupported library SHA: "+got)
    dis=subprocess.check_output(
        ["llvm-objdump","-d","--triple=thumbv7a-linux-android",str(path)],
        text=True)
    code={}
    for line in dis.splitlines():
        m=re.match(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)",line)
        if m:code[int(m[1],16)]=m[2]+" "+m[3]
    for addr,pattern in GATES.items():
        if not re.search(pattern,code.get(addr,"")):
            raise ValueError("semantic mismatch 0x%x: %s"%(addr,code.get(addr)))
    # Jump table TBH at 0x18e46, table starts at PC+4 = 0x18e4a.
    base=0x18e4a
    dispatch=lambda idx:base+2*struct.unpack_from("<H",blob,base+2*(idx-0x7f000102))[0]
    assert dispatch(0x7f000108)==0x196da
    assert dispatch(0x7f00010d)==0x19488
    # PC-relative .text literal + Thumb ADD r0,pc at 0x19e6a.
    literal=struct.unpack_from("<i",blob,0x1a958)[0]
    addr=(literal+0x19e6a+4)&0xffffffff
    assert blob[addr:blob.find(b"\0",addr)]==b"media.support.mvc"
    refs=[a for a,v in code.items() if 0x18dd4<=a<0x1a810 and
          re.search(r"\b(?:b|beq)(?:\.w)?\s+0x1a1(?:d8|e0)\b",v)]
    assert refs==[0x19e72,0x19eac],refs
    print("GAZELLE_STAGE15_MVC_INDEX_AUDIT_PASS")
    print("pin_sha256="+PIN+" instruction_checks="+str(len(GATES)))
    print("index=0x7f000108 target=0x196da property=media.support.mvc")
    print("store=0x1a1e0 strh r8,[owner+0x109], source_r8_zero=true")
    print("effect=clears owner+0x109 and owner+0x10a (conditional)")
    print("p7_stream_enable=NOT_ESTABLISHED; native_fel=NOT_PROVEN")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("library",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        assert 0x7f000108-0x7f000102==6
        assert 0x7f00010d-0x7f000102==11
        assert 0x109+1==0x10a
        print("GAZELLE_STAGE15_SOURCE_SELFTEST_PASS")
    elif args.library:
        evaluate(args.library.expanduser().resolve())
    else:
        p.error("provide the original libomx_framework_alt.so or --selftest")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError,AssertionError) as e:
        print("GAZELLE_STAGE15_MVC_INDEX_AUDIT_FAIL "+str(e),file=sys.stderr)
        sys.exit(1)
