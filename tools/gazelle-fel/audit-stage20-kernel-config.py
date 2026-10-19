#!/usr/bin/env python3
"""Offline, read-only, SHA-pinned Stage 20 Fire OS kernel config audit.

No ADB, no device commands, no kernel/ELF changes. Checks exact ARM64/DWARF
evidence, not actual P7 FEL reconstruction or active slave configuration.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PINS = {
 "stream_input": ("vendor_lib_modules_stream_input.ko", "fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c"),
 "decoder_common": ("vendor_lib_modules_decoder_common.ko", "a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b"),
 "amvdec_h265": ("vendor_lib_modules_amvdec_h265.ko", "0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040"),
}
# Exact original ARM64 instruction words represented by semantic mnemonic patterns.
GATES = {
 "stream_input": {
  0x29f0:r"mov\s+w2,\s*#0x10\b",
  0x2a14:r"cmp\s+w8,\s*#0x301\b",
  0x2a18:r"b\.eq\s+0x2c64",
  0x2c64:r"ldrb\s+w8,\s*\[x23,\s*#0x18\]",
  0x2c68:r"tbz\s+w8,\s*#0x0,\s*0x255c",
  0x2c6c:r"ldr\s+x19,\s*\[sp,\s*#0x18\]",
  0x2c70:r"cbz\s+x19,\s*0x255c",
  0x2c74:r"ldr\s+w21,\s*\[sp,\s*#0x24\]",
  0x2c78:r"sub\s+w8,\s*w21,\s*#0x1\b",
  0x2c7c:r"cmp\s+w8,\s*#0xfff\b",
  0x2c80:r"b\.hi\s+0x255c",
  0x2c88:r"mov\s+w9,\s*#0xdb1\b",
  0x2c8c:r"movk\s+w9,\s*#0x1,\s*lsl\s*#16",
  0x2c94:r"add\s+x22,\s*x8,\s*x9",
  0x2ca0:r"bl\s+0x2ca0",
  0x2cb0:r"bl\s+0x2cb0",
  0x2cb4:r"cbnz\s+x0,\s*0x255c",
  0x2cc0:r"mov\s+w10,\s*#0x1db4\b",
  0x2cc4:r"movk\s+w10,\s*#0x1,\s*lsl\s*#16",
  0x2ccc:r"str\s+w8,\s*\[x9,\s*x10\]",
  0x2cd0:r"b\s+0x3494",
 },
 "amvdec_h265": {
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
 },
 "decoder_common": {
  0x2eac:r"ldr\s+x9,\s*\[x19,\s*#0x38\]",
  0x2ecc:r"ldr\s+x8,\s*\[x19,\s*#0x40\]",
  0x2ed4:r"add\s+x0,\s*x8,\s*#0x50",
  0x2ed8:r"mov\s+w2,\s*#0xf8",
  0x2edc:r"mov\s+x1,\s*x22",
  0x2ee0:r"bl\s+0x2ee0",
 }}
CALLS = {
 "stream_input": {0x29fc:".text + 7710",0x2ca0:"__check_object_size",0x2cb0:".text + 7710",0x7814:"__arch_copy_from_user"},
 "amvdec_h265": {0xd88:"get_config_int",0xdb4:"get_config_int"},
 "decoder_common": {0x2ee0:"memcpy"},
}
LINE = re.compile(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)", re.I)

def run_cmd(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE)

def verify(folder):
    paths = {}
    for name, (filename, digest) in PINS.items():
        f = folder / filename
        if not f.is_file() or f.is_symlink():
            raise ValueError(f"missing/symlink {filename}")
        b = f.read_bytes()
        if b[:7] != b"\x7fELF\x02\x01\x01" or int.from_bytes(b[18:20], "little") != 183:
            raise ValueError(f"unsupported ARM64 ELF {filename}")
        if hashlib.sha256(b).hexdigest() != digest:
            raise ValueError(f"unsupported SHA {filename}")
        paths[name] = f
        print("PINNED_MODULE_PASS", name)
    for name, gates in GATES.items():
        lo,hi=min(gates)-32,max(gates)+32
        output = run_cmd("llvm-objdump","-d","--no-show-raw-insn",
            f"--start-address=0x{lo:x}",f"--stop-address=0x{hi:x}",str(paths[name]))
        dis = {}
        for line in output.splitlines():
            match=LINE.match(line)
            if match:dis[int(match[1],16)] = match[2]+" "+match[3]
        for addr,pattern in gates.items():
            if not re.search(pattern,dis.get(addr,"")):
                raise ValueError(f"unexpected {name} instruction 0x{addr:x}: {dis.get(addr)}")
        reloc=run_cmd("readelf","-rW",str(paths[name]))
        for addr,target in CALLS[name].items():
            pattern=rf"^\s*{addr:016x}\s+\S+\s+R_AARCH64_CALL26\s+\S+\s+{re.escape(target)}(?:\s|$)"
            if not re.search(pattern,reloc,re.M):
                raise ValueError(f"unexpected relocation {name} 0x{addr:x}: {target}")
        print("ARM64_GATE_PASS",name,len(gates),"relocations",len(CALLS[name]))
    dwarf=run_cmd("readelf","--debug-dump=info",str(paths["stream_input"]))
    for key,off in (("config","0x10db1"),("config_len","0x11db4"),
                    ("dolby_meta_with_el","0x11db9")):
        pattern=r"DW_AT_name[^\n]*:\s*"+re.escape(key)+r"\s*\n(?:[^\n]*\n){1,8}?[^\n]*DW_AT_data_member_location:\s*"+off+r"\b"
        if not re.search(pattern,dwarf):
            raise ValueError(f"missing DWARF member {key} {off}")
    if not re.search(r"<1><cc86>: Abbrev Number: .*\(DW_TAG_array_type\).*?DW_AT_count\s*:\s*4096",dwarf,re.S):
        raise ValueError("missing original char[4096] DWARF type")
    hevc_rel=run_cmd("readelf","-rW",str(paths["amvdec_h265"]))
    parsers=sum(1 for line in hevc_rel.splitlines()
                if "R_AARCH64_CALL26" in line and "get_config_int" in line
                and 0xd88 <= int(line.split()[0],16) <= 0x100c)
    if parsers!=16:raise ValueError(f"unexpected HEVC parser count {parsers}")
    print("DWARF_KERNEL_CONFIG_PASS size=4096 offset=0x10db1 len=0x11db4")
    print("HEVC_INSTANCE_PARSER_PASS get_config_int_calls=16")
    print("KERNEL_0x301_VALID_LENGTH=1..4096")
    print("INITIAL_MASTER_TO_SLAVE_COPY=0xf8_BYTES_NOT_CONFIG")
    print("OTHER_SLAVE_CONFIG_PATHS=UNRESOLVED")
    print("ACTIVE_FEL_RESIDUAL=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE20_KERNEL_CONFIG_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("module_dir",type=Path,nargs="?")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        assert len(PINS)==3 and sum(len(g) for g in GATES.values())==37
        assert sum(len(g) for g in CALLS.values())==7
        assert 0x11db4-0x10db1==4099
        print("GAZELLE_STAGE20_SOURCE_SELFTEST_PASS")
    elif a.module_dir:
        verify(a.module_dir.expanduser().resolve())
    else:p.error("module directory or --selftest required")

if __name__=="__main__":
    try: main()
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        print("GAZELLE_STAGE20_AUDIT_FAIL",e,file=sys.stderr)
        sys.exit(1)
