"""Small independent protocol/counter/graph models; NOT simulation of a DUT."""
from dataclasses import dataclass,replace,asdict
from pathlib import Path
from collections import Counter
import copy,importlib.util,json,unittest
C=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('check_rms_kernel',C/'check_rms_kernel.py');checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
@dataclass(frozen=True)
class Job:
 tokens:int=128
 hidden:int=1024
 input:int=0x100000
 weight:int=0x200000
 output:int=0x300000
 tag:int=17
 recipe:int=1
 phase:int=3

def valid(j):
 if j.recipe!=1 or j.phase not in (0,3) or not 1<=j.tokens<=128 or j.hidden not in (1024,2048) or not 0<=j.tag<0xffffffff:return False
 spans=((j.input,2*j.tokens*j.hidden),(j.weight,2*j.hidden),(j.output,2*j.tokens*j.hidden))
 return all(0<=a and a%64==0 and a+n<=1<<56 for a,n in spans) and all(not (a<b+m and b<a+n) for i,(a,n) in enumerate(spans) for b,m in spans[i+1:])

def counts(j):return dict(scalar=j.tokens*(5*j.hidden+j.hidden//16+44),format=j.tokens*j.hidden,memory=j.tokens*j.hidden//8,ack=2*j.tokens*j.hidden)
def trace(h):
 """Enumerate original lane8/residue4/block2/term16 schedule for one row."""
 out=[]
 for chunk in range(h//1024):
  for lane in range(1024):
   out+=['square','sum']
   if lane%16==15:out+=['residue']
 for i in range(32):
  out+=['foldResidue']
  if i%4==3:out+=['foldLane']
 out+=['mean','epsilon','root','inverse']
 for lane in range(h):out+=['normalize','gamma','weighted']
 return out

@dataclass
class Offer:
 held:bool=False
 def cycle(self,intent=True,ready=False,published=False,fault=False):
  visible=intent and (not fault or self.held)
  if published and not visible:raise ValueError('publication without raw')
  if visible and ready and not published:raise ValueError('false acceptance')
  if self.held and not intent:raise ValueError('withdrawn')
  old=self.held
  if published:self.held=not ready
  return visible,visible and ready,old

@dataclass(frozen=True)
class Terminal:
 accepted:Job
 status:int
 scalarAccepted:int
 scalarReturned:int
 formatAccepted:int
 formatReturned:int
 memoryAccepted:int
 memoryReturned:int
 writeBytes:int
 outputAckBytes:int
 outputCommitted:bool=True
 resourcesDrained:bool=True

def success(j):
 c=counts(j);return Terminal(j,0,c['scalar'],c['scalar'],c['format'],c['format'],c['memory'],c['memory'],c['ack'],c['ack'])
def terminal_ok(r,j):
 c=counts(j)
 return valid(j) and r.accepted==j and r.status==0 and r.outputCommitted and r.resourcesDrained and r.scalarAccepted==r.scalarReturned==c['scalar'] and r.formatAccepted==r.formatReturned==c['format'] and r.memoryAccepted==r.memoryReturned==c['memory'] and r.writeBytes==r.outputAckBytes==c['ack']
def scalar_drain(mode,active,held,leaf_poison,core_fault=False,quarantine=False,conflict=False,legacy=False,raw_return=False):
 return active and mode in (8,9) and held and not(core_fault or quarantine or conflict or legacy or raw_return)

class RmsKernel(unittest.TestCase):
 def test_profiles_same_resource_counts(self):
  for profile,h in ((1,1024),(2,1024),(3,2048),(4,2048)):
   j=Job(hidden=h)
   self.assertTrue(valid(j));self.assertEqual(counts(j),dict(scalar=669184 if h==1024 else 1332736,format=128*h,memory=16*h,ack=256*h))
 def test_original_schedule_counts(self):
  for h in (1024,2048):
   c=Counter(trace(h));self.assertEqual(sum(c.values()),5228 if h==1024 else 10412)
   self.assertEqual(c,Counter(square=h,sum=h,residue=h//16,foldResidue=32,foldLane=8,mean=1,epsilon=1,root=1,inverse=1,normalize=h,gamma=h,weighted=h))
 def test_phase_separation(self):
  self.assertTrue(valid(Job(phase=0)));self.assertTrue(valid(Job(phase=3)))
  for phase in (1,2,4):self.assertFalse(valid(Job(phase=phase)))
 def test_bad_geometry_no_success(self):
  for j in (Job(tokens=0),Job(tokens=129),Job(hidden=512),Job(hidden=4096),Job(tag=0xffffffff),Job(recipe=0)):
   self.assertFalse(valid(j));self.assertFalse(terminal_ok(success(j),j))
 def test_56bit_bound_and_alignment(self):
  self.assertTrue(valid(Job(output=(1<<56)-262144)))
  for j in (Job(output=(1<<56)-262080),Job(input=0x100001),Job(weight=(1<<56)-1984),Job(input=-64)):
   self.assertFalse(valid(j))
 def test_all_overlap_pairs(self):
  for j in (Job(weight=0x100000),Job(output=0x100000),Job(output=0x200000)):self.assertFalse(valid(j))
 def test_actual_counter_ack_all_required(self):
  j=Job();r=success(j);self.assertTrue(terminal_ok(r,j))
  for f in ('scalarAccepted','scalarReturned','formatAccepted','formatReturned','memoryAccepted','memoryReturned','writeBytes','outputAckBytes'):
   self.assertFalse(terminal_ok(replace(r,**{f:getattr(r,f)-1}),j),f)
 def test_typed_accepted_all_fields(self):
  j=Job();r=success(j)
  for f in asdict(j):self.assertFalse(terminal_ok(replace(r,accepted=replace(j,**{f:getattr(j,f)+1})),j),f)
 def test_input_success_not_post_success(self):
  self.assertFalse(terminal_ok(success(Job(phase=0)),Job(phase=3)))
 def test_fault_terminal_not_publishable(self):
  j=Job();r=success(j)
  for changed in ({'status':1},{'outputCommitted':False},{'resourcesDrained':False}):self.assertFalse(terminal_ok(replace(r,**changed),j))
 def test_terminal_stable_late_fault(self):
  r=success(Job());snapshot=asdict(r)
  for _ in range(3):self.assertEqual(asdict(r),snapshot) # published eligibility separately vetoed by parent
 def test_unpublished_local_offer_not_held(self):
  o=Offer();self.assertEqual(o.cycle(),(True,False,False));self.assertFalse(o.held)
  self.assertEqual(o.cycle(fault=True),(False,False,False))
 def test_published_held_survives_late_fault(self):
  for name in ('memory','scalar','format'):
   o=Offer();o.cycle(published=True);self.assertTrue(o.held,name)
   self.assertEqual(o.cycle(fault=True),(True,False,True))
   self.assertEqual(o.cycle(ready=True,published=True,fault=True),(True,True,True));self.assertFalse(o.held)
 def test_publication_contract_checks(self):
  with self.assertRaises(ValueError):Offer().cycle(fault=True,published=True)
  with self.assertRaises(ValueError):Offer().cycle(ready=True)
  with self.assertRaises(ValueError):Offer(held=True).cycle(intent=False)
 def test_counter_response_not_request(self):
  accepted=returned=ack=0;accepted+=1
  self.assertEqual((accepted,returned,ack),(1,0,0));returned+=1
  # errored output response returns transport but is not write ACK.
  self.assertEqual((accepted,returned,ack),(1,1,0))
 def test_unknown_does_not_refund_or_fabricate_drained(self):
  accepted=1;returned=0;quarantine=True
  self.assertNotEqual(accepted,returned);self.assertFalse(not quarantine and accepted==returned)
 def test_scalar_mode8_actual_debt_only(self):
  self.assertTrue(scalar_drain(8,True,True,True))
  for kw in ({'mode':7},{'mode':13},{'active':False},{'held':False},{'core_fault':True},{'quarantine':True},{'conflict':True},{'legacy':True},{'raw_return':True}):
   args=dict(mode=8,active=True,held=True,leaf_poison=True);args.update(kw);self.assertFalse(scalar_drain(**args),kw)
 def test_source_contracts(self):
  self.assertGreater(checker.check((C/'source/GdnRuntimeRmsNormOwnerV3.scala').read_text(),(C/'source/QwenOwnerProtocol.scala').read_text(),(C/'source/HostBlockTopV4.scala').read_text(),checker.BASE.read_text()),60)
 def test_source_mutations(self):
  r=(C/'source/GdnRuntimeRmsNormOwnerV3.scala').read_text();k=(C/'source/QwenOwnerProtocol.scala').read_text();t=(C/'source/HostBlockTopV4.scala').read_text();b=checker.BASE.read_text()
  variants=[('r',a) for a in ('r.phase:=j.qkRole','terminal.accepted:=accepted','terminal.outputAckBytes:=bytes','terminal.resourcesDrained:=io.resourcesDrained','bytes===expectedBytes && countsExact','scalarReturned:=scalarReturned+1.U','formatReturned:=formatReturned+1.U','val expectedMemory=(expectedFormat>>5)<<2','j.tag==="hffffffff".U','val visible=intent && ((!poison && !quarantine && !currentFault) || held)','when(published){held:= !ready}','publishedOffer(state===scalarIssue,io.scalar.request.ready,io.published.scalar)','val previousResidue=Mux(!chunk && !lane(4),0.U(32.W),previousPartial)')]
  variants += [('k',a) for a in ('val rmsJobHeld=RegInit(false.B)','r.accepted.asUInt=/=j.asUInt || r.tag=/=j.tag || r.outputAckBytes=/=r.writeBytes','io.runtimeRmsDoneFire.get.valid:=n.io.done.fire;io.runtimeRmsDoneFire.get.bits:=r','val rmsScalarDrain=enableRuntimeRmsNorm.B && active && mode===8.U &&')]
  variants += [('t',a) for a in ('cmd.io.runtimePostnormReceipt:=normLease.postnormReceipt','owner.io.runtimeRmsPublished.get.memory:=normLease.owned && rmsJob && hub.io.requests(1).valid','owner.io.runtimeRmsPublished.get.scalar:=normLease.owned && rmsJob && moeArithmetic.io.scalar(3).request.valid','owner.io.runtimeRmsPublished.get.format:=normLease.owned && rmsJob && moeArithmetic.io.formatRequest(3).valid')]
  for which,needle in variants:
   docs=dict(r=r,k=k,t=t);self.assertIn(needle,docs[which]);docs[which]=docs[which].replace(needle,'/* mutation removed contract */',1)
   with self.assertRaises(ValueError,msg=needle):checker.check(docs['r'],docs['k'],docs['t'],b)

if __name__=='__main__':unittest.main(argv=[__file__]+checker.unittest_args,verbosity=2)
