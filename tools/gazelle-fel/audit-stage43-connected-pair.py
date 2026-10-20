#!/usr/bin/env python3
"""Stage43 original kernel connected-list/master-slave bridge, offline only.

Original Fire OS 5.4 owner ELFs are SHA-pinned and inspected without execution.
Optional Stage42 sanitized ZIP is pinned and checked without exposing raw data.
"""
import argparse, hashlib, json, re, subprocess, sys, tempfile, zipfile
from pathlib import Path

ARCHIVE_SHA='02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44'
CAPTURE_SHA='ca99ef1dd6dd1f564f5aaa166f3e83acb3d80df635bc0b735d361d5e3c7dbdb7'
MODULES={
 'decoder_common':('a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b',4015344),
 'stream_input':('fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c',5239792),
}
PREFIX='gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_'
# ARM64 instruction words resolved against the exact two original ELF hashes.
GATES={
 'decoder_common':{
  0x26a8:'ldr w8, [x19, #0x148]',0x26b0:'b.ne 0x27a0',
  0x26d8:'ldr x8, [x19, #0x40]',0x26dc:'cbz x8, 0x2710',
  0x26e4:'str w9, [x8, #0x148]',0x26e8:'ldr x8, [x19, #0x40]',
  0x2710:'adrp x24, 0x2000',0x2714:'ldr x8, [x24]',
  0x2724:'add x22, x19, #0x8',0x273c:'bl 0x273c',
  0x2740:'tbz w0, #0x0, 0x2750',0x2744:'str x22, [x23, #0x8]',
  0x2750:'ldr x23, [x19, #0x40]',0x2754:'cbz x23, 0x2784',
  0x275c:'add x21, x23, #0x8',0x2770:'bl 0x2770',
  0x2774:'tbz w0, #0x0, 0x2784',0x2778:'str x21, [x22, #0x8]',
  0x277c:'stp x22, x19, [x23, #0x8]',0x2780:'str x21, [x19]',
  0x8a70:'adrp x8, 0x8000',0x8a74:'ldr x24, [x8]',
  0x8aac:'ldr x25, [x24]',0x8ab4:'cmp x24, x25',
  0x8ab8:'b.eq 0x8ba0',0x8b08:'bl 0x8b08',
  0x8b0c:'ldr x25, [x25]',0x8b14:'cmp x24, x25',
 },
 'stream_input':{
  0x20d8:'tbz w8, #0x0, 0x20ec',
  0x20dc:'ldrb w8, [x21, #0x154]',
  0x20e0:'tbz w8, #0x1, 0x20ec',
  0x20e4:'mov x0, x21',0x20e8:'bl 0x20e8',
 },
}
RELOCS={
 'decoder_common':[
  (0x2710,'R_AARCH64_ADR_PREL_PG_HI21','vdec_core.llvm.7425214269774233008 + 0'),
  (0x2714,'R_AARCH64_LDST64_ABS_LO12_NC','vdec_core.llvm.7425214269774233008 + 0'),
  (0x2758,'R_AARCH64_LDST64_ABS_LO12_NC','vdec_core.llvm.7425214269774233008 + 0'),
  (0x8a70,'R_AARCH64_ADR_PREL_PG_HI21','vdec_core.llvm.7425214269774233008 + 0'),
  (0x8a74,'R_AARCH64_LDST64_ABS_LO12_NC','vdec_core.llvm.7425214269774233008 + 0'),
  (0x273c,'R_AARCH64_CALL26','__list_add_valid + 0'),
  (0x2770,'R_AARCH64_CALL26','__list_add_valid + 0'),
  (0x8b08,'R_AARCH64_CALL26','sprintf + 0'),
 ],
 'stream_input':[(0x20e8,'R_AARCH64_CALL26','vdec_connect + 0')],
}
ROW=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)
def cmd(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def sha(data):return hashlib.sha256(data).hexdigest()
def canon(s):return re.sub(r'\s+','',s.split(' //',1)[0].split(' <',1)[0])

def audit_kernel(path):
 data=path.read_bytes()
 if not path.is_file() or path.is_symlink() or sha(data)!=ARCHIVE_SHA:raise ValueError('original owner archive SHA mismatch')
 with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory(prefix='stage43-private-') as tmp:
  for name,(hash_,size) in MODULES.items():
   matches=[i for i in z.infolist() if i.filename==PREFIX+name+'.ko' and not i.is_dir()]
   if len(matches)!=1 or matches[0].file_size!=size:raise ValueError('original ELF archive inventory mismatch')
   b=z.read(matches[0]);p=Path(tmp)/(name+'.ko');p.write_bytes(b)
   if sha(b)!=hash_ or b[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(b[18:20],'little')!=183:
    raise ValueError('original module mismatch '+name)
   symbols=cmd('readelf','-Ws',str(p))
   funcs={'decoder_common': [('vdec_connect',0x2688,308),('core_show',0x8a44,412)],
          'stream_input':[('amstream_port_init',0x1a84,2232)]}[name]
   for function,off,length in funcs:
    pat=rf'^\s*\d+:\s*{off:016x}\s+{length}\s+FUNC\s+\w+\s+DEFAULT\s+\d+\s+{function}\s*$'
    if not re.search(pat,symbols,re.M):raise ValueError('original function identity mismatch '+function)
   dis=cmd('llvm-objdump','-d','--no-show-raw-insn','--section=.text',str(p))
   found={}
   for line in dis.splitlines():
    m=ROW.match(line)
    if m:found[int(m[1],16)]=m[2]+' '+m[3]
   for at,expected in GATES[name].items():
    if canon(found.get(at,''))!=canon(expected):raise ValueError('instruction mismatch '+name+' '+hex(at)+' '+str(found.get(at)))
   relocation=cmd('readelf','-rW',str(p))
   for at,kind,target in RELOCS[name]:
    matches=[row for row in relocation.splitlines() if re.match(rf'^\s*{at:016x}\s+',row) and kind in row]
    if len(matches)!=1 or target not in matches[0]:
     raise ValueError('relocation mismatch '+name+' '+hex(at))
   print('ORIGINAL_ELF_CONNECTED_LIST_GATE_PASS',name,'instructions',len(GATES[name]),'relocations',len(RELOCS[name]))
 print('CONNECT_AND_CORE_SHARE_SAME_VDEC_CORE_GLOBAL=YES')
 print('CONNECT_FUNCTION=CONDITIONAL_INSERT_PRIMARY_AND_LINKED_SLAVE')
 print('CONNECT_SECOND_INSERT_REQUIRES_NON_NULL_SLAVE_AND_LIST_VALIDATION')
 print('CORE_SHOW=TRAVERSES_SAME_CONNECTED_LIST')
 print('STREAM_PORT_INIT=CONDITIONALLY_CALLS_VDEC_CONNECT')
 print('CORRECTED_INTERPRETATION=CONNECTED_COUNT_IS_MORE_DIRECT_THAN_STATUS_RECORDS')
 print('GAZELLE_FEL_STAGE43_ORIGINAL_BRIDGE_OFFLINE_PASS')

def audit_capture(path):
 if not path.is_file() or path.is_symlink() or sha(path.read_bytes())!=CAPTURE_SHA:raise ValueError('stage42 capture SHA mismatch')
 with zipfile.ZipFile(path) as z:
  if z.testzip():raise ValueError('stage42 ZIP CRC mismatch')
  names=z.namelist()
  jnames=[n for n in names if n.endswith('.json')]
  if len(names)!=2 or len(jnames)!=1 or any('/' in n for n in names):raise ValueError('unexpected sanitized archive inventory')
  payload=json.loads(z.read(jnames[0]));obs=payload.get('observations',[])
  if (payload.get('schema')!='gazelle-fel-stage42-v1' or payload.get('device_writes') is not False or
      payload.get('raw_kernel_addresses_retained') is not False or len(obs)!=9):raise ValueError('stage42 schema/safety/phase mismatch')
  for phase,expected_n,fmt in [('idle',0,'HDR10'),('P8',1,'DOVI'),('P7',1,'HDR10')]:
   rows=[r for r in obs if r['phase']==phase]
   if len(rows)!=3 or [r['sample'] for r in rows]!=[1,2,3]:raise ValueError('phase order mismatch')
   for r in rows:
    probes=r['probes']
    if set(probes)!= {'core','status','source','ports'} or any(p['read_status']!='OK' for p in probes.values()):raise ValueError('probe incomplete')
    c=probes['core']['value'];s=probes['status']['value']
    if c['connected_records']!=expected_n or s['reportable_records']!=expected_n or probes['source']['value']!=fmt:
     raise ValueError('unexpected visible decoder evidence')
   print('STAGE42_VERIFIED_PHASE',phase,'connected',expected_n,'reportable',expected_n,'source',fmt)
 print('P7_ADDITIONAL_CONNECTED_DECODER=NOT_OBSERVED_IN_3_OF_3_SAMPLES')
 print('P7_ADDITIONAL_ALLOCATED_BUT_NONCONNECTED_DECODER=NOT_EXCLUDED')
 print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
 print('GAZELLE_FEL_STAGE43_EVIDENCE_RECONCILIATION_PASS')

def selftest():
 assert len(GATES['decoder_common'])==28 and len(GATES['stream_input'])==5
 assert len(RELOCS['decoder_common'])==8 and len(RELOCS['stream_input'])==1
 print('GAZELLE_FEL_STAGE43_SOURCE_SELFTEST_PASS')

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('original_kernel_zip',type=Path,nargs='?');p.add_argument('stage42_capture_zip',type=Path,nargs='?')
 p.add_argument('--selftest',action='store_true');a=p.parse_args()
 selftest()
 if a.selftest:return
 if not a.original_kernel_zip or not a.stage42_capture_zip:p.error('supply original kernel ZIP and sanitized Stage42 capture ZIP')
 audit_kernel(a.original_kernel_zip.expanduser().resolve())
 audit_capture(a.stage42_capture_zip.expanduser().resolve())
 print('GAZELLE_FEL_STAGE43_OFFLINE_PASS')
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,AssertionError,subprocess.CalledProcessError,zipfile.BadZipFile) as e:
  print('GAZELLE_FEL_STAGE43_AUDIT_FAIL',e,file=sys.stderr);sys.exit(1)
