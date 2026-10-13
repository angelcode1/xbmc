#!/usr/bin/env python3
"""Read-only ARM32 OMX ELF: find PC-literal-plus-PC string references.

Requires readelf and llvm-objdump. No binary modification, device I/O or injection.
Does not cover every Thumb addressing mode, GOT/dataflow, dynamic calls or runtime writes.
"""
import argparse
import re
import struct
import subprocess
from pathlib import Path


def sections(path):
    result = {}
    data = subprocess.check_output(['readelf', '-SW', str(path)], text=True)
    for line in data.splitlines():
        m = re.search(r'\[\s*\d+\]\s+(\.[\w.]+)\s+\w+\s+([a-f\d]+)\s+([a-f\d]+)\s+([a-f\d]+)\s+', line)
        if m:
            result[m.group(1)] = tuple(int(s, 16) for s in m.groups()[1:])
    return result


def scan(path, needle):
    raw = path.read_bytes()
    sec = sections(path)
    if '.rodata' not in sec or '.text' not in sec:
        raise RuntimeError('Missing .rodata or .text')
    roaddr, rooff, rosize = sec['.rodata']
    codeaddr, codeoff, codesize = sec['.text']
    ro = raw[rooff:rooff + rosize]
    targets = [roaddr + i for i in range(len(ro)) if ro.startswith(needle, i)]
    if not targets:
        print(f'NO_STRING: {needle!r}')
        return
    disasm = subprocess.check_output([
        'llvm-objdump', '-d', '--triple=thumbv7a-linux-android', str(path)], text=True)
    func = '<unknown>'
    insns = []
    for line in disasm.splitlines():
        mf = re.match(r'^([a-f\d]{6,})\s+<([^>]+)>:', line)
        if mf:
            func = mf.group(2)
            continue
        mi = re.match(r'^\s*([a-f\d]{5,}):\s+[a-f\d ]+\s+([a-z][a-z\d.]*)\s*(.*)', line)
        if mi:
            insns.append((int(mi.group(1), 16), mi.group(2), mi.group(3), func))
    hits = set()
    for index, (addr, op, operand, parent) in enumerate(insns):
        if not op.startswith('ldr'):
            continue
        m = re.search(r'^([a-z\d]+),\s*\[pc,.*\]\s+@ (0x[a-f\d]+)', operand)
        if not m:
            continue
        reg, literal_va = m.group(1), int(m.group(2), 16)
        if not (codeaddr <= literal_va and literal_va + 4 <= codeaddr + codesize):
            continue
        val = struct.unpack_from('<I', raw, codeoff + literal_va - codeaddr)[0]
        for next_addr, next_op, next_args, _ in insns[index + 1:index + 8]:
            if next_addr - addr > 32:
                break
            if next_op in ('add', 'add.w') and re.match(rf'^{re.escape(reg)},\s*pc\b', next_args):
                target = (val + next_addr + 4) & 0xffffffff
                if target in targets:
                    hits.add((parent, addr, next_addr, target))
                break
    for target in targets:
        print(f'STRING VA=0x{target:x} literal={needle.decode("utf-8", "replace")}')
    if not hits:
        print('NO_PC_LITERAL_XREF_FOUND (does not establish runtime non-use)')
    for name, load, add, target in sorted(hits):
        print(f'XREF: {name}: LDR=0x{load:x} ADD_PC=0x{add:x} STRING=0x{target:x}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library', type=Path)
    parser.add_argument('--needle', default='dv_duallayer:1;')
    args = parser.parse_args()
    scan(args.library, args.needle.encode())
