"""Independent source-contract and abstract protocol checks; NOT DUT simulation."""
from pathlib import Path
from dataclasses import dataclass, replace
import argparse
import hashlib
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source/Bf16KvAppendRuntimeOwnerV13.scala'
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
ORIGINAL=args.original_source
ORIGINAL_SHA='bab2160771bf09755dc072d87bf72940bc62b41f8d5edf70cfe10da90caa5264'
REQUIRED=[
 'class Bf16KvAppendRuntimeOwnerV13 extends Module',
 'val rowWidth = UInt(16.W)', 'val kvHeads = UInt(16.W)',
 'r.tokens:=j.m;r.rowWidth:=j.n;r.kvHeads:=2.U;r.headDim:=j.k',
 'r.capacityTokens:=j.cacheCapacity;r.appendStart:=j.queryStart',
 'r.currentLength:=j.cacheLength;r.expectedLength:=j.expectedCacheLength',
 'r.currentGeneration:=j.currentGeneration;r.expectedGeneration:=j.expectedGeneration',
 'val MaxTokens=128', 'val CapacityTokens=128', 'val KvHeads=2', 'val HeadDim=256',
 'j.tokens>Bf16KvAppendRuntimeAbiV13.MaxTokens.U',
 'j.rowWidth=/=512.U || j.kvHeads=/=Bf16KvAppendRuntimeAbiV13.KvHeads.U',
 'j.headDim=/=Bf16KvAppendRuntimeAbiV13.HeadDim.U',
 'j.capacityTokens=/=Bf16KvAppendRuntimeAbiV13.CapacityTokens.U',
 'j.currentLength>j.capacityTokens || appendEnd>j.capacityTokens.pad(66)',
 'j.appendStart=/=j.currentLength || j.expectedLength=/=j.currentLength',
 'j.expectedGeneration=/=j.currentGeneration || j.currentGeneration==="hffffffff".U',
 '!j.cold || j.appendStart=/=0.U || j.currentLength=/=0.U || j.currentGeneration=/=0.U',
 'base(5,0)=/=0.U || base.pad(66)+size>(BigInt(1)<<56).U',
 'overlap(j.keyInput,inputBytes,j.valueInput,inputBytes)',
 'overlap(j.cacheBase,cacheBytes,j.keyInput,inputBytes)',
 'overlap(j.cacheBase,cacheBytes,j.valueInput,inputBytes)',
 'j.tag==="hffffffff".U',
 'val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)',
 'when(unknownMemory){drainUnknown:=true.B}',
 'io.resourcesDrained:=noService && memoryAccepted===sequence && quiet && !drainUnknown && !unknownMemory',
 'io.response.ready:=memoryDebt && !unknownMemory',
 'HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || drainUnknown)',
 '(poison || currentFault || drainUnknown) && memoryOffer && !memoryHeld.held && !io.memory.fire',
 'memoryAccepted:=memoryAccepted+1.U',
 'when(sequence=/="hffffffff".U){sequence:=sequence+1.U}',
 'when(state===waitTail && !r.error)',
 'when(valuePlane){valueAckBytes:=valueAckBytes+64.U}',
 '.otherwise{keyAckBytes:=keyAckBytes+64.U}',
 '.elsewhen(poison || currentFault || drainUnknown){state:=finish}',
 'when(state===waitInput){data:=r.data;state:=writeTail}',
 'when(beat+&1.U===(job.tokens<<4))',
 'when(valuePlane){state:=finish}',
 '.otherwise{valuePlane:=true.B;beat:=0.U;state:=readInput}',
 'io.memory.bits.data:=Mux(state===writeTail,data,0.U)',
 'io.memory.bits.mask:=Mux(state===writeTail,Fill(64,1.U(1.W)),0.U)',
 'val planeOffset=Mux(valuePlane,job.capacityTokens.pad(66)<<10,0.U)',
 'val inputAddress=Mux(valuePlane,job.valueInput,job.keyInput).pad(66)+beatOffset',
 'val tailAddress=job.cacheBase.pad(66)+planeOffset+appendOffset+beatOffset',
 'val exact=memoryAccepted===expectedMemory && sequence===expectedMemory &&',
 'keyAckBytes===expectedPlaneBytes && valueAckBytes===expectedPlaneBytes && bytes===expectedBytes',
 'val complete=status===Status.Ok.U && !poison && !currentFault && exact',
 'when(state===finish && io.resourcesDrained)',
 'terminal.proposalValid:=complete',
 'terminal.proposedLength:=job.currentLength+Mux(complete,job.tokens,0.U)',
 'terminal.proposedGeneration:=job.currentGeneration+Mux(complete,1.U,0.U)',
 'terminal.accepted:=job;terminal.tag:=job.tag',
 'io.done.valid:=state===report;io.done.bits:=terminal',
 'when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}',
]

def source_checks(s):
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()!=ORIGINAL_SHA:raise ValueError('original source identity')
    missing=[p for p in REQUIRED if p not in s]
    if missing:raise ValueError('source contract: '+repr(missing))
    for p in ('Module(new ', 'BlackBox', 'ScalarOp.', 'UnifiedScalarClient', 'scala.math', 'FloatMath'):
        if p in s:raise ValueError('forbidden new arithmetic/transport '+p)
    if s.count('terminal.accepted:=')!=1:raise ValueError('terminal overwritten')
    if s.count('memoryAccepted:=memoryAccepted+1.U')!=1:raise ValueError('accepted counter')
    if s.count('sequence:=sequence+1.U')!=1:raise ValueError('retired counter')
    return len(REQUIRED)+10

@dataclass(frozen=True)
class Job:
    tokens:int=16
    row_width:int=512
    heads:int=2
    dim:int=256
    key:int=0x100000
    value:int=0x200000
    cache:int=0x300000
    capacity:int=128
    append:int=0
    current_length:int=0
    expected_length:int=0
    generation:int=0
    expected_generation:int=0
    cold:bool=True
    tag:int=0x13572468

def valid(j):
    input_bytes=j.tokens*1024
    spans=((j.key,input_bytes),(j.value,input_bytes),(j.cache,j.capacity*2048))
    geometry=1<=j.tokens<=128 and j.row_width==512 and j.heads==2 and j.dim==256 and j.capacity==128
    geometry &= j.current_length<=j.capacity and j.append+j.tokens<=j.capacity
    spans_good=all(a>=0 and a%64==0 and a+n<=2**56 for a,n in spans)
    spans_good &= all(not(a<b+nb and b<a+na) for i,(a,na) in enumerate(spans) for b,nb in spans[i+1:])
    snapshot=j.append==j.current_length==j.expected_length==0 and j.generation==j.expected_generation==0 and j.cold
    return geometry and spans_good and snapshot and j.tag!=0xffffffff

class Model:
    """Independent serialized owner abstraction; no Scala or RTL is executed."""
    def __init__(self,j=Job()):
        self.j=j;self.state='read' if valid(j) else 'finish';self.poison=not valid(j)
        self.unknown=False;self.held=False;self.plane=0;self.beat=0;self.data=0
        self.accepted=0;self.returned=0;self.ack=[0,0];self.debt=None
        self.terminal=None;self.writes=[]
    def packet(self):
        write=self.state=='write'
        address=self.j.cache+self.plane*self.j.capacity*1024+self.j.append*1024+self.beat*64 if write else (self.j.value if self.plane else self.j.key)+self.beat*64
        return (write,address,self.data if write else 0,(2**64-1) if write else 0,self.j.tag,self.returned)
    def offer(self,ready=True,fault=False):
        self.poison |= fault
        present=self.state in ('read','write') and (not(self.poison or self.unknown) or self.held)
        packet=self.packet() if present else None
        if present:
            self.held=not ready
            if ready:
                self.debt=packet;self.accepted+=1;self.state='waitwrite' if packet[0] else 'waitread'
        elif self.state in ('read','write') and self.poison:self.state='finish'
        return packet,present and ready
    def response(self,tag=None,error=False,data=0,fault=False):
        self.poison |= fault
        identity=(self.j.tag,self.returned) if tag is None else tag
        if self.debt is None or identity!=self.debt[-2:]:
            self.poison=True;self.unknown=True;return False
        write=self.debt[0]
        self.returned+=1
        if write and not error:
            self.ack[self.plane]+=64;self.writes.append(self.debt)
        self.debt=None
        self.poison |= error
        if self.poison or self.unknown:self.state='finish'
        elif not write:self.data=data;self.state='write'
        elif self.beat+1==self.j.tokens*16:
            if self.plane:self.state='finish'
            else:self.plane=1;self.beat=0;self.state='read'
        else:self.beat+=1;self.state='read'
        return True
    @property
    def drained(self):
        return self.state not in ('read','write','waitread','waitwrite') and self.debt is None and self.accepted==self.returned and not self.unknown
    def report(self):
        if self.state!='finish' or not self.drained:return False
        exact=self.accepted==self.returned==self.j.tokens*64 and self.ack==[self.j.tokens*1024]*2
        complete=not self.poison and exact
        self.terminal=(complete,tuple(self.ack),self.accepted,self.returned,self.j.current_length+(self.j.tokens if complete else 0),self.j.generation+int(complete))
        self.state='report';return True
    def finish(self):
        while self.state!='finish':
            packet,fired=self.offer()
            if not fired:raise RuntimeError('not progress')
            self.response(data=beat_payload(self.plane,self.beat))
        return self.report()

def beat_payload(plane,beat):
    # Deliberately opaque nonfinite BF16 and varied words, not finite arithmetic.
    words=[(0x7fc1 if i%5==0 else (0xff80 if i%7==0 else ((plane<<15)^beat*37^i)&0xffff)) for i in range(32)]
    return sum(w<<(i*16) for i,w in enumerate(words))

class OwnerTests(unittest.TestCase):
    def test_source_contract(self):self.assertGreater(source_checks(SRC.read_text()),60)
    def test_original_identity(self):self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),ORIGINAL_SHA)
    def test_all_128_token_counts(self):
        for tokens in range(1,129):
            m=Model(Job(tokens=tokens));self.assertTrue(m.finish());self.assertTrue(m.terminal[0])
            self.assertEqual(m.ack,[tokens*1024]*2);self.assertEqual(m.accepted,tokens*64)
            self.assertEqual(m.terminal[-2:],(tokens,1))
    def test_exact_copy_opaque_bits_both_planes(self):
        for tokens in (1,16,128):
            m=Model(Job(tokens=tokens));m.finish()
            for i,p in enumerate(m.writes):
                plane,beat=divmod(i,tokens*16)
                self.assertEqual(p[1],m.j.cache+plane*128*1024+beat*64)
                self.assertEqual(p[2],beat_payload(plane,beat));self.assertEqual(p[3],2**64-1)
    def test_geometry_full_width_and_capacity(self):
        for field,values in {'tokens':(0,129,65535),'row_width':(0,2,256,513,65535),'heads':(0,1,3,258,65535),'dim':(0,128,257,65535),'capacity':(0,16,127,129,256,0xffffffff)}.items():
            for value in values:self.assertFalse(valid(replace(Job(),**{field:value})),(field,value))
    def test_snapshot_cold_only(self):
        for field,value in [('cold',False),('append',1),('current_length',1),('expected_length',1),('generation',1),('expected_generation',1),('generation',0xffffffff),('tag',0xffffffff)]:
            self.assertFalse(valid(replace(Job(),**{field:value})),field)
    def test_aperture_exact_end_not_wrap(self):
        self.assertTrue(valid(replace(Job(),cache=2**56-128*2048)))
        self.assertFalse(valid(replace(Job(),cache=2**56-128*2048+64)))
        self.assertFalse(valid(replace(Job(),cache=2**64-64)))
        for field in ('key','value','cache'):
            self.assertFalse(valid(replace(Job(),**{field:1})))
    def test_entire_cache_disjoint_not_just_written_tail(self):
        self.assertFalse(valid(replace(Job(tokens=1),key=0x300000+127*1024)))
        self.assertFalse(valid(replace(Job(tokens=1),value=0x300000+255*1024)))
        self.assertFalse(valid(replace(Job(),value=0x100000)))
    def test_final_v_ack_required(self):
        m=Model(Job(tokens=1))
        while not(m.state=='write' and m.plane==1 and m.beat==15):m.offer();m.response(data=123)
        self.assertEqual(m.ack,[1024,960]);self.assertFalse(m.report())
        m.offer();self.assertFalse(m.drained);self.assertFalse(m.report())
        m.response();self.assertTrue(m.report());self.assertTrue(m.terminal[0])
    def test_wrong_tag_keeps_debt_and_never_fakes_drain(self):
        m=Model();m.offer();debt=m.debt
        self.assertFalse(m.response(tag=(m.j.tag,999)));self.assertEqual(m.debt,debt)
        self.assertEqual(m.returned,0);self.assertFalse(m.drained);self.assertFalse(m.report())
        self.assertTrue(m.response());self.assertEqual(m.returned,1)
        self.assertFalse(m.drained);self.assertFalse(m.report());self.assertIsNone(m.terminal)
    def test_unsolicited_response_quarantines(self):
        m=Model();self.assertFalse(m.response());self.assertTrue(m.unknown)
        self.assertFalse(m.offer()[1]);self.assertFalse(m.drained);self.assertFalse(m.report())
    def test_wrong_tag_on_final_ack_never_proposes(self):
        m=Model(Job(tokens=1))
        while not(m.state=='write' and m.plane==1 and m.beat==15):m.offer();m.response(data=123)
        m.offer();self.assertFalse(m.response(tag=(m.j.tag^1,m.returned)))
        self.assertEqual(m.ack,[1024,960]);self.assertTrue(m.response());self.assertEqual(m.ack,[1024,1024])
        self.assertFalse(m.report())
    def test_held_read_survives_fault_until_fire(self):
        m=Model();packet,fired=m.offer(ready=False);self.assertFalse(fired)
        for _ in range(5):self.assertEqual(m.offer(ready=False,fault=True),(packet,False))
        self.assertEqual(m.offer(ready=True,fault=True),(packet,True));self.assertFalse(m.drained)
        self.assertTrue(m.response());self.assertTrue(m.report());self.assertFalse(m.terminal[0])
    def test_held_write_survives_fault_and_real_ack_counts(self):
        m=Model();m.offer();m.response(data=0x7fc1)
        packet,_=m.offer(ready=False)
        for _ in range(5):self.assertEqual(m.offer(ready=False,fault=True),(packet,False))
        self.assertEqual(m.offer(ready=True,fault=True),(packet,True));self.assertEqual(m.ack,[0,0])
        m.response();self.assertEqual(m.ack,[64,0]);self.assertTrue(m.report());self.assertFalse(m.terminal[0])
    def test_unexposed_offer_fault_has_no_effect(self):
        m=Model();self.assertEqual(m.offer(fault=True),(None,False));self.assertEqual(m.accepted,0)
        self.assertTrue(m.report());self.assertFalse(m.terminal[0])
    def test_read_fault_no_followup_write(self):
        m=Model();m.offer();m.response(fault=True,data=123)
        self.assertEqual(m.state,'finish');self.assertEqual(m.ack,[0,0]);self.assertTrue(m.report());self.assertFalse(m.terminal[0])
    def test_memory_error_retires_exact_debt_but_no_ack(self):
        for onwrite in (False,True):
            m=Model();m.offer()
            if onwrite:m.response(data=123);m.offer()
            self.assertTrue(m.response(error=True));self.assertEqual(m.accepted,m.returned)
            self.assertEqual(m.ack,[0,0]);self.assertTrue(m.report());self.assertFalse(m.terminal[0])
    def test_terminal_immutable_under_backpressure_late_fault(self):
        m=Model(Job(tokens=1));m.finish();terminal=m.terminal
        for _ in range(10):m.offer(fault=True);self.assertEqual(m.terminal,terminal)
        m.response(tag=(m.j.tag,999));self.assertEqual(m.terminal,terminal);self.assertFalse(m.drained)
    def test_inexact_count_no_proposal(self):
        m=Model(Job(tokens=1));m.finish();m.state='finish';m.ack[1]-=64
        self.assertTrue(m.report());self.assertFalse(m.terminal[0])
    def test_mutations_rejected(self):
        original=SRC.read_text()
        mutations=[
          ('val CapacityTokens=128','val CapacityTokens=256'),
          ('r.rowWidth:=j.n','r.rowWidth:=512.U'),
          ('!j.cold ||','j.cold ||'),
          ('j.appendStart=/=0.U','j.appendStart>128.U'),
          ('base.pad(66)+size','base+size'),
          ('overlap(j.cacheBase,cacheBytes,j.keyInput,inputBytes)','false.B'),
          ('io.response.ready:=memoryDebt && !unknownMemory','io.response.ready:=memoryDebt'),
          ('when(unknownMemory){drainUnknown:=true.B}','when(unknownMemory){drainUnknown:=false.B}'),
          ('quiet && !drainUnknown && !unknownMemory','quiet'),
          ('memoryAccepted===sequence && quiet','quiet'),
          ('!memoryHeld.held && !io.memory.fire','!io.memory.fire'),
          ('state===waitTail && !r.error','state===waitTail'),
          ('when(state===waitInput){data:=r.data','when(state===waitInput){data:=0.U'),
          ('when(valuePlane){state:=finish}','when(true.B){state:=finish}'),
          ('valueAckBytes===expectedPlaneBytes','valueAckBytes<=expectedPlaneBytes'),
          ('sequence===expectedMemory','sequence<=expectedMemory'),
          ('terminal.proposalValid:=complete','terminal.proposalValid:=true.B'),
          ('when(state===finish && io.resourcesDrained)','when(state===finish)'),
          ('io.done.bits:=terminal','io.done.bits:=0.U.asTypeOf(terminal)'),
        ]
        for before,after in mutations:
            self.assertIn(before,original)
            with self.assertRaises(ValueError,msg=before):source_checks(original.replace(before,after,1))

if __name__=='__main__':unittest.main(argv=[__file__]+unittest_args,verbosity=2)
