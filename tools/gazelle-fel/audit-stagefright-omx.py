#!/usr/bin/env python3
"""Read-only Fire OS PS7702 Stagefright OMX forensic gate (known SHA binaries only)."""
import argparse
import hashlib
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

DIGESTS = {
    'libstagefright.so': '4a79e1ce3737307e4dd9d23dfdf5fa20c358c1a1ff090c362e7376020e07131e',
    'libstagefright_omx.so': '849f1dd58078216f59d0cd82da5f7b01b1ab09b2e1cf4a0ccb7e20861dd6389a',
    'libmedia_omx.so': '1b06ef4802acd0cb24099149f43c91422170cbdda34c861056324f2df987f44c',
}
INDEX = 0x7f00010d
INSTRUCTION_WINDOWS = {
    'libstagefright_omx.so': [
        (0x21562, 0x2156e, {0x21568: r'ldr\s+r3,\s*\[r0,\s*#0x1c\]', 0x2156a:r'blx\s+r3'}),
        (0x346e6, 0x346f6, {0x346f2:r'blx\s+r5'}),
        (0x35e58, 0x35e70, {0x35e68:r'blx\s+r6'}),
    ],
}
LINE = re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][\w.]*)\s*(.*)')

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('directory',type=Path)
    a.add_argument('--maps',type=Path,help='optional read-only prior media.codec /proc/<pid>/maps capture')
    args=a.parse_args()
    if not shutil.which('llvm-objdump'):
        a.error('llvm-objdump required')
    binaries={}
    for name,expected in DIGESTS.items():
        path=args.directory/name
        if not path.is_file():
            print('MISSING_LIBRARY '+name,file=sys.stderr);return 2
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected:
            print('UNSUPPORTED_BINARY '+name,file=sys.stderr);return 2
        binaries[name]=data
        print('ELF_SHA_PASS '+name)
    data=binaries['libstagefright_omx.so']
    # Thumb PC-relative string loads and adds in OMXMaster::addVendorPlugin.
    for literal,add_insn,expected in [
        (0x1ebec,0x1eb80,b'libstagefrighthw.so\0'),
        (0x1ebf8,0x1ebb4,b'libstagefrightdolby.so\0'),
    ]:
        displacement=struct.unpack_from('<i',data,literal-0x3000)[0]
        ro_vaddr=add_insn+4+displacement
        offset=ro_vaddr-0x3000
        if data[offset:offset+len(expected)]!=expected:
            print('PLUGIN_POINTER_FAIL '+expected.decode(errors='replace'),file=sys.stderr);return 1
        print('PLUGIN_CALL_TARGET_PASS '+expected[:-1].decode()+' at rodata '+hex(ro_vaddr))
    if b'createOMXPlugin\0' not in data:
        print('OMX_PLUGIN_SYMBOL_FAIL',file=sys.stderr);return 1
    for name,windows in INSTRUCTION_WINDOWS.items():
        for start,stop,checks in windows:
            txt=subprocess.check_output([
                'llvm-objdump','-d','--triple=thumbv7a-linux-android',
                f'--start-address={start:#x}',f'--stop-address={stop:#x}',
                str(args.directory/name)
            ],text=True)
            ins={}
            for row in txt.splitlines():
                m=LINE.match(row)
                if m:ins[int(m[1],16)]=m[2]+' '+m[3]
            for address,rx in checks.items():
                actual=ins.get(address,'')
                if not re.search(rx,actual):
                    print(f'FORWARD_FAIL {name} {address:#x}: {actual}',file=sys.stderr)
                    return 1
            print(f'OMX_FORWARD_PASS {name} {start:#x}')
    for name,data in binaries.items():
        found=data.count(struct.pack('<I',INDEX))
        print(f'RAW_INDEX_COUNT {name} {INDEX:#x} {found}')
    print('NOTE: lack of raw literal does not exclude constructed indices or calls in other libraries')
    if args.maps:
        text=args.maps.read_text(errors='replace')
        for name in ['libstagefrighthw.so','libstagefrightdolby.so']:
            print(f'ACTIVE_MAP_LINES {name} '+str(sum(name in s for s in text.splitlines())))
        print('NOTE: map absence does not prove the library is missing from disk or never loaded')
    print('STAGEFRIGHT_OFFLINE_PASS')
    print('Runtime vendor parameter values and FEL contribution NOT verified')
    return 0

if __name__=='__main__':sys.exit(main())
