#!/usr/bin/env python3
"""Stage50: pinned original Kodi Blu-ray EL admission ordering gate, offline only.

Companion to the independently tested Stage50 extended macOS ZIP (26 gates,
25 tests). This repository gate is deliberately smaller and source-only.
No Cube, ADB, kernel, OMX, Kodi install, or optical-drive actions.
"""
import argparse
import hashlib
from pathlib import Path
import unittest

BLOBS={
    'DVDDemuxFFmpeg.cpp':'4955205e22ba462cff9998b03f9e5143d1ce1ef2',
    'VideoPlayer.cpp':'8b5cf1e6e2862936d2b3e58fe8997972d988c298',
    'DVDVideoCodecAndroidMediaCodec.cpp':'1a313fdc297db69607b2a3f0e82069def4b198f3',
}

def load_pinned(folder):
    data={}
    for name,sha in BLOBS.items():
        path=folder/name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing pinned source '+name)
        b=path.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if actual!=sha:
            raise ValueError('Git blob differs '+name)
        data[name]=b.decode('utf8')
    print('GAZELLE_FEL_STAGE50_REPO_SOURCE_PINS_PASS count=3')
    return data

def source_gates(s):
    demux=s['DVDDemuxFFmpeg.cpp']
    player=s['VideoPlayer.cpp']
    codec=s['DVDVideoCodecAndroidMediaCodec.cpp']
    start=demux.index('CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)')
    end=demux.index('void CDVDDemuxFFmpeg::AddStream(int streamIdx, CDemuxStream* stream)',start)
    block=demux[start:end]
    earlier=block.index('// Dolby Vision dual-track support.')
    mutation=block.index('bl->isDualStream = true;',earlier)
    bd=block.index('#ifdef HAVE_LIBBLURAY\n    if (m_pInput->IsStreamType(DVDSTREAM_TYPE_BLURAY))',mutation)
    discard=block.index('if (pStream->id == 0x1015)',bd)
    admission=block.index('AddStream(stream->uniqueId, stream);',discard)
    if not earlier<mutation<bd<discard<admission:
        raise ValueError('admission ordering changed')
    checks={
      'mutates_bl_before_discard':'bl->hdr_type = StreamHdrType::HDR_TYPE_DOLBYVISION;' in block[earlier:bd],
      'sets_dual_bl_before_discard':'bl->isDualStream = true;' in block[earlier:bd],
      'sets_dual_el_before_discard':'st->isDualStream = true;' in block[earlier:bd],
      'conditional_bluray': 'DVDSTREAM_TYPE_BLURAY' in block[bd:discard],
      'disc_discard': 'pStream->discard = AVDISCARD_ALL;' in block[discard:admission],
      'delete_candidate':'delete stream;' in block[discard:admission],
      'discard_returns_null':'return nullptr;' in block[discard:admission],
      'bd_nav_id':'stream->dvdNavId = pStream->id;' in block[discard:admission],
      'bd_language':'bluray->GetStreamInfo(pStream->id, blurayLanguage);' in block[discard:admission],
      'bd_default':'bluray->IsDefaultStream(pStream->id)' in block[discard:admission],
      'bd_duplicate':'duplicate bluray stream' in block[discard:admission],
      'EL_role_to_packet':'pPacket->isELPackage = video->isELStream;' in demux,
      'unselected_EL_forward':'else if (pPacket->isELPackage)' in player,
      'first_opposite_layer_predicate':'return pending.isEL != packet.isELPackage;' in codec,
    }
    bad=[key for key,val in checks.items() if not val]
    if bad:raise ValueError('Kodi original source gate changed: '+', '.join(bad))
    print('GAZELLE_FEL_STAGE50_REPO_SOURCE_GATES_PASS checks=15')
    print('BL_FLAGS_MUTATED_BEFORE_EL_ADMISSION=YES')
    print('DISC_EL_DISCARD=CONDITIONAL_PID_0X1015')
    print('DISC_NAV_LANGUAGE_DEFAULT_DUPLICATE_HANDLING=RETAIN_UNCHANGED')
    print('OWNER_ACTUAL_DISC_OR_FILE_INPUT=UNKNOWN')
    print('FEL_RECONSTRUCTION=NOT_PROVEN')

def eligibility(bluray,compiled,pid,p7,identity,epoch,menu,el_decoder,residual_oracle):
    if not (bluray and compiled and pid==0x1015):return 'OUT_OF_SCOPE'
    for value,name in [(p7,'P7'),(identity,'PAIR'),(epoch,'EPOCH'),(menu,'NAV'),
                       (el_decoder,'EL_DECODER'),(residual_oracle,'ORACLE')]:
        if not value:return 'BLOCK_'+name
    return 'DESIGN_ONLY_NOT_RUNTIME_PERMISSION'

class GateTests(unittest.TestCase):
    def test_not_bluray(self):self.assertEqual(eligibility(False,True,0x1015,1,1,1,1,1,1),'OUT_OF_SCOPE')
    def test_not_compiled(self):self.assertEqual(eligibility(True,False,0x1015,1,1,1,1,1,1),'OUT_OF_SCOPE')
    def test_wrong_pid(self):self.assertEqual(eligibility(True,True,0x1016,1,1,1,1,1,1),'OUT_OF_SCOPE')
    def test_unknown_p7(self):self.assertEqual(eligibility(True,True,0x1015,0,1,1,1,1,1),'BLOCK_P7')
    def test_no_identity(self):self.assertEqual(eligibility(True,True,0x1015,1,0,1,1,1,1),'BLOCK_PAIR')
    def test_no_epoch(self):self.assertEqual(eligibility(True,True,0x1015,1,1,0,1,1,1),'BLOCK_EPOCH')
    def test_no_disc_nav(self):self.assertEqual(eligibility(True,True,0x1015,1,1,1,0,1,1),'BLOCK_NAV')
    def test_no_el_decoder(self):self.assertEqual(eligibility(True,True,0x1015,1,1,1,1,0,1),'BLOCK_EL_DECODER')
    def test_no_pixel_oracle(self):self.assertEqual(eligibility(True,True,0x1015,1,1,1,1,1,0),'BLOCK_ORACLE')
    def test_all_still_not_permission(self):
        self.assertEqual(eligibility(True,True,0x1015,1,1,1,1,1,1),'DESIGN_ONLY_NOT_RUNTIME_PERMISSION')

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--selftest',action='store_true')
    a.add_argument('--source-dir',type=Path)
    options=a.parse_args()
    result=unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(GateTests))
    if not result.wasSuccessful():raise ValueError('synthetic gate failed')
    print('GAZELLE_FEL_STAGE50_REPO_SYNTHETIC_PASS cases='+str(result.testsRun))
    if options.selftest:return
    if not options.source_dir:a.error('Provide --source-dir')
    source_gates(load_pinned(options.source_dir.expanduser().resolve()))
    print('GAZELLE_FEL_STAGE50_REPO_OFFLINE_PASS')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,AssertionError) as e:
        print('GAZELLE_FEL_STAGE50_REPO_FAIL',e)
        raise SystemExit(1)
