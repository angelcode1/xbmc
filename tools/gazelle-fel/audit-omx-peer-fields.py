#!/usr/bin/env python3
"""Fail-closed, read-only static OMX peer-owner dataflow check for PS7702.4965N."""
import argparse, hashlib, re, shutil, struct, subprocess, sys
from pathlib import Path

SHA = {
 "libOmxBase.so":"7bbf3da721b69995add8a7cd6b5bd5fc0e6454c065c3d4690f81eebe2d69c7ee",
 "libomx_framework_alt.so":"fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba",
 "libOmxVideo.so":"eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77",
}
CHECKS = {
 "libomx_framework_alt.so":[
  ("owner binding",0x1db68,0x1db72,{0x1db6e:r"str\s+r1,\s*\[r0,\s*#0x4\]"}),
  ("DV HEVC constructor",0x164b6,0x164d4,{
    0x164c8:r"movs\s+r0,\s*#0xb",
    0x164ca:r"str\.w\s+r0,\s*\[r4,\s*#0x3dc\]"}),
  ("DAV1 constructor",0x164da,0x164f8,{
    0x164ea:r"movs\s+r0,\s*#0x1",
    0x164ec:r"movt\s+r0,\s*#0x7f10",
    0x164f0:r"str\.w\s+r0,\s*\[r4,\s*#0x3dc\]"}),
  ("parameter setter",0x19488,0x194b0,{
    0x194a2:r"ldr\s+r0,\s*\[r5,\s*#0xc\]",
    0x194a4:r"str\s+r0,\s*\[r4,\s*#0x20\]",
    0x194a6:r"ldr\s+r1,\s*\[r5,\s*#0x10\]",
    0x194a8:r"str\s+r1,\s*\[r4,\s*#0x24\]"}),
 ],
 "libOmxVideo.so":[
  ("Dolby access",0x30948,0x3096e,{
    0x30956:r"ldr\s+r1,\s*\[r0,\s*#0x4\]",
    0x30958:r"ldr\s+r2,\s*\[r1,\s*#0x20\]",
    0x3095a:r"cmp\.w\s+r2,\s*#0x400",
    0x30960:r"ldr\.w\s+r1,\s*\[r1,\s*#0x3dc\]"}),
  ("legacy dual-layer gate",0x21ac4,0x21ad4,{
    0x21ac8:r"ldr\s+r0,\s*\[r0,\s*#0x20\]",
    0x21aca:r"cmp\s+r0,\s*#0x10"}),
 ],
}
LINE = re.compile(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][\w.]*)\s*(.*)")
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path,help="directory holding all three vendor .so files")
    args=p.parse_args()
    od=shutil.which("llvm-objdump")
    if not od: p.error("llvm-objdump is required")
    for name, digest in SHA.items():
        f=args.directory/name
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=digest:
            print("UNSUPPORTED_BINARY "+str(f),file=sys.stderr)
            return 2
        print("PINNED_SHA_PASS "+name)
    b=(args.directory/"libomx_framework_alt.so").read_bytes()
    table=0x18e4a
    target=table+2*struct.unpack_from("<H",b,table+11*2)[0]
    if target!=0x19488:
        print("DISPATCH_FAIL "+hex(target),file=sys.stderr);return 1
    print("VENDOR_INDEX_DISPATCH_PASS 0x7f00010d -> 0x19488")
    for pos, suffix in [(0x28170,b".dvhe\x00"),(0x28189,b".dav1\x00")]:
        if b[pos:pos+len(suffix)]!=suffix:
            print("SUFFIX_FAIL "+hex(pos),file=sys.stderr);return 1
    print("CODEC_SUFFIX_LITERAL_PASS")
    failed=0
    for name,groups in CHECKS.items():
        for title,start,stop,checks in groups:
            out=subprocess.check_output([od,"-d","--triple=thumbv7a-linux-android",
              f"--start-address=0x{start:x}",f"--stop-address=0x{stop:x}",
              str(args.directory/name)],text=True)
            ins={}
            for line in out.splitlines():
                m=LINE.match(line)
                if m:ins[int(m[1],16)]=m[2]+" "+m[3]
            for address,pat in checks.items():
                if not re.search(pat,ins.get(address,"")):
                    print(f"FAIL {title} 0x{address:x}: {ins.get(address)}",file=sys.stderr)
                    failed+=1
            print(title+": "+("PASS" if all(re.search(pat,ins.get(a,"")) for a,pat in checks.items()) else "FAIL"))
    if failed:return 1
    print("OMX_PEER_OWNER_DATAFLOW_PASS")
    print("Static only: runtime values, EL path and true FEL output remain unverified.")
    return 0
if __name__=="__main__":sys.exit(main())
