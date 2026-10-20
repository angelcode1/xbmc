#!/usr/bin/env python3
"""Stage35 original Amazon HEVC flag alias and bounded consumer audit (offline)."""
import argparse,hashlib,re,shutil,subprocess,sys
from pathlib import Path
PIN='0260d4b3c2e51bc32e1fe9b0b1b1fcd1debb982c4f93eb0e70ef28ea3cc8c040'
FIELDS={'last_pts':0xa74,'shift_byte_count_lo':0xa88,'ip_mode':0x10a58,
        'dv_duallayer':0x10a74,'discard_dv_data':0x10a88,'metadata_config_flag':0x10af4}
GATES={
 0x9ec:'mov w10, #0x82c',0xa00:'movk w10, #0x1, lsl #16',
 0xa10:'mov x19, x0',0xa1c:'add x25, x0, x10',
 0xeec:'strb w8, [x25, #0x25c]',0xf28:'strb w8, [x25, #0x248]',
 0xfac:'cbnz w0, 0xffc',0xfbc:'str w9, [x25, #0x2c8]',
 0xfc0:'strb w10, [x25, #0x25c]',0xfc4:'strb w8, [x25, #0x248]',
 0xfc8:'tbz w9, #0x1, 0xfe4',0xfe0:'ldrb w8, [x25, #0x248]',
 0xfe4:'cbz w8, 0xffc',0xfe8:'adrp x2, 0x0',0xfec:'add x2, x2, #0x0',
 0xff0:'mov x0, x19',0xff4:'mov w1, wzr',0xff8:'bl 0xff8',
 0x54c0:'movk w8, #0x1, lsl #16',0x54c4:'ldr x20, [x23, x8]',
 0x5860:'ldr w9, [x20, #0xa74]',0x5888:'str w8, [x20, #0xa74]',
 0x9ef8:'mov x19, x1',0x9fa0:'mov w8, #0x7fc',
 0x9fa8:'movk w8, #0x1, lsl #16',0x9fb0:'add x25, x19, x8',
 0xa324:'ldr w8, [x19, #0xa88]',0xa548:'ldrb w8, [x25, #0x25c]',
 0xb190:'adrp x25, 0xb000',0xc568:'strb w9, [x25, #0x25c]'}
LINE=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)
def cmd(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def norm(s):return re.sub(r'\s+','',s.split(' //',1)[0].split(' <',1)[0])
def member(text,name,off):
 for h in re.finditer(r'DW_TAG_member\)\s*\n',text):
  block=text[h.end():h.end()+650]
  n=re.search(r'\n\s*<\d+><[0-9a-f]+>:\s+Abbrev Number:',block)
  if n:block=block[:n.start()]
  if (re.search(r'DW_AT_name\s*:.*:\s*'+re.escape(name)+r'\s*$',block,re.M) and
      re.search(r'DW_AT_data_member_location\s*:\s*(?:0x%x|%d)\s*$'%(off,off),block,re.M)):
   return True
 return False
def reloc(text,at,kind,target):
 pattern=r'^%016x\s+\S+\s+%s\s+\S+\s+%s\s*$'%(at,re.escape(kind),re.escape(target))
 return bool(re.search(pattern,text,re.M))
def inspect(path):
 if not path.is_file() or path.is_symlink():raise ValueError('original module missing/symlink')
 data=path.read_bytes()
 if hashlib.sha256(data).hexdigest()!=PIN:raise ValueError('original HEVC module hash mismatch')
 if data[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(data[18:20],'little')!=183:
  raise ValueError('original module must be ELF64 AArch64')
 for exe in ('llvm-objdump','readelf'):
  if not shutil.which(exe):raise ValueError('missing required offline tool '+exe)
 dwarf=cmd('readelf','-wi',str(path))
 if not re.search(r'DW_AT_name\s*:.*:\s*hevc_state_s\s*$',dwarf,re.M):
  raise ValueError('missing original hevc_state_s type')
 for name,offset in FIELDS.items():
  if not member(dwarf,name,offset):raise ValueError('wrong named DWARF field '+name)
  print('HEVC_FIELD_ALIAS_DWARF_PASS',name,'0x%x'%offset)
 dis=cmd('llvm-objdump','-d','--section=.text','--no-show-raw-insn',str(path))
 ins={}
 for line in dis.splitlines():
  m=LINE.match(line)
  if m:ins[int(m[1],16)]=m[2]+' '+m[3]
 for at,expected in GATES.items():
  if norm(ins.get(at,''))!=norm(expected):
   raise ValueError('original instruction mismatch at 0x%x: %s'%(at,ins.get(at,'')))
 for off,addresses in (('0x248',{0xf28,0xfc4,0xfe0}),
                       ('0x25c',{0xeec,0xfc0,0xa548,0xc568})):
  actual={at for at,text in ins.items() if re.search(r'\[x25,\s*#'+off+r'\]',text)}
  if actual!=addresses:raise ValueError('changed direct x25 census '+off)
  print('HEVC_X25_REFERENCE_CENSUS_PASS',off,'sites=%d'%len(addresses))
 relocations=cmd('readelf','-rW',str(path))
 for at,kind,target in ((0xfe8,'R_AARCH64_ADR_PREL_PG_HI21','.rodata + 25fa'),
                        (0xfec,'R_AARCH64_ADD_ABS_LO12_NC','.rodata + 25fa'),
                        (0xff8,'R_AARCH64_CALL26','.text + 138'),
                        (0xb190,'R_AARCH64_ADR_PREL_PG_HI21','.bss + 50')):
  if not reloc(relocations,at,kind,target):raise ValueError('missing relocation at 0x%x'%at)
 sections=cmd('readelf','-SW',str(path))
 header=next((x for x in sections.splitlines() if re.search(r'\[\s*7\]\s+\.rodata\s+PROGBITS',x)),None)
 m=re.search(r'\.rodata\s+PROGBITS\s+[0-9a-f]+\s+([0-9a-f]+)\s+([0-9a-f]+)',header or '')
 if not m:raise ValueError('missing original rodata section')
 start,size=[int(x,16) for x in m.groups()]
 if size!=0x3f9c or data[start+0x25fa:start+0x25fa+14]!=b'dv_duallayer\n\x00':
  raise ValueError('missing original conditional diagnostic string')
 assert 0x1082c+0x248==FIELDS['dv_duallayer']
 assert 0x1082c+0x25c==FIELDS['discard_dv_data']
 assert 0x107fc+0x25c==FIELDS['ip_mode']
 print('STAGE35_ORIGINAL_GATES_PASS fields=6 instructions=30 x25_sites=7 relocations=4')
 print('PROBE_DV_DUALLAYER_DIRECT_READ_0xFE0=CONDITIONAL_DEBUG_LOG')
 print('PROBE_DV_DUALLAYER_DEBUG_STRING=dv_duallayer')
 print('PROBE_DV_DUALLAYER_DIRECT_HARDWARE_OPERATION=NOT_SHOWN_IN_LOCAL_LOG_BRANCH')
 print('LOOKALIKE_PLUS_0xA74=last_pts_NOT_dv_duallayer')
 print('LOOKALIKE_PLUS_0xA88=shift_byte_count_lo_NOT_discard_dv_data')
 print('ISR_0xA548_FIELD=ip_mode_NOT_discard_dv_data')
 print('INDIRECT_OR_OTHER_REGISTER_CONSUMERS=NOT_EXCLUDED')
 print('P7_RUNTIME_CONFIG_EFFECT=NOT_MEASURED')
 print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
 print('GAZELLE_FEL_STAGE35_ORIGINAL_HEVC_OFFLINE_PASS')
def selftest():
 assert len(FIELDS)==6 and len(GATES)==30
 assert 0x1082c+0x248==0x10a74 and 0x1082c+0x25c==0x10a88
 assert 0x107fc+0x25c==0x10a58
 print('GAZELLE_FEL_STAGE35_SOURCE_SELFTEST_PASS')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('module',type=Path,nargs='?')
 p.add_argument('--selftest',action='store_true')
 a=p.parse_args();selftest()
 if a.selftest:return
 if not a.module:p.error('supply original amvdec_h265.ko')
 inspect(a.module.expanduser().resolve())
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,AssertionError,subprocess.CalledProcessError) as e:
  print('GAZELLE_FEL_STAGE35_AUDIT_FAIL',e,file=sys.stderr);sys.exit(1)
