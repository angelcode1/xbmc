#!/usr/bin/env python3
"""SHA-pinned, offline Gazelle HEVC aux DMA/consumer audit. No device I/O."""
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
# Exact original address + mnemonic + operands (no raw original bytes/ELFs).
OPCODES = """
9804 and w9, w9, #0xfffffff0
9808 and w8, w8, #0xfffffff0
980c str w9, [x19, #0x8e4]
9810 str w8, [x19, #0x8e8]
9814 add w20, w8, w9
981c add x2, x19, #0x908
9820 mov w3, #0xcc0
9824 mov x1, x20
982c bl 0x982c
9830 str x0, [x19, #0x8f0]
8a58 ldr w1, [x19, #0x908]
8a5c mov w0, #0x30d5
8a60 bl 0x8a60
8a64 ldr w8, [x19, #0x8e4]
8a68 ldr w9, [x19, #0x8e8]
8a6c mov w0, #0x30d6
8a70 lsl w8, w8, #12
8a78 orr w1, w8, w9, lsr #4
8a84 bl 0x8a84
cf64 ldr x25, [x19, #0x8f0]
cf68 tst w20, #0xff
cf74 ldr w8, [x19, #0x8e4]
cf88 lsr w8, w22, #13
cf8c and w22, w8, #0x7fff8
d058 ldrb w11, [x9, #0x1]
d07c ldrb w11, [x9, #0x1]
d084 cmp w11, #0xff
d090 cmp w12, #0x2
d098 cmp w12, #0x1
d120 add x11, x25, x9, lsl #1
d124 ldrh w13, [x11, #0x6]
d128 lsr w12, w13, #8
d144 ands w10, w21, #0xff
d1a8 strb w12, [x28, #0x4]
d1b4 ldrb w13, [x11, #0x6]
d1bc strb w13, [x26]
d1c4 ldrb w12, [x11, #0x4]
d1d0 ldrb w12, [x11, #0x2]
15738 tbnz w21, #0x5, 0x15914
15748 tbnz w21, #0x7, 0x1576c
157c0 ldr x9, [x8, #0x2ae8]
157c4 cbz x9, 0x158b4
157c8 mov w10, #0xf448
157cc movk w10, #0x1, lsl #16
157d0 ldr x10, [x9, x10]
157dc str x10, [x19, #0x10]
157e4 mov w10, #0xf450
157e8 movk w10, #0x1, lsl #16
157ec ldr w8, [x8, x10]
157f0 str w8, [x19, #0x18]
7210 mov w9, #0xf448
7214 movk w9, #0x1, lsl #16
7220 ldr x1, [x8]
7224 ldr w2, [x8, #0x8]
7228 bl 0x7228
7d5c mov w8, #0xf448
7d60 movk w8, #0x1, lsl #16
7d74 ldr x8, [x24]
d3d4 mov w9, #0xf448
d3d8 movk w9, #0x1, lsl #16
d3e0 ldr x0, [x20]
179c0 mov w24, #0xf448
179cc movk w24, #0x1, lsl #16
17a10 add x27, x20, x24
17a3c ldr x0, [x27]
3e74 ldr x8, [x19, #0x8f0]
3e80 ldr w8, [x19, #0x8e4]
3e84 ldr w9, [x19, #0x8e8]
3e88 ldr x2, [x19, #0x8f0]
3e8c ldr x3, [x19, #0x908]
3e98 bl 0x3e98
""".strip()
GATES = {int(row.split()[0],16):row.split(maxsplit=1)[1] for row in OPCODES.splitlines()}
CALLS={0x982c:"dma_alloc_attrs",0x8a60:"aml_write_dosbus",
       0x8a84:"aml_write_dosbus",0x3e98:"dma_free_attrs",
       0x7228:"decoder_do_aux_data_check"}
SYMS={(0xcee0,1080):"set_aux_data",(0x15708,560):"vh265_event_cb",
      (0x92ac,1796):"vh265_local_init"}
DWARF={"prefix_aux_size":2276,"suffix_aux_size":2280,"aux_addr":2288,
       "aux_data_buf":0x1f448,"aux_data_size":0x1f450}
LINE=re.compile(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$",re.I)

def run(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def normalized(instruction):
    return re.sub(r"\s+","",instruction.split("//",1)[0])

def check_field(dwarf,name,offset):
    members=re.findall(r"(?ms)^\s*<2><[0-9a-f]+>: Abbrev Number: \d+ \(DW_TAG_member\)(.*?)(?=^\s*<[12]><[0-9a-f]+>:)",dwarf)
    for block in members:
        n=re.search(r"DW_AT_name\s+:.*?:\s*([^\s]+)\s*$",block,re.M)
        o=re.search(r"DW_AT_data_member_location:\s*(0x[0-9a-f]+|\d+)\s*$",block,re.M)
        if n and o and n[1]==name and int(o[1],0)==offset:
            return True
    return False

def audit(folder):
    for name,sha in PINS.items():
        f=folder/("vendor_lib_modules_"+name+".ko")
        if not f.is_file() or f.is_symlink():
            raise ValueError("missing/symlink "+str(f))
        b=f.read_bytes()
        if b[:7]!=b"\x7fELF\x02\x01\x01" or int.from_bytes(b[18:20],"little")!=183:
            raise ValueError("wrong ELF/AArch64 "+str(f))
        if hashlib.sha256(b).hexdigest()!=sha:
            raise ValueError("wrong module SHA "+str(f))
        print("PINNED_MODULE_PASS",name)
    f=folder/"vendor_lib_modules_amvdec_h265.ko"
    op={}
    for line in run("llvm-objdump","-d","--no-show-raw-insn",str(f)).splitlines():
        m=LINE.match(line)
        if m:op[int(m[1],16)]=m[2]+" "+m[3]
    for addr,expected in GATES.items():
        if normalized(op.get(addr,""))!=normalized(expected):
            raise ValueError("instruction differs 0x%x: %s"%(addr,op.get(addr)))
    syms=run("readelf","-Ws",str(f))
    for (addr,size),name in SYMS.items():
        pattern=r"^\s*\d+:\s*%016x\s+%d\s+FUNC\s+LOCAL\s+DEFAULT\s+\d+\s+%s\s*$"%(addr,size,name)
        if not re.search(pattern,syms,re.M):
            raise ValueError("symbol differs "+name)
    relocs=run("readelf","-Wr",str(f))
    for addr,target in CALLS.items():
        rows=[row for row in relocs.splitlines()
              if re.match(r"^\s*%016x\s+\S+\s+R_AARCH64_CALL26\b"%addr,row)]
        if len(rows)!=1 or target not in rows[0]:
            raise ValueError("call relocation differs 0x%x"%addr)
    dwarf=run("readelf","-wi",str(f))
    for name,offset in DWARF.items():
        if not check_field(dwarf,name,offset):
            raise ValueError("DWARF field differs "+name)
    print("GAZELLE_FEL_STAGE24_GATES_PASS instructions=%d symbols=%d calls=%d dwarf_fields=%d"%(
        len(GATES),len(SYMS),len(CALLS),len(DWARF)))
    print("PRODUCER=DMA_AUX_BUFFER_REGISTERED_WITH_HEVC_HARDWARE")
    print("CONSUMER=PER_PICTURE_AUX_POINTER_AND_SIZE_EXPOSED_BY_EVENT_CALLBACK")
    print("AUX_TAG_SEMANTICS=UNKNOWN")
    print("P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE24_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("module_dir",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    assert len(PINS)==3 and len(GATES)==71 and len(CALLS)==5 and len(SYMS)==3 and len(DWARF)==5
    print("GAZELLE_FEL_STAGE24_SOURCE_SELFTEST_PASS")
    if a.selftest:return
    if a.module_dir is None:p.error("pass private original module directory or --selftest")
    audit(a.module_dir.expanduser().resolve())

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError,AssertionError) as exc:
        print("GAZELLE_FEL_STAGE24_AUDIT_FAIL",exc,file=sys.stderr)
        sys.exit(1)
