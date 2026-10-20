#!/usr/bin/env python3
"""Stage36 original Amazon HEVC metadata-export gates: offline, no device I/O."""
import argparse,hashlib,re,shutil,subprocess,sys
from pathlib import Path
SHA='0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040'
FUNCTIONS={'set_aux_data':(0xcee0,1080),'dolby_get_meta':(0xdc10,232),'vh265_event_cb':(0x15708,560)}
GATES={
 0xcf20:'cbz x23, 0xd01c',0xcf64:'ldr x25, [x19, #0x8f0]',
 0xd0cc:'bl 0xd0cc',0xd0d0:'cbz x0, 0xd2d4',
 0xd120:'add x11, x25, x9, lsl #1',0xd124:'ldrh w13, [x11, #0x6]',
 0xd128:'lsr w12, w13, #8',0xd144:'ands w10, w21, #0xff',
 0xd148:'b.eq 0xd164',0xd14c:'cmp w10, #0x2',
 0xd154:'cmp w10, #0x1',0xd15c:'cmp w12, #0x1',
 0xd1e8:'cmp w12, #0x1',0xd2f4:'str xzr, [x24]',
 0xd2f8:'str wzr, [x24, #0x8]',
 0xdc20:'mov x19, x0',0xdc34:'ldr x20, [x8, #0x88]',
 0xdc60:'mov w8, #0x1db9',0xdc64:'movk w8, #0x1, lsl #16',
 0xdc68:'ldrb w8, [x20, x8]',0xdc6c:'cbnz w8, 0xdc78',
 0xdc70:'ldr x8, [x20, #0x40]',0xdc74:'cbz x8, 0xdc9c',
 0xdc78:'ldr x1, [x19, #0xa28]',0xdc80:'mov w2, wzr',
 0xdc84:'mov w3, wzr',0xdc88:'bl 0xdc88',
 0xdc9c:'ldr x8, [x20, #0x38]',0xdca0:'cbz x8, 0xdcd8',
 0xdcbc:'ldr x1, [x8, #0xa28]',0xdcc0:'bl 0xdcc0',
 0xdcc8:'mov w3, #0x2',0xdcd4:'b 0xdc88',
 0x15738:'tbnz w21, #0x5, 0x15914',
 0x15748:'tbnz w21, #0x7, 0x1576c',
 0x1579c:'ldrb w22, [x4]',
  0x157a0:'str xzr, [x19, #0x10]',
  0x157a4:'str wzr, [x19, #0x18]',
  0x157b4:'cmp w22, #0x17',0x157b8:'b.hi 0x158b4',
  0x157c0:'ldr x9, [x8, #0x2ae8]',0x157c4:'cbz x9, 0x158b4',
  0x157c8:'mov w10, #0xf448',0x157cc:'movk w10, #0x1, lsl #16',
  0x157d0:'ldr x10, [x9, x10]',0x157dc:'str x10, [x19, #0x10]',
  0x157e4:'mov w10, #0xf450',0x157e8:'movk w10, #0x1, lsl #16',
  0x157ec:'ldr w8, [x8, x10]',0x157f0:'str w8, [x19, #0x18]',
}
RELOCS={0xd0cc:('R_AARCH64_CALL26','vzalloc'),
        0xdc88:('R_AARCH64_CALL26','.text + cee0'),
        0xdcc0:('R_AARCH64_CALL26','.text + cee0')}
ROW=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)',re.I)
def execute(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def clean(t):return re.sub(r'\s+','',t.split(' //',1)[0].split(' <',1)[0])
def audit(path):
 if not path.is_file() or path.is_symlink():raise ValueError('original private module missing/symlink')
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('original HEVC SHA256 mismatch')
 if raw[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(raw[18:20],'little')!=183:raise ValueError('not ELF64/AArch64 original')
 for tool in ('readelf','llvm-objdump'):
  if not shutil.which(tool):raise ValueError('missing offline '+tool)
 syms=execute('readelf','-Ws',str(path))
 for name,(addr,size) in FUNCTIONS.items():
  rule=r'^\s*\d+:\s*%016x\s+%d\s+FUNC\s+LOCAL\s+DEFAULT\s+\d+\s+%s\s*$'%(addr,size,name)
  if not re.search(rule,syms,re.M):raise ValueError('function identity differs '+name)
  print('ORIGINAL_HEVC_FUNCTION_PASS',name,'0x%x'%addr,'bytes=%d'%size)
 dis=execute('llvm-objdump','-d','--section=.text','--no-show-raw-insn',str(path))
 inst={}
 for line in dis.splitlines():
  m=ROW.match(line)
  if m:inst[int(m[1],16)]=m[2]+' '+m[3]
 for addr,expected in GATES.items():
  if clean(inst.get(addr,''))!=clean(expected):raise ValueError('HEVC opcode at 0x%x: %s'%(addr,inst.get(addr)))
 for name,(at,size) in FUNCTIONS.items():
  subset={a:s for a,s in inst.items() if at<=a<at+size}
  forbidden=[a for a,s in subset.items() if re.search(r'\[x\d+,\s*#0x(?:248|25c|10a74|10a88)\]',s)]
  if forbidden:raise ValueError('unexpected exact flag-relative operand in '+name+': '+repr(forbidden))
  print('BOUNDED_FLAG_OFFSET_DIRECT_READ_NOT_FOUND',name,'instructions=%d'%len(subset))
 relocs=execute('readelf','-rW',str(path))
 for at,(kind,target) in RELOCS.items():
  entries=[line for line in relocs.splitlines() if re.match(r'^\s*%016x\s+'%at,line)]
  if len(entries)!=1 or kind not in entries[0] or target not in entries[0]:
   raise ValueError('original call relocation mismatch at 0x%x'%at)
 print('GAZELLE_FEL_STAGE36_ORIGINAL_GATES_PASS functions=3 opcodes=%d relocs=%d'%(len(GATES),len(RELOCS)))
 print('DOLBY_GET_META_DISPATCH=CURRENT_IF_META_WITH_EL_OR_SLAVE_ELSE_MASTER_AND_CURRENT_SELECTOR_SPLIT')
 print('SET_AUX_DATA=DMA_BUFFER_SELECTOR_FILTER_WITH_ALLOCATION_FAILURE_CLEAR')
 print('EVENT_CALLBACK=DEFAULTS_AUX_PTR_SIZE_ZERO_THEN_LOOKUP_CONDITIONALLY_EXPORTS')
 print('DISCARD_DV_DATA_DIRECT_GATE_IN_THESE_THREE_BODIES=NOT_IDENTIFIED')
 print('DV_DUALLAYER_DIRECT_GATE_IN_THESE_THREE_BODIES=NOT_IDENTIFIED')
 print('INDIRECT_OR_FIRMWARE_SIDE_FLAG_EFFECT=NOT_EXCLUDED')
 print('RUNTIME_P7_METADATA_PRESENT=NOT_OBSERVED')
 print('RUNTIME_P7_EL_DECODER=NOT_OBSERVED')
 print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
 print('GAZELLE_FEL_STAGE36_ORIGINAL_HEVC_OFFLINE_PASS')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('module',type=Path,nargs='?');p.add_argument('--selftest',action='store_true');a=p.parse_args()
 assert len(FUNCTIONS)==3 and len(RELOCS)==3 and len(GATES)>=48
 assert 0xcee0+1080==0xd318 and 0xdc10+232==0xdcf8 and 0x15708+560==0x15938
 print('GAZELLE_FEL_STAGE36_SOURCE_SELFTEST_PASS')
 if a.selftest:return
 if a.module is None:p.error('pass original private amvdec_h265.ko')
 audit(a.module.expanduser().resolve())
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,subprocess.CalledProcessError,AssertionError) as ex:
  print('GAZELLE_FEL_STAGE36_AUDIT_FAIL',ex,file=sys.stderr);sys.exit(1)
