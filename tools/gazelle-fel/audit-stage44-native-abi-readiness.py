#!/usr/bin/env python3
"""Stage44: SHA-pinned Fire OS native decoder ABI and FEL-only experiment no-go gate.

Offline original owner ARM32 ELFs only. No ADB, OMX invocation, decoder writes,
Kodi changes or P7 test. Original binaries are not committed or redistributed.
"""
import argparse, hashlib, pathlib, re, subprocess, sys
SHA={
 'libOmxVideo.so':'eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77',
 'libomx_framework_alt.so':'fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba',
}
SYMBOLS={
 'codec_init':(0x58bdd,2988),'codec_write':(0x597d1,6),
 'codec_close':(0x597dd,108),'codec_checkin_pts':(0x5986f,20),
 'codec_checkin_pts_us64':(0x59885,80),'codec_set_dvmetawithel':(0x5a1a1,26),
}
GATES={
 'libOmxVideo.so':{
 0x58cd2:'mov.w r0, #0x10a0',0x58cda:'ldr.w r2, [r8, r0]',
 0x58ce6:'cmp r2, #0x1',0x58ce8:'it eq',0x58cea:'moveq r0, r3',
 0x58cec:'bl 0x67d14',
 0x590d0:'mov.w r0, #0x10a0',0x590d8:'ldr.w r2, [r8, r0]',
 0x597d0:'ldr r0, [r0]',0x597d2:'b.w 0x67dc4',
 0x597dc:'push {r4, r5, r6, lr}',0x597e0:'ldrb r0, [r4, #0x14]',
 0x59800:'ldr r0, [r4, #0x8]',0x59810:'ldr r0, [r4, #0x4]',
 0x5981c:'mov.w r0, #0xffffffff',0x59820:'str r0, [r4, #0x4]',
 0x59826:'ldr r0, [r4]',0x5982c:'mov.w r1, #0xffffffff',
 0x59830:'str r1, [r4]',
 0x5986e:'ldr r0, [r0]',0x59870:'mov r3, r1',
 0x59872:'movw r1, #0x53c2',0x59876:'mov.w r2, #0x10e',
 0x5987a:'movt r1, #0x4010',0x5987e:'b.w 0x67d94',
 0x5988a:'strd r2, r3, [sp]',0x5989c:'ldr r0, [r0]',
 0x5989e:'movt r1, #0x4004',0x598a2:'bl 0x67d34',
 0x598a6:'cmp.w r0, #0xffffffff',
 0x5a1a2:'mov.w r1, #0x12c0',0x5a1a6:'movw r2, #0x179',
 0x5a1aa:'str r3, [r0, r1]',0x5a1b0:'ldr r0, [r0]',
 },
 'libomx_framework_alt.so':{
 0x16832:'movs r0, #0x1',0x16834:'strb.w r0, [r4, #0x10a]',
 0x16886:'movs r0, #0x0',0x16888:'strb.w r0, [r4, #0x10a]',
 0x1a1e0:'strh.w r8, [r4, #0x109]',
 }
}
ROW=re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
def norm(x):return re.sub(r'\s+','',x.split(' @',1)[0].split(' //',1)[0].split(' <',1)[0])
def selftest():
 assert len(SHA)==2 and len(SYMBOLS)==6 and sum(map(len,GATES.values()))==39
 assert 0x12c0+4==0x12c4 and 0x10b4+0x200==0x12b4
 assert 0x1d11 & 0x400 and not (0x1911 & 0x400)
 print('GAZELLE_FEL_STAGE44_SOURCE_SELFTEST_PASS')
def audit(directory):
 for name,digest in SHA.items():
  p=directory/name
  if not p.is_file() or p.is_symlink():raise ValueError('private original ELF absent: '+name)
  raw=p.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=digest or raw[:7]!=b'\x7fELF\x01\x01\x01' or int.from_bytes(raw[18:20],'little')!=40:
   raise ValueError('original 32-bit ARM ELF identity differs: '+name)
  print('PINNED_ORIGINAL_VENDOR_ELF_PASS',name)
  if name=='libOmxVideo.so':
   sym=run('readelf','-Ws',str(p))
   for symbol,(address,size) in SYMBOLS.items():
    pat=rf'^\s*\d+:\s*{address:08x}\s+{size}\s+FUNC\s+GLOBAL\s+DEFAULT\s+12\s+{symbol}\s*$'
    if not re.search(pat,sym,re.M):raise ValueError('native symbol changed '+symbol)
   needed=re.findall(r'\(NEEDED\)\s+Shared library:',run('readelf','-d',str(p)))
   if len(needed)!=21:raise ValueError('native dependency count changed')
   print('NATIVE_EXPORT_SYMBOLS_PASS count=6 dependency_count=21')
  dis=run('llvm-objdump','--triple=thumbv7-unknown-linux-android',
          '-d','--no-show-raw-insn',str(p))
  inst={}
  for line in dis.splitlines():
   m=ROW.match(line)
   if m:inst[int(m[1],16)]=m[2]+' '+m[3]
  for at,expect in GATES[name].items():
   if norm(inst.get(at,''))!=norm(expect):
    raise ValueError('Thumb gate mismatch %s 0x%x: %s'%(name,at,inst.get(at)))
  print('ORIGINAL_THUMB_CONTRACT_PASS',name,'instructions',len(GATES[name]))
 print('CODEC_INIT_MODE_WORD=codec_para_plus_0x10a0')
 print('MODE_EQ_1_SELECTS=DV_HEVC_FRAME_DEVICE')
 print('MODE_OTHERWISE_SELECTS=DV_HEVC_STREAM_DEVICE_ON_AUDITED_BRANCH')
 print('CODEC_WRITE=BARE_FD_WRITE_WRAPPER_NOT_PACKET_OR_PTS_CONTRACT')
 print('PTS_API=THIRTY_TWO_BIT_0x10e_AND_SEPARATE_US64_IOCTL')
 print('CODEC_CLOSE=CONDITIONAL_AUX_HANDLES_AND_PRIMARY_FD_CLEANUP')
 print('EL_METADATA_FLAG=context_plus_0x12c0_separate_0x179_ioctl')
 print('FRAMEWORK_MODE_BYTE=OMX_OWNER_PLUS_0x10a_WITH_OVERLAPPING_SET_PARAMETER_HALFWORD')
 print('NATIVE_CONTEXT_MIN_EXTENT=0x12c4_NOT_COMPLETE_STRUCT_SIZE')
 print('NATIVE_LINKER_NAMESPACE_AND_SELINUX=NOT_TESTED')
 print('NATIVE_STREAM_PACKET_FORMAT_AND_PTS_TIMING=NOT_PROVEN')
 print('SUPPORTABLE_KODI_PER_INSTANCE_MODE_SELECTOR=NOT_IDENTIFIED')
 print('NATIVE_STREAM_BACKEND_IMPL=BLOCKED_NO_SAFE_RUNTIME_TEST')
 print('P7_EL_DECODER_AND_RPU_HANDSHAKE=NOT_PROVEN')
 print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
 print('GAZELLE_FEL_STAGE44_ORIGINAL_ABI_OFFLINE_PASS')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('private_original_vendor_dir',type=pathlib.Path,nargs='?')
 p.add_argument('--selftest',action='store_true')
 a=p.parse_args();selftest()
 if not a.selftest:
  if not a.private_original_vendor_dir:p.error('pass private original vendor ELF directory')
  audit(a.private_original_vendor_dir.expanduser().resolve())
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,subprocess.CalledProcessError,AssertionError) as exc:
  print('GAZELLE_FEL_STAGE44_FAIL',exc,file=sys.stderr);sys.exit(1)
