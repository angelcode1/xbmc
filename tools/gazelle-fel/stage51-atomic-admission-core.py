#!/usr/bin/env python3
"""Stage51 CI: pinned original Kodi source + atomic pair admission core, offline.

Independent smaller gate. Full 29/48 verifier is in the standalone Mac ZIP.
No device actions or Kodi patches. Python 3.9-compatible.
"""
import argparse
import hashlib
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

PINS={
 'DVDDemuxFFmpeg.cpp':'4955205e22ba462cff9998b03f9e5143d1ce1ef2',
 'VideoPlayer.cpp':'8b5cf1e6e2862936d2b3e58fe8997972d988c298',
 'DVDVideoCodecAndroidMediaCodec.cpp':'1a313fdc297db69607b2a3f0e82069def4b198f3',
}
@dataclass(frozen=True)
class Part:
    demux:int
    stream:int
    role:str
    pid:int=0
    registered:bool=False
    dual:bool=False

class Admission:
    def __init__(self):
        self.parts={}
        self.revision=0
        self.epoch=0
        self.issued=None
    def admit(self,part,bluray=False):
        key=(part.demux,part.stream)
        if key in self.parts:return 'DUPLICATE'
        if bluray and part.pid==0x1015:return 'ORIGINAL_DISC_EL_DISCARD'
        if part.role not in ('BL','EL') or part.dual:return 'INVALID'
        self.parts[key]=replace(part,registered=True)
        self.revision+=1
        self.issued=None
        return 'UNPAIRED'
    def propose(self,b,e,verified=False):
        if not verified:return None
        first=self.parts.get(b);second=self.parts.get(e)
        if first is None or second is None or first.demux!=second.demux:
            return None
        if first.role!='BL' or second.role!='EL' or b==e:return None
        if first.dual or second.dual:return None
        self.issued=(b,e,self.revision,self.epoch)
        return self.issued
    def commit(self,token,inject_failure=False):
        if token is None or token!=self.issued:return 'INVALID_PROPOSAL'
        b,e,rev,epoch=token
        if rev!=self.revision or epoch!=self.epoch:return 'STALE'
        changed=dict(self.parts)
        changed[b]=replace(changed[b],dual=True)
        if inject_failure:return 'ROLLED_BACK'
        changed[e]=replace(changed[e],dual=True)
        self.parts=changed
        self.revision+=1
        self.issued=None
        return 'MODEL_ATOMIC'
    def reset(self):
        self.epoch+=1
        self.revision+=1
        self.issued=None
        self.parts={k:replace(v,dual=False) for k,v in self.parts.items()}
    def remove(self,key):
        old=self.parts.pop(key,None)
        if old is None:return
        if old.dual:
            self.parts={k:replace(v,dual=False) if v.demux==old.demux else v
                        for k,v in self.parts.items()}
        self.revision+=1
        self.issued=None

def gate_source(folder):
    sources={}
    for name,digest in PINS.items():
        path=folder/name
        if not path.is_file() or path.is_symlink():
            raise ValueError('original source absent '+name)
        b=path.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if actual!=digest:raise ValueError('original source changed '+name)
        sources[name]=b.decode('utf-8')
    d=sources['DVDDemuxFFmpeg.cpp']
    p=sources['VideoPlayer.cpp']
    c=sources['DVDVideoCodecAndroidMediaCodec.cpp']
    a=d.index('// Dolby Vision dual-track support.')
    mutation=d.index('bl->isDualStream = true;',a)
    conditional=d.index('#ifdef HAVE_LIBBLURAY\n    if (m_pInput->IsStreamType(DVDSTREAM_TYPE_BLURAY))',mutation)
    discard=d.index('if (pStream->id == 0x1015)',conditional)
    admitted=d.index('AddStream(stream->uniqueId, stream);',discard)
    if not a<mutation<conditional<discard<admitted:
        raise ValueError('original admission ordering changed')
    checks=[
      'bl->hdr_type = StreamHdrType::HDR_TYPE_DOLBYVISION;' in d[a:mutation],
      'bl->dovi = st->dovi;' in d[a:mutation],
      'st->isELStream = true;' in d[a:conditional],
      'pStream->discard = AVDISCARD_ALL;' in d[discard:admitted],
      'delete stream;' in d[discard:admitted],
      'return nullptr;' in d[discard:admitted],
      'stream->dvdNavId = pStream->id;' in d[discard:admitted],
      'bluray->GetStreamInfo(pStream->id, blurayLanguage);' in d[discard:admitted],
      'bluray->IsDefaultStream(pStream->id)' in d[discard:admitted],
      'duplicate bluray stream' in d[discard:admitted],
      'pPacket->isELPackage = video->isELStream;' in d,
      'else if (pPacket->isELPackage)' in p,
      'return pending.isEL != packet.isELPackage;' in c,
    ]
    if not all(checks):raise ValueError('original source gates differ')
    print('GAZELLE_FEL_STAGE51_REPO_SOURCE_PINS_PASS count=3')
    print('GAZELLE_FEL_STAGE51_REPO_SOURCE_GATES_PASS checks=14')

class Tests(unittest.TestCase):
    def setUp(self):
        self.a=Admission()
        self.bl=Part(1,10,'BL',0x1011)
        self.el=Part(1,11,'EL',0x1015)
    def pair(self):
        self.a.admit(self.bl);self.a.admit(self.el)
        return self.a.propose((1,10),(1,11),True)
    def test_el_pid_disc_rejected(self):
        self.a.admit(self.bl)
        before=dict(self.a.parts)
        self.assertEqual(self.a.admit(self.el,True),'ORIGINAL_DISC_EL_DISCARD')
        self.assertEqual(before,self.a.parts)
    def test_file_bl_first(self):
        t=self.pair()
        self.assertEqual(self.a.commit(t),'MODEL_ATOMIC')
    def test_file_el_first(self):
        self.a.admit(self.el);self.a.admit(self.bl)
        self.assertIsNotNone(self.a.propose((1,10),(1,11),True))
    def test_unpaired_bl(self):
        self.a.admit(self.bl);self.assertFalse(self.a.parts[(1,10)].dual)
    def test_no_verified_binding(self):
        self.a.admit(self.bl);self.a.admit(self.el)
        self.assertIsNone(self.a.propose((1,10),(1,11),False))
    def test_injected_rollback(self):
        t=self.pair();before=dict(self.a.parts)
        self.assertEqual(self.a.commit(t,True),'ROLLED_BACK')
        self.assertEqual(before,self.a.parts)
    def test_tampered_token(self):
        t=self.pair()
        self.assertEqual(self.a.commit((t[0],t[1],t[2],t[3]+1)),'INVALID_PROPOSAL')
    def test_registry_stale_token(self):
        t=self.pair();self.a.admit(Part(1,12,'BL'))
        self.assertEqual(self.a.commit(t),'INVALID_PROPOSAL')
    def test_epoch_clears_dual(self):
        t=self.pair();self.a.commit(t);self.a.reset()
        self.assertFalse(self.a.parts[(1,10)].dual)
    def test_removed_el_clears_bl(self):
        t=self.pair();self.a.commit(t);self.a.remove((1,11))
        self.assertFalse(self.a.parts[(1,10)].dual)
    def test_duplicate_stream(self):
        self.a.admit(self.bl)
        self.assertEqual(self.a.admit(self.bl),'DUPLICATE')
    def test_cross_demux_blocked(self):
        self.a.admit(self.bl);self.a.admit(Part(2,11,'EL'))
        self.assertIsNone(self.a.propose((1,10),(2,11),True))
    def test_wrong_roles_blocked(self):
        self.a.admit(self.bl);self.a.admit(Part(1,11,'BL'))
        self.assertIsNone(self.a.propose((1,10),(1,11),True))
    def test_replayed_token_refused(self):
        t=self.pair();self.a.commit(t)
        self.assertEqual(self.a.commit(t),'INVALID_PROPOSAL')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-dir',type=Path)
    ap.add_argument('--selftest',action='store_true')
    args=ap.parse_args()
    result=unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise ValueError('reference tests failed')
    print('GAZELLE_FEL_STAGE51_REPO_MODEL_PASS cases='+str(result.testsRun))
    if args.selftest:return
    if args.source_dir is None:ap.error('--source-dir required')
    gate_source(args.source_dir.expanduser().resolve())
    print('GAZELLE_FEL_STAGE51_REPO_OFFLINE_PASS')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,AssertionError) as e:
        print('GAZELLE_FEL_STAGE51_REPO_FAIL',e)
        raise SystemExit(1)
