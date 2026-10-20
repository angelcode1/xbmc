#!/usr/bin/env python3
"""Gazelle FEL Stage 37: SHA-pinned original HEVC provider/Dolby registration audit.

Host only. Reads owner's original kernel ZIP, executes no ELF, ADB or device IO.
"""
import argparse,hashlib,pathlib,re,subprocess,sys,tempfile,zipfile
SHA={"amvdec_h265.ko":"0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040",
     "dovi_vs12.ko":"7c59782906328a9a524719ac0df18ea5d6395d901ca035e3ad7cfed7a9025224"}
ZIP_SHA="02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44"
PREFIX="gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_"
SIZES={"amvdec_h265.ko":1341624,"dovi_vs12.ko":2165616}
SLOTS={0x3ba0:0x15608,0x3ba8:0x7b58,0x3bb0:0x4ef8,0x3bb8:0x15708,0x3bc0:0x15938}
SYMS={"amvdec_h265.ko":{"vh265_vf_provider":(0x3ba0,40),
                         "vh265_vf_prov":(0x308,64),
                         "vh265_event_cb":(0x15708,560),
                         "vh265_init":(0x3818,1472)},
      "dovi_vs12.ko":{"DV_func":(0x18,96),
                       "metadata_parser_process":(0x28b98,444)}}
OPS={0x3b98:"ldrb w8, [x24, #0x244]",0x3b9c:"cbnz w8, 0x3c94",
     0x3ba0:"adrp x22, 0x3000",0x3bb8:"mov x0, x22",
     0x3bbc:"mov x3, x21",0x3bc0:"bl 0x3bc0",
     0x3bc4:"mov x0, x22",0x3bc8:"bl 0x3bc8",
     0x15748:"tbnz w21, #0x7, 0x1576c",
     0x1579c:"ldrb w22, [x4]",
     0x157a0:"str xzr, [x19, #0x10]",0x157a4:"str wzr, [x19, #0x18]",
     0x157b4:"cmp w22, #0x17",0x157b8:"b.hi 0x158b4",
     0x157c0:"ldr x9, [x8, #0x2ae8]",0x157c4:"cbz x9, 0x158b4",
     0x157d0:"ldr x10, [x9, x10]",0x157dc:"str x10, [x19, #0x10]",
     0x157ec:"ldr w8, [x8, x10]",0x157f0:"str w8, [x19, #0x18]"}
OPLINE=re.compile(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$",re.I)
def call(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def norm(s):return re.sub(r"\s+","",s.split(" //",1)[0].split(" <",1)[0])
def read_pinned(path):
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=ZIP_SHA:
        raise ValueError("wrong/missing original kernel archive")
    out={}
    with zipfile.ZipFile(path) as z:
        for name,expected in SHA.items():
            records=[i for i in z.infolist() if i.filename==PREFIX+name and not i.is_dir()]
            if len(records)!=1 or records[0].file_size!=SIZES[name]:
                raise ValueError("original archive inventory mismatch: "+name)
            b=z.read(records[0])
            if hashlib.sha256(b).hexdigest()!=expected or b[:7]!=b"\x7fELF\x02\x01\x01" or int.from_bytes(b[18:20],"little")!=183:
                raise ValueError("original ELF identity mismatch: "+name)
            out[name]=b
    return out
def audit(archive):
    binaries=read_pinned(archive)
    with tempfile.TemporaryDirectory(prefix="gazelle-stage37-private-") as temp:
        paths={}
        for name,blob in binaries.items():
            f=pathlib.Path(temp)/name;f.write_bytes(blob);paths[name]=f
            print("PINNED_ORIGINAL_MODULE_PASS",name)
        for name,symbols in SYMS.items():
            data=call("readelf","-Ws",str(paths[name]))
            for symbol,(addr,size) in symbols.items():
                pattern=r"^\s*\d+:\s*%016x\s+%d\s+\w+\s+\w+\s+DEFAULT\s+\d+\s+%s\s*$"%(addr,size,re.escape(symbol))
                if not re.search(pattern,data,re.M):raise ValueError("missing exact symbol "+symbol)
                print("ORIGINAL_CALLBACK_SYMBOL_PASS",symbol)
        f=paths["amvdec_h265.ko"]
        reloc=call("readelf","-rW",str(f))
        section=re.search(r"Relocation section '\.rela\.rodata\.__param_arr_decode_frame_count'[^\n]*\n(.*?)(?=\nRelocation section|\Z)",reloc,re.S)
        if not section:raise ValueError("expected original provider callback relocation section missing")
        for pos,target in SLOTS.items():
            pattern=r"^%016x\s+\S+\s+R_AARCH64_ABS64\s+\S+\s+\.text \+ %x\s*$"%(pos,target)
            if not re.search(pattern,section.group(1),re.M):raise ValueError("provider slot 0x%x mismatch"%pos)
            print("ORIGINAL_PROVIDER_CALLBACK_SLOT_PASS 0x%x -> 0x%x"%(pos,target))
        for off,symbol in ((0x3bc0,"vf_provider_init"),(0x3bc8,"vf_reg_provider")):
            pattern=r"^%016x\s+\S+\s+R_AARCH64_CALL26\s+\S+\s+%s \+ 0\s*$"%(off,symbol)
            if not re.search(pattern,reloc,re.M):raise ValueError("provider registration relocation mismatch "+symbol)
        for off,kind,addend in ((0x3bac,"R_AARCH64_ADR_PREL_PG_HI21","3ba0"),
                                (0x3bb4,"R_AARCH64_ADD_ABS_LO12_NC","3ba0"),
                                (0x3ba8,"R_AARCH64_ADR_PREL_PG_HI21","2c2d"),
                                (0x3bb0,"R_AARCH64_ADD_ABS_LO12_NC","2c2d")):
            pattern=r"^%016x\s+\S+\s+%s\s+\S+\s+\.rodata \+ %s\s*$"%(off,kind,addend)
            if not re.search(pattern,reloc,re.M):raise ValueError("provider pointer/name wiring differs at 0x%x"%off)
        ins={}
        for row in call("llvm-objdump","-d","--section=.text","--no-show-raw-insn",str(f)).splitlines():
            m=OPLINE.match(row)
            if m:ins[int(m[1],16)]=m[2]+" "+m[3]
        for at,expected in OPS.items():
            if norm(ins.get(at,""))!=norm(expected):raise ValueError("original opcode mismatch 0x%x: %s"%(at,ins.get(at,"")))
        header=next((s for s in call("readelf","-SW",str(f)).splitlines()
                    if re.search(r"\[\s*7\]\s+\.rodata\s+PROGBITS",s)),None)
        m=re.search(r"\.rodata\s+PROGBITS\s+\S+\s+(\S+)\s+(\S+)",header or "")
        if not m or int(m[2],16)!=0x3f9c:raise ValueError("wrong original rodata section")
        origin=int(m[1],16)
        if binaries["amvdec_h265.ko"][origin+0x2c2d:origin+0x2c2d+13]!=b"decoder.h265\x00":
            raise ValueError("original HEVC provider name differs")
        dolby=call("readelf","-rW",str(paths["dovi_vs12.ko"]))
        if not re.search(r"^0{0,15}dc\s+\S+\s+R_AARCH64_CALL26\s+\S+\s+register_dv_functions \+ 0\s*$",dolby,re.M):
            raise ValueError("original Dolby function-registration import missing")
    print("GAZELLE_FEL_STAGE37_ORIGINAL_PROVIDER_BRIDGE_PASS modules=2 callback_slots=5 opcodes=20 registered_provider_calls=2")
    print("ORIGINAL_HEVC_PROVIDER_LITERAL=decoder.h265")
    print("ORIGINAL_HEVC_PROVIDER_EVENT_CALLBACK=vh265_event_cb")
    print("AUX_EVENT_BIT7=BRANCH_PRESENT_NOT_RUNTIME_INVOKED")
    print("EVENT_AUX_EXPORT=CONDITIONAL_POINTER_AND_SIZE")
    print("DOLBY_REGISTERED_FUNCTION_TABLE=MODULE_SIDE_CONFIRMED")
    print("ORIGINAL_BUILTIN_VF_DISPATCH_AND_PROVIDER_ALIAS=NOT_VERIFIED")
    print("P7_RECEIVER_REQUEST_AND_NONEMPTY_AUX=NOT_OBSERVED")
    print("P7_EL_DECODER=NOT_OBSERVED")
    print("P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE37_OFFLINE_PASS")
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_archive",type=pathlib.Path,nargs="?")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    assert len(SLOTS)==5 and SLOTS[0x3bb8]==0x15708 and len(OPS)==20
    print("GAZELLE_FEL_STAGE37_SOURCE_SELFTEST_PASS")
    if a.selftest:return
    if not a.original_archive:p.error("provide original gazelle-fel-kernel-readonly ZIP")
    audit(a.original_archive.expanduser().resolve())
if __name__=="__main__":
    try:main()
    except (OSError,ValueError,zipfile.BadZipFile,AssertionError,subprocess.CalledProcessError) as exc:
        print("GAZELLE_FEL_STAGE37_AUDIT_FAIL",exc,file=sys.stderr);sys.exit(1)
