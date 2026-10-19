#!/usr/bin/env python3
"""SHA-pinned, offline Dolby HEVC aux-data role audit for original Gazelle modules.

Owner-provided binaries only. No device access, vendor execution or configuration
changes. Auxiliary metadata routing does not prove Profile 7 FEL reconstruction.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

PINS={
 'amvdec_h265':'0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040',
 'decoder_common':'a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b',
 'stream_input':'fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c',
}
# Exact instruction VA and operand checks, not vendor disassembly distribution.
GATES={
0xcee0:r'sub\s+sp,\s*sp,\s*#0x70',
0xcf04:r'mov\s+w21,\s*w3',
0xcf08:r'mov\s+w20,\s*w2',
0xcf0c:r'mov\s+x23,\s*x1',
0xcf20:r'cbz\s+x23,\s*0xd01c',
0xcf30:r'cbz\s+w0,\s*0xd01c',
0xcf40:r'b\.eq\s+0xd01c',
0xcf64:r'ldr\s+x25,\s*\[x19,\s*#0x8f0\]',
0xcf68:r'tst\s+w20,\s*#0xff',
0xcf6c:r'add\s+x24,\s*x23,\s*x8',
0xcf70:r'b\.eq\s+0xcf88',
0xcf74:r'ldr\s+w8,\s*\[x19,\s*#0x8e4\]',
0xcf7c:r'add\s+x25,\s*x25,\s*x8',
0xcf88:r'lsr\s+w8,\s*w22,\s*#13',
0xcf8c:r'and\s+w22,\s*w8,\s*#0x7fff8',
0xcf98:r'ldrb\s+w9,\s*\[x27\]',
0xcff4:r'cmp\s+w22,\s*w26',
0xcff8:r'b\.ls\s+0xd040',
0xd040:r'cbz\s+w22,\s*0xd01c',
0xd044:r'cmp\s+w26,\s*#0x1',
0xd058:r'ldrb\s+w11,\s*\[x9,\s*#0x1\]',
0xd084:r'cmp\s+w11,\s*#0xff',
0xd08c:r'and\s+w12,\s*w21,\s*#0xff',
0xd090:r'cmp\s+w12,\s*#0x2',
0xd094:r'b\.eq\s+0xd064',
0xd098:r'cmp\s+w12,\s*#0x1',
0xd09c:r'b\.eq\s+0xd0ac',
0xd0a0:r'cbnz\s+w12,\s*0xd070',
0xd0a4:r'add\s+w8,\s*w8,\s*#0x8',
0xd0b0:r'cmp\s+w11,\s*#0x1',
0xd0c0:r'add\s+w8,\s*w8,\s*w22',
0xd0c4:r'add\s+w8,\s*w8,\s*w9',
0xd0cc:r'bl\s+0xd0cc',
0xd0d0:r'cbz\s+x0,\s*0xd2d4',
0xd0d8:r'ldr\s+x1,\s*\[x24\]',
0xd0f0:r'bl\s+0xd0f0',
0xd0f8:r'bl\s+0xd0f8',
0xd108:r'str\s+x23,\s*\[x24\]',
0xd120:r'add\s+x11,\s*x25,\s*x9,\s*lsl\s*#1',
0xd124:r'ldrh\s+w13,\s*\[x11,\s*#0x6\]',
0xd128:r'lsr\s+w12,\s*w13,\s*#8',
0xd130:r'cmp\s+w12,\s*#0xff',
0xd144:r'ands\s+w10,\s*w21,\s*#0xff',
0xd148:r'b\.eq\s+0xd164',
0xd14c:r'cmp\s+w10,\s*#0x2',
0xd150:r'b\.eq\s+0xd1e8',
0xd154:r'cmp\s+w10,\s*#0x1',
0xd15c:r'cmp\s+w12,\s*#0x1',
0xd1a8:r'strb\s+w12,\s*\[x28,\s*#0x4\]',
0xd1d8:r'ldrh\s+w11,\s*\[x11\]',
0xd1e8:r'cmp\s+w12,\s*#0x1',
0xd1ec:r'b\.eq\s+0xd110',
0xd1fc:r'ldr\s+w9,\s*\[x24,\s*#0x8\]',
0xd214:r'str\s+w9,\s*\[x24,\s*#0x8\]',
0xd2e8:r'ldr\s+x0,\s*\[x24\]',
0xd2f0:r'bl\s+0xd2f0',
0xd2f4:r'str\s+xzr,\s*\[x24\]',
0xd2f8:r'str\s+wzr,\s*\[x24,\s*#0x8\]',
0xdc68:r'ldrb\s+w8,\s*\[x20,\s*x8\]',
0xdc6c:r'cbnz\s+w8,\s*0xdc78',
0xdc70:r'ldr\s+x8,\s*\[x20,\s*#0x40\]',
0xdc74:r'cbz\s+x8,\s*0xdc9c',
0xdc78:r'ldr\s+x1,\s*\[x19,\s*#0xa28\]',
0xdc80:r'mov\s+w2,\s*wzr',
0xdc84:r'mov\s+w3,\s*wzr',
0xdc88:r'bl\s+0xdc88',
0xdc9c:r'ldr\s+x8,\s*\[x20,\s*#0x38\]',
0xdcbc:r'ldr\s+x1,\s*\[x8,\s*#0xa28\]',
0xdcb0:r'mov\s+w3,\s*#0x1',
0xdcc0:r'bl\s+0xdcc0',
0xdcc4:r'ldr\s+x1,\s*\[x19,\s*#0xa28\]',
0xdcc8:r'mov\s+w3,\s*#0x2',
0xdcd4:r'b\s+0xdc88',
}
RELOCS={0xcf1c:'aml_read_dosbus',0xcf2c:'aml_read_dosbus',
        0xd0cc:'vzalloc',0xd0f0:'memcpy',0xd0f8:'vfree',
        0xd2f0:'vfree',0xdc88:'.text + cee0',0xdcc0:'.text + cee0'}
SYMS={(0xcee0,1080):'set_aux_data',(0xdc10,232):'dolby_get_meta'}
LINE=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)',re.I)

def command(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def include_tag(mode,tag):
    """Synthetic model of the verified selector; not vendor code."""
    if tag in (0,255): return False
    if mode==0: return True
    if mode==1: return tag==1
    if mode==2: return tag!=1
    return False

def selftest():
    tags=[0,1,2,255,3,1]
    assert [[t for t in tags if include_tag(m,t)] for m in (0,1,2,3)]==[
        [1,2,3,1],[1,1],[2,3],[]]
    for t in range(256):
        assert include_tag(0,t)==(include_tag(1,t) or include_tag(2,t))
        assert not(include_tag(1,t) and include_tag(2,t))
    assert len(PINS)==3 and len(GATES)==73 and len(SYMS)==2 and len(RELOCS)==8
    print('GAZELLE_FEL_STAGE23_SELECTOR_SELFTEST_PASS')

def audit(folder):
    for name,expected in PINS.items():
        f=folder/('vendor_lib_modules_'+name+'.ko')
        if not f.is_file() or f.is_symlink(): raise ValueError('missing/symlink '+str(f))
        blob=f.read_bytes()
        if blob[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(blob[18:20],'little')!=183:
            raise ValueError('not ELF64 AArch64 '+str(f))
        if hashlib.sha256(blob).hexdigest()!=expected: raise ValueError('SHA mismatch '+str(f))
        print('PINNED_MODULE_PASS',name)
    f=folder/'vendor_lib_modules_amvdec_h265.ko'
    listing=command('llvm-objdump','-d','--no-show-raw-insn',
        '--start-address=0xcee0','--stop-address=0xdcf8',str(f))
    code={}
    for line in listing.splitlines():
        m=LINE.match(line)
        if m:code[int(m[1],16)]=m[2]+' '+m[3]
    for addr,pat in GATES.items():
        if not re.search(pat,code.get(addr,'')):raise ValueError('opcode mismatch 0x%x'%addr)
    symbols=command('readelf','-Ws',str(f))
    for (va,size),name in SYMS.items():
        pat=r'^\s*\d+:\s*%016x\s+%d\s+FUNC\s+LOCAL\s+DEFAULT\s+\d+\s+%s\s*$'%(va,size,name)
        if not re.search(pat,symbols,re.M):raise ValueError('symbol/size mismatch '+name)
    reloc=command('readelf','-Wr',str(f))
    for addr,target in RELOCS.items():
        rows=[l for l in reloc.splitlines()
              if re.match(r'^\s*%016x\s+\S+\s+R_AARCH64_CALL26\b'%addr,l)]
        if len(rows)!=1 or target not in rows[0]:raise ValueError('reloc mismatch 0x%x'%addr)
    print('GAZELLE_FEL_STAGE23_STATIC_GATES_PASS instructions=%d symbols=%d calls=%d'%(
        len(GATES),len(SYMS),len(RELOCS)))
    print('AUX_MODE0=valid_tags MODE1=tag1 MODE2=valid_non1_tags')
    print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE23_AUX_DATA_OFFLINE_PASS')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('module_dir',nargs='?',type=Path)
    p.add_argument('--selftest',action='store_true')
    a=p.parse_args()
    selftest()
    if a.selftest: print('GAZELLE_FEL_STAGE23_SOURCE_SELFTEST_PASS')
    elif a.module_dir: audit(a.module_dir.expanduser().resolve())
    else:p.error('supply original module directory or --selftest')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        print('GAZELLE_FEL_STAGE23_AUDIT_FAIL',e,file=sys.stderr)
        sys.exit(1)
