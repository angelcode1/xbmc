#!/usr/bin/env python3
"""Read-only SHA-pinned OMX mode contract audit for Fire TV Cube 3.

No adb, sysfs, ELF writes or MediaCodec calls. Tests explicitly named functions
and instruction patterns; absence of a direct store is NOT a whole-program proof.
"""
import argparse, hashlib, pathlib, re, subprocess, sys
PIN = {
 'libomx_framework_alt.so':'fc63dd4be1267e1798fea1f742b60e7ea6a35790a57198efc09c5de0a409baba',
 'libOmxVideo.so':'eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77',
}
EXPECTED={
 'libomx_framework_alt.so':{
  'ctor':(0x162e0,0x16900),
  'setParameter_mvc':(0x19e60,0x19e80),
  'setConfig':(0x1b574,0x1b9f8),
  'vendorExtensionInitializer':(0x1747c,0x17f1c),
 },
 'libOmxVideo.so':{'awesome_setUp':(0x26128,0x2619a), 'aml_mode_word':(0x1efb6,0x1efd4)}
}
GATES={
 'libomx_framework_alt.so':{
 0x163d4:r'str\.w\s+r5,\s*\[r4,\s*#0x109\]',
 0x16834:r'strb\.w\s+r0,\s*\[r4,\s*#0x10a\]',
 0x16888:r'strb\.w\s+r0,\s*\[r4,\s*#0x10a\]',
 0x19e66:r'mov\.w\s+r8,\s*#0x0\b',
 0x1a1e0:r'strh\.w\s+r8,\s*\[r4,\s*#0x109\]',
 },
 'libOmxVideo.so':{
 0x2612c:r'ldrb\.w\s+r1,\s*\[r0,\s*#0x109\]',
 0x26134:r'ldrb\.w\s+r2,\s*\[r0,\s*#0x10a\]',
 0x26138:r'strb\.w\s+r2,\s*\[r4,\s*#0xdd\]',
 0x26172:r'cmp\s+r1,\s*#0xc\b',
 0x26178:r'cmp\.w\s+r0,\s*#0x400\b',
 0x26192:r'strb\.w\s+r0,\s*\[r4,\s*#0xdd\]',
 0x1efd2:r'str\s+r3,\s*\[r4,\s*r0\]',
 }}
LINE=re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+([a-z][a-z\d.]*)\s*(.*)',re.I)
def insns(elf,start=None,stop=None):
    args=['llvm-objdump','-d','--triple=thumbv7a-linux-android']
    if start is not None:args += [f'--start-address=0x{start:x}',f'--stop-address=0x{stop:x}']
    args.append(str(elf))
    out=subprocess.check_output(args, text=True,stderr=subprocess.PIPE)
    found={}
    for line in out.splitlines():
        m=LINE.match(line)
        if m:found[int(m[1],16)]=m[2]+' '+m[3]
    return found
def audit(directory):
    files={}
    for name,sha in PIN.items():
        f=directory/name
        if not f.is_file():raise ValueError('missing '+str(f))
        raw=f.read_bytes()
        if raw[:7]!=b'\x7fELF\x01\x01\x01' or int.from_bytes(raw[18:20],'little')!=40:
            raise ValueError('not ARM32 ELF '+name)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('unexpected SHA '+name)
        files[name]=f
        print('PINNED_ELF_PASS',name,sha)
    for name, tests in GATES.items():
        all_code=insns(files[name])
        for addr,pattern in tests.items():
            if not re.search(pattern,all_code.get(addr,'')):
                raise ValueError(f'{name} 0x{addr:x} mismatch {all_code.get(addr)}')
        print('SEMANTIC_INSTRUCTIONS_PASS',name,len(tests))
    fw=files['libomx_framework_alt.so']
    config=insns(fw,*EXPECTED['libomx_framework_alt.so']['setConfig'])
    # Exact stores via r4 (the this pointer), not a global alias analysis.
    writes=[(addr,line) for addr,line in config.items() if re.search(r'\b(?:str|strh|strb)(?:\.w)?\s+\S+,\s*\[r4,\s*#0x(?:109|10a)\]',line)]
    if writes:
        raise ValueError('unexpected mode-field store(s): '+repr(writes))
    print('SETCONFIG_DIRECT_MODE_STORES_ABSENT bounds=0x1b574-0x1b9f8 checked='+str(len(config)))
    # Only confirm the names exist; not an extension-to-index mapping.
    blob=fw.read_bytes()
    markers=[b'is-mvc\0',b'profile-level\0',b'low-latency\0',b'save-mem\0',b'renderByOmx\0']
    for term in markers:
        if blob.count(term)<1:raise ValueError('extension string changed '+repr(term))
    print('NAMED_VENDOR_EXTENSION_STRINGS_PASS names='+','.join(x[:-1].decode() for x in markers))
    print('FRAME_OVERRIDE_GATE=internal_format_0xC_AND_owner_profile_0x400; applicability_to_P7_NOT_PROVEN')
    print('INSTANCE_SCOPED_STREAM_API=NOT_IDENTIFIED (NOT A GLOBAL ABSENCE PROOF)')
    print('COREELEC_STREAM_PACKET_FORMAT=REQUIRES_SEPARATE_VALIDATION')
    print('FEL_NATIVE_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE16_OFFLINE_CONTRACT_PASS')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',nargs='?',type=pathlib.Path)
    p.add_argument('--selftest',action='store_true')
    a=p.parse_args()
    if a.selftest:
        assert len(PIN)==2 and sum(map(len,GATES.values()))==12
        print('GAZELLE_FEL_STAGE16_SOURCE_SELFTEST_PASS')
    elif a.directory:audit(a.directory.expanduser().resolve())
    else:p.error('pass private vendor library directory or --selftest')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        print('GAZELLE_FEL_STAGE16_AUDIT_FAIL',str(e),file=sys.stderr);sys.exit(1)
