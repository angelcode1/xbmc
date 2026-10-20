#!/usr/bin/env python3
"""Gazelle FEL Stage31: original Fire OS config submission and error-path gates.

Offline ELF inspection only. No library execution, ADB, ioctl, or device writes.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

PIN = 'eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77'
GATES = {
    0x281c4:'cmp r1, #0xb',
    0x281c6:'bne.w 0x284ea',
    0x281ca:'ldrb.w r1, [r4, #0xdc]',
    0x281ce:'cmp r1, #0x0',
    0x281d0:'beq.w 0x284a2',
    0x281e4:'movw r1, #0x10b4',
    0x281ea:'mov.w r1, #0x200',
    0x281fa:'movw r5, #0x12b4',
    0x281fe:'str r0, [r1, r5]',
    0x28202:'ldrb.w r0, [r0, #0x35d]',
    0x28206:'cbnz r0, 0x28210',
    0x28208:'ldr.w r0, [r4, #0x13c]',
    0x2820c:'cmp r0, #0xc',
    0x2820e:'beq 0x28236',
    0x28214:'ldr.w r2, [pc, #0x6c4]',
    0x2821e:'movw r1, #0x10b3',
    0x28224:'mov.w r1, #0xffffffff',
    0x28234:'str r0, [r1, r5]',
    0x591ac:'bl 0x5aa64',
    0x591b2:'cmp.w r4, #0xffffffff',
    0x591b6:'ble 0x59228',
    0x59406:'bl 0x5aa64',
    0x5940c:'cmp.w r4, #0xffffffff',
    0x59410:'ble.w 0x5964e',
    0x5aa9e:'movw r0, #0x12b4',
    0x5aaa2:'ldr.w r0, [r8, r0]',
    0x5aaa6:'cbz r0, 0x5aadc',
    0x5aaaa:'movw r0, #0x10b4',
    0x5aaae:'movw r1, #0x53c6',
    0x5aab4:'movw r2, #0x301',
    0x5aaba:'movt r1, #0x4010',
    0x5aac4:'bl 0x67d94',
    0x5aac8:'cmp.w r0, #0xffffffff',
    0x5aacc:'bgt 0x5aadc',
    0x5aad8:'bl 0x658b4',
    0x5aadc:'movs r0, #0x0',
    0x5aade:'b 0x5aae4',
}
SOURCE_RE = re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z0-9.]*)\s*(.*)', re.I)

def normalized(t):
    return re.sub(r'\s+', '', t.split(' @ ', 1)[0].split(' <', 1)[0])

def expected_flag(hevc, auxiliary_mode_enabled, owner_flag, native_format):
    """Synthetic representation of verified conditional branches, not vendor code."""
    config_built = hevc and auxiliary_mode_enabled
    return config_built, config_built and (owner_flag or native_format != 12)

def selftest():
    assert len(GATES) == 37
    assert expected_flag(True, True, False, 12) == (True, False)
    assert expected_flag(True, True, True, 12) == (True, True)
    assert expected_flag(True, True, False, 11) == (True, True)
    assert expected_flag(True, False, True, 11) == (False, False)
    assert expected_flag(False, True, True, 11) == (False, False)
    print('GAZELLE_FEL_STAGE31_SOURCE_SELFTEST_PASS')

def audit(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('missing/symlink ELF')
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != PIN:
        raise ValueError('original vendor ELF SHA mismatch')
    if blob[:7] != b'\x7fELF\x01\x01\x01' or int.from_bytes(blob[18:20], 'little') != 40:
        raise ValueError('not original ELF32 little-endian ARM')
    exe = shutil.which('llvm-objdump')
    if not exe:
        raise ValueError('llvm-objdump not found (brew install llvm)')
    groups = [(0x281c0, 0x28240), (0x591a8, 0x591bc), (0x59404, 0x59414),
              (0x5aa9e, 0x5aae2)]
    found = {}
    for lo, hi in groups:
        dis = subprocess.check_output((exe, '-d', '--triple=thumbv7a-linux-android',
             '--start-address=0x%x' % lo, '--stop-address=0x%x' % hi, str(path)),
             text=True, stderr=subprocess.PIPE)
        for line in dis.splitlines():
            match = SOURCE_RE.match(line)
            if match:
                found[int(match[1],16)] = match[2] + ' ' + match[3]
    for addr, expected in GATES.items():
        if normalized(found.get(addr,'')) != normalized(expected):
            raise ValueError('original instruction mismatch at 0x%x: %s' % (addr, found.get(addr)))
    print('PINNED_VENDOR_ELF_PASS libOmxVideo.so')
    print('STAGE31_CONFIG_INSTRUCTION_GATES_PASS count=%d' % len(GATES))
    print('AWESOME_HEVC_CONFIG_REQUIRES=hevc_format_0x0b_AND_decoder_flag_0xdc_nonzero')
    print('NEGATIVE_DV_APPEND_PREDICATE=owner_flag_0x35d_nonzero_OR_native_field_0x13c_not_0x0c')
    print('CONFIG_IOCTL=AMSTREAM_SET_PTR_CONFIGS_0x301')
    print('CONFIG_IOCTL_RETURN_ERROR=LOGGED_BUT_HELPER_RETURNS_ZERO')
    print('CODEC_INIT_CHECKS_HELPER_RETURN=YES_BUT_IOCTL_ERROR_CAN_BE_MASKED')
    print('P7_RUNTIME_CONFIG_IOCTL_RESULT=NOT_OBSERVED')
    print('P7_HDR10_ROOT_CAUSE=NOT_PROVEN')
    print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE31_OFFLINE_PASS')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('original_vendor_elf',nargs='?',type=Path)
    p.add_argument('--selftest',action='store_true')
    a=p.parse_args()
    selftest()
    if a.selftest:return
    if not a.original_vendor_elf:p.error('supply exact original /vendor/lib/libOmxVideo.so')
    audit(a.original_vendor_elf.expanduser().resolve())

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,AssertionError,subprocess.CalledProcessError) as e:
        print('GAZELLE_FEL_STAGE31_AUDIT_FAIL',e,file=sys.stderr)
        sys.exit(1)
