#!/usr/bin/env python3
"""Offline, SHA-pinned Gazelle DOVI function-registration audit; no device operations.

DOVI parser registration is not proof of HEVC AUX consumption or FEL pixels.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PINS = {
 "amvdec_av1":"531c961700f3db34755df5471c8ac8fda4263328e5c1ccca41dc6f30be265ea3",
 "amvdec_h265":"0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040",
 "decoder_common":"a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b",
 "dovi_vs12":"7c59782906328a9a524719ac0df18ea5d6395d901ca035e3ad7cfed7a9025224",
 "firmware":"08de9242c6f65c8a05474d6344eaf5b86d8cadb71a9d91f9b61c4b051ade16e6",
 "stream_input":"fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c",
}
FIELDS = {
 "version_info":0,"metadata_parser_init":8,"metadata_parser_reset":16,
 "metadata_parser_process":24,"metadata_parser_release":32,"control_path":40,
 "tv_control_path":48,"multi_control_path":56,"multi_mp_init":64,
 "multi_mp_reset":72,"multi_mp_process":80,"multi_mp_release":88,
}
FUNCTIONS = {
 "multi_control_path":(0x387c,5460,0x50),
 "metadata_parser_init":(0x287b0,372,0x58),
 "metadata_parser_reset":(0x28b24,116,0x60),
 "metadata_parser_process":(0x28b98,444,0x68),
 "metadata_parser_release":(0x28ab8,108,0x70),
}
INSTRUCTIONS={
 ".init.text":{0xd4:"adrp x0, 0x0",0xd8:"add x0, x0, #0x0",0xdc:"bl 0xdc"},
 ".exit.text":{0x18:"bl 0x18"},
 ".text":{0x1eb3c:"mov x19, x1",0x1eb40:"mov x20, x0",
          0x1eb48:"mov w8, #0x16d8",0x1eb4c:"movk w8, #0x3, lsl #16",
          0x1eb50:"str x19, [x20, x8]"},
}
LINE=re.compile(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$",re.I)

def cmd(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def symbol(table,name,address,size,kind="FUNC"):
    pat=r"^\s*\d+:\s*%016x\s+%d\s+%s\s+GLOBAL\s+DEFAULT\s+\d+\s+%s\s*$"%(address,size,kind,re.escape(name))
    if not re.search(pat,table,re.M):raise ValueError("symbol mismatch "+name)

def reloc_section(text,section):
    m=re.search(r"(?ms)^Relocation section '\.rela\."+re.escape(section)+r"' .*?\n(.*?)(?=^Relocation section |\Z)",text)
    if not m:raise ValueError("missing relocation section "+section)
    return m[1]

def relocation(table,address,kind,target):
    rows=[l for l in table.splitlines() if re.match(r"^\s*%016x\s+"%address,l)]
    if len(rows)!=1 or not re.search(r"\b"+re.escape(kind)+r"\s+\S+\s+"+re.escape(target)+r" \+ 0\s*$",rows[0]):
        raise ValueError("relocation mismatch "+target+" "+hex(address))

def dwarf_fields(text):
    m=re.search(r"(?ms)^ <1><[0-9a-f]+>:.*?\(DW_TAG_structure_type\)\n(?:(?!^ <1><).)*?DW_AT_name\s+:.*?: dolby_vision_func_s\n(?:(?!^ <1><).)*?DW_AT_byte_size\s+: 96\n((?:(?!^ <1><).)*)",text)
    if not m:raise ValueError("missing 96-byte dolby_vision_func_s")
    found={}
    for block in re.split(r"(?=^ <2><[0-9a-f]+>: Abbrev Number: \d+ \(DW_TAG_member\))",m[1],flags=re.M):
        n=re.search(r"DW_AT_name\s+:.*?:\s*(\w+)\s*$",block,re.M)
        offset=re.search(r"DW_AT_data_member_location\s*:\s*(\d+)\s*$",block,re.M)
        if n and offset:found[n[1]]=int(offset[1])
    return found

def normalize(s):
    return re.sub(r"\s+","",s.split("//",1)[0].split(" <",1)[0])

def audit(folder):
    all_symbols={}
    for name,hash_expected in PINS.items():
        f=folder/("vendor_lib_modules_"+name+".ko")
        if not f.is_file() or f.is_symlink():raise ValueError("missing/symlink "+str(f))
        blob=f.read_bytes()
        if blob[:7]!=b"\x7fELF\x02\x01\x01" or int.from_bytes(blob[18:20],"little")!=183:
            raise ValueError("not original ELF64 AArch64 "+str(f))
        if hashlib.sha256(blob).hexdigest()!=hash_expected:
            raise ValueError("kernel module SHA mismatch "+str(f))
        all_symbols[name]=cmd("readelf","-Ws",str(f))
        print("PINNED_MODULE_PASS",name)
    f=folder/"vendor_lib_modules_dovi_vs12.ko"
    syms=all_symbols["dovi_vs12"]
    symbol(syms,"DV_func",0x18,96,"OBJECT")
    symbol(syms,"init_module",0,244)
    symbol(syms,"cleanup_module",0,40)
    symbol(syms,"register_dec_event_callback",0x1eb2c,56)
    for name,(address,size,offset) in FUNCTIONS.items():
        symbol(syms,name,address,size)
    for name in ("register_dv_functions","unregister_dv_functions"):
        if not re.search(r"^\s*\d+:\s*0+\s+0\s+NOTYPE\s+GLOBAL\s+DEFAULT\s+UND\s+"+name+r"\s*$",syms,re.M):
            raise ValueError("missing imported registration symbol "+name)
        for mod,table in all_symbols.items():
            for line in table.splitlines():
                if re.search(r"\b"+name+r"\s*$",line):
                    cols=line.split()
                    if len(cols)>=8 and cols[6]!="UND":
                        raise ValueError("external receiver unexpectedly present in "+mod)
    found=dwarf_fields(cmd("readelf","-wi",str(f)))
    for name,offset in FIELDS.items():
        if found.get(name)!=offset:raise ValueError("DWARF ABI mismatch "+name)
    relocs=cmd("readelf","-Wr",str(f))
    rt=reloc_section(relocs,"rodata.DV_func")
    for name,(_,_,offset) in FUNCTIONS.items():
        relocation(rt,offset,"R_AARCH64_ABS64",name)
    init=reloc_section(relocs,"init.text")
    relocation(init,0xd4,"R_AARCH64_ADR_PREL_PG_HI21","DV_func")
    relocation(init,0xd8,"R_AARCH64_ADD_ABS_LO12_NC","DV_func")
    relocation(init,0xdc,"R_AARCH64_CALL26","register_dv_functions")
    relocation(reloc_section(relocs,"exit.text"),0x18,"R_AARCH64_CALL26","unregister_dv_functions")
    for section,checks in INSTRUCTIONS.items():
        code={}
        for line in cmd("llvm-objdump","-d","--no-show-raw-insn",
                        "--section="+section,str(f)).splitlines():
            m=LINE.match(line)
            if m:code[int(m[1],16)]=m[2]+" "+m[3]
        for address,expected in checks.items():
            if normalize(code.get(address,""))!=normalize(expected):
                raise ValueError("opcode mismatch "+section+" "+hex(address))
    print("GAZELLE_FEL_STAGE25_GATES_PASS hashes=6 members=12 function_relocs=5 registration_relocs=4 symbols=9 opcodes=9")
    print("DOVI_KERNEL_TABLE=REGISTERED_METADATA_PARSER_AND_CONTROL_PATH_CALLBACKS")
    print("REGISTER_DV_FUNCTIONS_RESOLVER=EXTERNAL_TO_SIX_COLLECTED_MODULES")
    print("HEVC_AUX_EVENT_TO_DOVI_PARSER_CONNECTION=NOT_PROVEN")
    print("AUX_TAG_INTERPRETATION=NOT_PROVEN")
    print("P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE25_OFFLINE_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("module_dir",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    assert len(PINS)==6 and len(FIELDS)==12 and len(FUNCTIONS)==5
    assert sum(map(len,INSTRUCTIONS.values()))==9
    assert {x[2] for x in FUNCTIONS.values()}=={0x50,0x58,0x60,0x68,0x70}
    print("GAZELLE_FEL_STAGE25_SOURCE_SELFTEST_PASS")
    if args.selftest:return
    if not args.module_dir:p.error("supply original six private modules or --selftest")
    audit(args.module_dir.expanduser().resolve())

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError,AssertionError) as exc:
        print("GAZELLE_FEL_STAGE25_AUDIT_FAIL",exc,file=sys.stderr)
        sys.exit(1)
