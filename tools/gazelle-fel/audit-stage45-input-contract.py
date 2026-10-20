#!/usr/bin/env python3
"""Original Fire OS native write/PTS ABI vs pinned Kodi MediaCodec P7 input.

Host-only, no ADB, native execution, vendor writes, or playback changes.
Never publish private original .so files. A bounded source code audit does NOT
establish an event happened on the user's playback device.
"""
import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ORIGINAL_SHA = 'eb79f44c3b327e140ef0faedaab3b82ce7ed2f9bf0531fb4b28c532feef90e77'
KODI_COMMIT = 'a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd'
KODI_GIT_BLOB = '1a313fdc297db69607b2a3f0e82069def4b198f3'
KODI_PATH = 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp'
# Instructions are all from SHA-pinned, original Amazon ARM32 ELF.
GATES = {
    0x58cd2: 'mov.w r0, #0x10a0',
    0x58cda: 'ldr.w r2, [r8, r0]',
    0x58ce6: 'cmp r2, #0x1',
    0x58cea: 'moveq r0, r3',
    0x58cec: 'bl 0x67d14',
    0x597d0: 'ldr r0, [r0]',
    0x597d2: 'b.w 0x67dc4',
    0x5986e: 'ldr r0, [r0]',
    0x59870: 'mov r3, r1',
    0x59872: 'movw r1, #0x53c2',
    0x59876: 'mov.w r2, #0x10e',
    0x5987a: 'movt r1, #0x4010',
    0x5987e: 'b.w 0x67d94',
    0x59884: 'push {r7, lr}',
    0x5988a: 'strd r2, r3, [sp]',
    0x5988e: 'mov r2, sp',
    0x59898: 'movw r1, #0x5395',
    0x5989c: 'ldr r0, [r0]',
    0x5989e: 'movt r1, #0x4004',
    0x598a2: 'bl 0x67d34',
    0x598a6: 'cmp.w r0, #0xffffffff',
    0x5a1a2: 'mov.w r1, #0x12c0',
    0x5a1a6: 'movw r2, #0x179',
    0x5a1aa: 'str r3, [r0, r1]',
}
SYMBOLS = {
    'codec_write': (0x597d1, 6),
    'codec_checkin_pts': (0x5986f, 20),
    'codec_checkin_pts_us64': (0x59885, 80),
    'codec_set_dvmetawithel': (0x5a1a1, 26),
}
LINE = re.compile(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*)$',re.I)

def normalize(value):
    return re.sub(r'\s+', '', value.split(' @',1)[0].split(' //',1)[0].split(' <',1)[0])

def private_vendor_audit(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('original libOmxVideo.so not a regular file')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ORIGINAL_SHA or data[:7]!=b'\x7fELF\x01\x01\x01' or int.from_bytes(data[18:20], 'little')!=40:
        raise ValueError('private original vendor ELF SHA/ARM identity mismatch')
    symbols = subprocess.check_output(['readelf','-Ws',str(path)],text=True)
    for name,(addr,size) in SYMBOLS.items():
        pat = rf'^\s*\d+:\s*{addr:08x}\s+{size}\s+FUNC\s+GLOBAL\s+DEFAULT\s+12\s+{name}\s*$'
        if not re.search(pat,symbols,re.M):
            raise ValueError('vendor export identity mismatch '+name)
    dis = subprocess.check_output(['llvm-objdump','--triple=thumbv7-unknown-linux-android','-d','--no-show-raw-insn',str(path)],text=True)
    ins={}
    for line in dis.splitlines():
        m=LINE.match(line)
        if m: ins[int(m[1],16)]=m[2]+' '+m[3]
    for at,expected in GATES.items():
        if normalize(ins.get(at,''))!=normalize(expected):
            raise ValueError('original ARM32 Thumb gate mismatch at 0x%x: %s'%(at,ins.get(at)))
    print('GAZELLE_FEL_STAGE45_ORIGINAL_VENDOR_IDENTITY_PASS')
    print('GAZELLE_FEL_STAGE45_NATIVE_INPUT_GATES_PASS instructions=%d exports=%d'%(len(GATES),len(SYMBOLS)))
    print('NATIVE_CODEC_WRITE=FD_WRITE_WRAPPER_NO_PACKETIZER_IN_THIS_BODY')
    print('NATIVE_CHECKIN_PTS32=SELECTOR_0x10E_IOCTL_0x401053C2')
    print('NATIVE_CHECKIN_PTS_US64=DIFFERENT_IOCTL_0x40045395')
    print('NATIVE_CHECKIN_PTS_TIMEBASE=NOT_ESTABLISHED_BY_EXPORTS')
    print('NATIVE_DV_META_WITH_EL=SEPARATE_CONTEXT_FLAG_AND_IOCTL_0x179')

def region(data,begin,end):
    a=data.find(begin)
    if a<0:raise ValueError('Kodi source start marker missing: '+begin)
    b=data.find(end,a+len(begin))
    if b<0 or b-a>60000:raise ValueError('Kodi source end marker missing/implausible: '+end)
    return data[a:b]

def kodi_source_audit(path):
    if not path.is_file() or path.is_symlink():raise ValueError('Kodi cpp file absent/nonregular')
    blob=path.read_bytes()
    git_hash=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
    if git_hash!=KODI_GIT_BLOB:
        raise ValueError('Kodi source Git blob mismatch: need exact pinned integration checkout')
    text=blob.decode('utf-8')
    add=region(text,'bool CDVDVideoCodecAndroidMediaCodec::AddData(', 'void CDVDVideoCodecAndroidMediaCodec::')
    # BL/EL pairing lambda: the only search predicate in this bounded find_if
    pairing=region(add,'auto other = std::find_if(', 'if (other == m_doviLayerPackets.end())')
    lambda_match=re.search(r'\[&packet\]\(const DolbyLayerPacket& pending\)\s*\{(.*?)\}',pairing,re.S)
    if not lambda_match or not re.search(r'return\s+pending\.isEL\s*!=\s*packet\.isELPackage\s*;',lambda_match[1]):
        raise ValueError('Kodi BL/EL match predicate changed')
    if re.search(r'pending\.pts|packet\.pts|pending\.dts|packet\.dts',lambda_match[1]):
        raise ValueError('BL/EL predicate now checks timestamps: review needed')
    if not re.search(r'while\s*\(m_doviLayerPackets\.size\(\)\s*>\s*8\)',add):
        raise ValueError('Kodi pair queue cap differs')
    # Format strings inside the block contain literal braces (e.g. '{}').
    # Bound the check by the following comment instead of using a brace-naive regex.
    cap = region(add, 'if ((size_t)iSize > out_size)',
                 '// Inspect exactly the size that fits MediaCodec')
    if len(cap)>1000 or not re.search(r'iSize\s*=\s*out_size\s*;', cap):
        raise ValueError('Kodi MediaCodec capacity truncation path differs')
    required=[r'm_codec->getInputBuffer\(m_indexInputBuffer\)',
              r'memcpy\(dst_ptr,\s*pData,\s*iSize\)',
              r'presentationTimeUs\s*=\s*\(pts\s*-\s*m_dtsShift\)',
              r'm_codec->queueInputBuffer\(m_indexInputBuffer,\s*offset,\s*iSize,\s*presentationTimeUs,\s*flags\)',
              r'm_codec->queueSecureInputBuffer\(m_indexInputBuffer,',
              r'if\s*\(packet\.isDualStream\)',
              r'm_bitstream->Convert\(blData,\s*blSize,\s*elData,\s*elSize\)']
    for pat in required:
        if not re.search(pat,add):raise ValueError('Kodi bounded input contract changed: '+pat)
    configure=region(text,'bool CDVDVideoCodecAndroidMediaCodec::ConfigureMediaCodec(', 'void CDVDVideoCodecAndroidMediaCodec::') if 'bool CDVDVideoCodecAndroidMediaCodec::ConfigureMediaCodec(' in text else ''
    # Independently scoped mode control is not proven by the presence of normal Android JNI.
    if 'm_codec->configure(mediaformat' not in text or 'm_codec->start();' not in text:
        raise ValueError('Kodi MediaCodec startup contract changed')
    print('GAZELLE_FEL_STAGE45_KODI_SOURCE_PIN_PASS commit='+KODI_COMMIT)
    print('GAZELLE_FEL_STAGE45_KODI_INPUT_GATES_PASS checks=%d'%(len(required)+7))
    print('KODI_P7_LAYER_MATCH=OPPOSITE_LAYER_ONLY_NO_TIMESTAMP_PREDICATE')
    print('KODI_PAIR_QUEUE=MAX_8_WITH_OLDEST_DROP')
    print('KODI_INPUT_CAPACITY=CONDITIONAL_iSize_TRUNCATION_BEFORE_MEMCPY')
    print('KODI_MEDIA_CODEC_PTS=PASS_PRESENTATION_TIME_US_FROM_PTS_OR_DTS_MINUS_DTS_SHIFT')
    print('KODI_INPUT_SINK=ANDROID_MEDIACODEC_QUEUE_INPUT_BUFFER_NOT_NATIVE_CODEC_WRITE')
    print('KODI_JNI_FEEDER_AUTOMATICALLY_SATISFIES_NATIVE_STREAM_PACKET_CONTRACT=NOT_PROVEN')
    print('KODI_P7_PTS_MISMATCH_IN_OWNERS_PLAYBACK=NOT_OBSERVED')
    print('KODI_P7_INPUT_TRUNCATION_IN_OWNERS_PLAYBACK=NOT_OBSERVED')

def selftest():
    assert len(GATES)==24 and len(SYMBOLS)==4
    assert len(KODI_GIT_BLOB)==40 and len(KODI_COMMIT)==40
    assert 0x10b4 + 0x200 == 0x12b4
    print('GAZELLE_FEL_STAGE45_SOURCE_SELFTEST_PASS')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest',action='store_true')
    parser.add_argument('--original',type=Path)
    parser.add_argument('--kodi',type=Path)
    parser.add_argument('--kodi-only',action='store_true')
    parser.add_argument('--vendor-only',action='store_true')
    args=parser.parse_args()
    selftest()
    if args.selftest:return
    if args.kodi_only and args.vendor_only:
        parser.error('choose only one partial audit mode')
    if args.kodi_only:
        if not args.kodi:parser.error('--kodi required for --kodi-only')
        kodi_source_audit(args.kodi.expanduser().resolve())
        print('GAZELLE_FEL_STAGE45_KODI_ONLY_PASS')
        return
    if args.vendor_only:
        if not args.original:parser.error('--original required for --vendor-only')
        private_vendor_audit(args.original.expanduser().resolve())
        print('GAZELLE_FEL_STAGE45_VENDOR_ONLY_PASS')
        return
    if not args.original or not args.kodi:
        parser.error('both --original private libOmxVideo.so and --kodi pinned C++ source required')
    private_vendor_audit(args.original.expanduser().resolve())
    kodi_source_audit(args.kodi.expanduser().resolve())
    print('NATIVE_STREAM_PACKET_INPUT_FORMAT=NOT_VERIFIED')
    print('NATIVE_PTS_CONVERSION_TO_KODI_TIMEBASE=NOT_VERIFIED')
    print('SUPPORTED_P7_ONLY_MODE_CONTROL=NOT_VERIFIED')
    print('NATIVE_P7_BACKEND_READINESS=BLOCKED_NO_GO')
    print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE45_OFFLINE_PASS')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.CalledProcessError,UnicodeError,AssertionError) as exc:
        print('GAZELLE_FEL_STAGE45_FAIL',str(exc),file=sys.stderr);sys.exit(1)
