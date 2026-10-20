#!/usr/bin/env python3
"""Gazelle FEL Stage46: pinned Kodi-source audit + synthetic P7 packet-policy tests.

HOST ONLY. This is a contract MODEL, not a Kodi patch or a decoder/feed
implementation. PTS units, memory limits, stream syntax, and device safety
remain UNVALIDATED against native Fire OS. Never performs device IO.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from typing import Optional

KODI_GIT_BLOB = '1a313fdc297db69607b2a3f0e82069def4b198f3'
KODI_COMMIT = 'a7046638a7ba7deb06c12f3a9ad4f05c85f5bacd'
MAX_SIGNED_INT = (1 << 31) - 1


def source_region(source: str, begin: str, end: str, limit: int = 50_000) -> str:
    a = source.find(begin)
    if a < 0:
        raise ValueError('missing pinned Kodi code marker: ' + begin)
    b = source.find(end, a + len(begin))
    if b <= a or b - a > limit:
        raise ValueError('ambiguous/missing bounded Kodi code marker: ' + end)
    return source[a:b]


def audit_uploaded_source(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError('Kodi source file absent or symlink')
    payload = path.read_bytes()
    git_blob = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\x00' + payload).hexdigest()
    if git_blob != KODI_GIT_BLOB:
        raise ValueError('exact integrated Kodi Git blob SHA-1 mismatch')
    src = payload.decode('utf-8')
    add = source_region(src, 'bool CDVDVideoCodecAndroidMediaCodec::AddData(',
                        'void CDVDVideoCodecAndroidMediaCodec::Reset()')
    pair = source_region(add, 'auto other = std::find_if(',
                         'if (other == m_doviLayerPackets.end())', 2000)
    match = re.search(r'\[&packet\]\(const DolbyLayerPacket& pending\)\s*\{(.*?)\}', pair, re.S)
    if not match or not re.search(r'return\s+pending\.isEL\s*!=\s*packet\.isELPackage\s*;', match[1]):
        raise ValueError('BL/EL pairing predicate no longer matches pinned source')
    if re.search(r'\b(?:pts|dts)\b', match[1]):
        raise ValueError('pairing timestamp predicate modified: audit again')
    checks = {
        'queue_max_8': bool(re.search(r'while\s*\(m_doviLayerPackets\.size\(\)\s*>\s*8\)', add)),
        'overflow_drops_oldest': 'm_doviLayerPackets.pop_front();' in add,
        'stores_pending_pts': bool(re.search(r'pending\.pts\s*=\s*pts\s*;', add)),
        'stores_pending_dts': bool(re.search(r'pending\.dts\s*=\s*dts\s*;', add)),
        'layer_convert': bool(re.search(r'm_bitstream->Convert\(blData,\s*blSize,\s*elData,\s*elSize\)', add)),
        'uses_bl_pending_pts_on_el_arrival': bool(re.search(r'pts\s*=\s*pending\.pts\s*;', add)),
        'converted_size': 'm_bitstream->GetConvertSize()' in add,
        'capacity_clamp': bool(re.search(r'if\s*\(\(size_t\)iSize\s*>\s*out_size\)', add)),
        'capacity_shortens_packet': bool(re.search(r'iSize\s*=\s*out_size\s*;', source_region(
            add, 'if ((size_t)iSize > out_size)',
            '// Inspect exactly the size that fits MediaCodec', 1200))),
        'queued_android_input': 'm_codec->queueInputBuffer(m_indexInputBuffer, offset, iSize, presentationTimeUs, flags)' in add,
        'queued_secure_android_input': 'm_codec->queueSecureInputBuffer(m_indexInputBuffer,' in add,
        'pts_shift': bool(re.search(r'presentationTimeUs\s*=\s*\(pts\s*-\s*m_dtsShift\)', add)),
        'dts_fallback': bool(re.search(r'presentationTimeUs\s*=\s*\(dts\s*-\s*m_dtsShift\)', add)),
    }
    reset = source_region(src, 'void CDVDVideoCodecAndroidMediaCodec::Reset()',
                          'bool CDVDVideoCodecAndroidMediaCodec::Reconfigure(', 4500)
    checks['reset_clears_pending'] = 'm_doviLayerPackets.clear();' in reset
    if not all(checks.values()):
        raise ValueError('one or more original Kodi input/control checks changed: ' + str(
            [k for k, v in checks.items() if not v]))
    print('GAZELLE_FEL_STAGE46_PINNED_KODI_SOURCE_PASS commit=' + KODI_COMMIT)
    print('GAZELLE_FEL_STAGE46_EXACT_SOURCE_GATES_PASS checks=' + str(len(checks) + 1))
    print('SOURCE_PAIR_PREDICATE=OPPOSITE_LAYER_NO_PTS_OR_DTS_EQUALITY')
    print('SOURCE_QUEUE_OVERFLOW=EVICTS_OLDEST_INSTEAD_OF_FAIL_CLOSED')
    print('SOURCE_CAPACITY_PATH=SHORTENS_ACCESS_UNIT')
    print('SOURCE_RESET=CLEARS_PENDING_LAYER_PACKETS')
    print('P7_LIVE_TIMESTAMP_MISPAIR=NOT_OBSERVED')
    print('P7_LIVE_CAPACITY_TRUNCATION=NOT_OBSERVED')
    return checks


@dataclass(frozen=True)
class Packet:
    layer: str
    pts: Optional[int]   # abstract integer ticks, NOT verified native units
    size: int            # not actual video data; counts only
    generation: int = 0


@dataclass(frozen=True)
class Pair:
    pts: int
    bl_size: int
    el_size: int
    generation: int


class ReferencePairer:
    """Policy proposal, deliberately not a direct implementation of Kodi.

    - strict BL/EL PTS identity (no guessed tolerance)
    - fail closed on missing/duplicate timestamps or overflow
    - no cross-discontinuity pair
    - retains sizes only, no sensitive stream samples
    """
    def __init__(self, max_pending: int = 8, max_pending_bytes: int = 8 * 1024 * 1024):
        if max_pending <= 0 or max_pending_bytes <= 0:
            raise ValueError('invalid model limits')
        self.max_pending = max_pending
        self.max_pending_bytes = max_pending_bytes
        self.pending: list[Packet] = []
        self.generation = 0

    def reset(self):
        self.pending.clear()
        self.generation += 1

    def submit(self, p: Packet) -> tuple[str, Optional[Pair]]:
        if (p.layer not in ('BL', 'EL') or type(p.pts) is not int or
            type(p.size) is not int or p.size <= 0 or p.size > MAX_SIGNED_INT or
            p.generation != self.generation):
            self.pending.clear()
            return 'REJECT_INVALID', None
        if any(q.layer == p.layer and q.pts == p.pts for q in self.pending):
            self.pending.clear()
            return 'REJECT_DUPLICATE', None
        match = next((i for i,q in enumerate(self.pending)
                      if q.layer != p.layer and q.pts == p.pts and q.generation == p.generation), None)
        if match is not None:
            q = self.pending.pop(match)
            bl, el = (p,q) if p.layer == 'BL' else (q,p)
            if bl.size + el.size > MAX_SIGNED_INT:
                self.pending.clear()
                return 'REJECT_SIZE_OVERFLOW', None
            return 'PAIRED', Pair(p.pts, bl.size, el.size, p.generation)
        if (len(self.pending) >= self.max_pending or
            sum(q.size for q in self.pending) + p.size > self.max_pending_bytes):
            self.pending.clear()
            return 'REJECT_BOUNDED_QUEUE', None
        self.pending.append(p)
        return 'WAIT', None


def strict_input_budget(encoded_size: int, capacity: int) -> str:
    """Never report success for a partial/shortened access unit."""
    if (type(encoded_size) is not int or type(capacity) is not int or
        encoded_size <= 0 or capacity <= 0 or encoded_size > MAX_SIGNED_INT):
        return 'REJECT_INVALID'
    if encoded_size > capacity:
        return 'REJECT_OVERSIZE_NO_TRUNCATION'
    return 'ACCEPT_WHOLE_ACCESS_UNIT'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.q = ReferencePairer()
    def send(self, layer, pts, size=100):
        return self.q.submit(Packet(layer, pts, size, self.q.generation))
    def test_bl_then_el(self):
        self.assertEqual(self.send('BL',100)[0], 'WAIT')
        result,pair=self.send('EL',100,40)
        self.assertEqual((result,pair.bl_size,pair.el_size,pair.pts),('PAIRED',100,40,100))
    def test_el_then_bl(self):
        self.send('EL',100,40)
        result,pair=self.send('BL',100)
        self.assertEqual((result,pair.bl_size,pair.el_size,pair.pts),('PAIRED',100,40,100))
    def test_interleaved_no_cross_frame_pair(self):
        self.send('BL',100)
        self.send('BL',200)
        result,pair=self.send('EL',200)
        self.assertEqual((result,pair.pts),('PAIRED',200))
        self.assertEqual([(x.layer,x.pts) for x in self.q.pending],[('BL',100)])
    def test_el_interleaved(self):
        self.send('EL',100);self.send('EL',200)
        _,pair=self.send('BL',200)
        self.assertEqual(pair.pts,200)
    def test_different_pts_never_pair(self):
        self.send('BL',100)
        self.assertEqual(self.send('EL',200)[0],'WAIT')
        self.assertEqual(len(self.q.pending),2)
    def test_missing_timestamp_rejected(self):
        self.send('BL',100)
        self.assertEqual(self.send('EL',None)[0],'REJECT_INVALID')
        self.assertEqual(len(self.q.pending),0)
    def test_float_timestamp_rejected(self):
        self.assertEqual(self.send('BL',100.01)[0],'REJECT_INVALID')
    def test_bool_timestamp_rejected(self):
        self.assertEqual(self.send('BL',True)[0],'REJECT_INVALID')
    def test_duplicate_bl_refused(self):
        self.send('BL',100)
        self.assertEqual(self.send('BL',100)[0],'REJECT_DUPLICATE')
        self.assertFalse(self.q.pending)
    def test_duplicate_el_refused(self):
        self.send('EL',100)
        self.assertEqual(self.send('EL',100)[0],'REJECT_DUPLICATE')
    def test_overflow_fails_closed(self):
        for i in range(8):
            self.assertEqual(self.send('BL',i)[0],'WAIT')
        self.assertEqual(self.send('BL',8)[0],'REJECT_BOUNDED_QUEUE')
        self.assertFalse(self.q.pending)
    def test_byte_budget_fails_closed(self):
        q=ReferencePairer(max_pending_bytes=100)
        self.assertEqual(q.submit(Packet('BL',0,80))[0],'WAIT')
        self.assertEqual(q.submit(Packet('EL',1,30))[0],'REJECT_BOUNDED_QUEUE')
    def test_flush_excludes_prior_generation(self):
        self.send('BL',100);gen=self.q.generation;self.q.reset()
        self.assertEqual(self.q.submit(Packet('EL',100,40,gen))[0],'REJECT_INVALID')
        self.assertEqual(self.send('EL',100)[0],'WAIT')
    def test_reset_discards_queue(self):
        self.send('BL',100);self.q.reset()
        self.assertEqual(len(self.q.pending),0)
        self.assertEqual(self.send('EL',100)[0],'WAIT')
    def test_negative_size_rejected(self):
        self.assertEqual(self.send('BL',100,-1)[0],'REJECT_INVALID')
    def test_zero_size_rejected(self):
        self.assertEqual(self.send('BL',100,0)[0],'REJECT_INVALID')
    def test_over_int_max_rejected(self):
        self.assertEqual(self.send('BL',100,MAX_SIGNED_INT+1)[0],'REJECT_INVALID')
    def test_pair_sum_overflows_signed_int(self):
        q=ReferencePairer(max_pending_bytes=MAX_SIGNED_INT)
        self.assertEqual(q.submit(Packet('BL',0,MAX_SIGNED_INT))[0],'WAIT')
        self.assertEqual(q.submit(Packet('EL',0,1))[0],'REJECT_SIZE_OVERFLOW')
    def test_unsupported_layer_rejected(self):
        self.assertEqual(self.send('RPU',100)[0],'REJECT_INVALID')
    def test_exact_buffer_fit(self):
        self.assertEqual(strict_input_budget(4096,4096),'ACCEPT_WHOLE_ACCESS_UNIT')
    def test_oversized_input_no_truncate(self):
        self.assertEqual(strict_input_budget(4097,4096),'REJECT_OVERSIZE_NO_TRUNCATION')
    def test_zero_capacity_rejected(self):
        self.assertEqual(strict_input_budget(100,0),'REJECT_INVALID')
    def test_invalid_budget_sizes(self):
        self.assertEqual(strict_input_budget(0,100),'REJECT_INVALID')
        self.assertEqual(strict_input_budget(MAX_SIGNED_INT+1,MAX_SIGNED_INT+1),'REJECT_INVALID')
    def test_no_timebase_assumptions(self):
        self.send('BL',10)
        self.assertEqual(self.send('EL',11)[0],'WAIT')
    def test_bl_el_size_values_not_payloads(self):
        self.send('BL',42,101)
        _,pair=self.send('EL',42,202)
        self.assertEqual((pair.bl_size,pair.el_size),(101,202))
    def test_existing_p8_unaffected_by_reference_model(self):
        # This is an offline policy assertion, NOT execution of Kodi's P8 path.
        self.assertEqual(self.q.pending,[])
        self.assertEqual(strict_input_budget(10,10),'ACCEPT_WHOLE_ACCESS_UNIT')


def run_tests(verbosity=1) -> int:
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    out=unittest.TextTestRunner(stream=sys.stderr,verbosity=verbosity).run(suite)
    if not out.wasSuccessful():
        raise ValueError('offline regression test failure')
    return out.testsRun


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--kodi',type=Path)
    ap.add_argument('--json',type=Path,help='optional source-only sanitized output')
    args=ap.parse_args()
    count=run_tests()
    print('GAZELLE_FEL_STAGE46_SYNTHETIC_REGRESSIONS_PASS cases=%d'%count)
    if args.selftest:
        print('GAZELLE_FEL_STAGE46_SOURCE_SELFTEST_PASS')
        return
    if args.kodi is None:
        ap.error('provide --kodi exact integrated Kodi C++ source')
    gates=audit_uploaded_source(args.kodi.expanduser().resolve())
    result={
        'schema':'gazelle-fel-stage46-source-model-v1',
        'pinned_kodi_git_blob':KODI_GIT_BLOB,
        'tests_passed':count,
        'source_gates_passed':len(gates)+1,
        'reference_model_only':True,
        'kodi_source_modified':False,
        'device_access':False,
        'original_vendor_binary_distributed':False,
        'runtime_p7_mispair_measured':False,
        'runtime_p7_truncation_measured':False,
        'native_packetization_pts_timebase_verified':False,
        'p7_fel_pixel_reconstruction_proven':False,
        'native_p7_backend_ready':False,
    }
    if args.json:
        dest=args.json.expanduser().resolve()
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(result,indent=2)+'\n')
    print('MODEL_PTS_MATCH=EXACT_INTEGER_IDENTITY_ASSUMPTION_NOT_VALIDATED_FOR_ALL_DEMUXERS')
    print('MODEL_QUEUE_LIMIT=8_PACKETS_AND_8MIB_EXAMPLE_NOT_PRODUCTION_LIMITS')
    print('MODEL_INPUT_BUDGET=REJECT_WHOLE_OVERSIZE_ACCESS_UNIT_NEVER_TRUNCATE')
    print('REFERENCE_MODEL_NOT_COMPILED_KODI_OR_DECODER_PATCH=true')
    print('NATIVE_STREAM_HEVC_PACKET_PTS_CONTRACT=NOT_PROVEN')
    print('KODI_P7_MISPAIR_IN_OWNER_CAPTURE=NOT_PROVEN')
    print('KODI_P7_INPUT_TRUNCATION_IN_OWNER_CAPTURE=NOT_PROVEN')
    print('P7_NATIVE_FEL_BACKEND=BLOCKED_NO_GO')
    print('P7_FEL_PIXEL_RECONSTRUCTION=NOT_PROVEN')
    print('GAZELLE_FEL_STAGE46_OFFLINE_PASS')

if __name__=='__main__':
    try:
        main()
    except (ValueError,OSError,UnicodeError,AssertionError) as exc:
        print('GAZELLE_FEL_STAGE46_FAIL',exc,file=sys.stderr)
        raise SystemExit(1)
