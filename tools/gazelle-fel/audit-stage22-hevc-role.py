#!/usr/bin/env python3
"""Fail-closed, offline Fire OS HEVC paired-role and Dolby metadata audit.

Use only the original Gazelle PS7702.4965N private kernel modules. This script
does not run vendor code or perform any device I/O, sysfs writes or ioctls.
Static source findings DO NOT prove live master/slave decoding or FEL pixels.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PINS = {
    "amvdec_h265":"0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040",
    "decoder_common":"a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b",
    "stream_input":"fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c",
}
# Exact opcode/operand checks, not generic string detection.
GATES = {
0x09c4:r"ldr\s+x8,\s*\[x21,\s*#0x80\]",
0x09c8:r"ldr\s+x20,\s*\[x8\]",
0x0d44:r"ldr\s+w8,\s*\[x26,\s*#0x111c\]",
0x0d48:r"cbz\s+w8,\s*0x1024",
0x0d4c:r"mov\s+w8,\s*#0xdb1\b",
0x0d50:r"movk\s+w8,\s*#0x1,\s*lsl\s*#16",
0x0d88:r"bl\s+0xd88",
0x1024:r"ldr\s+x8,\s*\[x20,\s*#0x208\]",
0x1028:r"cbz\s+x8,\s*0x10d8",
0x103c:r"stp\s+x9,\s*x10,\s*\[x11\]",
0x1050:r"b\s+0x10e4",
0x10d8:r"mov\s+w8,\s*#0x1e\b",
0x10e4:r"ldr\s+w8,\s*\[x21\]",
0x1270:r"ldr\s+x8,\s*\[x20,\s*#0x38\]",
0x127c:r"strb\s+w8,\s*\[x19,\s*#0x7b1\]",
0x1288:r"ldr\s+x8,\s*\[x20,\s*#0x40\]",
0x12a0:r"ldr\s+w8,\s*\[x8,\s*#0xa88\]",
0x12a4:r"str\s+w8,\s*\[x19,\s*#0xa88\]",
0xdc34:r"ldr\s+x20,\s*\[x8,\s*#0x88\]",
0xdc60:r"mov\s+w8,\s*#0x1db9\b",
0xdc64:r"movk\s+w8,\s*#0x1,\s*lsl\s*#16",
0xdc68:r"ldrb\s+w8,\s*\[x20,\s*x8\]",
0xdc6c:r"cbnz\s+w8,\s*0xdc78",
0xdc70:r"ldr\s+x8,\s*\[x20,\s*#0x40\]",
0xdc74:r"cbz\s+x8,\s*0xdc9c",
0xdc78:r"ldr\s+x1,\s*\[x19,\s*#0xa28\]",
0xdc88:r"bl\s+0xdc88",
0xdc9c:r"ldr\s+x8,\s*\[x20,\s*#0x38\]",
0xdca0:r"cbz\s+x8,\s*0xdcd8",
0xdca4:r"mov\s+w9,\s*#0x1e40\b",
0xdca8:r"movk\s+w9,\s*#0x1,\s*lsl\s*#16",
0xdcac:r"ldr\s+x8,\s*\[x8,\s*x9\]",
0xdcb0:r"mov\s+w3,\s*#0x1\b",
0xdcbc:r"ldr\s+x1,\s*\[x8,\s*#0xa28\]",
0xdcc0:r"bl\s+0xdcc0",
0xdcc4:r"ldr\s+x1,\s*\[x19,\s*#0xa28\]",
0xdcc8:r"mov\s+w3,\s*#0x2\b",
0xdcd4:r"b\s+0xdc88",
0xdcd8:r"ldr\s+w8,\s*\[x20,\s*#0x150\]",
0xdce4:r"b\.ne\s+0xdc8c",
}
RELOCS = {0x0d88:"get_config_int", 0xdc88:".text + cee0",0xdcc0:".text + cee0"}
SYMS = {0x98c:"ammvdec_h265_probe",0xdc10:"dolby_get_meta",0xcee0:"set_aux_data"}
LINE = re.compile(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)",re.I)

def cmd(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def audit(folder):
    for name,expected in PINS.items():
        f=folder/("vendor_lib_modules_"+name+".ko")
        if not f.is_file() or f.is_symlink():
            raise ValueError("missing/symlink original "+str(f))
        blob=f.read_bytes()
        if blob[:7]!=b"\x7fELF\x02\x01\x01" or int.from_bytes(blob[18:20],"little")!=183:
            raise ValueError("unsupported AArch64 ELF "+str(f))
        if hashlib.sha256(blob).hexdigest()!=expected:
            raise ValueError("unsupported Amazon module SHA "+str(f))
        print("PINNED_MODULE_PASS",name)
    f=folder/"vendor_lib_modules_amvdec_h265.ko"
    text=cmd("llvm-objdump","-d","--no-show-raw-insn",
             "--start-address=0x980","--stop-address=0xdd00",str(f))
    code={}
    for line in text.splitlines():
        m=LINE.match(line)
        if m:code[int(m[1],16)]=m[2]+" "+m[3]
    for address,regex in GATES.items():
        if not re.search(regex,code.get(address,"")):
            raise ValueError("instruction changed: 0x%x %s"%(address,code.get(address)))
    reloc=cmd("readelf","-Wr",str(f))
    for address,referent in RELOCS.items():
        rows=[line for line in reloc.splitlines()
              if re.match(r"^\s*%016x\s+\S+\s+R_AARCH64_CALL26\b"%address,line)]
        if len(rows)!=1 or referent not in rows[0]:
            raise ValueError("call target differs at 0x%x"%address)
    syms=cmd("readelf","-Ws",str(f))
    for address,name in SYMS.items():
        pattern=r"^\s*\d+:\s*%016x\s+\d+\s+FUNC\s+LOCAL\s+DEFAULT\s+\d+\s+%s\s*$"%(address,name)
        if not re.search(pattern,syms,re.M):
            raise ValueError("function identity differs: "+name)
    print("HEVC_ROLE_GATES_PASS",len(GATES),"relocations",len(RELOCS))
    print("ZERO_CONFIG=probe_continues_without_get_config_int")
    print("METADATA=distinct_current_slave_and_master_buffer_branches")
    print("SLAVE_CONFIGURATION_AT_RUNTIME=UNKNOWN")
    print("P7_FEL_RESIDUAL=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE22_HEVC_ROLE_SOURCE_AUDIT_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("module_dir",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        assert len(PINS)==3 and len(GATES)==40
        assert set(RELOCS)=={0xd88,0xdc88,0xdcc0}
        print("GAZELLE_FEL_STAGE22_SOURCE_SELFTEST_PASS")
    elif a.module_dir:audit(a.module_dir.expanduser().resolve())
    else:p.error("pass original kernel module directory or --selftest")
if __name__=="__main__":
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        print("GAZELLE_STAGE22_AUDIT_FAIL",error,file=sys.stderr)
        sys.exit(1)
