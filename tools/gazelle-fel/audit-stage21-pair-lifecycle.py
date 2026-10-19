#!/usr/bin/env python3
"""SHA-pinned offline Fire OS Gazelle master/slave init audit.

Static-only: no adb, sysfs, live native function calls, kernel writes, or
dynamic loading. Never assume a paired vdec or DV flag proves FEL pixels.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PIN = {
  "stream_input":"fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c",
  "decoder_common":"a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b",
  "amvdec_h265":"0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040",
}
# Exact instruction-address/operand pairs; require original hashes.
GATES = {
"decoder_common": {
 0x8a0:r"bl\s+0x8a0",0x93c:r"cbz\s+x20,\s*0x950",
 0x944:r"str\s+x20,\s*\[x19,\s*#0x38\]",0x948:r"str\s+x19,\s*\[x20,\s*#0x40\]",
 0x2ecc:r"ldr\s+x8,\s*\[x19,\s*#0x40\]",
 0x2ed0:r"cbz\s+x8,\s*0x2ee4",0x2ed4:r"add\s+x0,\s*x8,\s*#0x50",
 0x2ed8:r"mov\s+w2,\s*#0xf8",0x2edc:r"mov\s+x1,\s*x22",
 0x2ee0:r"bl\s+0x2ee0",
 0x2f88:r"ldr\s+w8,\s*\[x19,\s*#0x150\]",
 0x2fbc:r"ldrb\s+w8,\s*\[x25\]",0x2fc0:r"cbz\s+w8,\s*0x30cc",
 0x2fc8:r"mov\s+w9,\s*#0x1db9",
 0x2fcc:r"movk\s+w9,\s*#0x1,\s*lsl\s*#16",
 0x2fd0:r"strb\s+wzr,\s*\[x8,\s*x9\]",
 0x4cc:r"mov\s+w9,\s*#0x1db9",
 0x4e4:r"strb\s+w8,\s*\[x20,\s*x9\]",
},
"stream_input":{
 0x1ab4:r"ldp\s+x21,\s*x19,\s*\[x20\]",
 0x1f6c:r"mov\s+x0,\s*x23",
 0x1f88:r"bl\s+0x1f88",
 0x1f94:r"ldrb\s+w8,\s*\[x8,\s*#0x19\]",
 0x1f9c:r"bl\s+0x1f9c",
 0x1fa0:r"tbz\s+w0,\s*#0x8,\s*0x1fcc",
 0x1fa8:r"ldr\s+x0,\s*\[x23,\s*#0x40\]",
 0x1fc4:r"bl\s+0x1fc4",
 0x2c84:r"ldr\s+x8,\s*\[x20\]",
 0x2c94:r"add\s+x22,\s*x8,\s*x9",
 0x2ccc:r"str\s+w8,\s*\[x9,\s*x10\]",
 0x7454:r"bl\s+0x7454",
 0x7474:r"ldr\s+x0,\s*\[x8,\s*#0x40\]",
 0x7478:r"cbz\s+x0,\s*0x768c",
 0x7480:r"bl\s+0x7480",
},
"amvdec_h265":{
 0x9c4:r"ldr\s+x8,\s*\[x21,\s*#0x80\]",
 0x9c8:r"ldr\s+x20,\s*\[x8\]",
 0xa14:r"add\s+x26,\s*x20,\s*x8",
 0xd44:r"ldr\s+w8,\s*\[x26,\s*#0x111c\]",
 0xd48:r"cbz\s+w8,\s*0x1024",
 0xd4c:r"mov\s+w8,\s*#0xdb1",
 0xd50:r"movk\s+w8,\s*#0x1,\s*lsl\s*#16",
 0xd54:r"add\s+x21,\s*x20,\s*x8",
 0xd80:r"mov\s+x0,\s*x21",
 0xd88:r"bl\s+0xd88",
}}
RELOCS={
"decoder_common":{(0x8a0,"vzalloc"),(0x2ee0,"memcpy")},
"stream_input":{(0x1f88,"vdec_init"),(0x1fc4,"vdec_init"),
                (0x7454,"vdec_set_dv_metawithel"),(0x7480,"vdec_set_dv_metawithel")},
"amvdec_h265":{(0xd88,"get_config_int")},
}
LINE=re.compile(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)",re.I)
def run_cmd(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def verify(directory):
    total=0
    for name,sha in PIN.items():
        path=directory/("vendor_lib_modules_"+name+".ko")
        if not path.is_file() or path.is_symlink():raise ValueError("missing/symlink "+name)
        blob=path.read_bytes()
        if blob[:7]!=b"\x7fELF\x02\x01\x01" or int.from_bytes(blob[18:20],"little")!=183:
            raise ValueError("unexpected ELF64 AArch64 "+name)
        if hashlib.sha256(blob).hexdigest()!=sha:raise ValueError("unexpected SHA "+name)
        print("PINNED_MODULE_PASS",name)
        out=run_cmd("llvm-objdump","-d","--no-show-raw-insn",str(path))
        ins={}
        for line in out.splitlines():
            m=LINE.match(line)
            if m:ins[int(m[1],16)]=m[2]+" "+m[3]
        for addr,pat in GATES[name].items():
            if not re.search(pat,ins.get(addr,"")):
                raise ValueError("instruction %s 0x%x %r"%(name,addr,ins.get(addr)))
        reloc=run_cmd("readelf","-rW",str(path))
        for addr,sym in RELOCS[name]:
            pat=(r"^\s*%016x\s+\S+\s+R_AARCH64_CALL26\s+\S+\s+%s(?:\s|$)"
                 %(addr,re.escape(sym)))
            if not re.search(pat,reloc,re.M):
                raise ValueError("relocation %s 0x%x %s"%(name,addr,sym))
        total+=len(GATES[name])
        print("GATE_PASS",name,"instructions",len(GATES[name]),"relocations",len(RELOCS[name]))
    assert 0x50+0xf8==0x148<0x10db1<0x11db4<0x11db9
    print("PAIR_INITIALIZATION=PRIMARY_THEN_CONDITIONAL_SLAVE")
    print("0x301_CONFIG_COPY=AUDITED_PRIMARY_ONLY")
    print("SLAVE_STARTS_ZERO=vzalloc; 0xf8_COPY_EXCLUDES_CONFIG_AND_DV_META")
    print("HEVC_PROBE=OWN_INSTANCE_CONFIG_LEN")
    print("DV_META=CONDITIONAL_INIT_CLEAR_AND_CONDITIONAL_SLAVE_IOCTL_SET")
    print("LIVE_SLAVE_CONFIG=UNKNOWN; FEL_RESIDUAL=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE21_PAIR_LIFECYCLE_PASS instructions=%d relocations=%d"%
          (total,sum(map(len,RELOCS.values()))))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("module_dir",type=Path,nargs="?")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        assert len(PIN)==3
        assert sum(len(x) for x in GATES.values())==43
        assert sum(map(len,RELOCS.values()))==7
        assert 0x50+0xf8<0x10db1
        print("GAZELLE_STAGE21_SOURCE_SELFTEST_PASS")
    elif a.module_dir:verify(a.module_dir.expanduser().resolve())
    else:p.error("pass private module directory or --selftest")
if __name__=="__main__":
    try: main()
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print("GAZELLE_STAGE21_AUDIT_FAIL",exc,file=sys.stderr)
        sys.exit(1)
