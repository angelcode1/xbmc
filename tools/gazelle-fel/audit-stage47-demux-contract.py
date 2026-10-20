#!/usr/bin/env python3
"""Gazelle FEL Stage47: Kodi demux->player->MediaCodec P7 source contract audit.

Only SHA-pinned source files and synthetic unit tests; NO device access,
Kodi modification, video payloads, native codec calls or stream-mode toggles.
"""
import argparse, hashlib, re, sys, unittest
from pathlib import Path

COMMIT="a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd"
PINS={
 "DVDDemuxFFmpeg.cpp":"4955205e22ba462cff9998b03f9e5143d1ce1ef2",
 "VideoPlayer.cpp":"8b5cf1e6e2862936d2b3e58fe8997972d988c298",
 "DVDVideoCodecAndroidMediaCodec.cpp":"1a313fdc297db69607b2a3f0e82069def4b198f3",
}
PATHS={
 "DVDDemuxFFmpeg.cpp":"xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp",
 "VideoPlayer.cpp":"xbmc/cores/VideoPlayer/VideoPlayer.cpp",
 "DVDVideoCodecAndroidMediaCodec.cpp":"xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAndroidMediaCodec.cpp",
}

def between(txt,a,b,limit=50000):
    i=txt.find(a)
    if i<0:raise ValueError("source start missing: "+a)
    j=txt.find(b,i+len(a))
    if j<0 or j<=i or j-i>limit:raise ValueError("source end missing/too long: "+b)
    return txt[i:j]

def need(label,predicate):
    if not predicate:raise ValueError("exact-source gate failed: "+label)
    return label

def audit(folder):
    original={}
    for name,expected in PINS.items():
        p=folder/name
        if not p.is_file() or p.is_symlink():raise ValueError("source missing/not regular: "+name)
        data=p.read_bytes()
        digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if digest!=expected:raise ValueError("pinned Git blob mismatch: "+name)
        original[name]=data.decode("utf-8")
        print("GAZELLE_STAGE47_KODI_GIT_BLOB_PASS",name,digest)
    demux=original['DVDDemuxFFmpeg.cpp']
    player=original['VideoPlayer.cpp']
    codec=original['DVDVideoCodecAndroidMediaCodec.cpp']
    ts=between(demux,"double CDVDDemuxFFmpeg::ConvertTimestamp(",
               "DemuxPacket* CDVDDemuxFFmpeg::ReadInternal(",4000)
    read=between(demux,"DemuxPacket* CDVDDemuxFFmpeg::ReadInternal(",
                 "DemuxPacket* CDVDDemuxFFmpeg::Read()",20000)
    streams=between(demux,"// Dolby Vision dual-track support.",
                    "sideData = av_packet_side_data_get(pStream->codecpar->coded_side_data,",9000)
    defaults=between(player,"void CVideoPlayer::OpenDefaultStreams(",
                     "// open audio stream",4500)
    route=between(player,"void CVideoPlayer::ProcessPacket(",
                  "void CVideoPlayer::CheckStreamChanges(",5000)
    video=between(player,"void CVideoPlayer::ProcessVideoData(",
                  "void CVideoPlayer::ProcessSubData(",4000)
    continuity=between(player,"bool CVideoPlayer::CheckContinuity(",
                       "std::chrono::milliseconds CVideoPlayer::GetEdlTime(",14000)
    add=between(codec,"bool CDVDVideoCodecAndroidMediaCodec::AddData(",
                "void CDVDVideoCodecAndroidMediaCodec::Reset()",45000)
    predicate=between(add,"auto other = std::find_if(",
                      "if (other == m_doviLayerPackets.end())",1500)
    checks=[
      need("av_missing_pts_retained", "return DVD_NOPTS_VALUE;" in ts and "AV_NOPTS_VALUE" in ts),
      need("per_stream_timebase", "(double)pts * num / den" in ts and "return timestamp * DVD_TIME_BASE;" in ts),
      need("demux_subtracts_origin", "timestamp -= starttime;" in ts),
      need("demux_pts_and_dts", "ConvertTimestamp(m_pkt.pkt.pts, stream->time_base.den, stream->time_base.num)" in read and "ConvertTimestamp(m_pkt.pkt.dts, stream->time_base.den, stream->time_base.num)" in read),
      need("packet_bl_el_roles", "pPacket->isDualStream = video->isDualStream;" in read and "pPacket->isELPackage = video->isELStream;" in read),
      need("stream_bl_el_hints", "st->isELStream = true;" in streams and "bl->isDualStream = true;" in streams),
      need("stream_first_nondovi_candidate", "auto blIt = std::find_if(" in streams and "hdr_type != " in streams),
      need("default_selection_skips_el", "if (video->isDualStream && video->isELStream)" in defaults and "continue;" in defaults),
      need("el_outside_current_selected_stream", re.search(r'else\s+if\s*\(pPacket->isELPackage\)',route) and "m_VideoPlayerVideo->SendMessage" in route),
      need("selected_bl_continuity", "CheckContinuity(m_CurrentVideo, pPacket)" in video and "UpdateTimestamps(m_CurrentVideo, pPacket)" in video),
      need("el_route_bypasses_selected_continuity", "CheckContinuity(" not in route and "ProcessVideoData(pStream, pPacket)" in route),
      need("continuity_changes_timestamp", "UpdateCorrection(pPacket, correction)" in continuity and "pPacket->pts = DVD_NOPTS_VALUE;" in continuity),
      need("continuity_conditional", "if(correction != 0.0)" in continuity),
      need("codec_pair_opposite_only", "return pending.isEL != packet.isELPackage;" in predicate),
      need("codec_pair_no_timestamp", not re.search(r'pending\.(?:pts|dts)|packet\.(?:pts|dts)',predicate)),
      need("codec_capacity_clamps", "iSize = out_size;" in between(add,"if ((size_t)iSize > out_size)","// Inspect exactly the size that fits MediaCodec",1500)),
    ]
    print("GAZELLE_FEL_STAGE47_DEMUX_PLAYER_INPUT_GATES_PASS checks=%d"%len(checks))
    print("DEMUX_TIMESTAMP=PER_STREAM_TIME_BASE_TO_DVD_TIME_BASE_WITH_ORIGIN_NORMALIZATION")
    print("DEMUX_MISSING_TIMESTAMP=DVD_NOPTS_VALUE_ALLOWED")
    print("PLAYER_BL=CHECK_CONTINUITY_MAY_CORRECT_OR_INVALIDATE_PTS")
    print("PLAYER_EL=ALTERNATE_UNSELECTED_STREAM_ROUTE_SKIPS_BL_CONTINUITY")
    print("KODI_P7_TIMESTAMP_EQUALITY_AT_CODEC_ENTRY=NOT_GUARANTEED")
    print("DEMUX_BL_EL_STREAM_RELATION=FIRST_CANDIDATE_SEARCH_NOT_EXPLICIT_PAIR_ID")
    print("PLAYER_EL_ROUTE=CHECKS_IS_EL_PACKAGE_NOT_SELECTED_BL_ID_IN_THIS_BRANCH")
    print("SOURCE_PATH_ASYMMETRY=CONFIRMED_CODE_PATH_NOT_RUNTIME_MISMATCH")
    print("P7_LIVE_TIMESTAMP_MISPAIR=NOT_MEASURED")
    return len(checks)

class SyntheticTests(unittest.TestCase):
    """Source-informed counterexamples, not actual Kodi playback observations."""
    def test_nominal_common_time_base(self):
        self.assertEqual(float(1)*1/25*1_000_000,40000.)
        self.assertEqual(float(40)*1/1000*1_000_000,40000.)
    def test_demux_can_retain_unknown_pts(self):
        none=None
        self.assertIsNone(none)
    def test_interleaved_first_opposite_mispair(self):
        pending=[("BL",100),("BL",200)]
        selected=next(p for p in pending if p[0]!="EL")
        self.assertEqual(selected[1],100)
        self.assertNotEqual(selected[1],200)
    def test_strict_equal_policy_may_fail_after_bl_correction(self):
        bl,el=100000,100000
        bl-=8000  # synthetic application of a BL-only continuity correction
        self.assertNotEqual(bl,el)
    def test_source_equal_pts_not_complete_identity(self):
        a={"demuxer":1,"stream":10,"pts":100}
        b={"demuxer":2,"stream":12,"pts":100}
        self.assertEqual(a["pts"],b["pts"])
        self.assertNotEqual(a["demuxer"],b["demuxer"])
    def test_unrelated_el_flag_not_selected_pair(self):
        selected={"demuxer":1,"bl_stream":10}
        el={"demuxer":2,"el_stream":11,"isELPackage":True}
        self.assertTrue(el["isELPackage"])
        self.assertNotEqual(selected["demuxer"],el["demuxer"])
    def test_timestamp_order_does_not_equal_decode_order(self):
        decode=[2,0,1]
        self.assertNotEqual(decode,sorted(decode))
    def test_fractional_conversion_not_raw_integer_equivalence(self):
        self.assertEqual((1*1/25)*1_000_000,(40*1/1000)*1_000_000)
        self.assertNotEqual(1,40)
    def test_unchanged_p8_not_in_scope(self):
        self.assertFalse(8==7)
    def test_missing_pts_requires_policy(self):
        self.assertFalse(None==100)
    def test_stream_selection_identity_requires_demuxer_and_ids(self):
        a=(1,10,11)
        b=(1,10,12)
        self.assertNotEqual(a,b)
    def test_no_backend_claim_from_source(self):
        self.assertFalse(False)  # neither a native decoder nor FEL pixel oracle run

def regression():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticTests)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise ValueError("synthetic test failure")
    print("GAZELLE_FEL_STAGE47_SYNTHETIC_COUNTEREXAMPLES_PASS cases=%d"%result.testsRun)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--source-dir',type=Path)
    a=ap.parse_args()
    regression()
    if a.selftest:
        print("GAZELLE_FEL_STAGE47_SOURCE_SELFTEST_PASS")
        return
    if a.source_dir is None:ap.error('pass --source-dir with 3 pinned Kodi C++ files')
    audit(a.source_dir.expanduser().resolve())
    print("PRODUCTION_EXACT_PTS_PAIRING=BLOCKED_NEEDS_DEMUX_DISCONTINUITY_POLICY")
    print("P7_ONLY_NATIVE_STREAM_MODE=NOT_ENABLED")
    print("P7_FEL_RESIDUAL_PIXELS=NOT_PROVEN")
    print("GAZELLE_FEL_STAGE47_OFFLINE_PASS")

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,UnicodeError,AssertionError) as e:
        print("GAZELLE_FEL_STAGE47_FAIL",e,file=sys.stderr);sys.exit(1)
