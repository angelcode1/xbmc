#!/usr/bin/env python3
"""Stage 39: original Fire OS HEVC instance-provider name selection, offline only.

Read-only checks of owner SHA-pinned module archive, DWARF, original relocations,
and bounded ARM64 code. Does not call kernel functions, ADB, or change settings.
"""
import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ARCHIVE_SHA = '02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44'
MODULES = {
    'amvdec_h265.ko': ('0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040', 1341624),
    'decoder_common.ko': ('a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b', 4015344),
}
PREFIX = 'gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_'
NAMES = {
    'dveldec2': 0x6c4,
    'dvbldec': 0xa9d,
    'dvbldec2': 0x1f3c,
    'dveldec': 0x2eff,
    'decoder.h265': 0x2c2d,
    'vdec.h265.%02x': 0x1539,
}
GATES = {
    0x106c:'mov w8, #0xc98', 0x1070:'movk w8, #0x1, lsl #16',
    0x1080:'mov w1, #0x10', 0x1084:'bl 0x1084',
    0x108c:'mov w8, #0x38b0', 0x1090:'movk w8, #0x1, lsl #16',
    0x1094:'adrp x9, 0x1000', 0x1098:'add x8, x20, x8',
    0x109c:'ldrb w10, [x8]', 0x10a0:'ldr w9, [x9]',
    0x10a4:'ldr x8, [x20, #0x38]',
    0x10a8:'mov w11, #0xc98', 0x10ac:'movk w11, #0x1, lsl #16',
    0x10b0:'add x0, x20, x11', 0x10b4:'cbz w10, 0x124c',
    0x10b8:'adrp x10, 0x1000', 0x10bc:'adrp x11, 0x1000',
    0x10c0:'add x10, x10, #0x0', 0x10c4:'add x11, x11, #0x0',
    0x10c8:'cbz w9, 0x1260', 0x10cc:'cmp x8, #0x0',
    0x10d0:'csel x2, x11, x10, ne', 0x10d4:'b 0x1268',
    0x124c:'adrp x10, 0x1000', 0x1250:'adrp x11, 0x1000',
    0x1254:'add x10, x10, #0x0', 0x1258:'add x11, x11, #0x0',
    0x125c:'cbnz w9, 0x10cc', 0x1260:'cmp x8, #0x0',
    0x1264:'csel x2, x10, x11, ne', 0x1268:'mov w1, #0x10',
    0x126c:'bl 0x126c',
    0x1270:'ldr x8, [x20, #0x38]', 0x1274:'cmp x8, #0x0',
    0x1278:'cset w8, ne', 0x127c:'strb w8, [x19, #0x7b1]',
    0x1100:'adrp x2, 0x1000', 0x1104:'add x0, x20, x8',
    0x1108:'add x2, x2, #0x0', 0x1114:'bl 0x1114',
    0x3ba8:'adrp x1, 0x3000', 0x3bb0:'add x1, x1, #0x0',
    0x3bc0:'bl 0x3bc0', 0x3bc8:'bl 0x3bc8',
}
LINE = re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)

def cmd(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def normalize(s):
    return re.sub(r'\s+','',s.split(' //',1)[0].split(' <',1)[0])

def naming(stream_multi, master_present, toggle):
    """Synthetic branch oracle, NOT a runtime observation or driver execution."""
    if not all(type(x) is bool for x in (stream_multi,master_present,toggle)):
        raise ValueError('not bool')
    root = 'dveldec' if (master_present != toggle) else 'dvbldec'
    return root + ('2' if stream_multi else '')

def read_archive(path):
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=ARCHIVE_SHA:
        raise ValueError('original owner archive SHA invalid/missing')
    modules={}
    with zipfile.ZipFile(path) as z:
        for name,(digest,length) in MODULES.items():
            full=PREFIX+name
            infos=[i for i in z.infolist() if i.filename==full and not i.is_dir()]
            if len(infos)!=1 or infos[0].file_size!=length:raise ValueError('archive module inventory mismatch '+name)
            b=z.read(infos[0])
            if hashlib.sha256(b).hexdigest()!=digest or b[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(b[18:20],'little')!=183:
                raise ValueError('wrong original ELF module '+name)
            modules[name]=b
    return modules

def dwarf_field(text,name,off):
    for m in re.finditer(r'DW_TAG_member\)',text):
        part=text[m.end():m.end()+750]
        boundary=re.search(r'\n\s*<\d+><[0-9a-f]+>:\s+Abbrev Number:',part)
        if boundary:part=part[:boundary.start()]
        if re.search(r'DW_AT_name\s*:.*:\s*'+re.escape(name)+r'\s*$',part,re.M) and re.search(
          r'DW_AT_data_member_location\s*:\s*(?:0x%x|%d)\s*$'%(off,off),part,re.M):
            return True
    return False

def check_reloc(reloc,at,kind,section,offset):
    target=r'^\s*%016x\s+\S+\s+%s\s+\S+\s+%s \+ %x\s*$'%(at,kind,re.escape(section),offset)
    if not re.search(target,reloc,re.M):
        raise ValueError('original relocation mismatch 0x%x %s + 0x%x'%(at,section,offset))

def audit(archive):
    modules=read_archive(archive)
    print('GAZELLE_STAGE39_OWNER_ARCHIVE_SHA_PASS')
    with tempfile.TemporaryDirectory(prefix='gazelle-stage39-original-') as temp:
        paths={}
        for name,blob in modules.items():
            p=Path(temp)/name;p.write_bytes(blob);paths[name]=p
            print('PINNED_ORIGINAL_ELF_PASS',name)
        h=paths['amvdec_h265.ko'];k=paths['decoder_common.ko']
        dwarf=cmd('readelf','-wi',str(h))
        common=cmd('readelf','-wi',str(k))
        if not dwarf_field(dwarf,'is_stream_mode_dv_multi',0x138b0):
            raise ValueError('original HEVC named stream-mode flag DWARF mismatch')
        if not dwarf_field(common,'master',0x38):
            raise ValueError('original vdec_s.master DWARF mismatch')
        print('ORIGINAL_NAMED_FIELDS_PASS is_stream_mode_dv_multi_0x138b0 master_0x38')
        symbols=cmd('readelf','-Ws',str(h))
        if not re.search(r'^\s*\d+:\s*0000000000000090\s+4\s+OBJECT\s+LOCAL\s+DEFAULT\s+5\s+dv_toggle_prov_name\s*$',symbols,re.M):
            raise ValueError('module selector symbol dv_toggle_prov_name differs')
        print('ORIGINAL_NAMED_SELECTOR_PASS dv_toggle_prov_name_bss_0x90')
        data=modules['amvdec_h265.ko']
        hdr=cmd('readelf','-SW',str(h))
        line=next((x for x in hdr.splitlines() if re.search(r'\[\s*7\]\s+\.rodata\s+PROGBITS',x)),None)
        mm=re.search(r'\.rodata\s+PROGBITS\s+\S+\s+(\S+)\s+(\S+)',line or '')
        if not mm or int(mm.group(2),16)!=0x3f9c:raise ValueError('original rodata section mismatch')
        rodata_start=int(mm.group(1),16)
        for name,off in NAMES.items():
            val=data[rodata_start+off:rodata_start+off+len(name)+1]
            if val!=name.encode('ascii')+b'\0':raise ValueError('provider literal mismatch '+name)
            print('ORIGINAL_PROVIDER_LITERAL_PASS',name,'rodata=0x%x'%off)
        reloc=cmd('readelf','-rW',str(h))
        for at,kind,off in ((0x10b8,'R_AARCH64_ADR_PREL_PG_HI21',0x6c4),
                            (0x10bc,'R_AARCH64_ADR_PREL_PG_HI21',0x1f3c),
                            (0x10c0,'R_AARCH64_ADD_ABS_LO12_NC',0x6c4),
                            (0x10c4,'R_AARCH64_ADD_ABS_LO12_NC',0x1f3c),
                            (0x124c,'R_AARCH64_ADR_PREL_PG_HI21',0x2eff),
                            (0x1250,'R_AARCH64_ADR_PREL_PG_HI21',0xa9d),
                            (0x1254,'R_AARCH64_ADD_ABS_LO12_NC',0x2eff),
                            (0x1258,'R_AARCH64_ADD_ABS_LO12_NC',0xa9d)):
            check_reloc(reloc,at,kind,'.rodata',off)
        for at,kind,section,off in ((0x1094,'R_AARCH64_ADR_PREL_PG_HI21','.bss',0x90),
                                     (0x1074,'R_AARCH64_ADR_PREL_PG_HI21','.rodata',0x1539),
                                     (0x107c,'R_AARCH64_ADD_ABS_LO12_NC','.rodata',0x1539),
                                     (0x3ba8,'R_AARCH64_ADR_PREL_PG_HI21','.rodata',0x2c2d),
                                     (0x3bb0,'R_AARCH64_ADD_ABS_LO12_NC','.rodata',0x2c2d)):
            check_reloc(reloc,at,kind,section,off)
        for at,symbol in ((0x1084,'snprintf'),(0x126c,'snprintf'),
                          (0x1114,'vf_provider_init'),(0x3bc0,'vf_provider_init'),
                          (0x3bc8,'vf_reg_provider')):
            check_reloc(reloc,at,'R_AARCH64_CALL26',symbol,0)
        ins={}
        for line in cmd('llvm-objdump','-d','--section=.text','--no-show-raw-insn',str(h)).splitlines():
            m=LINE.match(line)
            if m:ins[int(m[1],16)]=m[2]+' '+m[3]
        for addr,op in GATES.items():
            if normalize(ins.get(addr,''))!=normalize(op):
                raise ValueError('original instruction mismatch 0x%x: %s'%(addr,ins.get(addr)))
        print('GAZELLE_FEL_STAGE39_ORIGINAL_GATES_PASS instructions=%d literals=%d relocations=18 fields=2 modules=2'%(len(GATES),len(NAMES)))
        for multi in (False,True):
            for toggle in (False,True):
                for master in (False,True):
                    print('PROVIDER_NAME_RULE stream_mode_dv_multi=%d toggle_prov_name=%d master_present=%d selected=%s'%(
                        multi,toggle,master,naming(multi,master,toggle)))
        print('HEVC_NAMING_RELATION=dvbldec_and_dveldec_ARE_ORIGINAL_INSTANCE_CHOICES')
        print('GENERIC_DECODER_H265=SEPARATE_COMPILED_PROVIDER_INIT_PATH')
        print('RUNTIME_P7_INSTANCE_FLAGS_AND_TOGGLE=NOT_MEASURED')
        print('P7_LIVE_PROVIDER=dvbldec_OBSERVED_IN_STAGE38')
        print('P7_EL_SLAVE=NOT_PROVEN')
        print('P7_DOLBY_AUX_PAYLOAD=NOT_MEASURED')
        print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
        print('GAZELLE_FEL_STAGE39_OFFLINE_PASS')

def selftest():
    assert len(GATES)==44 and len(NAMES)==6
    assert naming(False,False,False)=='dvbldec'
    assert naming(False,True,False)=='dveldec'
    assert naming(False,False,True)=='dveldec'
    assert naming(False,True,True)=='dvbldec'
    assert naming(True,False,False)=='dvbldec2'
    assert naming(True,True,False)=='dveldec2'
    assert naming(True,False,True)=='dveldec2'
    assert naming(True,True,True)=='dvbldec2'
    print('GAZELLE_FEL_STAGE39_SOURCE_SELFTEST_PASS')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('original_archive',nargs='?',type=Path)
    p.add_argument('--selftest',action='store_true')
    a=p.parse_args();selftest()
    if a.selftest:return
    if not a.original_archive:p.error('provide owner original kernel ZIP')
    audit(a.original_archive.expanduser().resolve())

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,zipfile.BadZipFile,subprocess.CalledProcessError,AssertionError) as e:
        print('GAZELLE_FEL_STAGE39_FAIL',e,file=sys.stderr)
        sys.exit(1)
