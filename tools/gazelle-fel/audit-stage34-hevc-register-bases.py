#!/usr/bin/env python3
"""Stage 34: correct original HEVC flag mapping with register-base and DWARF gates.

Host-only: SHA-pinned owner original ELF64 modules, no ADB or device changes.
"""
import argparse,hashlib,re,shutil,subprocess,sys
from pathlib import Path

PINS={'amvdec_h265.ko':'0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040',
      'decoder_common.ko':'a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b'}
FIELDS={'ip_mode':0x10a58,'dv_duallayer':0x10a74,
        'discard_dv_data':0x10a88,'metadata_config_flag':0x10af4}
GATES={
 0x9ec:'mov w10, #0x82c',0xa00:'movk w10, #0x1, lsl #16',
 0xa08:'movk w2, #0x1, lsl #16',0xa10:'mov x19, x0',
 0xa1c:'add x25, x0, x10',0xeec:'strb w8, [x25, #0x25c]',
 0xf28:'strb w8, [x25, #0x248]',0xfbc:'str w9, [x25, #0x2c8]',
 0xfc0:'strb w10, [x25, #0x25c]',0xfc4:'strb w8, [x25, #0x248]',
 0xfe0:'ldrb w8, [x25, #0x248]',0x9ef8:'mov x19, x1',
 0x9f14:'ldr x22, [x8, #0x88]',0x9f9c:'movk w9, #0x1, lsl #16',
 0x9fa0:'mov w8, #0x7fc',0x9fa4:'add x20, x19, x9',
 0x9fa8:'movk w8, #0x1, lsl #16',0x9fac:'mov x0, x20',
 0x9fb0:'add x25, x19, x8',0xa548:'ldrb w8, [x25, #0x25c]',
 0xa54c:'cbz w8, 0xb000',0xb190:'adrp x25, 0xb000',
 0xc548:'ldr w11, [x25, #0x2f4]',0xc554:'ldr x9, [x22, #0x40]',
 0xc55c:'ldr x9, [x22, #0x38]',0xc568:'strb w9, [x25, #0x25c]',
}
LINE=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)
def cmd(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def clean(s):return re.sub(r'\s+','',s.split(' //',1)[0].split(' <',1)[0])
def member(dwarf,name,offset):
 for m in re.finditer(r'DW_TAG_member\)\s*\n',dwarf):
  part=dwarf[m.end():m.end()+550]
  next_member=re.search(r'\n\s*<2><[0-9a-f]+>:\s+Abbrev Number:',part)
  if next_member:part=part[:next_member.start()]
  if (re.search(r'DW_AT_name\s*:.*:\s*'+re.escape(name)+r'\s*$',part,re.M) and
      re.search(r'DW_AT_data_member_location\s*:\s*(?:0x%x|%d)\s*$'%(offset,offset),part,re.M)):
   return True
 return False
def audit(root):
 paths={}
 for name,digest in PINS.items():
  path=root/name
  if not path.is_file() or path.is_symlink():raise ValueError('missing/symlink '+name)
  blob=path.read_bytes()
  if hashlib.sha256(blob).hexdigest()!=digest:raise ValueError('wrong module SHA '+name)
  if blob[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(blob[18:20],'little')!=183:
   raise ValueError('not ELF64 AArch64 '+name)
  paths[name]=path
  print('PINNED_MODULE_PASS',name)
 for binary in ('readelf','llvm-objdump'):
  if not shutil.which(binary):raise ValueError('missing tool '+binary)
 dwarf=cmd('readelf','-wi',str(paths['amvdec_h265.ko']))
 if not re.search(r'DW_AT_name\s*:.*:\s*hevc_state_s\s*$',dwarf,re.M):
  raise ValueError('missing original hevc_state_s type')
 for name,offset in FIELDS.items():
  if not member(dwarf,name,offset):raise ValueError('original member missing '+name)
  print('ORIGINAL_HEVC_DWARF_FIELD_PASS',name,'0x%x'%offset)
 common=cmd('readelf','-wi',str(paths['decoder_common.ko']))
 for name,offset in (('master',0x38),('slave',0x40)):
  if not member(common,name,offset):raise ValueError('original vdec_s member missing '+name)
  print('ORIGINAL_VDEC_DWARF_FIELD_PASS',name,'0x%x'%offset)
 dis=cmd('llvm-objdump','-d','--section=.text','--no-show-raw-insn',
         str(paths['amvdec_h265.ko']))
 ins={}
 for line in dis.splitlines():
  m=LINE.match(line)
  if m:ins[int(m[1],16)]=m[2]+' '+m[3]
 for addr,expected in GATES.items():
  if clean(ins.get(addr,''))!=clean(expected):
   raise ValueError('opcode mismatch 0x%x %s'%(addr,ins.get(addr)))
 for off,expected in {'0x248':{0xf28,0xfc4,0xfe0},
                      '0x25c':{0xeec,0xfc0,0xa548,0xc568}}.items():
  found={addr for addr,code in ins.items()
         if re.search(r'\[x25,\s*#'+off+r'\]',code)}
  if found!=expected:raise ValueError('direct x25 site set changed '+off)
  print('X25_RELATIVE_REFERENCE_PASS',off,'count=%d'%len(found))
 reloc=cmd('readelf','-rW',str(paths['amvdec_h265.ko']))
 if not re.search(r'^0{0,15}b190\s+\S+\s+R_AARCH64_ADR_PREL_PG_HI21\s+\S+\s+\.bss \+ 50\s*$',reloc,re.M):
  raise ValueError('missing original .bss rebase relocation')
 assert 0x1082c+0x25c==FIELDS['discard_dv_data']
 assert 0x1082c+0x248==FIELDS['dv_duallayer']
 assert 0x107fc+0x25c==FIELDS['ip_mode']
 print('GAZELLE_FEL_STAGE34_GATES_PASS original_modules=2 dwarf_fields=6 opcodes=26 x25_reference_sites=7 relocation=1')
 print('NEGATIVE_DV_CONFIG_WRITES=hevc_state_s.discard_dv_data_0x10a88')
 print('DV_DUALLAYER_CONFIG_WRITES=hevc_state_s.dv_duallayer_0x10a74')
 print('METADATA_FLAG_OVERRIDE_TARGETS=discard_dv_data_AND_dv_duallayer')
 print('ISR_0xa548_READS=hevc_state_s.ip_mode_0x10a58_NOT_discard_dv_data')
 print('ISR_0xb190_REBASES_X25=external_bss_PAGE_NOT_probe_HEVC_base')
 print('ISR_0xc568_SAME_FLAG_WRITE=NOT_PROVEN')
 print('P7_RUNTIME_EFFECT=NOT_OBSERVED')
 print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
 print('GAZELLE_FEL_STAGE34_OFFLINE_PASS')
def selftest():
 assert len(PINS)==2 and len(FIELDS)==4 and len(GATES)==26
 assert 0x1082c+0x25c==0x10a88 and 0x1082c+0x248==0x10a74
 assert 0x107fc+0x25c==0x10a58 and 0x10a58!=0x10a88
 print('GAZELLE_FEL_STAGE34_SOURCE_SELFTEST_PASS')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('module_dir',nargs='?',type=Path)
 p.add_argument('--selftest',action='store_true')
 a=p.parse_args()
 selftest()
 if a.selftest:return
 if not a.module_dir:p.error('provide original two module folder')
 audit(a.module_dir.expanduser().resolve())
if __name__=='__main__':
 try:main()
 except (ValueError,OSError,AssertionError,subprocess.CalledProcessError) as exc:
  print('GAZELLE_FEL_STAGE34_OFFLINE_FAIL',exc,file=sys.stderr)
  sys.exit(1)
