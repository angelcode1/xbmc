#!/usr/bin/env python3
"""Source integration check for candidate Kodi APK, not a full C++ compile.

Runs in existing Android ARMv7 full-APK GitHub Actions workflow BEFORE SDK
download or build. Scope: ensure guarded BL/EL pairing and NAL assembly are
actually called from Kodi's real decoder, rather than only compiling tests.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2]
source = root / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp'
codec_header = root / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/GazelleFELPairing.h'
converter = root / 'xbmc/utils/BitstreamConverter.cpp'
reader_header = root / 'xbmc/utils/GazelleFELNalReader.h'
files = {
    'decoder': source.read_text(),
    'pairing': codec_header.read_text(),
    'converter': converter.read_text(),
    'reader': reader_header.read_text(),
}

required = {
    'decoder': (
        '#include "GazelleFELPairing.h"',
        'GazelleFELPairing::FindMate(',
        'GazelleFELPairing::CanBuffer(',
        'GazelleFELPairing::ValidClock(',
        'm_bitstream->Convert(blData, blSize, elData, elSize)',
        'refusing incomplete',
        'm_doviLayerPackets.clear()',
        'm_codec->queueInputBuffer(',
    ),
    'pairing': (
        'kMaxPendingPackets = 8',
        'kMaxPendingBytes = 64u * 1024u * 1024u',
        'kMaxLayerPacketBytes = 16u * 1024u * 1024u',
        'kClockToleranceUs = 100.0',
        'SameAccessUnit(',
        'FindMate(',
        'CanBuffer(',
    ),
    'converter': (
        '#include "GazelleFELNalReader.h"',
        'm_convert_bitstream ? m_sps_pps_context.length_size : 4',
        'GazelleFEL::LengthPrefixedReader blReader(',
        'GazelleFEL::LengthPrefixedReader elReader(',
        'if (!validLayer(buf, bl_frame_nal_buf_size)',
        'HEVC_NAL_UNSPEC62',
        'HEVC_NAL_UNSPEC63',
    ),
    'reader': (
        'class LengthPrefixedReader',
        'bool Complete() const noexcept',
        'if (length < 2 || length > m_size - m_pos)',
    ),
}

def validate(contents):
    errors = []
    for file, needles in required.items():
        for needle in needles:
            if needle not in contents[file]:
                errors.append(f'{file}: expected source path missing: {needle}')
    # This check targets the dual-stream branch in the actual AddData method;
    # no silent P7 queue eviction may be resurrected.
    ad = contents['decoder']
    start = ad.find('if (packet.isDualStream)')
    end = ad.find('if (m_state == MEDIACODEC_STATE_FLUSHED)', start)
    if start < 0 or end < start:
        errors.append('decoder: cannot isolate dual stream pairing branch')
    else:
        section = ad[start:end]
        if '.pop_front()' in section:
            errors.append('decoder: silent BL/EL queue eviction reintroduced')
        if 'std::find_if(' in section:
            errors.append('decoder: first-opposite-layer matching reintroduced')
        if 'static_cast<size_t>(std::numeric_limits<int>::max())' not in section:
            errors.append('decoder: signed converter input size unchecked')
    # A silent capacity clamp inside the P7 guard is unacceptable.
    cap = ad.find('if ((size_t)iSize > out_size)')
    if cap < 0:
        errors.append('decoder: capacity handling missing')
    else:
        tail = ad[cap:cap + 900]
        if 'm_hints.dovi.dv_profile == 7' not in tail or 'return false;' not in tail:
            errors.append('decoder: P7 oversized packet might be truncated')
    if not (('blReader.Next(nal)' in contents['converter']) and ('elReader.Next(nal)' in contents['converter'])):
        errors.append('converter: reader traversal missing')
    return errors

def selftest():
    assert validate(files) == [], '\n'.join(validate(files))
    tampered = dict(files)
    tampered['decoder'] = tampered['decoder'].replace(
        'GazelleFELPairing::FindMate(', 'BROKEN_FIRST_LAYER_MATCH(', 1)
    assert validate(tampered), 'mutated decoder unexpectedly accepted'
    tampered = dict(files)
    tampered['converter'] = tampered['converter'].replace(
        'GazelleFEL::LengthPrefixedReader elReader(',
        'UNGUARDED_EL_READER(', 1)
    assert validate(tampered), 'mutated EL converter unexpectedly accepted'
    print('GAZELLE_FEL_KODI_INTEGRATION_SELFTEST_PASS fail_closed=true no_device=true')

if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
    errors = validate(files)
    if errors:
        for e in errors:
            print('ERROR:', e, file=sys.stderr)
        sys.exit(2)
    print('GAZELLE_FEL_KODI_INTEGRATION_SOURCE_PASS source_verified=true full_android_compile=false no_device=true')
