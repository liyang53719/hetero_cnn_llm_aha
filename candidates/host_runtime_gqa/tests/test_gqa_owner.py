"""Independent bounded protocol/count model and source recipe checks; NOT DUT simulation."""
from pathlib import Path
import argparse,hashlib,re,unittest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source/Bf16CausalGqaRuntimeOwnerV14.scala'
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
ORIGINAL=args.original_source
BASE_SHA='d1dc6e1707ec0ae303b439b90904adb37dbce9df53e0156011e167a11ae92d18'

def block(s,marker):
 start=s.index(marker); brace=s.index('{',start);depth=1;i=brace+1
 while depth:
  depth += (s[i]=='{')-(s[i]=='}');i+=1
 return s[start:i]

def source_contract(s):
 required=[
 'val MaxTokens = 128','val MaxCacheTokens = 256','val MaxQueryHeads = 16','val MaxHeadDim = 256',
 'val rowWidth = UInt(16.W)','val qkOrder = UInt(8.W)','j.rowWidth === (j.queryHeads.pad(32)<<8) && j.qkOrder<=1.U',
 'val scalar = new UnifiedScalarClientV2','val matrix = new MatrixStreamPort','val requestPolicy = UnifiedScalarPolicyV2.Legacy.U(2.W)',
 'publishedOffer(memoryIntent,io.memory.ready,io.memoryPublished)',
 'publishedOffer(groupIntent,io.matrix.group.ready,io.matrixGroupPublished)',
 'publishedOffer(stepIntent,io.matrix.step.ready,io.matrixStepPublished)','publishedOffer(state===scalarIssue,io.scalar.request.ready,io.scalarPublished)',
 'when(published){held:= !ready}', '.elsewhen(state =/= drain) { state := drain }',
 'val visible=intent && ((!poison && !drainUnknown && !currentFault) || held)',
 'assert(!published || visible', 'assert(!(visible && ready) || published',
 'val heldOffer = (io.memoryPublished && !io.memory.ready)',
 '(io.scalarPublished && !io.scalar.request.ready)', '(io.matrixGroupPublished && !io.matrix.group.ready)',
 '(io.matrixStepPublished && !io.matrix.step.ready)', 'when(state===idle && !io.job.fire){state:=locked}',
 'io.response.ready := memoryPending && !unknownMemory','io.scalar.result.ready := scalarPending && !unknownScalar',
 'io.matrix.done.ready := matrixActive && !unknownMatrixDone && !matrixTerminalUnsafe',
 'when(earlyMatrixDone){matrixTerminalUnsafe:=true.B}',
 'memoryAccepted===sequence && scalarAccepted===scalarReturned',
 'matrixGroupsAccepted===matrixGroupsReturned && !drainUnknown && !unknown && !matrixTerminalUnsafe',
 'when(memoryPendingWrite && !r.error) { bytes := bytes + 64.U }',
 'when((state =/= idle || io.job.fire) && state =/= finish && state =/= report && state =/= locked)',
 'io.done.valid := state === report','io.done.bits := terminal','when(state===finish && io.resourcesDrained)',
 'terminal.accepted:=job','terminal.matrixGroupsAccepted:=matrixGroupsAccepted;terminal.matrixGroupsReturned:=matrixGroupsReturned',
 'terminal.outputCommitted:=complete','terminal.drained:=io.resourcesDrained',
 'job.tokens.pad(96) * job.cacheLength.pad(96) * job.queryHeads.pad(96) * 6.U',
 '16.U * job.queryHeads.pad(96) * (job.tokens.pad(96) + queryTiles * job.cacheLength.pad(96))',
 'queryTiles * job.queryHeads.pad(96) * (keyTiles + 1.U)',
 'job.tokens.pad(96) * job.queryHeads.pad(96) * 512.U',
 'val tagsFit = j.tag.pad(96)+groupsWide.pad(96)<=(BigInt(1)<<32).U',
 'terminal.status:=Mux(status===Status.Ok.U && !complete,Status.Protocol.U,status)',
 ]
 for x in required:
  if x not in s: raise ValueError(x)
 for x in ('admissionFault','HeldDecoupledOffer(','Module(new','new GdnScalarClient','when(!drainUnknown) { scalarPending := false.B }'):
  if x in s:raise ValueError('forbidden '+x)
 return len(required)

class Debt:
 def __init__(self): self.pending=None;self.accepted=0;self.returned=0;self.poison=False;self.unknown=False;self.bytes=0
 def issue(self,tag,write=False):
  if self.pending is not None or self.poison:raise ValueError('no fresh authority')
  self.pending=(tag,write);self.accepted+=1
 def response(self,tag,error=False):
  if self.pending is None or tag!=self.pending[0]:self.unknown=True;self.poison=True;return False
  _,write=self.pending;self.pending=None;self.returned+=1
  if write and not error:self.bytes+=64
  self.poison|=error
  return True
 @property
 def drained(self):return self.pending is None and self.accepted==self.returned and not self.unknown

class Held:
 def __init__(self):self.held=False;self.payload=None
 def step(self,intent,payload,ready,fault):
  if self.held and (not intent or payload!=self.payload):raise ValueError('held mutation')
  valid=intent and (not fault or self.held)
  fire=valid and ready
  if valid:self.held=not ready;self.payload=payload
  return valid,fire

def fault_transition(state,fault,held,debt,unknown):
 next_state=state
 if state=='drain' and not debt and not unknown:next_state='finish'
 if fault:
  if state=='idle':next_state='locked'
  elif state not in ('finish','report','locked'):
   if held:next_state=state
   elif state!='drain':next_state='drain'
 if state=='finish' and not debt and not unknown:next_state='report'
 return next_state

class PublicationIntent:
 def __init__(self):self.held=False;self.payload=None
 def step(self,intent,payload,ready,fault,published):
  if self.held and (not intent or payload!=self.payload):raise ValueError('actual held mutation')
  visible=intent and (not fault or self.held)
  if published and not visible:raise ValueError('publication without raw intent')
  if visible and ready and not published:raise ValueError('fire without actual publication')
  if published:self.held=not ready;self.payload=payload
  return visible,visible and ready

class TestGqaOwner(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.s=SOURCE.read_text();cls.o=ORIGINAL.read_text()
 def test_original_pin(self):self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),BASE_SHA)
 def test_contract(self):self.assertGreaterEqual(source_contract(self.s),30)
 def test_arithmetic_switch_is_identical(self):self.assertEqual(block(self.s,'switch(operation)'),block(self.o,'switch(operation)'))
 def test_scalar_operands_identical(self):
  start='  io.scalar.request.bits.op';end='  io.scalar.result.ready'
  new=self.s.replace('io.scalar.request.bits.payload.','io.scalar.request.bits.')
  self.assertEqual(new[new.index(start):new.index(end)],self.o[self.o.index(start):self.o.index(end)])
 def test_matrix_operand_routes_identical(self):
  start='  val qkDimension';end='  val collectingResult'
  self.assertEqual(self.s[self.s.index(start):self.s.index(end)],self.o[self.o.index(start):self.o.index(end)])
 def test_memory_address_recipe_identical(self):
  start='  val queryRow';end='  io.memory.valid'
  old=self.o[self.o.index(start):self.o.index(end)]
  new=self.s[self.s.index(start):self.s.index('  val memoryIntent')]
  self.assertEqual(new,old)
 def test_bf16_selector_identical(self):
  self.assertEqual(block(self.s,'object GqaRuntimeMatrixResultSelectV14').replace('GqaRuntimeMatrixResultSelectV14','GqaMatrixResultSelect'),block(self.o,'object GqaMatrixResultSelect'))
 def test_fixed_memories_identical(self):
  for line in self.o.splitlines():
   if 'Mem(' in line or 'Reg(Vec(' in line:self.assertIn(line,self.s)
 def test_all_six_scalar_nodes_no_mask_skip(self):
  body=block(self.s,'switch(operation)')
  self.assertEqual(re.findall(r'is\((\w+)\)',body),['scaleScore','maskScore','difference','exponential','sumExp','divide'])
  self.assertIn('maskScore -> Mux(allowed, 0.U(32.W), "hff7f0000".U)',self.s)
  self.assertIn('scaleScore -> ScalarOp.MulIeeeRne.U',self.s)
  self.assertIn('exponential -> ScalarOp.ExpNegative.U',self.s)
 def test_count_equations_all_supported_shapes(self):
  for m in range(1,129):
   qrows=[min(16,m-q) for q in range(0,m,16)]
   for c in range(1,257):
    kcols=[min(32,c-k) for k in range(0,c,32)]
    for h in (8,16):
     scalar=sum(r*k*6 for r in qrows for k in kcols)*h
     memory=(sum(qrows)*16+len(qrows)*sum(kcols)*16)*h
     groups=len(qrows)*(len(kcols)+1)*h
     self.assertEqual(scalar,6*m*c*h)
     self.assertEqual(memory,16*h*(m+((m+15)//16)*c))
     self.assertEqual(groups,((m+15)//16)*h*((c+31)//32+1))
     self.assertLess(max(scalar,memory,groups),2**32)
 def test_cold_128_q8_q16_counts(self):
  for h in (8,16):
   self.assertEqual(6*128*128*h,786432 if h==8 else 1572864)
   self.assertEqual(16*h*(128+8*128),147456 if h==8 else 294912)
   self.assertEqual(8*h*(4+1),320 if h==8 else 640)
   self.assertEqual(128*h*512,524288 if h==8 else 1048576)
 def test_actual_memory_ack_not_offer(self):
  x=Debt();x.issue(7,True);self.assertEqual(x.bytes,0);x.response(7);self.assertEqual(x.bytes,64)
 def test_failed_ack_not_success(self):
  x=Debt();x.issue(7,True);x.response(7,True);self.assertEqual(x.bytes,0);self.assertTrue(x.poison)
 def test_unknown_retains_debt_later_exact_retires(self):
  x=Debt();x.issue(7,True);self.assertFalse(x.response(8));self.assertIsNotNone(x.pending)
  self.assertTrue(x.response(7));self.assertEqual((x.accepted,x.returned,x.bytes),(1,1,64));self.assertFalse(x.drained)
 def test_unsolicited_never_becomes_ack(self):
  x=Debt();self.assertFalse(x.response(0));self.assertEqual((x.accepted,x.returned,x.bytes),(0,0,0));self.assertFalse(x.drained)
 def test_fault_blocks_unpublished_all_interfaces(self):
  for name in ('memory','scalar','group','step'):
   x=Held();self.assertEqual(x.step(True,(name,7),True,True),(False,False))
 def test_held_survives_fault_and_ready(self):
  for name in ('memory','scalar','group','step'):
   x=Held();p=(name,7);self.assertEqual(x.step(True,p,False,False),(True,False))
   self.assertEqual(x.step(True,p,False,True),(True,False));self.assertEqual(x.step(True,p,True,True),(True,True))
 def test_held_cannot_mutate_or_disappear(self):
  for intent,p in ((False,7),(True,8)):
   x=Held();x.step(True,7,False,False)
   with self.assertRaises(ValueError):x.step(intent,p,False,True)
 def test_actual_publication_is_not_raw_intent(self):
  for interface in ('memory','scalar','group','step'):
   x=PublicationIntent();p=(interface,7)
   self.assertEqual(x.step(True,p,False,False,False),(True,False));self.assertFalse(x.held)
   self.assertEqual(x.step(True,p,False,True,False),(False,False));self.assertFalse(x.held)
 def test_genuinely_published_hold_survives_fault(self):
  for interface in ('memory','scalar','group','step'):
   x=PublicationIntent();p=(interface,7)
   self.assertEqual(x.step(True,p,False,False,True),(True,False));self.assertTrue(x.held)
   self.assertEqual(x.step(True,p,False,True,True),(True,False))
   self.assertEqual(x.step(True,p,True,True,True),(True,True));self.assertFalse(x.held)
 def test_publication_observer_assertions(self):
  for interface in ('memory','scalar','group','step'):
   with self.assertRaises(ValueError):PublicationIntent().step(True,interface,True,False,False)
   with self.assertRaises(ValueError):PublicationIntent().step(True,interface,False,True,True)
 def test_no_publication_comb_feedback(self):
  helper=block(self.s,'def publishedOffer(')
  line=next(l for l in helper.splitlines() if 'val visible=' in l)
  self.assertNotIn('published',line)
  for l in self.s.splitlines():
   if 'io.resetRequired :=' in l or 'val currentFault =' in l:self.assertNotIn('Published',l)
  self.assertNotIn('admissionFault',self.s)
 def test_sticky_parent_fault_reaches_failed_report(self):
  state='active'
  for expected in ('drain','finish','report'):
   state=fault_transition(state,True,False,False,False);self.assertEqual(state,expected)
  self.assertEqual(fault_transition('idle',True,False,False,False),'locked')
 def test_fault_held_then_drain_report(self):
  for interface in ('memory','scalar','group','step'):
   self.assertEqual(fault_transition(interface,True,True,False,False),interface)
   self.assertEqual(fault_transition(interface,True,False,True,False),'drain')
   self.assertEqual(fault_transition('drain',True,False,True,False),'drain')
   self.assertEqual(fault_transition('drain',True,False,False,False),'finish')
   self.assertEqual(fault_transition('finish',True,False,False,False),'report')
   self.assertEqual(fault_transition('drain',True,False,False,True),'drain')
 def test_tag_range_no_wrap(self):
  groups=8*16*(8+1)
  self.assertLess((2**32-groups)+(groups-1),2**32)
  self.assertGreater((2**32-groups+1)+groups,2**32)
 def test_full_width_order_and_geometry_reject_alias(self):
  legal=lambda n,q,o:n==q*256 and q in (8,16) and o<=1
  self.assertTrue(legal(2048,8,0));self.assertTrue(legal(4096,16,1))
  for n,q,o in ((2049,8,0),(4097,16,1),(2048,8,2),(2048,8,255),(8192,32,0)):
   self.assertFalse(legal(n,q,o))
 def test_mutation_detection(self):
  mutations=[('val MaxCacheTokens = 256','val MaxCacheTokens = 128'),('val qkOrder = UInt(8.W)','val qkOrder = UInt(1.W)'),
   (' && !unknownMemory',''),(' && !unknownScalar',''),(' && !matrixTerminalUnsafe',''),
   ('when(memoryPendingWrite && !r.error)','when(memoryPendingWrite)'),(' * 6.U',' * 5.U'),
   ('terminal.outputCommitted:=complete','terminal.outputCommitted:=true.B'),('io.done.bits := terminal','io.done.bits := job'),
   ('val scalar = new UnifiedScalarClientV2','val scalar = new GdnScalarClient'),
   ('when(state===finish && io.resourcesDrained)','when(state===finish)'),('j.qkOrder<=1.U','j.qkOrder<=255.U'),
   (' && !drainUnknown && !unknown && !matrixTerminalUnsafe',' && !unknown && !matrixTerminalUnsafe'),
   ('when(published){held:= !ready}','when(visible){held:= !ready}'),
   ('io.memoryPublished && !io.memory.ready','io.memory.valid && !io.memory.ready'),
   ('.elsewhen(state =/= drain) { state := drain }','.elsewhen(faultNow || state =/= drain) { state := drain }')]
  for a,b in mutations:
   self.assertIn(a,self.s)
   with self.assertRaises(ValueError,msg=a):source_contract(self.s.replace(a,b))
 def test_delimiters(self):
  s=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',self.s,flags=re.S)
  stack=[];pairs={')':'(',']':'[','}':'{'}
  for c in s:
   if c in '([{':stack.append(c)
   elif c in ')]}':self.assertTrue(stack);self.assertEqual(stack.pop(),pairs[c])
  self.assertEqual(stack,[])
if __name__=='__main__':unittest.main(argv=[__file__]+unittest_args,verbosity=2)
