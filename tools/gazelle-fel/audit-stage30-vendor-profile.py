#!/usr/bin/env python3
"""Stage 30: original PS7702.4965N OMX profile/config ABI gates. Host-only."""
import argparse,hashlib,re,shutil,struct,subprocess,sys
from pathlib import Path

SHA={
 "libomx_framework_alt.so":"fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba",
 "libOmxVideo.so":"eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77",
}
# Exact address and instruction/operands of owner-provided ELF32 Thumb binaries.
F={
0x164c8:"movs r0, #0xb",0x164ca:"str.w r0, [r4, #0x3dc]",
0x18fdc:"movs r0, #0x1",0x18fde:"movt r0, #0x7f80",
0x18fe2:"cmp r6, r0",0x18fe8:"ldr r0, [r5, #0xc]",
0x18ff2:"str.w r0, [r4, #0x36c]",0x18ffa:"ldr r0, [r5, #0x10]",
0x18ffc:"str.w r0, [r4, #0x370]",0x194a2:"ldr r0, [r5, #0xc]",
0x194a4:"str r0, [r4, #0x20]",0x194a6:"ldr r1, [r5, #0x10]",
0x194a8:"str r1, [r4, #0x24]",
}
V={
0x1eb6e:"ldr.w r8, [r2, #0x36c]",0x1edaa:"ldr.w r0, [r0, #0x3dc]",
0x1edb2:"cmp r0, #0xb",0x1edb4:"bne 0x1ee5c",
0x1edce:"b 0x1ef1c",0x1ee5c:"cmp.w r8, #0x400",
0x30958:"ldr r2, [r1, #0x20]",0x3095a:"cmp.w r2, #0x400",
0x30960:"ldr.w r1, [r1, #0x3dc]",0x3096a:"cmp r1, r2",
0x30986:"bl 0x66b44",0x309a4:"bl 0x66b54",
0x309ce:"b.w 0x66b64",0x309d2:"b.w 0x66b74",
0x281c4:"cmp r1, #0xb",0x281e4:"movw r1, #0x10b4",
0x281ea:"mov.w r1, #0x200",0x281f4:"ldr.w r1, [r4, #0x190]",
0x281fa:"movw r5, #0x12b4",0x28202:"ldrb.w r0, [r0, #0x35d]",
0x2820c:"cmp r0, #0xc",0x2820e:"beq 0x28236",
0x28214:"ldr.w r2, [pc, #0x6c4]",0x2821a:"add r2, pc",
0x28224:"mov.w r1, #0xffffffff",
0x21ac8:"ldr r0, [r0, #0x20]",0x21aca:"cmp r0, #0x10",
0x21acc:"bne.w 0x21d82",0x21ad4:"ldr.w r2, [pc, #0x4f8]",
0x21ada:"add r2, pc",0x21ae4:"mov.w r1, #0xffffffff",
0x590d0:"mov.w r0, #0x10a0",0x590d8:"ldr.w r2, [r8, r0]",
0x58ce6:"cmp r2, #0x1",0x58cea:"moveq r0, r3",
}
STRINGS=[
(0x288d8,0x281ee,"hevc_buf_width:%d;hevc_buf_height:%d;hevc_buf_margin:%d;hevc_double_write_mode:%d"),
(0x288dc,0x2821a,"negative_dv:1;"),
(0x21fd0,0x21ada,"dv_duallayer:1;"),
]
LINE=re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)',re.I)

def norm(x):
 return re.sub(r'\s+','',x.split(' @ ',1)[0].split(' <',1)[0])

def elf(root,name):
 p=root/name
 if not p.is_file() or p.is_symlink():raise ValueError("missing/symlink "+name)
 b=p.read_bytes()
 if hashlib.sha256(b).hexdigest()!=SHA[name]:raise ValueError("wrong vendor sha "+name)
 if b[:7]!=b'\x7fELF\x01\x01\x01' or int.from_bytes(b[18:20],'little')!=40:
  raise ValueError("not ELF32 ARM "+name)
 print("PINNED_VENDOR_ELF_PASS",name)
 return p,b

def ops(path,checks):
 exe=shutil.which("llvm-objdump")
 if not exe:raise ValueError("llvm-objdump missing; brew install llvm")
 ins={}
 addresses=sorted(checks)
 start=last=addresses[0];groups=[]
 for n in addresses[1:]:
  if n-last>0x250:groups.append((start,last+4));start=n
  last=n
 groups.append((start,last+4))
 for lo,hi in groups:
  listing=subprocess.check_output([exe,"-d","--triple=thumbv7a-linux-android",
   "--start-address=0x%x"%lo,"--stop-address=0x%x"%hi,str(path)],
   stderr=subprocess.PIPE,text=True)
  for line in listing.splitlines():
   m=LINE.match(line)
   if m:ins[int(m[1],16)]=m[2]+" "+m[3]
 for addr,expected in checks.items():
  if norm(ins.get(addr,""))!=norm(expected):
   raise ValueError("instruction mismatch "+path.name+" "+hex(addr)+" "+ins.get(addr,"?"))

def literal(b,loc,add):
 val=struct.unpack_from('<i',b,loc-0x2000)[0]
 va=(add+4+val)&0xffffffff
 if not 0x69b90<=va<0xaafd0:raise ValueError("string outside pinned rodata")
 return b[va-0x2000:va-0x2000+140].split(b'\0',1)[0].decode('ascii')

def audit(root):
 fw,_=elf(root,"libomx_framework_alt.so")
 video,data=elf(root,"libOmxVideo.so")
 ops(fw,F);ops(video,V)
 for loc,add,expected in STRINGS:
  found=literal(data,loc,add)
  if found!=expected:raise ValueError("string differs @"+hex(loc))
  print("PINNED_CONFIG_STRING_PASS",found)
 print("GAZELLE_FEL_STAGE30_ORIGINAL_VENDOR_PASS instruction_gates=48 config_literals=3 modules=2")
 print("DV_OMX_PROFILE_OFFSET=0x36c")
 print("AMLOGIC_PROFILE_OFFSET=0x20")
 print("DVHE_SUBTYPE_OFFSET=0x3dc")
 print("HEVC_DVHE_PROFILE_0x400_TEST=CONDITIONALLY_BYPASSED_FOR_SUBTYPE_0x0b")
 print("AWESOME_CONFIG=HEVC_FIELDS_AND_CONDITIONAL_NEGATIVE_DV")
 print("LEGACY_CONFIG=CONDITIONAL_DV_DUALLAYER")
 print("P7_RUNTIME_CONFIG_CONTENT=NOT_MEASURED")
 print("P7_HDR10_CAUSE=NOT_PROVEN")
 print("P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN")
 print("GAZELLE_FEL_STAGE30_OFFLINE_PASS")

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("library_dir",type=Path,nargs="?")
 p.add_argument("--selftest",action="store_true")
 a=p.parse_args()
 assert len(SHA)==2 and len(F)==13 and len(V)==35 and len(STRINGS)==3
 assert norm("str.w r0, [r4, #0x36c] @ test")==norm(F[0x18ff2])
 print("GAZELLE_FEL_STAGE30_SOURCE_SELFTEST_PASS")
 if a.selftest:return
 if not a.library_dir:p.error("provide path containing original two .so libraries")
 audit(a.library_dir.expanduser().resolve())

if __name__=="__main__":
 try:main()
 except (OSError,ValueError,UnicodeError,AssertionError,struct.error,subprocess.CalledProcessError) as e:
  print("GAZELLE_FEL_STAGE30_OFFLINE_FAIL",e,file=sys.stderr)
  sys.exit(1)
