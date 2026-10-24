#!/usr/bin/env python3
"""Bounded exact-original Amlogic P7 input-mode store audit; NO device actions.

Only confirms immediate-offset stores to mode bytes in pinned ARM32 vendor ELFs.
Untracked pointer aliasing/indirect writes and native runtime are NOT proven absent.
Do not commit vendor ELF, disassembly or private device paths.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

SPECS = {
    "libOmxVideo.so": {
        "sha256": "eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77",
        "offsets": {0xdc, 0xdd},
        "writes": {
            0x1de74: ("strh.w", 0xdd), 0x1de7c: ("strb.w", 0xdc),
            0x1ef9a: ("strb.w", 0xdd), 0x26130: ("strb.w", 0xdc),
            0x26138: ("strb.w", 0xdd), 0x26192: ("strb.w", 0xdd),
            0x287dc: ("strb.w", 0xdd), 0x31efa: ("strb.w", 0xdd),
            0x32512: ("strb.w", 0xdd), 0x32e9a: ("strb.w", 0xdd),
            0x33368: ("strb.w", 0xdd), 0x338c8: ("strb.w", 0xdc),
            0x3398e: ("strb.w", 0xdc), 0x339cc: ("strb.w", 0xdd),
            0x391fa: ("strh.w", 0xdd), 0x391fe: ("strb.w", 0xdc),
            0x4d70c: ("str.w", 0xdc), 0x3d798: ("strb.w", 0xdc),
            0x3d7a0: ("strb.w", 0xdd),
        },
        "forbid_method": "setParameter",
    },
    "libomx_framework_alt.so": {
        "sha256": "fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba",
        "offsets": {0x109, 0x10a},
        "writes": {
            0x163d4: ("str.w", 0x109), 0x16572: ("strb.w", 0x109), 0x16780: ("strb.w", 0x109),
            0x16834: ("strb.w", 0x10a), 0x16888: ("strb.w", 0x10a),
            0x16c4e: ("strb.w", 0x109), 0x1a1e0: ("strh.w", 0x109),
        },
        "only_method": "OmxVideoDecoderC",
    },
}
DISASM = re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4,8}\s+)+([a-z][a-z0-9.]*)\s+[^\n]*?\[r\d+, #0x([0-9a-f]+)\]', re.I)
SYMBOL = re.compile(r'^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+\S+\s+\S+\s+\S+\s+(\S+)', re.M)


def parse_writes(disasm: str, offsets: set[int]) -> dict[int, tuple[str,int]]:
    found = {}
    for line in disasm.splitlines():
        m = DISASM.match(line)
        if not m:
            continue
        addr, inst, off = int(m[1],16), m[2], int(m[3],16)
        if not inst.startswith(('strb', 'strh', 'str')):
            continue
        width = 1 if inst.startswith('strb') else 2 if inst.startswith('strh') else 4
        if any(off <= target < off + width for target in offsets):
            if addr in found:
                raise ValueError(f'duplicate parsed store at 0x{addr:x}')
            found[addr] = (inst, off)
    return found


def owner_map(readelf: str, addresses: set[int]) -> dict[int,str]:
    symbols = []
    for m in SYMBOL.finditer(readelf):
        addr, length, name = int(m[1], 16) & ~1, int(m[2]), m[3]
        if length > 0:
            symbols.append((addr, addr+length, name))
    result = {}
    for address in addresses:
        candidates = [(hi-lo, name) for lo,hi,name in symbols if lo <= address < hi]
        if not candidates:
            raise ValueError(f'unknown original function for 0x{address:x}')
        result[address] = min(candidates)[1]
    return result


def check(spec: dict, disasm: str, syms: str) -> dict:
    observed = parse_writes(disasm,spec['offsets'])
    if observed != spec['writes']:
        missing = sorted(set(spec['writes'])-set(observed))
        unexpected = sorted(set(observed)-set(spec['writes']))
        changed = sorted(a for a in observed.keys() & spec['writes'].keys() if observed[a] != spec['writes'][a])
        raise ValueError(f'original direct-writer map mismatch missing={missing} unexpected={unexpected} changed={changed}')
    owners = owner_map(syms,set(observed))
    if spec.get('only_method'):
        expected_zero = ('19e66: f04f 0800', '1a1e0: f8a4 8109')
        if any(token not in disasm for token in expected_zero):
            raise ValueError('expected MVC setter zero-valued source/store witnesses missing')
    if spec.get('forbid_method') and any(spec['forbid_method'] in s for s in owners.values()):
        raise ValueError('native mode has directly mapped writes in setParameter')
    if spec.get('only_method'):
        for address,name in owners.items():
            if spec['only_method'] not in name and not (address == 0x1a1e0 and 'setParameter' in name):
                raise ValueError(f'framework unexpected writer owner 0x{address:x} {name}')
    return {
        'direct_writers': len(observed),
        'bounded_writer_functions': sorted(set(owners.values())),
        'setter_direct_store': 'MVC_zero_pair_only' if spec.get('only_method') else 'none',
        'decoding_or_runtime_proven': False,
    }


def selftest() -> None:
    sample='''   1234: f884 0109     strb.w r0, [r4, #0x109]\n   1238: f8a4 8109     strh.w r8, [r4, #0x109]\n   123c: f8c4 0108     str.w r0, [r4, #0x108]\n'''
    actual=parse_writes(sample,{0x109,0x10a})
    assert actual=={0x1234:('strb.w',0x109),0x1238:('strh.w',0x109),0x123c:('str.w',0x108)},actual
    assert parse_writes(sample,{0xdc,0xdd})=={}
    try:
        check({'offsets':{0x109},'writes':{0x1234:('strb.w',0x109)},'only_method':'constructor'},sample,'')
        raise AssertionError('mutation not rejected')
    except ValueError:
        pass
    try:
        owner_map('   10: 00000100 64 FUNC GLOBAL DEFAULT 12 SampleConstructor\n',{0x222})
        raise AssertionError('out of bounds mapping')
    except ValueError:
        pass
    print('GAZELLE_FEL_PINNED_MODE_WRITER_SELFTEST_PASS synthetic=true original_elf=false')


def run_elf(name:str, path:Path, objdump:str, readelf:str) -> dict:
    spec=SPECS[name]
    if not path.is_file() or path.stat().st_size>32_000_000:
        raise ValueError(f'refuse absent/oversized ELF: {name}')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != spec['sha256']:
        raise ValueError(f'{name} original SHA256 mismatch; never reuse offsets')
    disasm=subprocess.run([objdump,'-d','--triple=thumbv7-linux-gnueabihf',str(path)],capture_output=True,text=True,check=True,timeout=60).stdout
    symbols=subprocess.run([readelf,'-Ws',str(path)],capture_output=True,text=True,check=True,timeout=15).stdout
    audit=check(spec,disasm,symbols)
    return {'name':name,'sha256':digest,**audit}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--video',type=Path)
    ap.add_argument('--framework',type=Path)
    ap.add_argument('--report',type=Path,help='new report path; never overwrite')
    ap.add_argument('--llvm-objdump',default=shutil.which('llvm-objdump'))
    ap.add_argument('--readelf',default=shutil.which('readelf'))
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    if not(args.video and args.framework and args.report and args.llvm_objdump and args.readelf):
        ap.error('--video, --framework, --report, llvm-objdump and readelf required')
    if args.report.exists():
        ap.error('report exists; refusing overwrite')
    data={
      'scope':'exact original immediate-offset stores only; indirect/alias writes and runtime NOT excluded',
      'claimed_safe_per_instance_setter':False,
      'approved_for_device':False,
      'files':[run_elf('libOmxVideo.so',args.video,args.llvm_objdump,args.readelf),
               run_elf('libomx_framework_alt.so',args.framework,args.llvm_objdump,args.readelf)],
    }
    args.report.write_text(json.dumps(data,indent=2)+'\n')
    print('GAZELLE_FEL_PINNED_MODE_WRITER_ORIGINAL_PASS no_device=true source_only=true native_fel=false')
    return 0

if __name__=='__main__':
    raise SystemExit(main())