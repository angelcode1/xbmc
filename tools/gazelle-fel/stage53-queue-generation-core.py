#!/usr/bin/env python3
"""Gazelle FEL Stage53: original Kodi worker-queue/codec-reuse source-only gate.
Python 3.9+. No device IO, no Kodi modifications, no FEL claims.
"""
import argparse, hashlib, unittest
from dataclasses import dataclass
from pathlib import Path

PINS={
 'DVDDemuxFFmpeg.cpp':'4955205e22ba462cff9998b03f9e5143d1ce1ef2',
 'VideoPlayer.cpp':'8b5cf1e6e2862936d2b3e58fe8997972d988c298',
 'DVDVideoCodecAndroidMediaCodec.cpp':'1a313fdc297db69607b2a3f0e82069def4b198f3',
 'VideoPlayerVideo.cpp':'51ca08050efcd32648d20876e7ac1cae9df6e368',
}
def segment(text,begin,end):
 a=text.index(begin);b=text.index(end,a+len(begin))
 return text[a:b]
def original_source_gate(folder):
 data={}
 for name,sha in PINS.items():
  p=folder/name
  if not p.is_file() or p.is_symlink():raise ValueError('source missing '+name)
  b=p.read_bytes()
  got=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
  if got!=sha:raise ValueError('original source Git blob mismatch '+name)
  data[name]=b.decode('utf-8')
 demux=data['DVDDemuxFFmpeg.cpp']
 player=data['VideoPlayer.cpp']
 codec=data['DVDVideoCodecAndroidMediaCodec.cpp']
 worker=data['VideoPlayerVideo.cpp']
 in_demux=segment(demux,'DemuxPacket* CDVDDemuxFFmpeg::ReadInternal(', 'DemuxPacket* CDVDDemuxFFmpeg::Read()')
 in_player=segment(player,'bool CVideoPlayer::ReadPacket(', 'void CVideoPlayer::')
 in_codec=segment(codec,'bool CDVDVideoCodecAndroidMediaCodec::Reconfigure(', 'CDVDVideoCodec::VCReturn CDVDVideoCodecAndroidMediaCodec::GetPicture(')
 in_add=segment(codec,'bool CDVDVideoCodecAndroidMediaCodec::AddData(', 'void CDVDVideoCodecAndroidMediaCodec::Reset()')
 in_reset=segment(codec,'void CDVDVideoCodecAndroidMediaCodec::Reset()', 'bool CDVDVideoCodecAndroidMediaCodec::Reconfigure(')
 in_setup=segment(worker,'void CVideoPlayerVideo::OpenStream(CDVDStreamInfo& hint,','void CVideoPlayerVideo::CloseStream(')
 in_process=segment(worker,'void CVideoPlayerVideo::Process()', 'void CVideoPlayerVideo::UpdatePlayerInfo()')
 in_recover=segment(worker,'bool CVideoPlayerVideo::ProcessDecoderOutput(', 'void CVideoPlayerVideo::')
 in_streamchange=segment(in_process,'else if (pMsg->IsType(CDVDMsg::GENERAL_STREAMCHANGE))','else if (pMsg->IsType(CDVDMsg::VIDEO_DRAIN))')
 checks={
  'demux_streamchange':'pPacket->iStreamId = DMX_SPECIALID_STREAMCHANGE;' in in_demux,
  'demux_rebuild_before_signal': in_demux.index('CreateStreams(m_program);')<in_demux.index('pPacket->iStreamId = DMX_SPECIALID_STREAMCHANGE;'),
  'player_receives_signal':'packet->iStreamId == DMX_SPECIALID_STREAMCHANGE' in in_player,
  'player_opens_defaults':'OpenDefaultStreams(false);' in in_player,
  'worker_streamchange_message':'CDVDMsg(GENERAL_STREAMCHANGE)' in worker,
  'worker_drain':'SetCodecControl(DVD_CODEC_CTRL_DRAIN)' in in_streamchange,
  'worker_streamchange_open':'OpenStream(msg->m_hints, std::move(msg->m_codec));' in in_streamchange,
  'worker_streamchange_no_reset':'m_pVideoCodec->Reset();' not in in_streamchange,
  'worker_reuse':'m_pVideoCodec->Reconfigure(hint)' in in_setup,
  'worker_reused_codec_moved':'codec = std::move(m_pVideoCodec);' in in_setup,
  'worker_only_replay_clear':'m_packets.clear();' in in_setup,
  'codec_reconfigure_ignores_id_extra':'~(CDVDStreamInfo::COMPARE_ID | CDVDStreamInfo::COMPARE_EXTRADATA)' in in_codec,
  'codec_reconfigure_can_succeed':'return true;' in in_codec,
  'codec_reconfigure_no_half_clear':'m_doviLayerPackets.clear();' not in in_codec,
  'codec_bl_el_halves':'m_doviLayerPackets.emplace_back(std::move(pending));' in in_add,
  'codec_reset_does_clear_halves':'m_doviLayerPackets.clear();' in in_reset,
  'worker_flush_resets':'m_pVideoCodec->Reset();' in in_process,
  'worker_adddata':'m_pVideoCodec->AddData(*pPacket)' in in_process,
  'worker_backpressure_requeues':'SendMessageBack(pMsg);' in in_process,
  'worker_replay_priority_ten':'SendMessage(msg, 10);' in in_recover,
  'worker_decoder_reopen':'m_pVideoCodec->Reopen();' in in_recover,
 }
 bad=[name for name,success in checks.items() if not success]
 if bad:raise ValueError('worker source mismatch: '+', '.join(bad))
 print('GAZELLE_FEL_STAGE53_REPO_PINNED_SOURCE_PASS files=4')
 print('GAZELLE_FEL_STAGE53_REPO_SOURCE_GATES_PASS checks=%d'%len(checks))
 print('CODEC_RECONFIGURE_REUSES_WITH_NO_EXPLICIT_PENDING_HALF_CLEAR=SOURCE_CONDITIONAL')
 print('WORKER_QUEUED_REPLAY=SOURCE_CONFIRMED_NOT_LIVE_REPLAY')
 return len(checks)

@dataclass(frozen=True)
class Half:
 epoch:int
 role:str
 pts:int
class GenerationModel:
 def __init__(self):
  self.epoch=0;self.valid=True;self.pending=[];self.replay=[]
 def boundary(self):
  self.epoch+=1;self.pending.clear();self.replay.clear();self.valid=False
 def rebind(self,epoch):
  if epoch!=self.epoch:return False
  self.valid=True
  return True
 def packet(self,half):
  if half.epoch!=self.epoch:return 'STALE'
  if not self.valid:return 'NO_BINDING'
  index=next((i for i,p in enumerate(self.pending) if p.role!=half.role and p.pts==half.pts),None)
  if index is None:self.pending.append(half);return 'WAIT'
  self.pending.pop(index);return 'PAIR'
class Tests(unittest.TestCase):
 def setUp(self):self.g=GenerationModel()
 def test_pair_bl_el(self):
  self.assertEqual(self.g.packet(Half(0,'BL',100)),'WAIT')
  self.assertEqual(self.g.packet(Half(0,'EL',100)),'PAIR')
 def test_pair_el_bl(self):
  self.g.packet(Half(0,'EL',100))
  self.assertEqual(self.g.packet(Half(0,'BL',100)),'PAIR')
 def test_different_pts(self):
  self.g.packet(Half(0,'BL',100))
  self.assertEqual(self.g.packet(Half(0,'EL',101)),'WAIT')
 def test_boundary_half_clear(self):
  self.g.packet(Half(0,'BL',100));self.g.boundary()
  self.assertFalse(self.g.pending)
 def test_boundary_replay_clear(self):
  self.g.replay.append(Half(0,'BL',100));self.g.boundary()
  self.assertFalse(self.g.replay)
 def test_old_packet_rejected(self):
  self.g.boundary();self.g.rebind(1)
  self.assertEqual(self.g.packet(Half(0,'EL',100)),'STALE')
 def test_no_binding_after_boundary(self):
  self.g.boundary()
  self.assertEqual(self.g.packet(Half(1,'EL',100)),'NO_BINDING')
 def test_rebind_epoch(self):
  self.g.boundary();self.assertTrue(self.g.rebind(1))
 def test_wrong_rebind(self):
  self.g.boundary();self.assertFalse(self.g.rebind(0))
 def test_new_pair(self):
  self.g.packet(Half(0,'BL',100));self.g.boundary();self.g.rebind(1)
  self.assertEqual(self.g.packet(Half(1,'EL',100)),'WAIT')
 def test_old_replay_rejected(self):
  self.g.boundary();self.g.rebind(1)
  self.assertEqual(self.g.packet(Half(0,'BL',100)),'STALE')
 def test_many_boundaries(self):
  for i in range(5):self.g.boundary()
  self.assertEqual(self.g.epoch,5)
 def test_new_epoch_pair(self):
  self.g.boundary();self.g.rebind(1)
  self.g.packet(Half(1,'BL',7))
  self.assertEqual(self.g.packet(Half(1,'EL',7)),'PAIR')
 def test_half_cannot_cross_epochs(self):
  self.g.packet(Half(0,'BL',7));self.g.boundary();self.g.rebind(1)
  self.assertEqual(self.g.packet(Half(1,'EL',7)),'WAIT')
 def test_reopen_requires_rebind(self):
  self.g.boundary();self.assertFalse(self.g.valid)
 def test_safe_model_has_no_payload(self):
  self.assertFalse(hasattr(Half(0,'BL',1),'data'))

def main():
 a=argparse.ArgumentParser(description=__doc__)
 a.add_argument('--selftest',action='store_true')
 a.add_argument('--source-dir',type=Path)
 args=a.parse_args()
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
 r=unittest.TextTestRunner(verbosity=0).run(suite)
 if not r.wasSuccessful():raise ValueError('synthetic tests failed')
 print('GAZELLE_FEL_STAGE53_REPO_GENERATION_TESTS_PASS cases=%d'%r.testsRun)
 if args.selftest:return
 if args.source_dir is None:a.error('--source-dir required')
 original_source_gate(args.source_dir.expanduser().resolve())
 print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
 print('GAZELLE_FEL_STAGE53_REPO_OFFLINE_PASS')
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,AssertionError,UnicodeError) as e:
  print('GAZELLE_FEL_STAGE53_REPO_FAIL',e)
  raise SystemExit(1)
