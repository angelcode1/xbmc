#!/usr/bin/env python3
"""Stage52 CI: pinned Kodi stream object lifetime and observer-version no-go.

Python 3.9+; model and source checks only. Not a Kodi patch.
"""
import argparse, hashlib, unittest
from dataclasses import dataclass, replace
from pathlib import Path

PINS={
 'DVDDemuxFFmpeg.cpp':'4955205e22ba462cff9998b03f9e5143d1ce1ef2',
 'VideoPlayer.cpp':'8b5cf1e6e2862936d2b3e58fe8997972d988c298',
 'DVDVideoCodecAndroidMediaCodec.cpp':'1a313fdc297db69607b2a3f0e82069def4b198f3',
}
def interval(s,start,stop):
 a=s.index(start);b=s.index(stop,a+len(start))
 return s[a:b]

def source_audit(base):
 s={}
 for name,pin in PINS.items():
  p=base/name
  if not p.is_file() or p.is_symlink():raise ValueError('missing source '+name)
  raw=p.read_bytes()
  if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=pin:
   raise ValueError('source pin mismatch '+name)
  s[name]=raw.decode('utf8')
 d=s['DVDDemuxFFmpeg.cpp'];p=s['VideoPlayer.cpp'];c=s['DVDVideoCodecAndroidMediaCodec.cpp']
 rebuild=interval(d,'void CDVDDemuxFFmpeg::CreateStreams(unsigned int program)','void CDVDDemuxFFmpeg::SaveProbedStreamParameters()')
 freed=interval(d,'void CDVDDemuxFFmpeg::DisposeStreams()','CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)')
 pairing=interval(d,'CDemuxStream* CDVDDemuxFFmpeg::AddStream(int streamIdx)','void CDVDDemuxFFmpeg::AddStream(int streamIdx, CDemuxStream* stream)')
 replace_code=interval(d,'void CDVDDemuxFFmpeg::AddStream(int streamIdx, CDemuxStream* stream)','std::string CDVDDemuxFFmpeg::GetFileName()')
 change=interval(p,'void CVideoPlayer::CheckStreamChanges(CCurrentStream& current, CDemuxStream* stream)','void CVideoPlayer::ProcessAudioData(')
 get=interval(d,'CDemuxStream* CDVDDemuxFFmpeg::GetStream(int iStreamId) const','int CDVDDemuxFFmpeg::GetNrOfStreams()')
 conditions={
  'get_raw':'return it->second;' in get,
  'get_raw_list':'std::vector<CDemuxStream*>' in get,
  'rebuild_disposes':'DisposeStreams();' in rebuild,
  'rebuild_change_snapshot':'prevChanges[streamIdx] = stream->changes;' in rebuild,
  'rebuild_version_bump':'stream->changes = it->second + 1;' in rebuild,
  'rebuild_repopulates':'addStreamKeepingChanges(streamIdx);' in rebuild,
  'free_owned_pointers':'delete it->second;' in freed,
  'clear_map':'m_streams.clear();' in freed,
  'clear_parsers':'m_parsers.clear();' in freed,
  'overwrite_bumps_version':'stream->changes = res.first->second->changes + 1;' in replace_code,
  'overwrite_deletes_pointer':'delete res.first->second;' in replace_code,
  'overwrite_publishes_new':'res.first->second = stream;' in replace_code,
  'pairing_inplace_bl':'bl->isDualStream = true;' in pairing,
  'pairing_inplace_el':'el->isDualStream = true;' in pairing,
  'pairing_inplace_hdr':'bl->hdr_type = StreamHdrType::HDR_TYPE_DOLBYVISION;' in pairing,
  'pairing_no_version_bump':'->changes' not in pairing,
  'player_pointer_identity':'current.stream  != (void*)stream' in change,
  'player_changes_identity':'current.changes != stream->changes' in change,
  'player_hints_if_change':'current.hint != CDVDStreamInfo(*stream, true)' in change,
  'player_stores_pointer':'current.stream = (void*)stream;' in change,
  'player_stores_version':'current.changes = stream->changes;' in change,
  'codec_reset_pair_queue':'m_doviLayerPackets.clear();' in c,
 }
 if not all(conditions.values()):
  raise ValueError('original Kodi lifetime gate differs: '+str([k for k,v in conditions.items() if not v]))
 print('GAZELLE_FEL_STAGE52_REPO_SOURCE_PINS_PASS count=3')
 print('GAZELLE_FEL_STAGE52_REPO_SOURCE_GATES_PASS checks=%d'%len(conditions))
 print('ORIGINAL_PAIR_METADATA_MUTATION_NO_VERSION_NOTIFY=CONFIRMED_CODE_PATH')
 print('RUNTIME_UAF=NOT_DEMONSTRATED')

@dataclass(frozen=True)
class St:
 ident:int
 role:str
 version:int
 object_generation:int
 paired:bool=False
class Registry:
 def __init__(self):
  self.parts={};self.epoch=0;self.rev=0;self.serial=0;self.pair=None;self.offer=None
 def _revoke(self):
  self.parts={i:(replace(x,paired=False,version=x.version+1) if x.paired else x)
              for i,x in self.parts.items()}
  self.pair=None;self.offer=None
 def put(self,ident,role):
  self._revoke()
  old=self.parts.get(ident);self.serial+=1
  self.parts[ident]=St(ident,role,old.version+1 if old else 0,self.serial)
  self.rev+=1
 def observer(self,ident):
  a=self.parts[ident]
  return a.ident,a.object_generation,a.version,self.epoch
 def current(self,o):
  a=self.parts.get(o[0])
  return a is not None and self.observer(o[0])==o
 def offer_pair(self,bl,el,verified):
  self.offer=None
  if not verified or bl==el or bl not in self.parts or el not in self.parts:return None
  if self.parts[bl].role!='BL' or self.parts[el].role!='EL':return None
  self.offer=(bl,el,self.rev,self.epoch,self.parts[bl].object_generation,self.parts[el].object_generation)
  return self.offer
 def commit(self,proposal,fault=False):
  if proposal is None or proposal!=self.offer:return 'STALE'
  bl,el,rev,epoch,bg,eg=proposal
  if rev!=self.rev or epoch!=self.epoch or self.parts[bl].object_generation!=bg or self.parts[el].object_generation!=eg:
   return 'STALE'
  new=dict(self.parts);new[bl]=replace(new[bl],paired=True,version=new[bl].version+1)
  if fault:return 'ROLLBACK'
  new[el]=replace(new[el],paired=True,version=new[el].version+1)
  self.parts=new;self.pair=(bl,el);self.rev+=1;self.offer=None
  return 'PUBLISHED_IN_MODEL'
 def remove(self,ident):
  self._revoke();self.parts.pop(ident,None);self.rev+=1
 def rebuild(self,definitions):
  self._revoke();old=self.parts
  self.epoch+=1;self.rev+=1;self.parts={}
  for ident,role in definitions:
   self.serial+=1;prior=old.get(ident)
   self.parts[ident]=St(ident,role,prior.version+1 if prior else 0,self.serial)
 def flush(self):
  self._revoke();self.epoch+=1;self.rev+=1

class Tests(unittest.TestCase):
 def setUp(self):
  self.s=Registry();self.s.put(10,'BL');self.s.put(11,'EL')
 def offer(self):return self.s.offer_pair(10,11,True)
 def test_01_live_observer(self):self.assertTrue(self.s.current(self.s.observer(10)))
 def test_02_replace_invalidates(self):
  o=self.s.observer(10);self.s.put(10,'BL');self.assertFalse(self.s.current(o))
 def test_03_no_proof(self):self.assertIsNone(self.s.offer_pair(10,11,False))
 def test_04_atomic_commit(self):self.assertEqual(self.s.commit(self.offer()),'PUBLISHED_IN_MODEL')
 def test_05_both_commit(self):
  self.s.commit(self.offer());self.assertTrue(all(x.paired for x in self.s.parts.values()))
 def test_06_partial_rollback(self):
  t=self.offer();prior=dict(self.s.parts)
  self.assertEqual(self.s.commit(t,True),'ROLLBACK');self.assertEqual(self.s.parts,prior)
 def test_07_tampered_token(self):
  t=self.offer();self.assertEqual(self.s.commit(t[:-1]+(999,)),'STALE')
 def test_08_stale_replacement(self):
  t=self.offer();self.s.put(11,'EL');self.assertEqual(self.s.commit(t),'STALE')
 def test_09_replay(self):
  t=self.offer();self.s.commit(t);self.assertEqual(self.s.commit(t),'STALE')
 def test_10_rebuild_revokes(self):
  self.s.commit(self.offer());self.s.rebuild([(10,'BL'),(11,'EL')]);self.assertIsNone(self.s.pair)
 def test_11_rebuild_new_generation(self):
  o=self.s.observer(10);self.s.rebuild([(10,'BL')]);self.assertFalse(self.s.current(o))
 def test_12_remove_el_revokes_bl(self):
  self.s.commit(self.offer());o=self.s.observer(10)
  self.s.remove(11);self.assertFalse(self.s.current(o))
 def test_13_flush_revokes(self):
  t=self.offer();self.s.flush();self.assertEqual(self.s.commit(t),'STALE')
 def test_14_unknown_partner(self):self.assertIsNone(self.s.offer_pair(10,99,True))
 def test_15_inplace_change_requires_version(self):
  self.s.commit(self.offer());old=self.s.observer(10)
  self.s.put(11,'EL');self.assertFalse(self.s.current(old))
 def test_16_nonpair_stream_rebuild(self):
  self.s.rebuild([(10,'BL'),(12,'OTHER')]);self.assertIsNone(self.s.offer_pair(10,12,True))

def main():
 a=argparse.ArgumentParser(description=__doc__)
 a.add_argument('--selftest',action='store_true');a.add_argument('--source-dir',type=Path)
 options=a.parse_args()
 result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 if not result.wasSuccessful():raise ValueError('offline policy tests failed')
 print('GAZELLE_FEL_STAGE52_REPO_SYNTHETIC_PASS cases=%d'%result.testsRun)
 if options.selftest:return
 if not options.source_dir:a.error('--source-dir required')
 source_audit(options.source_dir.expanduser().resolve())
 print('GAZELLE_FEL_STAGE52_REPO_OFFLINE_PASS')
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,AssertionError) as e:
  print('GAZELLE_FEL_STAGE52_REPO_FAIL',e);raise SystemExit(1)
