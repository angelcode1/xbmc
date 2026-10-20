#!/usr/bin/env python3
"""Stage 33: original Amazon HEVC config-key -> private flag mapping (offline).

SHA pinned ELF64 AArch64 disassembly, original ELF relocations and NUL-delimited
.rodata: no device commands, codec execution, kernel writes or binary patches.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

SHA = '0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040'
# Original key loading instructions + paired relocations: ELF .rodata offsets.
KEYS = {
    'negative_dv':         (0xeb8, 0xebc, 0xec8, 0xed8),
    'dv_duallayer':        (0xef4, 0xef8, 0xf04, 0x2448),
    'parm_v4l_metadata_config_flag': (0xf98, 0xf9c, 0xfa8, 0x1573),
}
# Verified actual code windows for parser success, bit override and later ISR read.
# A null/zero metadata flag is NOT shown to cause P7 HDR10 output.
GATES = {
    0xec8:'bl 0xec8', 0xecc:'cbnz w0, 0xef4',
    0xed0:'ldr w8, [sp]', 0xee0:'cmp w8, #0x0',
    0xee4:'cset w8, ne', 0xeec:'strb w8, [x25, #0x25c]',
    0xf04:'bl 0xf04', 0xf08:'cbnz w0, 0xf30',
    0xf0c:'ldr w8, [sp]', 0xf1c:'cmp w8, #0x0',
    0xf20:'cset w8, ne', 0xf28:'strb w8, [x25, #0x248]',
    0xfa8:'bl 0xfa8', 0xfac:'cbnz w0, 0xffc',
    0xfb0:'ldr w9, [sp]', 0xfb4:'ubfx w10, w9, #1, #1',
    0xfb8:'and w8, w9, #0x1', 0xfbc:'str w9, [x25, #0x2c8]',
    0xfc0:'strb w10, [x25, #0x25c]',
    0xfc4:'strb w8, [x25, #0x248]',
    0xa548:'ldrb w8, [x25, #0x25c]',
    0xa54c:'cbz w8, 0xb000',
    0xc568:'strb w9, [x25, #0x25c]',
}
LINE = re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$', re.I)

def run(*cmd):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)

def normalize(s):
    return re.sub(r'\s+', '', s.split(' //',1)[0].split(' <',1)[0])

def marker(relocs,address,kind,sym,add):
    rows = [line for line in relocs.splitlines()
            if re.match(r'^\s*%016x\s+' % address, line)]
    selected = [line for line in rows
                if re.search(r'\b'+kind+r'\s+\S+\s+'+re.escape(sym)+r' \+ '+format(add,'x')+r'\s*$',line)]
    if len(selected) != 1:
        raise ValueError('relocation mismatch at 0x%x %s + %x' % (address,sym,add))

def rodata_bytes(blob,sections):
    line = next((s for s in sections.splitlines() if re.search(r'\[\s*7\]\s+\.rodata\s+PROGBITS',s)),None)
    if line is None: raise ValueError('missing expected original .rodata section')
    m = re.search(r'\.rodata\s+PROGBITS\s+[0-9a-f]+\s+([0-9a-f]+)\s+([0-9a-f]+)',line)
    if not m: raise ValueError('unreadable section header')
    at,size=(int(x,16) for x in m.groups())
    if size != 0x3f9c or len(blob) < at+size:
        raise ValueError('unexpected original .rodata section size')
    return blob[at:at+size]

def wordbits(v):
    if type(v) is not int or not 0 <= v <= 0xffffffff:
        raise ValueError('invalid synthetic unsigned config flag')
    return {'negative_dv_flag_bit':(v>>1)&1,'dv_duallayer_flag_bit':v&1}

def selftest():
    assert len(KEYS)==3 and len(GATES)==23
    assert wordbits(0)=={'negative_dv_flag_bit':0,'dv_duallayer_flag_bit':0}
    assert wordbits(1)=={'negative_dv_flag_bit':0,'dv_duallayer_flag_bit':1}
    assert wordbits(2)=={'negative_dv_flag_bit':1,'dv_duallayer_flag_bit':0}
    assert wordbits(3)=={'negative_dv_flag_bit':1,'dv_duallayer_flag_bit':1}
    print('GAZELLE_FEL_STAGE33_SOURCE_SELFTEST_PASS')

def audit(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('original kernel ELF missing/symlink')
    blob=path.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=SHA:
        raise ValueError('original Amazon HEVC module SHA mismatch')
    if blob[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(blob[18:20],'little')!=183:
        raise ValueError('not original AArch64 ELF64 little endian')
    if not shutil.which('llvm-objdump') or not shutil.which('readelf'):
        raise ValueError('llvm-objdump and readelf must be in PATH')
    relocs=run('readelf','-rW',str(path))
    section=run('readelf','-SW',str(path))
    rodata=rodata_bytes(blob,section)
    for key,(hi,lo,call,offset) in KEYS.items():
        for address,kind in ((hi,'R_AARCH64_ADR_PREL_PG_HI21'),
                             (lo,'R_AARCH64_ADD_ABS_LO12_NC')):
            marker(relocs,address,kind,'.rodata',offset)
        marker(relocs,call,'R_AARCH64_CALL26','get_config_int',0)
        raw=rodata[offset:offset+len(key)+1]
        if raw != key.encode('ascii')+b'\0':
            raise ValueError('wrong key string %s at 0x%x'%(key,offset))
        print('PINNED_HEVC_CONFIG_KEY_PASS',key,'rodata=0x%x'%offset,
              'get_config_int_call=0x%x'%call)
    dis={}
    for lo,hi in ((0xeb8,0xfcc),(0xa548,0xa550),(0xc568,0xc56c)):
        txt=run('llvm-objdump','-d','--section=.text','--no-show-raw-insn',
                '--start-address=0x%x'%lo,'--stop-address=0x%x'%hi,str(path))
        for line in txt.splitlines():
            m=LINE.match(line)
            if m:dis[int(m[1],16)]=m[2]+' '+m[3]
    for at,expected in GATES.items():
        if normalize(dis.get(at,''))!=normalize(expected):
            raise ValueError('original instruction mismatch 0x%x: %s'%(at,dis.get(at)))
    print('HEVC_CONFIG_INSTRUCTION_GATES_PASS count=%d'%len(GATES))
    print('HEVC_CONFIG_KEY_RELOCATIONS_PASS count=9')
    print('NEGATIVE_DV_CONFIG_SUCCESS_WRITES=private_HEVC_plus_0x25c')
    print('DV_DUALLAYER_CONFIG_SUCCESS_WRITES=private_HEVC_plus_0x248')
    print('METADATA_CONFIG_PRESENT_OVERRIDES=negative_dv_bit1,dv_duallayer_bit0')
    print('NEGATIVE_DV_FLAG_LATER_READ=vh265_isr_thread_fn_0xa548')
    print('NEGATIVE_DV_FLAG_LATER_WRITE=vh265_isr_thread_fn_0xc568')
    print('P7_RUNTIME_CONFIG_VALUES=NOT_OBSERVED')
    print('P7_HDR10_ROOT_CAUSE=NOT_PROVEN')
    print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE33_ORIGINAL_HEVC_OFFLINE_PASS')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('module_file',type=Path,nargs='?')
    p.add_argument('--selftest',action='store_true')
    a=p.parse_args()
    selftest()
    if a.selftest:return
    if not a.module_file:p.error('provide original amvdec_h265.ko or --selftest')
    audit(a.module_file.expanduser().resolve())

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,AssertionError,subprocess.CalledProcessError) as exc:
        print('GAZELLE_FEL_STAGE33_OFFLINE_FAIL',exc,file=sys.stderr)
        sys.exit(1)
