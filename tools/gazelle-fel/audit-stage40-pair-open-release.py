#!/usr/bin/env python3
"""Stage40: original Amazon Fire OS HEVC frame/stream paired lifecycle audit.

Host-only SHA-pinned static ELF audit. Does not access Cube, play content,
execute vendor modules, or modify driver/OMX/stream flags.
"""
import argparse, hashlib, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

ARCHIVE_SHA = '02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44'
MEMBER_PREFIX = 'gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_'
MODULES = {
    'stream_input': ('fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c', 5239792),
    'decoder_common': ('a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b', 4015344),
}
EXPECTED_PORTS = {
    'amstream_dves_hevc': (15, 0x1911),
    'amstream_dves_hevc_frame': (17, 0x1d11),
}
FUNCTIONS = {
    'amstream_open': (0x1320, 1064),
    'amstream_release': (0x1748, 828),
    'amstream_port_init': (0x1a84, 2232),
    'vdec_create': (0x824, 476),
}
GATES = {
  'stream_input': {
    0x1600:'ldrb w8, [x24]',
    0x1604:'tbz w8, #0x0, 0x1654',
    0x1608:'mov x0, x21',
    0x160c:'mov x1, xzr',
    0x1610:'bl 0x1610',
    0x1614:'str x0, [x20]',
    0x1618:'cbz x0, 0x16bc',
    0x161c:'ldr w8, [x24]',
    0x1620:'tbnz w8, #0xa, 0x1654',
    0x1624:'mov x1, x0',
    0x1628:'tbnz w8, #0xc, 0x1638',
    0x162c:'bl 0x162c',
    0x1630:'tbz w0, #0x8, 0x1654',
    0x1634:'ldr x1, [x20]',
    0x1638:'mov x0, x21',
    0x163c:'bl 0x163c',
    0x1640:'ldr x8, [x20]',
    0x1644:'str x0, [x8, #0x40]',
    0x1648:'ldr x0, [x20]',
    0x164c:'ldr x8, [x0, #0x40]',
    0x1650:'cbz x8, 0x16d4',
    0x1694:'mov w0, wzr',
    0x16d4:'bl 0x16d4',
    0x16d8:'mov x0, x20',
    0x16dc:'str wzr, [x22]',
    0x16e0:'bl 0x16e0',
    0x16f0:'mov w0, #-0xc',
    0x16f4:'b 0x16a0',
    0x17f4:'ldr w0, [x23, #0x18]',
    0x17f8:'tbz w0, #0x0, 0x1824',
    0x17fc:'ldr x8, [x19]',
    0x1800:'cbz x8, 0x1824',
    0x1804:'ldr x20, [x8, #0x40]',
    0x1808:'mov x0, x8',
    0x180c:'bl 0x180c',
    0x1810:'cbz x20, 0x181c',
    0x1814:'mov x0, x20',
    0x1818:'bl 0x1818',
    0x181c:'str xzr, [x19]',
    0x18e8:'ldr x0, [x19]',
    0x18ec:'cbz x0, 0x1908',
    0x18f0:'ldr x20, [x0, #0x40]',
    0x18f4:'bl 0x18f4',
    0x18f8:'cbz x20, 0x1904',
    0x18fc:'mov x0, x20',
    0x1900:'bl 0x1900',
    0x1904:'str xzr, [x19]',
    0x1f6c:'mov x0, x23',
    0x1f88:'bl 0x1f88',
    0x1f8c:'tbnz w0, #0x1f, 0x2268',
    0x1f90:'ldr x8, [x23, #0x48]',
    0x1f94:'ldrb w8, [x8, #0x19]',
    0x1f98:'tbnz w8, #0x4, 0x1fa4',
    0x1f9c:'bl 0x1f9c',
    0x1fa0:'tbz w0, #0x8, 0x1fcc',
    0x1fa8:'ldr x0, [x23, #0x40]',
    0x1fc4:'bl 0x1fc4',
    0x1fc8:'tbnz w0, #0x1f, 0x2274',
  },
  'decoder_common': {
    0x898:'mov w0, #0x38c8',
    0x89c:'movk w0, #0x1, lsl #16',
    0x8a0:'bl 0x8a0',
    0x8a4:'mov x19, x0',
    0x8a8:'cbz x0, 0x978',
    0x93c:'cbz x20, 0x950',
    0x940:'mov w8, #0x1',
    0x944:'str x20, [x19, #0x38]',
    0x948:'str x19, [x20, #0x40]',
    0x950:'adrp x8, 0x0',
    0x9b4:'mov x0, x19',
    0x9d4:'adrp x0, 0x0',
    0x9e4:'mov x19, xzr',
    0x9e8:'b 0x9b4',
  },
}
CALLS = {
  'stream_input': {
    0x1610:'vdec_create', 0x162c:'vdec_get_debug_flags',
    0x163c:'vdec_create',0x16d4:'vdec_release',0x16e0:'kfree',
    0x180c:'vdec_release',0x1818:'vdec_release',
    0x18f4:'vdec_release',0x1900:'vdec_release',
    0x1f88:'vdec_init',0x1f9c:'vdec_get_debug_flags',
    0x1fc4:'vdec_init',
  },
  'decoder_common':{0x8a0:'vzalloc'},
}
LINE = re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)',re.I)
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def normalized(s):return re.sub(r'\s+','',s.split(' //',1)[0].split(' <',1)[0])
def open_path(port_type,debug_pair=False):
    """Synthetic representation of the verified bit precedence, not kernel execution."""
    if port_type & 0x400:return 'FRAME_SKIPS_SECOND_CREATE'
    if port_type & 0x1000 or debug_pair:return 'ATTEMPTS_SECOND_CREATE'
    return 'NO_SECOND_CREATE'
def pin_original(archive):
    if not archive.is_file() or archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_SHA:
        raise ValueError('original owner kernel archive absent or SHA mismatch')
    values={}
    with zipfile.ZipFile(archive) as z:
        for name,(digest,length) in MODULES.items():
            target=MEMBER_PREFIX+name+'.ko'
            matches=[info for info in z.infolist() if info.filename==target and not info.is_dir()]
            if len(matches)!=1 or matches[0].file_size!=length:raise ValueError('unexpected original archive member '+name)
            b=z.read(matches[0])
            if hashlib.sha256(b).hexdigest()!=digest or b[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(b[18:20],'little')!=183:
                raise ValueError('unexpected original ELF SHA/identity '+name)
            values[name]=b
    return values
def verify_port_table(binary,path):
    syms=run('readelf','-Ws',str(path))
    if not re.search(r'^\s*\d+:\s*00000000000005f0\s+1520\s+OBJECT\s+LOCAL\s+DEFAULT\s+8\s+ports\s*$',syms,re.M):
        raise ValueError('ports[] original symbol identity mismatch')
    sections=run('readelf','-SW',str(path))
    def sec(name):
        row=next((x for x in sections.splitlines() if re.search(r'\[\s*\d+\]\s+'+re.escape(name)+r'\s+PROGBITS',x)),None)
        m=re.search(re.escape(name)+r'\s+PROGBITS\s+\S+\s+(\S+)\s+(\S+)',row or '')
        if not m:raise ValueError('missing original '+name)
        return int(m[1],16),int(m[2],16)
    doff,dsize=sec('.data')
    roff,rsize=sec('.rodata')
    if dsize!=0x1710:raise ValueError('original .data size mismatch')
    reloc=run('readelf','-rW',str(path))
    section=None;table={}
    for line in reloc.splitlines():
        m=re.match(r"^Relocation section '([^']+)'",line)
        if m:section=m[1];continue
        if section!='.rela.data.userdata_mutex':continue
        m=re.match(r'^\s*([0-9a-f]+)\s+\S+\s+R_AARCH64_ABS64\s+\S+\s+\.rodata \+ ([0-9a-f]+)\s*$',line)
        if m:table[int(m[1],16)]=int(m[2],16)
    for name,(idx,type_) in EXPECTED_PORTS.items():
        base=0x5f0+idx*0x50
        ptr=table.get(base)
        if ptr is None or ptr+len(name)+1>rsize:raise ValueError('original port name pointer missing')
        if binary[roff+ptr:roff+ptr+len(name)+1]!=name.encode()+b'\0':
            raise ValueError('original port name relocation differs '+name)
        current=int.from_bytes(binary[doff+base+0x18:doff+base+0x1c],'little')
        if current!=type_:raise ValueError('original initialized port type differs '+name)
        print('PINNED_PORT_INITIAL_TYPE_PASS',name,'0x%04x'%current)
def verify_original(archive):
    binaries=pin_original(archive)
    if not shutil.which('readelf') or not shutil.which('llvm-objdump'):
        raise ValueError('install binutils readelf and LLVM objdump')
    with tempfile.TemporaryDirectory(prefix='gazelle-stage40-private-') as tmp:
        files={}
        for name,blob in binaries.items():
            p=Path(tmp)/(name+'.ko');p.write_bytes(blob);files[name]=p
            print('PINNED_ORIGINAL_ELF_PASS',name)
        verify_port_table(binaries['stream_input'],files['stream_input'])
        for name,checks in GATES.items():
            p=files[name]
            dump=run('llvm-objdump','-d','--section=.text','--no-show-raw-insn',str(p))
            ins={}
            for line in dump.splitlines():
                m=LINE.match(line)
                if m:ins[int(m[1],16)]=m[2]+' '+m[3]
            for addr,expected in checks.items():
                if normalized(ins.get(addr,''))!=normalized(expected):
                    raise ValueError('unexpected %s instruction 0x%x: %r'%(name,addr,ins.get(addr)))
            reloc=run('readelf','-rW',str(p))
            for addr,sym in CALLS[name].items():
                pattern=r'^\s*%016x\s+\S+\s+R_AARCH64_CALL26\s+\S+\s+%s \+ 0\s*$'%(addr,re.escape(sym))
                if not re.search(pattern,reloc,re.M):
                    raise ValueError('unexpected call relocation %s 0x%x %s'%(name,addr,sym))
            print('ORIGINAL_LIFECYCLE_CODE_PASS',name,'instructions=%d'%len(checks),'call_relocations=%d'%len(CALLS[name]))
        syms=run('readelf','-Ws',str(files['stream_input']))
        for name,(addr,size) in (('amstream_open',(0x1320,1064)),
                                 ('amstream_release',(0x1748,828)),
                                 ('amstream_port_init',(0x1a84,2232))):
            pat=r'^\s*\d+:\s*%016x\s+%d\s+FUNC\s+LOCAL\s+DEFAULT\s+10\s+%s\s*$'%(addr,size,name)
            if not re.search(pat,syms,re.M):raise ValueError('original local function identity mismatch '+name)
        dsyms=run('readelf','-Ws',str(files['decoder_common']))
        if not re.search(r'^\s*\d+:\s*0000000000000824\s+476\s+FUNC\s+GLOBAL\s+DEFAULT\s+10\s+vdec_create\s*$',dsyms,re.M):
            raise ValueError('original vdec_create identity changed')
    print('STAGE40_STATIC_GATES_PASS instructions=%d call_relocations=%d symbols=4 port_types=2'%(
         sum(len(x) for x in GATES.values()),sum(len(x) for x in CALLS.values())))
    print('FRAME_0x1D11=BIT10_EARLY_SKIP_EVEN_WITH_DUALDEC_BIT12')
    print('STREAM_0x1911=ATTEMPT_PRIMARY_THEN_SECOND_VDEC_CREATE')
    print('STREAM_SECOND_CREATE_NULL=CHECKED_AND_OPEN_RETURNS_NEG_ENOMEM')
    print('VDEC_CREATE_LINKS=secondary_master_plus_0x38_primary_slave_plus_0x40')
    print('RELEASE=PRIMARY_AND_LINKED_SECONDARY_CONDITIONALLY_RELEASED')
    print('PORT_INIT=SEPARATE_PRIMARY_AND_CONDITIONAL_SECONDARY_VDEC_INIT')
    print('LIVE_P7_FRAME_DEVICE=OBSERVED_PRIOR_CAPTURE_NOT_REMEASURED')
    print('LIVE_P7_MASTER_SLAVE_POINTERS=NOT_MEASURED')
    print('LIVE_P7_EL_DECODING=NOT_PROVEN')
    print('NATIVE_STREAM_MODE_SWITCH_SAFE=NOT_ESTABLISHED')
    print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE40_OFFLINE_PASS')
def selftest():
    assert len(MODULES)==2
    assert sum(len(x) for x in CALLS.values())==13
    assert open_path(0x1911)=='ATTEMPTS_SECOND_CREATE'
    assert open_path(0x1d11)=='FRAME_SKIPS_SECOND_CREATE'
    assert open_path(0x111)=='NO_SECOND_CREATE'
    assert open_path(0x111,True)=='ATTEMPTS_SECOND_CREATE'
    assert open_path(0x1d11,True)=='FRAME_SKIPS_SECOND_CREATE'
    assert 0x1d11 & 0x400 and 0x1911 & 0x1000
    print('GAZELLE_FEL_STAGE40_SOURCE_SELFTEST_PASS')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('original_kernel_zip',type=Path,nargs='?')
    p.add_argument('--selftest',action='store_true')
    args=p.parse_args();selftest()
    if args.selftest:return
    if args.original_kernel_zip is None:p.error('supply original owner kernel ZIP')
    verify_original(args.original_kernel_zip.expanduser().resolve())
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,zipfile.BadZipFile,AssertionError,subprocess.CalledProcessError) as e:
        print('GAZELLE_FEL_STAGE40_AUDIT_FAIL',e,file=sys.stderr);sys.exit(1)
