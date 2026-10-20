#!/usr/bin/env python3
"""Gazelle FEL Stage42: original vdec/core all-connected vs status-listed decoder probe.

Offline original Amazon ELF audit + optional privacy-filtered, strictly read-only
idle/P8/P7 sampling. The original core sysfs text contains kernel addresses:
NEVER retain, print, transmit or save raw contents. Only counts and coarse
status classes can leave Python memory. Zero modifications to the Cube.
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

ZIP_SHA = '02f56e511dab017346ad0accf78024bcb0fc0ba2ecd1fbce81c38c07c1f37d44'
KO_SHA = 'a10f33ca4d3c0e8fd7aa58a495d64559a338f009e2652c238852a009d98a0c6b'
MEMBER = 'gazelle-fel-kernel-readonly-20261019-191050/modules/vendor_lib_modules_decoder_common.ko'
PHASES=('idle','P8','P7')
READ_PATHS = {
    'core':'/sys/class/vdec/core',
    'status':'/sys/class/vdec/vdec_status',
    'source':'/sys/class/amdolby_vision/src_format',
    'ports':'/sys/class/amstream/ports',
}
# Addresses/operand pairs in the owner's exact original kernel module.
# The core_show loop enumerates *connected* vdec objects; vdec_status_show
# filters by state, callback and callback result. Neither exposes master/slave.
GATES = {
    0x8a70:'adrp x8, 0x8000',
    0x8a74:'ldr x24, [x8]',
    0x8a7c:'bl 0x8a7c',
    0x8a80:'ldr x8, [x24]',
    0x8a8c:'cmp x24, x8',
    0x8a90:'b.eq 0x8b78',
    0x8aac:'ldr x25, [x24]',
    0x8ab4:'cmp x24, x25',
    0x8ab8:'b.eq 0x8ba0',
    0x8af8:'ldr x8, [x25, #0x18]',
    0x8b08:'bl 0x8b08',
    0x8b0c:'ldr x25, [x25]',
    0x8b14:'cmp x24, x25',
    0x8b18:'b.eq 0x8ba0',
    0x8b1c:'ldr w9, [x25, #0x150]',
    0x8b24:'ldr w8, [x25, #0x140]',
    0x8b28:'ldr w2, [x25, #0x28]',
    0x8b3c:'cmp w8, #0x3',
    0x8b40:'sub x3, x25, #0x8',
    0x8b58:'ldrsw x8, [x25, #0x148]',
    0x8ba0:'adrp x8, 0x8000',
    0x8bb0:'bl 0x8bb0',
    0x8e58:'add w22, w22, #0x1',
    0x8e5c:'ldr x21, [x21]',
    0x8e68:'ldr w8, [x21, #0x140]',
    0x8e6c:'and w8, w8, #0xfffffffe',
    0x8e70:'cmp w8, #0x2',
    0x8e74:'b.ne 0x8e5c',
    0x8ea8:'ldr x8, [x21, x8]',
    0x8eac:'cbz x8, 0x8c90',
    0x8eb4:'blr x8',
    0x8eb8:'cbz w0, 0x8c90',
}
RELOCS = {
    0x3a8:('R_AARCH64_ABS64','.rodata + 37ca'),
    0x3b8:('R_AARCH64_ABS64','.text + 8a44'),
    0x3c8:('R_AARCH64_ABS64','.rodata + 1efd'),
    0x3d8:('R_AARCH64_ABS64','.text + 8be0'),
    0x8a70:('R_AARCH64_ADR_PREL_PG_HI21','vdec_core.llvm.7425214269774233008 + 0'),
    0x8aa8:('R_AARCH64_CALL26','sprintf + 0'),
    0x8b08:('R_AARCH64_CALL26','sprintf + 0'),
    0x8bb0:('R_AARCH64_CALL26','_raw_spin_unlock_irqrestore + 0'),
}
LINE=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)
# The original format has leading tab and "vdec.%d (". Only extract the
# integer id to identify distinct entries; discard all pointers/states/strings.
CONNECTED=re.compile(r'^\s*vdec\.(\d{1,3})\s+\(',re.M)
REPORTABLE=re.compile(r'^vdec channel (\d{1,3}) statistics:\s*$',re.M)

def execute(*cmd):
    return subprocess.check_output(cmd,text=True,stderr=subprocess.PIPE)

def canonical(op):
    return re.sub(r'\s+','',op.split(' //',1)[0].split(' <',1)[0])

def section(binary,filename,name):
    rows=execute('readelf','-SW',str(filename)).splitlines()
    row=next((r for r in rows if re.search(r'\[\s*\d+\]\s+'+re.escape(name)+r'\s+PROGBITS',r)),None)
    m=re.search(re.escape(name)+r'\s+PROGBITS\s+\S+\s+(\S+)\s+(\S+)',row or '')
    if not m:raise ValueError('required section missing: '+name)
    at,length=[int(v,16) for v in m.groups()]
    if at+length>len(binary):raise ValueError('section beyond ELF')
    return binary[at:at+length]

def audit(archive):
    if not archive.is_file() or archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest()!=ZIP_SHA:
        raise ValueError('original owner kernel archive hash mismatch/missing')
    with zipfile.ZipFile(archive) as z:
        members=[r for r in z.infolist() if r.filename==MEMBER and not r.is_dir()]
        if len(members)!=1 or members[0].file_size!=4015344:
            raise ValueError('unexpected original decoder_common archive entry')
        original=z.read(members[0])
    if hashlib.sha256(original).hexdigest()!=KO_SHA or original[:7]!=b'\x7fELF\x02\x01\x01' or int.from_bytes(original[18:20],'little')!=183:
        raise ValueError('original kernel module SHA/ELF identity mismatch')
    for binary in ('llvm-objdump','readelf'):
        if not shutil.which(binary):raise ValueError('missing local offline binary: '+binary)
    with tempfile.TemporaryDirectory(prefix='gazelle-fel-stage42-') as t:
        p=Path(t)/'decoder_common.ko';p.write_bytes(original)
        symbols=execute('readelf','-Ws',str(p))
        for sym,addr,length,kind in (
            ('class_attr_core',0x3a8,32,'OBJECT'),
            ('class_attr_vdec_status',0x3c8,32,'OBJECT'),
            ('core_show',0x8a44,412,'FUNC'),
            ('vdec_status_show',0x8be0,868,'FUNC')):
            pattern=(r'^\s*\d+:\s*%016x\s+%d\s+%s\s+LOCAL\s+DEFAULT\s+\d+\s+%s\s*$'%
                     (addr,length,kind,re.escape(sym)))
            if not re.search(pattern,symbols,re.M):raise ValueError('original symbol mismatch: '+sym)
        data=section(original,p,'.data')
        ro=section(original,p,'.rodata')
        for attr in (0x3a8,0x3c8):
            if int.from_bytes(data[attr+8:attr+12],'little')!=0o444:
                raise ValueError('read-only sysfs mode 0444 mismatch')
        for off,literal in ((0x37ca,b'core\x00'),(0x1efd,b'vdec_status\x00'),
                            (0x1a52,b'\tvdec.%d ('),(0x1ee2,b'connected vdec list empty\n\x00')):
            if ro[off:off+len(literal)]!=literal:
                raise ValueError('original vdec/core format mismatch 0x%x'%off)
        reloc=execute('readelf','-rW',str(p))
        for addr,(kind,target) in RELOCS.items():
            lines=[r for r in reloc.splitlines() if re.match(r'^\s*%016x\s+'%addr,r)]
            if not any(kind in r and target in r for r in lines):
                raise ValueError('original relocation mismatch 0x%x'%addr)
        ins={}
        dis=execute('llvm-objdump','-d','--section=.text','--no-show-raw-insn',
                    '--start-address=0x8a44','--stop-address=0x8f44',str(p))
        for line in dis.splitlines():
            m=LINE.match(line)
            if m:ins[int(m[1],16)]=m[2]+' '+m[3]
        for at,expected in GATES.items():
            if canonical(ins.get(at,''))!=canonical(expected):
                raise ValueError('original instruction mismatch 0x%x: %s'%(at,ins.get(at)))
        print('PINNED_ORIGINAL_DECODER_COMMON_PASS')
        print('READONLY_SYSFS_ATTR_PASS core_0444_and_vdec_status_0444')
        print('ORIGINAL_CONNECTED_LIST_CODE_PASS core_show=0x8a44')
        print('ORIGINAL_STATUS_FILTER_CODE_PASS vdec_status_show=0x8be0')
        print('ORIGINAL_DEBUG_FORMAT_PASS vdec_id_only_parser_no_pointer_storage')
        print('GAZELLE_FEL_STAGE42_OFFLINE_GATES_PASS instructions=%d relocations=%d symbols=4'%(len(GATES),len(RELOCS)))
        print('CONNECTED_LIST=UNFILTERED_BY_STATUS_CALLBACK_BUT_ONLY_CONNECTED_DECODERS')
        print('NONCONNECTED_ALLOCATED_INSTANCE=NOT_EXCLUDED')
        print('P7_EL_FRAME_CONTRIBUTION=NOT_PROVEN')
        print('GAZELLE_FEL_STAGE42_ORIGINAL_CORE_OFFLINE_PASS')

def extract_core(raw):
    """Strict, privacy-reduced parser. Never return or print raw kernel pointers."""
    ids=[int(v) for v in CONNECTED.findall(raw)]
    if len(ids)>16 or len(ids)!=len(set(ids)):
        return {'status':'AMBIGUOUS','connected_records':None}
    if ids:
        if ' Core: last_sched ' not in raw and 'Core: last_sched ' not in raw:
            return {'status':'UNPARSEABLE','connected_records':None}
        return {'status':'CONNECTED_RECORDS','connected_records':len(ids)}
    if 'connected vdec list empty' in raw:
        return {'status':'EMPTY_CONNECTED_LIST','connected_records':0}
    return {'status':'UNPARSEABLE','connected_records':None}

def extract_status(raw):
    if re.search(r'\bNo vdec\s*\.',raw,re.I):return {'status':'NO_VDEC','reportable_records':0}
    ids=[int(v) for v in REPORTABLE.findall(raw)]
    if ids and len(ids)<=16 and len(set(ids))==len(ids):
        return {'status':'REPORTABLE_RECORDS','reportable_records':len(ids)}
    return {'status':'UNPARSEABLE','reportable_records':None}

def extract_source(raw):
    m=re.search(r'^inst1:\s*([^\n]{1,120})',raw,re.M)
    if not m:return 'UNKNOWN'
    if 'FORMAT_DOVI' in m[1]:return 'DOVI'
    if 'FORMAT_HDR10' in m[1]:return 'HDR10'
    if 'FORMAT_SDR' in m[1]:return 'SDR'
    return 'OTHER_OR_UNKNOWN'

def extract_ports(raw):
    result={}
    parts=re.split(r'(?=^amstream_[A-Za-z0-9_]+\s*:\s*$)',raw,flags=re.M)
    for block in parts:
        m=re.search(r'^\s*(amstream_dves_hevc(?:_frame)?)\s*:\s*$',block,re.M)
        if not m:continue
        v=re.search(r'^\s*type:(\d+)',block,re.M)
        f=re.search(r'^\s*flag:(\d+)',block,re.M)
        result[m[1]]={'port_type':int(v[1]) if v else None,'port_flag':int(f[1]) if f else None}
    return result

def adb_path():
    exe=shutil.which(os.environ['ADB']) if os.environ.get('ADB') else shutil.which('adb')
    if not exe:
        fallback='/Applications/adblink.app/Contents/MacOS/adbfiles/adb'
        exe=fallback if Path(fallback).is_file() else None
    if not exe:raise ValueError('ADB unavailable; install platform-tools or set ADB')
    r=subprocess.run([exe,'devices'],text=True,capture_output=True,timeout=12,errors='replace')
    devices=[ln.split() for ln in r.stdout.splitlines()[1:] if len(ln.split())==2 and ln.split()[1]=='device']
    if r.returncode or len(devices)!=1:raise ValueError('require exactly one authorized ADB device')
    return exe

def read(adb,key):
    if key not in READ_PATHS:raise ValueError('node not allowlisted')
    try:
        res=subprocess.run([adb,'shell',"su -c 'cat "+READ_PATHS[key]+"'"],
                           text=True,capture_output=True,timeout=12,errors='replace')
    except subprocess.TimeoutExpired:return {'read_status':'TIMEOUT','value':None}
    if res.returncode:return {'read_status':'UNAVAILABLE','value':None}
    raw=res.stdout.replace('\r','')
    if len(raw.encode('utf-8'))>32768:
        return {'read_status':'OVERSIZE','value':None}
    # raw only exists inside this function and is not written, logged or returned.
    parsed=({'core':extract_core,'status':extract_status,'source':extract_source,
             'ports':extract_ports}[key])(raw)
    return {'read_status':'OK','value':parsed}

def selftest():
    assert len(GATES)==32 and len(RELOCS)==8
    assert extract_core(' Core: last_sched 0xabcdef, sched_mask f\n\tvdec.0 (0xabcdef (hevc)), status = connected\n') == {'status':'CONNECTED_RECORDS','connected_records':1}
    assert extract_core(' Core: last_sched 0xabcdef\n\tvdec.0 (0x1)\n\tvdec.1 (0x2)\n')['connected_records']==2
    assert extract_core('connected vdec list empty\n')['connected_records']==0
    assert extract_core(' Core: last_sched 0xabcdef\n')['status']=='UNPARSEABLE'
    assert extract_core(' Core: last_sched 0xabcdef\n\tvdec.0 (0x1)\n\tvdec.0 (0x2)\n')['status']=='AMBIGUOUS'
    assert extract_status('vdec channel 0 statistics:\n')['reportable_records']==1
    assert extract_status('No vdec.\n')['reportable_records']==0
    assert '0xabcdef' not in json.dumps(extract_core(' Core: last_sched 0xabcdef\n\tvdec.0 (0xabcdef)\n'))
    assert extract_source('inst1: DV FORMAT_DOVI')=='DOVI'
    assert extract_source('inst1: HDR10 FORMAT_HDR10')=='HDR10'
    assert all(x.startswith('/sys/class/') for x in READ_PATHS.values())
    print('GAZELLE_FEL_STAGE42_SOURCE_SELFTEST_PASS')

def capture(out):
    adb=adb_path()
    rows=[]
    phase_instructions={'idle':'Stop all Kodi video playback',
                        'P8':'Play a known-working P8 video',
                        'P7':'Stop P8 and play the P7 FEL test'}
    for phase in PHASES:
        print('\n%s: %s. Press Enter to capture.'%(phase,phase_instructions[phase]),flush=True)
        input()
        for n in range(1,4):
            when=dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')
            probes={key:read(adb,key) for key in READ_PATHS}
            row={'phase':phase,'sample':n,'timestamp_utc':when,'probes':probes}
            rows.append(row)
            c=(probes['core']['value'] or {}).get('connected_records')
            s=(probes['status']['value'] or {}).get('reportable_records')
            print('%s sample %s/3: connected=%s reportable=%s'%(phase,n,c,s),flush=True)
            if n<3:time.sleep(2)
    out.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
    stem='stage42-connected-decoder-'+stamp
    jsonfile=out/(stem+'.json');txtfile=out/(stem+'.txt');zipfile_name=out/(stem+'.zip')
    obj={'schema':'gazelle-fel-stage42-v1','device_writes':False,
         'raw_kernel_addresses_retained':False,'observations_non_atomic':True,
         'connected_list_not_all_allocated_instances':True,'observations':rows}
    jsonfile.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
    lines=['GAZELLE_FEL_STAGE42_CONNECTED_DECODER_CAPTURE','DEVICE_WRITES=NONE',
           'RAW_KERNEL_POINTERS_RETAINED=NO',
           'CORE_LIST_IS_CONNECTED_OBJECTS_NOT_ALL_ALLOCATED_DECODERS',
           'CORE_RECORDS_DO_NOT_PROVE_LINKED_EL_OR_RESIDUAL_PIXELS']
    for row in rows:
        probes=row['probes'];core=probes['core']['value'] or {};status=probes['status']['value'] or {}
        lines.append('PHASE=%s SAMPLE=%s SOURCE=%s CONNECTED=%s REPORTABLE=%s CORE_READ=%s CORE_CLASS=%s STATUS_CLASS=%s'%(
            row['phase'],row['sample'],probes['source']['value'],core.get('connected_records'),
            status.get('reportable_records'),probes['core']['read_status'],core.get('status'),status.get('status')))
    lines.extend(('P7_EL_DECODER=NOT_PROVEN','P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN',
                  'GAZELLE_FEL_STAGE42_CAPTURE_COMPLETE'))
    txtfile.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with zipfile.ZipFile(zipfile_name,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(jsonfile,jsonfile.name);z.write(txtfile,txtfile.name)
    print('UPLOAD_FILE='+str(zipfile_name))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    flags=p.add_mutually_exclusive_group(required=True)
    flags.add_argument('--selftest',action='store_true')
    flags.add_argument('--audit',type=Path)
    flags.add_argument('--capture',action='store_true')
    p.add_argument('--out',type=Path,default=Path.home()/'Downloads'/'gazelle-fel-stage42-results')
    a=p.parse_args()
    selftest()
    if a.audit:audit(a.audit.expanduser().resolve())
    elif a.capture:capture(a.out.expanduser())

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,zipfile.BadZipFile,subprocess.CalledProcessError,EOFError,KeyboardInterrupt) as e:
        print('GAZELLE_FEL_STAGE42_FAIL',str(e),file=sys.stderr);sys.exit(1)
