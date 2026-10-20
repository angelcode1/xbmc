#!/usr/bin/env python3
"""Stage49: source-only disc EL discard, BL/EL track-binding and clock gates.

This small repository gate complements the 20-case standalone Mac bundle.
Does not access the Cube, alter Kodi, or execute native decoder code.
"""
import argparse
import hashlib
import re
from pathlib import Path

PINS = {
 'DVDDemuxFFmpeg.cpp':'4955205e22ba462cff9998b03f9e5143d1ce1ef2',
 'VideoPlayer.cpp':'8b5cf1e6e2862936d2b3e58fe8997972d988c298',
 'DVDVideoCodecAndroidMediaCodec.cpp':'1a313fdc297db69607b2a3f0e82069def4b198f3',
}

def pinned_source(folder):
    answer={}
    for name, expected in PINS.items():
        p=folder/name
        if not p.is_file() or p.is_symlink():
            raise ValueError('Missing original source '+name)
        blob=p.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
        if actual!=expected:
            raise ValueError('Original integrated Kodi source blob changed '+name)
        answer[name]=blob.decode('utf-8')
    print('GAZELLE_FEL_STAGE49_REPO_SOURCE_PINS_PASS count=3')
    return answer

def verify_source(s):
    demux=s['DVDDemuxFFmpeg.cpp']
    player=s['VideoPlayer.cpp']
    decoder=s['DVDVideoCodecAndroidMediaCodec.cpp']
    pair=demux.find('// Dolby Vision dual-track support.')
    el_role=demux.find('st->isELStream = true;',pair)
    discard=demux.find('if (pStream->id == 0x1015)',pair)
    if not (0<=pair<el_role<discard):
        raise ValueError('Original pair before disc discard ordering differs')
    excerpt=demux[discard-320:discard+620]
    assert '#ifdef HAVE_LIBBLURAY' in demux[discard-800:discard]
    assert 'IsStreamType(DVDSTREAM_TYPE_BLURAY)' in demux[discard-800:discard]
    assert 'pStream->discard = AVDISCARD_ALL;' in excerpt
    assert 'delete stream;' in excerpt and 'return nullptr;' in excerpt
    assert 'bl->isDualStream = true;' in demux[pair:discard]
    assert 'st->isDualStream = true;' in demux[pair:discard]
    assert 'pPacket->isELPackage = video->isELStream;' in demux
    selected=player.index('void CVideoPlayer::ProcessVideoData(')
    fallback=player.index('else if (pPacket->isELPackage)')
    assert 'CheckContinuity(m_CurrentVideo, pPacket);' in player[selected:selected+900]
    assert 'm_VideoPlayerVideo->SendMessage' in player[fallback:fallback+400]
    assert 'UpdateCorrection(packet, m_offset_pts);' in player
    m=decoder.index('auto other = std::find_if(')
    pred=decoder[m:decoder.index('if (other == m_doviLayerPackets.end())',m)]
    assert 'return pending.isEL != packet.isELPackage;' in pred
    assert 'pending.pts' not in pred and 'packet.pts' not in pred
    assert 'iSize = out_size;' in decoder
    print('GAZELLE_FEL_STAGE49_REPO_SOURCE_GATES_PASS checks=14')
    print('CONDITIONAL_DISC_EL_PID_0X1015_IS_DISCARDED=YES')
    print('PAIR_METADATA_MAY_PRECEDE_DISC_DISCARD=YES')
    print('DEMUX_AND_PLAYER_HAVE_NO_SINGLE_VALIDATED_PAIR_CLOCK_OWNER=YES')
    print('BLURAY_PID_IN_OWNER_CAPTURE=NOT_ESTABLISHED')
    print('RUNTIME_FEL_EL_DECODING=NOT_PROVEN')

def selftest():
    def disc_gate(is_bluray,have_libbluray,pid):
        return bool(is_bluray and have_libbluray and pid==0x1015)
    assert disc_gate(True,True,0x1015)
    assert not disc_gate(True,False,0x1015)
    assert not disc_gate(False,True,0x1015)
    assert not disc_gate(True,True,0x1016)
    print('GAZELLE_FEL_STAGE49_REPO_SELFTEST_PASS cases=4')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest',action='store_true')
    parser.add_argument('--source-dir',type=Path)
    args=parser.parse_args()
    selftest()
    if args.selftest:return
    if args.source_dir is None:parser.error('Require --source-dir')
    verify_source(pinned_source(args.source_dir.expanduser().resolve()))
    print('GAZELLE_FEL_STAGE49_REPO_OFFLINE_PASS')

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,AssertionError) as err:
        print('GAZELLE_FEL_STAGE49_REPO_FAIL',err)
        raise SystemExit(1)
