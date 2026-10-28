"""Source and abstract contract checks; NOT Scala elaboration or DUT tests."""
from pathlib import Path
import argparse
import hashlib
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source/PartialRopeRuntimeOwnerV12.scala'
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
ORIGINAL=args.original_source
ORIGINAL_SHA='7a3f5bffe06772671f30ac1484065afae9abc895063a2e4769999bf76487c322'

def block(s, marker):
    start=s.index(marker)
    opening=s.index('{', start)
    level=1
    i=opening+1
    while level:
        if s[i]=='{':level+=1
        if s[i]=='}':level-=1
        i+=1
    return s[start:i]

def norm(s):return re.sub(r'\s+', '',s)

def numeric_recipe(s):
    out={}
    for name in ('op','a','b'):
        marker='io.scalar.request.bits.'+('payload.' if 'bits.payload.op' in s else '')+name+' :='
        start=s.index(marker)
        end=s.index('\n  ',start+len(marker))
        # a/b include continued MuxLookup Seq lines until the next assignment.
        if name in ('a','b'):
            end=s.index(')))', start)+3
        out[name]=norm(s[start:end].replace('.payload.','.'))
    out['switch']=norm(block(s,'switch(operation)'))
    start=s.index('  val even =')
    end=s.index('\n  ',s.index('def widened(index: Int): UInt =',start)+4)
    out['operands']=norm(s[start:end])
    return out

def source_checks(text):
    original=ORIGINAL.read_text()
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()!=ORIGINAL_SHA:raise ValueError('original hash')
    if numeric_recipe(text)!=numeric_recipe(original):raise ValueError('frozen numeric recipe')
    required=[
        'r.policy:=j.qkNormPolicy',
        'val heads = UInt(16.W)',
        'val ScalarOperationsPerHead=192',
        'j.tokens>PartialRopeRuntimeAbiV12.MaxTokens.U',
        'j.heads=/=8.U && j.heads=/=16.U,j.heads=/=2.U',
        'j.role>1.U', 'j.policy=/="hb1".U',
        'positionEnd>j.trigTokens.pad(66)',
        'overlap(j.output, vectorBytes, j.input, vectorBytes)',
        'overlap(j.output, vectorBytes, j.trig, trigBytes)',
        'val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)',
        'val unknownScalar=io.scalar.result.valid && (!scalarDebt || io.scalar.result.bits.policy=/=requestPolicy)',
        'io.response.ready:=memoryDebt && !unknownMemory',
        'io.scalar.result.ready:=scalarDebt && !unknownScalar',
        'when(unknown){drainUnknown:=true.B}',
        'io.resourcesDrained:=noService && quiet && !drainUnknown && !unknown',
        'HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || drainUnknown)',
        'HeldDecoupledOffer(state===scalarIssue,io.scalar.request.ready,poison || currentFault || drainUnknown)',
        'memoryOffer && !memoryHeld.held && !io.memory.fire',
        'state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire',
        'when(state===waitOutput && !r.error){bytes:=bytes+64.U}',
        'PartialRope64Math.bf16RneFlags(io.scalar.result.bits.value)',
        'val combinedFlags = io.scalar.result.bits.flags | conversionFlags',
        '!io.scalar.result.bits.primitiveFlagsValid',
        'combinedFlags(4, 1).orR || !TensorMath.finite(r) || rounded(14, 7) === 255.U',
        'MuxLookup(beat, input(beat))(Seq(0.U -> evenOutput.asUInt, 1.U -> oddOutput.asUInt))',
        'when(nonfinite && (state === waitTrig || beat < 2.U))',
        'val exact=memoryAccepted===expectedMemory && sequence===expectedMemory &&',
        'scalarAccepted===expectedScalar && scalarReturned===expectedScalar && bytes===expectedBytes',
        'terminal.accepted:=job;terminal.tag:=job.tag',
        'io.done.valid:=state===report;io.done.bits:=terminal',
        'when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}'
    ]
    missing=[x for x in required if x not in text]
    if missing:raise ValueError('source contract '+repr(missing))
    for forbidden in ('Module(new ', 'BlackBox', 'ScalarOp.Sqrt', 'ScalarOp.Div', 'FloatMath', 'scala.math'):
        if forbidden in text:raise ValueError('new implementation '+forbidden)
    if text.count('terminal.accepted:=')!=1:raise ValueError('mutable terminal')
    if text.count('memoryAccepted:=memoryAccepted+1.U')!=1:raise ValueError('accepted memory count')
    if text.count('scalarReturned:=scalarReturned+1.U')!=1:raise ValueError('returned scalar count')
    return len(required)+13

class Protocol:
    """One serialized held/request/debt model of the source's control contract."""
    def __init__(self,kind='memory'):
        self.kind=kind;self.state='issue';self.held=False;self.poison=False;self.quarantine=False
        self.payload=(0xA5A50000,0x12345678);self.debt=None
        self.accepted=0;self.returned=0;self.bytes=0;self.terminal=None
    def issue(self,ready,fault=False):
        self.poison |= fault
        visible=self.state=='issue' and (not(self.poison or self.quarantine) or self.held)
        fired=visible and ready
        if visible:self.held=not ready
        if fired:
            self.accepted+=1;self.debt=self.payload;self.state='wait'
        elif self.state=='issue' and self.poison and not self.held:
            self.state='finish'
        return visible,fired,self.payload
    def response(self,identity,error=False,write=False):
        match=self.state=='wait' and identity==self.debt
        if not match:
            self.poison=True;self.quarantine=True
            return False
        self.returned+=1;self.debt=None
        if write and not error:self.bytes+=64
        self.poison|=error
        self.state='finish' if self.poison or self.quarantine else 'next'
        return True
    def report(self,expected):
        if self.state!='finish' or self.quarantine or self.debt is not None:return False
        exact=(self.accepted,self.returned,self.bytes)==expected
        self.terminal=(not self.poison and exact,self.accepted,self.returned,self.bytes)
        self.state='report';return True

def shape(tokens,role,heads,position,trig_tokens,base=(0x100000,0x200000,0x400000),policy=0xB1):
    v=tokens*heads*512;t=trig_tokens*128
    valid=tokens in range(1,129) and role in (0,1) and heads in ((8,16) if role==0 else (2,)) and policy==0xB1
    valid=valid and position+tokens<=trig_tokens
    spans=[(base[0],v),(base[1],t),(base[2],v)]
    valid=valid and all(a%64==0 and a+n<=2**56 for a,n in spans)
    valid=valid and not any(base[2]<a+n and a<base[2]+v for a,n in spans[:2])
    return valid

class SourceTests(unittest.TestCase):
    def test_source_contract(self):self.assertGreater(source_checks(SRC.read_text()),40)
    def test_frozen_recipe(self):self.assertEqual(numeric_recipe(SRC.read_text()),numeric_recipe(ORIGINAL.read_text()))
    def test_scalar_exact(self):
        for m in (1,16,128):
            for heads in (2,8,16):
                operations=[(t,h,p,k) for t in range(m) for h in range(heads) for p in range(32) for k in range(6)]
                self.assertEqual(len(operations),m*heads*192)
        self.assertEqual(128*16*192,393216)
    def test_memory_exact(self):
        for m in (1,16,128):
            for heads in (2,8,16):
                reads=sum(2+8*heads for _ in range(m));writes=m*heads*8
                self.assertEqual(reads+writes,m*(2+heads*16));self.assertEqual(writes*64,m*heads*512)
    def test_mutations_rejected(self):
        text=SRC.read_text()
        pairs=[('ScalarOp.Mul.U, ScalarOp.Add.U','ScalarOp.Add.U, ScalarOp.Add.U'),
          ('mulOs -> odd','mulOs -> even'),('mulEs -> sin','mulEs -> cos'),
          ('products(0) := rounded','products(0) := r'),
          ('r.policy:=j.qkNormPolicy','r.policy:="hb1".U'),
          ('j.heads=/=16.U','j.heads=/=32.U'),
          ('positionEnd>j.trigTokens.pad(66)','positionEnd>=j.trigTokens.pad(66)'),
          ('io.response.ready:=memoryDebt && !unknownMemory','io.response.ready:=memoryDebt'),
          ('io.scalar.result.ready:=scalarDebt && !unknownScalar','io.scalar.result.ready:=scalarDebt'),
          ('!memoryHeld.held && !io.memory.fire','!io.memory.fire'),
          ('!scalarHeld.held && !io.scalar.request.fire','!io.scalar.request.fire'),
          ('state===waitOutput && !r.error','state===waitOutput'),
          ('sequence===expectedMemory','sequence<=expectedMemory'),
          ('scalarReturned===expectedScalar','scalarReturned<=expectedScalar'),
          ('bytes===expectedBytes','bytes<=expectedBytes'),
          ('beat < 2.U','beat < 8.U'),('1.U -> oddOutput.asUInt','1.U -> evenOutput.asUInt'),
          ('bits.flags | conversionFlags','bits.flags')]
        for old,new in pairs:
            with self.subTest(old=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):source_checks(text.replace(old,new,1))
    def test_full_width_bad_heads(self):
        for heads in (0,1,4,24,32,64,72,80,264,65535):self.assertFalse(shape(1,0,heads,0,1))
    def test_geometry(self):
        for m in (1,16,128):
            self.assertTrue(shape(m,0,8,0,m));self.assertTrue(shape(m,0,16,3,m+3));self.assertTrue(shape(m,1,2,1,m+1))
        for args in ((0,0,8,0,1),(129,0,8,0,129),(1,2,2,0,1),(1,1,16,0,1),(1,0,8,1,1)):
            self.assertFalse(shape(*args))
        self.assertFalse(shape(1,0,8,0,1,policy=0xC1))
    def test_span_overlap(self):
        self.assertFalse(shape(1,0,8,0,1,base=(0x100000,0x200000,0x100000)))
        self.assertFalse(shape(1,0,8,0,1,base=(0x100000,0x200000,0x200000)))
        self.assertFalse(shape(1,0,8,0,1,base=(2**56-64,0x200000,0x400000)))
        self.assertFalse(shape(1,0,8,0,1,base=(0x100001,0x200000,0x400000)))

class FaultTests(unittest.TestCase):
    def test_first_fault_no_request(self):
        p=Protocol();self.assertEqual(p.issue(False,True)[:2],(False,False));self.assertEqual(p.accepted,0)
    def test_held_fault_preserved(self):
        for kind in ('memory','scalar'):
            p=Protocol(kind);original=p.issue(False)
            for _ in range(20):self.assertEqual(p.issue(False,True),original)
            self.assertEqual(p.issue(True)[:2],(True,True));self.assertEqual(p.accepted,1)
            self.assertTrue(p.response(p.payload));self.assertEqual(p.returned,1);self.assertEqual(p.state,'finish')
    def test_unknown_no_retire_then_known_drain(self):
        for kind in ('memory','scalar'):
            p=Protocol(kind);p.issue(True)
            self.assertFalse(p.response((0,0)));self.assertEqual(p.returned,0);self.assertEqual(p.debt,p.payload)
            self.assertTrue(p.response(p.payload));self.assertEqual(p.returned,1);self.assertTrue(p.quarantine)
            self.assertFalse(p.report((1,1,0)))
    def test_unknown_held_does_not_retract(self):
        p=Protocol();old=p.issue(False);self.assertFalse(p.response((0,0)))
        self.assertEqual(p.issue(False),old);self.assertEqual(p.issue(True)[:2],(True,True))
    def test_failed_write_not_ack(self):
        p=Protocol();p.issue(True);p.response(p.payload,error=True,write=True)
        self.assertEqual(p.bytes,0);self.assertTrue(p.report((1,1,0)));self.assertFalse(p.terminal[0])
    def test_late_fault_real_write_ack(self):
        p=Protocol();p.issue(False);p.issue(True,True);p.response(p.payload,write=True)
        self.assertEqual(p.bytes,64);p.report((1,1,64));self.assertFalse(p.terminal[0])
    def test_duplicate_quarantine(self):
        p=Protocol();p.issue(True);p.response(p.payload)
        self.assertFalse(p.response(p.payload));self.assertEqual(p.returned,1);self.assertTrue(p.quarantine)
    def test_terminal_immutable(self):
        p=Protocol();p.issue(True);p.response(p.payload,write=True);p.state='finish';p.report((1,1,64))
        snapshot=p.terminal;p.issue(False,True);self.assertEqual(p.terminal,snapshot)
    def test_exact_actual_counts_not_geometry(self):
        p=Protocol();p.state='finish';p.report((1,1,64));self.assertFalse(p.terminal[0])

if __name__=='__main__':unittest.main(argv=[__file__]+unittest_args,verbosity=2)
