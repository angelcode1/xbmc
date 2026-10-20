#!/usr/bin/env python3
"""Stage48 minimal inspectable reference model; offline only, not installed Kodi.

Full 36-regression source/policy verifier is distributed separately as a
SHA-pinned Stage48 macOS bundle. This model establishes core acceptance rules.
"""
from dataclasses import dataclass
from fractions import Fraction
import unittest

MAX_I32=(1<<31)-1

@dataclass(frozen=True)
class Clock:
    stream_id:int
    num:int
    den:int
    origin:Fraction
    correction:Fraction
    verified:bool

    def canonical(self,pts):
        if not self.verified or self.den<=0 or self.num<=0 or type(pts) is not int:
            return None
        return Fraction(pts*self.num,self.den)-self.origin+self.correction

@dataclass(frozen=True)
class Binding:
    demux_id:int
    bl:Clock
    el:Clock
    epoch:int
    p7_only:bool
    verified:bool

@dataclass(frozen=True)
class Packet:
    demux_id:int
    stream_id:int
    role:str
    pts:int|None
    size:int
    epoch:int

class ReferencePairPolicy:
    """No video payload bytes: only metadata and sizes. Reject ambiguous states."""
    def __init__(self,binding,max_packets=8,max_bytes=8*1024*1024):
        if max_packets<=0 or max_bytes<=0:raise ValueError('invalid limits')
        self.binding=binding
        self.limit=max_packets
        self.bytes=max_bytes
        self.pending=[]

    def rebind(self,next_binding):
        if next_binding.epoch<=self.binding.epoch:raise ValueError('epoch not advanced')
        self.pending.clear()
        self.binding=next_binding

    def submit(self,p,capacity):
        b=self.binding
        if not b.p7_only:return 'BYPASS_NON_P7'
        if not b.verified or b.bl.stream_id==b.el.stream_id:
            self.pending.clear();return 'REJECT_BINDING'
        if p.epoch!=b.epoch:
            self.pending.clear();return 'REJECT_EPOCH'
        clk=b.bl if p.role=='BL' else b.el if p.role=='EL' else None
        if clk is None or p.demux_id!=b.demux_id or p.stream_id!=clk.stream_id:
            self.pending.clear();return 'REJECT_TRACK'
        if type(p.size) is not int or p.size<=0 or p.size>MAX_I32 or type(capacity) is not int or capacity<=0:
            self.pending.clear();return 'REJECT_SIZE'
        timestamp=clk.canonical(p.pts)
        if timestamp is None:
            self.pending.clear();return 'REJECT_TIMELINE'
        if any(old.role==p.role and t==timestamp for old,t in self.pending):
            self.pending.clear();return 'REJECT_DUPLICATE'
        idx=next((i for i,(old,t) in enumerate(self.pending) if old.role!=p.role and t==timestamp),None)
        if idx is not None:
            previous,_=self.pending.pop(idx)
            if p.size+previous.size>MAX_I32 or p.size+previous.size>capacity:
                self.pending.clear();return 'REJECT_WHOLE_AU'
            return 'PAIR'
        if len(self.pending)>=self.limit or sum(v.size for v,_ in self.pending)+p.size>self.bytes:
            self.pending.clear();return 'REJECT_BUDGET'
        self.pending.append((p,timestamp));return 'WAIT'


def binding(epoch=0,verified=True,p7=True):
    return Binding(1,Clock(10,1,1000,Fraction(0),Fraction(0),verified),
                   Clock(11,1,1000,Fraction(0),Fraction(0),verified),epoch,p7,verified)

class PolicyTests(unittest.TestCase):
    def setUp(self):self.q=ReferencePairPolicy(binding())
    def p(self,role,pts,stream=None,size=100,epoch=0,demux=1,capacity=1000):
        if stream is None:stream=10 if role=='BL' else 11
        return self.q.submit(Packet(demux,stream,role,pts,size,epoch),capacity)
    def test_bl_first(self):self.assertEqual((self.p('BL',100),self.p('EL',100)),('WAIT','PAIR'))
    def test_el_first(self):self.assertEqual((self.p('EL',100),self.p('BL',100)),('WAIT','PAIR'))
    def test_out_of_order(self):
        self.p('BL',100);self.p('BL',200)
        self.assertEqual(self.p('EL',200),'PAIR')
        self.assertEqual(self.q.pending[0][0].pts,100)
    def test_missing_pts(self):self.assertEqual(self.p('BL',None),'REJECT_TIMELINE')
    def test_wrong_demux(self):self.assertEqual(self.p('BL',100,demux=2),'REJECT_TRACK')
    def test_wrong_track(self):self.assertEqual(self.p('EL',100,stream=99),'REJECT_TRACK')
    def test_unverified_clock(self):
        self.q=ReferencePairPolicy(binding(verified=False));self.assertEqual(self.p('BL',100),'REJECT_BINDING')
    def test_duplicate(self):
        self.p('BL',100);self.assertEqual(self.p('BL',100),'REJECT_DUPLICATE')
    def test_over_capacity(self):
        self.p('BL',100);self.assertEqual(self.p('EL',100,capacity=199),'REJECT_WHOLE_AU')
    def test_queue_cap(self):
        for i in range(8):self.assertEqual(self.p('BL',i),'WAIT')
        self.assertEqual(self.p('BL',8),'REJECT_BUDGET')
    def test_epoch_rebind(self):
        self.p('BL',100);self.q.rebind(binding(epoch=1))
        self.assertEqual(self.p('EL',100,epoch=1),'WAIT')
    def test_stale_packet(self):
        self.q.rebind(binding(epoch=1));self.assertEqual(self.p('BL',100),'REJECT_EPOCH')
    def test_p8_bypass(self):
        self.q=ReferencePairPolicy(binding(p7=False))
        self.assertEqual(self.p('BL',100),'BYPASS_NON_P7')
    def test_explicit_correction(self):
        b=binding();corrected=Clock(10,1,1000,Fraction(0),Fraction(-1,1000),True)
        self.q=ReferencePairPolicy(Binding(1,corrected,b.el,0,True,True))
        self.assertEqual((self.p('BL',101),self.p('EL',100)),('WAIT','PAIR'))

if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(PolicyTests))
    if not r.wasSuccessful():raise SystemExit(1)
    print('GAZELLE_FEL_STAGE48_REPO_CORE_SELFTEST_PASS cases=%d'%r.testsRun)
