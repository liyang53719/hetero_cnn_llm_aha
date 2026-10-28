"""Pinned-source and small protocol/count tests; NOT Scala/DUT/numerical execution."""
from pathlib import Path
import argparse,hashlib,json,re,unittest
C=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
F=args.original_source
N=C/'source/QkNorm256RuntimeOwnerV11.scala'
OLD=F.read_text();NEW=N.read_text()
def need(v,m):
 if not v:raise ValueError(m)
def normal(s):
 return re.sub(r'\s+','',s.replace('io.scalar.request.bits.payload.','io.scalar.request.bits.').replace('io.scalar.result.bits.flags','io.scalarFlags').replace('io.scalar.result.bits.primitiveFlagsValid','io.scalarFlagsValid'))
def braced(s,key):
 start=s.index('{',s.index(key));n=1;i=start+1
 while n:
  n+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[start:i]
def count_fsm(c2):
 op='square';lane=0;tree_index=0;tree_count=8;counts={};addresses=[]
 for limit in range(2000):
  counts[op]=counts.get(op,0)+1
  if op=='square':
   addresses.append(lane)
   if c2:op='torchTermAdd'
   elif lane%16==15:tree_index=0;tree_count=8;op='tree'
   else:lane+=1
  elif op=='torchTermAdd':
   if lane>>5!=7:lane+=32;op='square'
   elif (lane>>3)&3==0:lane=8+(lane&7);op='square'
   else:op='torchResidueFold'
  elif op=='torchResidueFold':
   if (lane>>3)&3==3:op='torchLaneFold'
   else:lane=((((lane>>3)&3)+1)<<3)+(lane&7);op='square'
  elif op=='torchLaneFold':
   if lane&7==7:lane=0;op='mean'
   else:lane=(lane&7)+1;op='square'
  elif op=='tree':
   if tree_index+1==tree_count:
    tree_index=0
    if tree_count==1:op='running'
    tree_count>>=1
   else:tree_index+=1
  elif op=='running':
   if lane==255:lane=0;op='mean'
   else:lane+=1;op='square'
  elif op=='mean':op='epsilon'
  elif op=='epsilon':op='torchSqrt' if c2 else 'slope'
  elif op=='slope':op='intercept'
  elif op=='intercept':op='seedSquare'
  elif op=='seedSquare':op='normProduct'
  elif op=='normProduct':op='half'
  elif op=='half':op='correction'
  elif op=='correction':op='newton'
  elif op=='newton':op='rescale'
  elif op in ('rescale','torchDivide'):op='gamma'
  elif op=='torchSqrt':op='torchDivide'
  elif op=='gamma':op='normalize'
  elif op=='normalize':op='weighted'
  elif op=='weighted':
   if lane==255:return counts,addresses
   lane+=1;op='gamma'
 raise ValueError('FSM did not terminate')
class Transport:
 """Abstract one-request owner debt, matching fresh-source control decisions."""
 def __init__(self):self.state='issue';self.held=False;self.poison=False;self.unknown=False;self.accepted=0;self.returned=0;self.acks=0;self.terminal=None
 def step(self,ready=False,fault=False,response=False,match=True,write=False,error=False):
  unknown=response and (self.state!='wait' or not match)
  current=fault or unknown
  visible=self.state=='issue' and (not(self.poison or current or self.unknown) or self.held)
  fire=visible and ready
  if visible:self.held=not ready
  if current:self.poison=True
  if unknown:self.unknown=True
  if fire:self.accepted+=1;self.state='wait'
  elif self.state=='issue' and self.poison and not self.held and not self.unknown:self.state='finish'
  elif self.state=='wait' and response and match and not self.unknown:
   self.returned+=1
   if error:self.poison=True
   if write and not error:self.acks+=64
   self.state='finish'
  elif self.state=='finish' and not self.unknown:
   self.terminal=(not self.poison,self.accepted,self.returned,self.acks);self.state='report'
  return visible,fire
class OwnerTests(unittest.TestCase):
 def test_frozen_pin(self):self.assertEqual(hashlib.sha256(F.read_bytes()).hexdigest(),'ead0cb3cd75fd3ece09fa0f1bba6da0221e8123523694aa4d06985d3b05f695a')
 def test_scalar_mapping_exact(self):
  for field,end in [('op','io.scalar.request.bits.a'),('a','io.scalar.request.bits.b'),('b','io.scalar.result.ready')]:
   def extract(s):
    s=s.replace('bits.payload.','bits.')
    return s.split('io.scalar.request.bits.'+field,1)[1].split(end,1)[0]
   self.assertEqual(normal(extract(OLD)),normal(extract(NEW)))
 def test_arithmetic_switch_exact(self):self.assertEqual(normal(braced(OLD,'switch(operation)')),normal(braced(NEW,'switch(operation)')))
 def test_rom_exact(self):
  def extract(s):return s.split('val rsqrtCoefficients =',1)[1].split('.map(h => BigInt(h, 16).U(64.W)))',1)[0]
  self.assertEqual(extract(OLD),extract(NEW))
 def test_memory_operand_mapping_exact(self):
  def extract(s):return s.split('io.memory.bits.write :=',1)[1].split('io.response.ready',1)[0]
  self.assertEqual(normal(extract(OLD)),normal(extract(NEW)))
 def test_no_arithmetic_instance(self):
  clean=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/','',NEW)
  self.assertNotIn('Module(new',clean);self.assertNotIn('formatRequest',clean)
 def test_c1_scalar_count(self):
  counts,addresses=count_fsm(False)
  self.assertEqual(sum(counts.values()),1290);self.assertEqual(addresses,list(range(256)))
  self.assertEqual(counts['tree'],240);self.assertEqual(counts['running'],16)
 def test_c2_scalar_count_and_order(self):
  counts,addresses=count_fsm(True)
  self.assertEqual(sum(counts.values()),1316)
  self.assertEqual(addresses,[32*t+8*r+l for l in range(8) for r in range(4) for t in range(8)])
  self.assertEqual(counts['torchResidueFold'],24);self.assertEqual(counts['torchLaneFold'],8)
 def test_max_runtime_contracts(self):
  self.assertEqual(128*16*1316,2695168);self.assertEqual(8+128*16*32,65544)
  self.assertEqual(8+128*2*16,4104);self.assertEqual(128*16*1024,2097152)
 def test_current_fault_suppresses_new(self):
  m=Transport();self.assertEqual(m.step(ready=True,fault=True),(False,False));self.assertEqual(m.accepted,0);self.assertEqual(m.state,'finish')
 def test_held_request_survives_fault(self):
  m=Transport();m.step();self.assertTrue(m.held)
  self.assertEqual(m.step(fault=True),(True,False));self.assertEqual(m.state,'issue')
  self.assertEqual(m.step(ready=True,fault=True),(True,True));self.assertEqual(m.state,'wait')
  m.step(response=True,write=True);self.assertEqual((m.accepted,m.returned,m.acks),(1,1,64));m.step();self.assertEqual(m.terminal,(False,1,1,64))
 def test_fault_does_not_refund_debt(self):
  m=Transport();m.step(ready=True);m.step(fault=True)
  self.assertEqual((m.accepted,m.returned,m.state),(1,0,'wait'));self.assertIsNone(m.terminal)
 def test_bad_correlation_quarantines(self):
  m=Transport();m.step(ready=True);m.step(response=True,match=False);m.step(response=True)
  self.assertEqual((m.accepted,m.returned,m.state),(1,0,'wait'));self.assertTrue(m.unknown);self.assertIsNone(m.terminal)
 def test_early_return_quarantines(self):
  m=Transport();m.step(response=True);self.assertTrue(m.unknown);self.assertEqual(m.accepted,0);self.assertIsNone(m.terminal)
 def test_held_terminal_immutable(self):
  m=Transport();m.step(ready=True);m.step(response=True,write=True);m.step();t=m.terminal
  m.step(fault=True);self.assertEqual(m.terminal,t)
 def test_error_write_not_ack(self):
  m=Transport();m.step(ready=True);m.step(response=True,write=True,error=True);self.assertEqual(m.acks,0);m.step();self.assertFalse(m.terminal[0])
 def test_exact_terminal_source_contract(self):
  for item in ['memoryAccepted===expectedMemory && sequence===expectedMemory','scalarAccepted===expectedScalar && scalarReturned===expectedScalar && bytes===expectedBytes','io.done.valid:=state===report;io.done.bits:=terminal','when(state===finish && io.resourcesDrained)','terminal.accepted:=job','io.scalar.result.bits.primitiveFlagsValid','terminal.outputAckBytes:=bytes']:
   self.assertIn(item,NEW)
 def test_delimiters(self):
  s=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"','',NEW);stack=[]
  for c in s:
   if c in '([{':stack.append(c)
   elif c in ')]}':self.assertTrue(stack);self.assertEqual(stack.pop(),{')':'(',']':'[','}':'{'}[c])
  self.assertFalse(stack)
if __name__=='__main__':unittest.main(argv=[__file__]+unittest_args,verbosity=2)
