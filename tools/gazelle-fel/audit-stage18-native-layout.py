#!/usr/bin/env python3
"""Fire TV Cube Gazelle Stage 18 native decoder ABI auditor.

Offline-only: given a private original /vendor/lib/libOmxVideo.so, derive the
named codec_para_t field offsets from the vendor's own dump_codec_param()
logging instructions. Never calls the library, accesses a device, or writes ELF.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

SHA = 'eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77'
FIELDS = {
 'handle':0x0, 'cntl_handle':0x4,'sub_handle':0x8,'audio_utils_handle':0xc,
 'stream_type':0x10, 'has_video':0x14,'has_audio':0x14,'has_sub':0x14,'noblock':0x14,
 'video_type':0x18, 'audio_type':0x1c,'sub_type':0x20,
 'video_pid':0x24,'audio_pid':0x28,'sub_pid':0x2c,'audio_channels':0x30,
 'audio_samplerate':0x34,'vbuf_size':0x38,'abuf_size':0x3c,
 'am_sysinfo.format':0x40,'am_sysinfo.width':0x44,'am_sysinfo.height':0x48,
 'am_sysinfo.rate':0x4c,'am_sysinfo.extra':0x50,'am_sysinfo.status':0x54,
 'am_sysinfo.ratio':0x58,'am_sysinfo.ratio64':0x60,
 'packet_size':0x1084,'avsync_threshold':0x1088,'SessionID':0x1090,
 'dspdec_not_supported':0x1094,'switch_audio_flag':0x1098,
 'automute_flag':0x109c,'decoder_type':0x10a0, 'dves_type':0x10a4,
 'drmmode':0x10a8,'video_path':0x10ac,'receive_id':0x10b0,
 'config':0x10b4,'config_len':0x12b4,
}
FLAG_BITS={'has_video':0,'has_audio':1,'has_sub':2,'noblock':3}
SYM_START=0x588ac
SYM_STOP=0x58b36
TEXT_BIAS=0x2000
RO_LO=0x69b90
RO_HI=RO_LO+0x4143c
INSTRUCTION=re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z\d.]*)\s*(.*)')

def run(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def insns(raw):
    result=[]
    for line in raw.splitlines():
        m=INSTRUCTION.match(line)
        if m:
            result.append((int(m[1],16),m[2],m[3]))
    return result

def read_cstring(blob,addr):
    if not RO_LO <= addr < RO_HI:
        raise ValueError('format string outside pinned rodata at '+hex(addr))
    offset=addr-TEXT_BIAS
    ending=blob.find(b'\0',offset,offset+100)
    if ending<0: raise ValueError('missing short NUL-terminated logging string')
    return blob[offset:ending].decode('ascii')

def field_source(group,name):
    if name in FLAG_BITS:
        reads=[(a,o,t) for a,o,t in group if re.match(r'r0,\s*\[r4,\s*#0x14\]',t) and o.startswith('ldrb')]
        if len(reads)!=1:
            raise ValueError(name+': no exact source byte read')
        test=[(a,o,t) for a,o,t in group if ('r3' in t and (o in ('and','ubfx')))]
        if len(test)!=1:
            raise ValueError(name+': no single flag extract')
        inst=test[0][2]
        bit=FLAG_BITS[name]
        if bit==0 and not re.match(r'r3,\s*r0,\s*#0x1\b',inst):
            raise ValueError(name+': wrong bit 0 extraction')
        if bit>0 and not re.match(r'r3,\s*r0,\s*#0x%x,\s*#0x1\b'%bit,inst):
            raise ValueError(name+': wrong bit %d extraction'%bit)
        return reads[0][0],FIELDS[name],f'bit {bit} of byte'
    if name=='am_sysinfo.ratio64':
        x=[a for a,o,t in group if o=='ldrd' and re.match(r'r0,\s*r1,\s*\[r4,\s*#96\]',t)]
        if len(x)!=1:raise ValueError('ratio64 source instruction missing')
        return x[0],0x60,'64-bit, loaded via ldrd'
    if name=='config':
        x=[(a,o,t) for a,o,t in group if o in ('add','adds') and t=='r3, r4, r0']
        if len(x)!=1:raise ValueError('config address source instruction missing')
        prev=[(a,o,t) for a,o,t in group if a<x[0][0] and o.startswith('mov') and t=='r0, #0x10b4']
        if len(prev)!=1:raise ValueError('config address constant missing')
        return x[0][0],0x10b4,'inline pointer to string'
    hits=[]
    for a,o,t in group:
        if o.startswith('ldr') and re.match(r'r3,\s*\[r4',t):
            if re.fullmatch(r'r3,\s*\[r4\]',t):
                offset=0
            else:
                m=re.fullmatch(r'r3,\s*\[r4,\s*#(0x[0-9a-f]+|\d+)\]',t)
                if m:
                    offset=int(m[1],0)
                elif re.fullmatch(r'r3,\s*\[r4,\s*r0\]',t):
                    prior=[x for x in group if x[0]<a and x[1].startswith('mov') and re.match(r'r0,\s*#0x[0-9a-f]+$',x[2])]
                    if not prior:raise ValueError(name+': index setup missing')
                    offset=int(prior[-1][2].split('#')[1],0)
                else:raise ValueError(name+': unsupported source '+t)
            hits.append((a,offset))
    if len(hits)!=1:raise ValueError(name+': ambiguous logging data source '+repr(hits))
    return hits[0][0],hits[0][1],'32-bit field'

def audit(file):
    blob=file.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=SHA:raise ValueError('unsupported vendor SHA256')
    if blob[:7]!=b'\x7fELF\x01\x01\x01' or int.from_bytes(blob[18:20],'little')!=40:
        raise ValueError('not original little-endian 32-bit ARM ELF')
    sym=run('readelf','-Ws',str(file))
    if not re.search(r'\b000588ad\s+816\s+FUNC\s+GLOBAL\s+DEFAULT\s+\d+\s+dump_codec_param\b',sym):
        raise ValueError('expected exported logger address/size differs')
    code=insns(run('llvm-objdump','-d','--triple=thumbv7a-linux-android',
                   f'--start-address=0x{SYM_START:x}',f'--stop-address=0x{SYM_STOP:x}',str(file)))
    blocks=[]; current=[]
    for a,o,t in code:
        current.append((a,o,t))
        if ((o.startswith('bl') or o.startswith('b.')) and '0x658b4' in t):
            blocks.append(current);current=[]
    if len(blocks)!=40:
        raise ValueError('logger call count changed: '+str(len(blocks)))
    result=[]
    for block in blocks:
        loads=[(a,t) for a,o,t in block if o.startswith('ldr') and re.match(r'r2,\s*\[pc,',t) and '@ 0x' in t]
        adds=[a for a,o,t in block if o.startswith('add') and t=='r2, pc']
        if len(loads)!=1 or len(adds)!=1:
            raise ValueError('logger format address not unique')
        literal=int(re.search(r'@ 0x([0-9a-f]+)',loads[0][1])[1],16)
        if not 0x1d940 <= literal < 0x68084:raise ValueError('literal outside pinned .text')
        rel=struct.unpack_from('<i',blob,literal-TEXT_BIAS)[0]
        address=(rel+adds[0]+4)&0xffffffff
        message=read_cstring(blob,address)
        match=re.fullmatch(r'dump_codec_param: ([\w.]+)=%(?:d|u|s|llu)\n',message)
        if not match:raise ValueError('unexpected logging string '+repr(message))
        name=match[1]
        if name not in FIELDS or any(x['field']==name for x in result):
            raise ValueError('unexpected/duplicate field name '+name)
        load_addr,offset,note=field_source(block,name)
        if offset!=FIELDS[name]:
            raise ValueError(f'{name} expected {FIELDS[name]:#x} found {offset:#x}')
        result.append(dict(field=name,offset_hex=f'0x{offset:x}',
                           offset_decimal=offset,load_instruction=f'0x{load_addr:x}',kind=note))
    if set(x['field'] for x in result)!=set(FIELDS):
        raise ValueError('not all expected named fields found')
    # Independently check decoder init/metadata paths and their struct-relative field constants.
    native=insns(run('llvm-objdump','-d','--triple=thumbv7a-linux-android',
             '--start-address=0x594c0','--stop-address=0x594e8',str(file)))
    native+=insns(run('llvm-objdump','-d','--triple=thumbv7a-linux-android',
             '--start-address=0x5a1a0','--stop-address=0x5a1b9',str(file)))
    patterns={
      0x594c6:r'movw\s+r0,\s*#0x12b8',
      0x594ce:r'movw\s+r2,\s*#0x177',
      0x594d2:r'ldr\.w\s+r3,\s*\[r8,\s*r0\]',
      0x5a1a2:r'mov\.w\s+r1,\s*#0x12c0',
      0x5a1a6:r'movw\s+r2,\s*#0x179',
      0x5a1aa:r'str\s+r3,\s*\[r0,\s*r1\]',
    }
    lookup={a:o+' '+t for a,o,t in native}
    for a,p in patterns.items():
        if not re.search(p,lookup.get(a,'')):
            raise ValueError(f'init/EL metadata instruction mismatch at {a:#x}: {lookup.get(a)}')
    info=dict(sha256=SHA, logger_va='0x588ad',
              named_field_count=len(result),fields=result,
              bounds={'config_start':'0x10b4','config_len':'0x12b4',
                      'inline_config_span_bytes':0x200,'reset_value':'0x12b8',
                      'dolby_meta_with_el':'0x12c0',
                      'minimum_observed_context_bytes':0x12c4,
                      'exact_size':'UNKNOWN'},
              source='Original vendor log format addresses matched to original ARM loads',
              verified_init_instructions=len(patterns),
              note='Read-only static partial field map, NOT a complete C struct or safe allocation template')
    return info

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('library',nargs='?',type=Path)
    p.add_argument('--json',type=Path,help='write derived field data as JSON')
    p.add_argument('--selftest',action='store_true')
    args=p.parse_args()
    if args.selftest:
        assert len(FIELDS)==40 and FIELDS['config_len']-FIELDS['config']==512
        assert FLAG_BITS['noblock']==3 and 0x12c0+4==0x12c4
        print('GAZELLE_STAGE18_NATIVE_LAYOUT_SOURCE_SELFTEST_PASS')
        return
    if not args.library:p.error('supply exact original libOmxVideo.so or --selftest')
    data=audit(args.library)
    print('GAZELLE_STAGE18_VENDOR_SHA_PIN_PASS',SHA)
    for row in data['fields']:
        print(f'FIELD {row["offset_hex"]:>7s} {row["field"]:<28s} {row["kind"]}')
    print('AUDITED_LOGGING_CALLS=40')
    print('EXACT_FIELD_OFFSETS_VERIFIED=40')
    print('INIT_EL_METADATA_GATES_VERIFIED=6')
    print('INLINE_CONFIG_SPAN=512 (upper bound from neighboring config_len field)')
    print('EXACT_CONTEXT_SIZE=UNKNOWN; FULL_ABI_LAYOUT=NOT_VERIFIED')
    print('GAZELLE_FEL_STAGE18_NATIVE_LAYOUT_PASS')
    if args.json:args.json.write_text(json.dumps(data,indent=2)+'\n')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        print('GAZELLE_FEL_STAGE18_NATIVE_LAYOUT_FAIL',str(e),file=sys.stderr)
        sys.exit(1)