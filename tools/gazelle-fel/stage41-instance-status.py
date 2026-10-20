#!/usr/bin/env python3
"""Gazelle FEL Stage41: original read-only vdec status gate and redacted live P8/P7 sampling.

No device writes or changes to playback. User manually controls playback.
Never retain raw sysfs messages, names, identifiers, or pointers.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

PIN_ZIP = '02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44'
PIN_ELF = 'a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b'
ZIP_MEMBER = 'gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_decoder_common.ko'
PHASES=('idle','P8','P7')
READS={
 'vdec_status':'/sys/class/vdec/vdec_status',
 'ports':'/sys/class/amstream/ports',
 'source':'/sys/class/amdolby_vision/src_format',
}
GATES={
 0x8c18:'adrp x8, 0x8000',
 0x8c1c:'ldr x19, [x8]',
 0x8c48:'ldr x21, [x19]',
 0x8c50:'cmp x19, x21',
 0x8c54:'b.eq 0x8ed4',
 0x8c90:'adrp x1, 0x8000',
 0x8c94:'and w2, w22, #0xff',
 0x8ca0:'bl 0x8ca0',
 0x8e58:'add w22, w22, #0x1',
 0x8e5c:'ldr x21, [x21]',
 0x8e60:'cmp x19, x21',
 0x8e64:'b.eq 0x8eec',
 0x8e68:'ldr w8, [x21, #0x140]',
 0x8e6c:'and w8, w8, #0xfffffffe',
 0x8e70:'cmp w8, #0x2',
 0x8e74:'b.ne 0x8e5c',
 0x8e78:'sub x0, x21, #0x8',
 0x8ea0:'mov w8, #0x1dd0',
 0x8ea4:'movk w8, #0x1, lsl #16',
 0x8ea8:'ldr x8, [x21, x8]',
 0x8eac:'cbz x8, 0x8c90',
 0x8eb4:'blr x8',
 0x8eb8:'cbz w0, 0x8c90',
 0x8eec:'adrp x8, 0x8000',
 0x8efc:'bl 0x8efc',
}
LINE=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)',re.I)
CHANNEL=re.compile(r'^vdec channel (\d{1,3}) statistics:\s*$',re.M)
PORT_GROUP=re.compile(r'(?=^amstream_[a-z0-9_]+\s*:\s*$)',re.M)


def command(*args):
 return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def instruction(s):
 return re.sub(r'\s+','',s.split(' //',1)[0].split(' <',1)[0])

def verify_archive(path):
 if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=PIN_ZIP:
  raise ValueError('original private owner kernel archive SHA mismatch/missing')
 with zipfile.ZipFile(path) as z:
  members=[x for x in z.infolist() if x.filename==ZIP_MEMBER and not x.is_dir()]
  if len(members)!=1 or members[0].file_size!=4015344:
   raise ValueError('unexpected original decoder_common module inventory')
  blob=z.read(members[0])
 if hashlib.sha256(blob).hexdigest()!=PIN_ELF or blob[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(blob[18:20],'little')!=183:
  raise ValueError('original decoder_common ELF identity mismatch')
 return blob


def audit(path):
 data=verify_archive(path)
 with tempfile.TemporaryDirectory(prefix='gazelle-fel41-private-') as d:
  f=Path(d)/'decoder_common.ko';f.write_bytes(data)
  syms=command('readelf','-Ws',str(f))
  for name,addr,size in [('class_attr_vdec_status',0x3c8,32),('vdec_status_show',0x8be0,868)]:
   pat=r'^\s*\d+:\s*%016x\s+%d\s+(?:FUNC|OBJECT)\s+LOCAL\s+DEFAULT\s+\d+\s+%s\s*$'%(addr,size,name)
   if not re.search(pat,syms,re.M):raise ValueError('original named symbol mismatch: '+name)
  sections=command('readelf','-SW',str(f))
  def offset(name):
   row=next((line for line in sections.splitlines() if re.search(r'\[\s*\d+\]\s+'+re.escape(name)+r'\s+PROGBITS',line)),None)
   m=re.search(re.escape(name)+r'\s+PROGBITS\s+\S+\s+(\S+)\s+(\S+)',row or '')
   if not m:raise ValueError('missing original section '+name)
   return int(m[1],16),int(m[2],16)
  data_off,_=offset('.data');ro_off,ro_len=offset('.rodata')
  if int.from_bytes(data[data_off+0x3d0:data_off+0x3d4],'little')!=0o444:
   raise ValueError('vdec status sysfs mode not 0444')
  if data[ro_off+0x1efd:ro_off+0x1efd+12]!=b'vdec_status\x00':
   raise ValueError('vdec status sysfs name differs')
  if data[ro_off+0x28f6:ro_off+0x28f6+29]!=b'vdec channel %u statistics:\n\0':
   raise ValueError('vdec per-instance header format differs')
  relocs=command('readelf','-rW',str(f))
  for at,kind,target in (
   (0x3c8,'R_AARCH64_ABS64','.rodata + 1efd'),
   (0x3d8,'R_AARCH64_ABS64','.text + 8be0'),
   (0x8c18,'R_AARCH64_ADR_PREL_PG_HI21','vdec_core.llvm.7425214269774233008 + 0'),
   (0x8ca0,'R_AARCH64_CALL26','sprintf + 0'),
   (0x8efc,'R_AARCH64_CALL26','_raw_spin_unlock_irqrestore + 0')):
   lines=[line for line in relocs.splitlines() if re.match(r'^\s*%016x\s+'%at,line)]
   if not any(kind in row and target in row for row in lines):
    raise ValueError('relocation mismatch at 0x%x for %s'%(at,target))
  dis=command('llvm-objdump','-d','--section=.text','--no-show-raw-insn','--start-address=0x8be0','--stop-address=0x8f44',str(f))
  found={}
  for line in dis.splitlines():
   m=LINE.match(line)
   if m:found[int(m[1],16)]=m[2]+' '+m[3]
  for at,expected in GATES.items():
   if instruction(found.get(at,''))!=instruction(expected):
    raise ValueError('original vdec_status_show instruction differs at 0x%x: %s'%(at,found.get(at,'')))
  print('PINNED_ORIGINAL_MODULE_PASS decoder_common.ko')
  print('READONLY_SYSFS_ATTR_PASS name=vdec_status mode=0444')
  print('ORIGINAL_VDEC_LIST_STATUS_GATES_PASS instructions=%d relocations=5'%len(GATES))
  print('ELIGIBLE_STATUS_RECORDS=LIST_ENUMERATION_WITH_STATE_AND_CALLBACK_FILTER')
  print('STATUS_CALLBACK_POINTER_AND_FORMAT=ORIGINAL_MODULE_VERIFIED')
  print('VISIBLE_STATUS_RECORDS_MAY_UNDERCOUNT_ALLOCATED_VDECS=YES')
  print('STATUS_ENDPOINT_EXPOSES_MASTER_SLAVE_POINTER_DIRECTLY=NOT_VERIFIED')
  print('P7_RUNTIME_LINKED_DECODER=NOT_OBSERVED')
  print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
  print('GAZELLE_FEL_STAGE41_ORIGINAL_STATUS_OFFLINE_PASS')


def parse_status(raw):
 if re.search(r'\bNo vdec\s*\.',raw,re.I):
  return {'classification':'NO_VDEC','visible_records':0,'channel_ordinals':[]}
 channels=[int(x) for x in CHANNEL.findall(raw)]
 if channels:
  if len(channels)>16 or len(set(channels))!=len(channels):
   return {'classification':'AMBIGUOUS','visible_records':None,'channel_ordinals':[]}
  return {'classification':'STATUS_RECORDS','visible_records':len(channels),
          'channel_ordinals':channels}
 return {'classification':'UNPARSEABLE','visible_records':None,'channel_ordinals':[]}


def parse_ports(raw):
 values={}
 for fragment in PORT_GROUP.split(raw):
  header=re.search(r'^\s*(amstream_dves_hevc(?:_frame)?)\s*:\s*$',fragment,re.M)
  if not header:continue
  name=header[1]
  def num(field):
   m=re.search(r'^\s*'+field+r':(-?\d+)',fragment,re.M)
   return int(m[1]) if m else None
  values[name]={'type':num('type'),'flag':num('flag')}
 return values


def parse_source(raw):
 match=re.search(r'^inst1:\s*([^\n]{1,160})',raw,re.M)
 if not match:return 'UNKNOWN'
 text=match[1]
 if 'FORMAT_DOVI' in text:return 'DOVI'
 if 'FORMAT_HDR10' in text:return 'HDR10'
 if 'FORMAT_SDR' in text:return 'SDR'
 return 'OTHER'


def adb_executable():
 exe=shutil.which(os.environ['ADB']) if os.environ.get('ADB') else shutil.which('adb')
 if not exe:
  p='/Applications/adblink.app/Contents/MacOS/adbfiles/adb'
  exe=p if Path(p).is_file() else None
 if not exe:raise ValueError('adb executable absent; set ADB or install Android platform-tools')
 res=subprocess.run([exe,'devices'],capture_output=True,text=True,timeout=12)
 live=[x.split() for x in res.stdout.splitlines()[1:] if len(x.split())==2 and x.split()[1]=='device']
 if res.returncode or len(live)!=1:raise ValueError('exactly one authorized ADB device required')
 return exe


def read_status(adb,name):
 if name not in READS:raise ValueError('sysfs probe not allowlisted')
 try:
  p=subprocess.run([adb,'shell',"su -c 'cat "+READS[name]+"'"],capture_output=True,text=True,
                  errors='replace',timeout=12)
 except subprocess.TimeoutExpired:return {'status':'TIMEOUT','value':None}
 if p.returncode:return {'status':'UNAVAILABLE','value':None}
 if len(p.stdout)>48000:return {'status':'TOO_LARGE','value':None}
 if name=='vdec_status':value=parse_status(p.stdout.replace('\r',''))
 elif name=='ports':value=parse_ports(p.stdout.replace('\r',''))
 else:value=parse_source(p.stdout.replace('\r',''))
 return {'status':'OK','value':value}


def capture(directory):
 adb=adb_executable()
 rows=[]
 for phase,instruction_text in [('idle','Stop Kodi playback'),
                                ('P8','Play your known-working P8 video'),
                                ('P7','Stop P8; play your P7 FEL test')]:
  print('\n%s: %s. Press Enter when ready.'%(phase,instruction_text),flush=True)
  input()
  for n in range(1,4):
   stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')
   probes={key:read_status(adb,key) for key in READS}
   rows.append({'phase':phase,'sample':n,'utc':stamp,'probes':probes})
   print('%s sample %s records=%s'%(phase,n,(probes['vdec_status']['value'] or {}).get('visible_records')))
   if n<3:time.sleep(2)
 directory.mkdir(parents=True,exist_ok=True)
 stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
 stem='stage41-visible-instances-'+stamp
 jsonfile=directory/(stem+'.json');txtfile=directory/(stem+'.txt');zfile=directory/(stem+'.zip')
 jsonfile.write_text(json.dumps({'schema':'gazelle-fel-stage41-v1','device_writes':False,
   'raw_sysfs_stored':False,'probes_not_atomic':True,'observations':rows},indent=2)+'\n')
 lines=['GAZELLE_FEL_STAGE41_VISIBLE_STATUS_CAPTURE','DEVICE_WRITES=NONE',
        'RAW_SYSFS_RETAINED=NO','VISIBLE_RECORDS_ARE_FILTERED_NOT_ALL_ALLOCATED_DECODERS']
 for row in rows:
  p=row['probes'];val=p['vdec_status']['value'] or {}
  lines.append('PHASE=%s SAMPLE=%d STATUS=%s VISIBLE=%s SOURCE=%s FRAME_PORT=%s STREAM_PORT=%s'%(
   row['phase'],row['sample'],val.get('classification','UNAVAILABLE'),val.get('visible_records'),
   p['source']['value'],(p['ports']['value'] or {}).get('amstream_dves_hevc_frame'),
   (p['ports']['value'] or {}).get('amstream_dves_hevc')))
 lines+=['ALLOCATION_OR_EL_FRAME_PROOF=NOT_ESTABLISHED','P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN',
         'GAZELLE_FEL_STAGE41_CAPTURE_COMPLETE']
 txtfile.write_text('\n'.join(lines)+'\n')
 with zipfile.ZipFile(zfile,'w',zipfile.ZIP_DEFLATED) as z:
  z.write(jsonfile,jsonfile.name);z.write(txtfile,txtfile.name)
 print('UPLOAD_FILE='+str(zfile))


def selftest():
 assert len(GATES)==25
 assert parse_status('No vdec.\n')['visible_records']==0
 a=parse_status('vdec channel 0 statistics:\nframe width : 3840\nvdec channel 1 statistics:\n')
 assert a['visible_records']==2 and a['channel_ordinals']==[0,1]
 assert parse_status('codec information only')['classification']=='UNPARSEABLE'
 assert parse_status('vdec channel 0 statistics:\nvdec channel 0 statistics:')['classification']=='AMBIGUOUS'
 assert parse_source('inst1: DV FORMAT_DOVI')=='DOVI'
 assert parse_source('inst1: HDR10 FORMAT_HDR10')=='HDR10'
 ports=parse_ports('amstream_dves_hevc_frame:\ntype:7441\nflag:267(Used)\namstream_dves_hevc:\ntype:6417\nflag:0\n')
 assert ports['amstream_dves_hevc_frame']['type']==0x1d11
 assert ports['amstream_dves_hevc']['type']==0x1911
 assert all(path.startswith('/sys/class/') for path in READS.values())
 print('GAZELLE_FEL_STAGE41_SOURCE_SELFTEST_PASS')


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 x=parser.add_mutually_exclusive_group(required=True)
 x.add_argument('--selftest',action='store_true')
 x.add_argument('--audit',type=Path)
 x.add_argument('--capture',action='store_true')
 parser.add_argument('--out',type=Path,default=Path.home()/'Downloads'/'gazelle-fel-stage41-results')
 args=parser.parse_args()
 selftest()
 if args.audit:audit(args.audit.expanduser().resolve())
 if args.capture:capture(args.out.expanduser())
if __name__=='__main__':
 try:main()
 except (ValueError,OSError,subprocess.CalledProcessError,zipfile.BadZipFile,EOFError,KeyboardInterrupt) as e:
  print('GAZELLE_FEL_STAGE41_FAIL',str(e),file=sys.stderr);sys.exit(1)
