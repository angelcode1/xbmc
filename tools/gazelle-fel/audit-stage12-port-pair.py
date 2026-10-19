#!/usr/bin/env python3
"""Offline, read-only FEL port-type pairing audit for pinned Gazelle stream_input.ko.

Validates the original AArch64 kernel-module SHA, ELF port table, rodata name
relocations and second-decoder branch. Static ELF state is NOT live kernel state.
Never invokes adb, loads a module, or writes decoder/kernel settings.
"""
import argparse
import hashlib
import re
import struct
import subprocess
import sys
from pathlib import Path

SHA="fc6ef560f6d86d3359cf1f8b0a185971984e024b93818e19272e6e76ac04d14c"
EXPECTED={
  "amstream_hevc":0x0111,
  "amstream_hevc_frame":0x0d11,
  "amstream_dves_avc":0x1811,
  "amstream_dves_avc_frame":0x1c11,
  "amstream_dves_hevc":0x1911,
  "amstream_dves_hevc_frame":0x1d11,
}
GATES={
  0x15d0:r"mov\s+w8,\s*#0x50",
  0x1600:r"ldrb\s+w8,\s*\[x24\]",
  0x1604:r"tbz\s+w8,\s*#0x0,\s*0x1654",
  0x1610:r"bl\b",
  0x161c:r"ldr\s+w8,\s*\[x24\]",
  0x1620:r"tbnz\s+w8,\s*#0xa,\s*0x1654",
  0x1628:r"tbnz\s+w8,\s*#0xc,\s*0x1638",
  0x162c:r"bl\b",
  0x1630:r"tbz\s+w0,\s*#0x8,\s*0x1654",
  0x163c:r"bl\b",
  0x1644:r"str\s+x0,\s*\[x8,\s*#0x40\]",
}

def cmd(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)

def parse_sections(f):
    result={}
    for line in cmd("readelf","-SW",str(f)).splitlines():
        m=re.match(r"^\s*\[\s*\d+\]\s+(\.\w+)\s+\S+\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)",line)
        if m:
            result[m[1]]=tuple(int(x,16) for x in m.groups()[1:])
    if ".data" not in result or ".rodata" not in result:
        raise ValueError("Missing .data or .rodata")
    return result

def ports_symbol(f):
    matches=[]
    for line in cmd("readelf","-sW",str(f)).splitlines():
        m=re.match(r"^\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+OBJECT\s+LOCAL\s+DEFAULT\s+8\s+ports\s*$",line)
        if m:matches.append((int(m[1],16),int(m[2])))
    if matches!=[(0x5f0,0x50*19)]:
        raise ValueError("Port table changed: "+repr(matches))
    return matches[0]

def rodata_relocations(f):
    section=None
    names={}
    for line in cmd("readelf","-rW",str(f)).splitlines():
        hd=re.match(r"^Relocation section '([^']+)'",line)
        if hd:
            section=hd[1]
            continue
        if section!=".rela.data.userdata_mutex":continue
        m=re.match(r"^\s*([0-9a-f]+)\s+\S+\s+R_AARCH64_ABS64\s+\S+\s+\.rodata\s+\+\s+([0-9a-f]+)\s*$",line)
        if m:names[int(m[1],16)]=int(m[2],16)
    return names

def run(f):
    b=f.read_bytes()
    if b[:7]!=b"\x7fELF\x02\x01\x01" or int.from_bytes(b[18:20],"little")!=183:
        raise ValueError("Not little-endian AArch64 ELF64")
    got=hashlib.sha256(b).hexdigest()
    if got!=SHA:raise ValueError("UNSUPPORTED_BUILD sha256="+got)
    print("PINNED_MODULE_PASS sha256="+got)
    sections=parse_sections(f)
    _,data_off,_=sections[".data"]
    _,ro_off,ro_size=sections[".rodata"]
    ro=b[ro_off:ro_off+ro_size]
    start,size=ports_symbol(f)
    pointers=rodata_relocations(f)
    ports={}
    for index in range(size//0x50):
        base=start+index*0x50
        ptr=pointers.get(base)
        if ptr is None or ptr>=len(ro):raise ValueError("Missing name relocation "+str(index))
        end=ro.find(b"\x00",ptr)
        if end<0:raise ValueError("Unterminated name")
        name=ro[ptr:end].decode("ascii")
        if name in ports:raise ValueError("Duplicate device name")
        port_type=struct.unpack_from("<I",b,data_off+base+0x18)[0]
        ports[name]=(index,port_type)
    if len(ports)!=19 or any(ports.get(n,(None,None))[1]!=typ for n,typ in EXPECTED.items()):
        raise ValueError("Unexpected static port type table")
    print("PORT_TABLE_PASS entries=19 stride=0x50 type_offset=0x18")
    dis=cmd("llvm-objdump","-d","--no-show-raw-insn","--start-address=0x15d0","--stop-address=0x1654",str(f))
    lines={}
    for line in dis.splitlines():
        m=re.match(r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)",line)
        if m:lines[int(m[1],16)]=m[2]+" "+m[3]
    for addr,pat in GATES.items():
        if not re.search(pat,lines.get(addr,"")):raise ValueError("Branch instruction mismatch 0x%x: %s"%(addr,lines.get(addr)))
    reloc=cmd("readelf","-Wr",str(f))
    for addr,sym in [(0x1610,"vdec_create"),(0x162c,"vdec_get_debug_flags"),(0x163c,"vdec_create")]:
        if not re.search(r"^\s*%016x\s+\S+\s+R_AARCH64_CALL26\s+\S+\s+%s(?:\s|$)"%(addr,sym),reloc,re.M):
            raise ValueError("Call relocation mismatch: 0x%x %s"%(addr,sym))
    print("ALLOCATION_BRANCH_PASS instructions=11 relocations=3")
    for n in EXPECTED:
        i,t=ports[n]
        print("PORT idx=%02d name=%s initial_type=0x%04x bit10_skip=%d bit12_second=%d"%(i,n,t,bool(t&0x400),bool(t&0x1000)))
    frame=ports["amstream_dves_hevc_frame"][1]
    stream=ports["amstream_dves_hevc"][1]
    assert frame & 0x400 and frame & 0x1000
    assert not stream & 0x400 and stream & 0x1000
    print("FRAME_PORT=SECOND_DECODER_SKIPPED_BY_BIT10")
    print("STREAM_PORT=SECOND_DECODER_CREATION_ATTEMPT_IF_OPEN_SUCCEEDS")
    print("RUNTIME_PORT_TYPE=UNMEASURED FEL_RESIDUAL=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE12_PORT_PAIR_AUDIT_PASS")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("module",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    args=p.parse_args()
    if args.selftest:
        assert EXPECTED["amstream_dves_hevc"]&0x1000
        assert not EXPECTED["amstream_dves_hevc"]&0x400
        assert EXPECTED["amstream_dves_hevc_frame"]&0x400
        print("GAZELLE_FEL_STAGE12_SOURCE_SELFTEST_PASS")
        return
    if args.module is None:p.error("module path required")
    run(args.module.expanduser().resolve())

if __name__=="__main__":
    try:main()
    except (ValueError,AssertionError,OSError,subprocess.CalledProcessError) as exc:
        print("GAZELLE_FEL_STAGE12_PORT_PAIR_AUDIT_FAIL",exc,file=sys.stderr)
        sys.exit(1)
