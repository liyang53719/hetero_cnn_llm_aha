"""Bounded pure contract models and source checks, NOT Chisel/RTL execution."""
import sys,unittest,json,hashlib,re
from pathlib import Path
O=Path(__file__).resolve().parents[1];sys.path.insert(0,str(O))
import select_sources as selection
S=lambda n:(O/'source'/n).read_text()
def counts(h,m):
 if h not in (16,32) or m not in (16,128):raise ValueError('shape')
 c=2 if m==128 else 1
 return (h*c*((832 if h==32 else 64)+2209),h*c*4704,h*c*329472+4*m*h)
def allowed(slot,kind,stage):return (slot,kind,stage) in ((10,4,72),(11,10,78),(12,11,79))
def shape(policy,multiply,b):return policy in (0,3) or policy==4 and not multiply and all(x==0 for x in b)
class Ledger:
 def __init__(self,quota):self.quota=quota;self.accepted=0;self.issued=0;self.returned=0;self.offer=None;self.pending=None;self.poison=False
 def accept(self,owner,payload):
  if self.poison or self.offer is not None or self.accepted>=self.quota:return False
  self.offer=(owner,self.accepted,payload);self.accepted+=1;return True
 def issue(self,ready):
  if ready and self.offer is not None and self.pending is None:self.pending=self.offer;self.offer=None;self.issued+=1
 def result(self,tag,ready):
  if self.pending is None or self.pending[:2]!=tag:self.poison=True;return None
  if not ready:return None
  p=self.pending;self.pending=None;self.returned+=1;return p
 def drained(self):return self.offer is None and self.pending is None and self.accepted==self.issued==self.returned
 def retire(self,success):return self.drained() and (not success or not self.poison and self.returned==self.quota)
class IntegrationTests(unittest.TestCase):
 def test_four_exact_counts(self):
  for h,m,total in ((16,16,5347840),(16,128,10701824),(32,16,10695680),(32,128,21403648)):
   scalar,derived,execute=counts(h,m);self.assertEqual(derived+execute,total);self.assertEqual(derived,h*(2 if m==128 else 1)*4704)
 def test_maximums(self):self.assertEqual(counts(32,128),(194624,301056,21102592))
 def test_no_whole_chunk_halving(self):
  for h in (16,32):
   for m in (16,128):
    _,d,e=counts(h,m);old=h*(2 if m==128 else 1)*663648+8*m*h;self.assertEqual(d+e-old//2,d//2)
 def test_no_slot_alias(self):
  self.assertTrue(allowed(12,11,79));self.assertFalse(allowed(11,11,79));self.assertFalse(allowed(10,11,79));self.assertFalse(allowed(12,4,72))
 def test_policy_shape(self):
  for p in range(8):
   for mul in (False,True):
    for b in ([0]*32,[1]*32):self.assertEqual(shape(p,mul,b),p in (0,3) or p==4 and not mul and b==[0]*32)
 def test_stalled_offer_survives_fault(self):
  l=Ledger(2);self.assertTrue(l.accept(12,tuple(range(32))));original=l.offer;l.poison=True
  for _ in range(9):l.issue(False);self.assertEqual(l.offer,original)
  self.assertFalse(l.accept(11,()));l.issue(True);self.assertEqual(l.pending,original)
  self.assertIsNotNone(l.result((12,0),True));self.assertTrue(l.retire(False));self.assertFalse(l.retire(True))
 def test_return_backpressure(self):
  l=Ledger(1);l.accept(12,());l.issue(True)
  for _ in range(8):self.assertIsNone(l.result((12,0),False));self.assertEqual(l.returned,0);self.assertFalse(l.drained())
  self.assertIsNotNone(l.result((12,0),True));self.assertTrue(l.retire(True))
 def test_wrong_return_quarantine(self):
  for tag in ((11,0),(12,1),(10,0)):
   l=Ledger(1);l.accept(12,());l.issue(True);self.assertIsNone(l.result(tag,True));self.assertTrue(l.poison);self.assertEqual(l.returned,0);self.assertFalse(l.drained())
 def test_exactly_once(self):
  l=Ledger(1);l.accept(12,());l.issue(True);l.result((12,0),True);self.assertIsNone(l.result((12,0),True));self.assertEqual(l.returned,1)
 def test_quota_only_actual_accept(self):
  l=Ledger(2);l.accept(12,());
  for _ in range(4):self.assertFalse(l.accept(12,()));self.assertEqual(l.accepted,1)
  self.assertFalse(l.retire(True));l.issue(True);l.result((12,0),True);self.assertFalse(l.retire(True))
  l.accept(12,());l.issue(True);l.result((12,1),True);self.assertTrue(l.retire(True));self.assertFalse(l.accept(12,()))
 def test_selector_default_legacy(self):
  d=selection.select();self.assertFalse(d['enableChunk32']);self.assertEqual(len(d['source_paths']),159)
 def test_selector_actual_path(self):
  d=selection.select(hardware_source='gdn-chunk32-abort-v2');self.assertTrue(d['enableChunk32']);self.assertEqual(len(d['source_paths']),162)
  for n in ('HostBlockTopV4.scala','QwenOwnerProtocol.scala','HostRuntimeChunkWiringV9.scala','GdnRuntimeChunkLeafCollection.scala'):
   self.assertEqual(next(p for p in d['source_paths'] if Path(p).name==n),str(O/'source'/n))
  self.assertIn('enableChunk32=true',Path(d['helper']).read_text());self.assertEqual(d['profiles'],list(range(5)))
 def test_helper_is_unique_selected_input(self):
  for mode in ('legacy','gdn-chunk32-abort-v2'):
   d=selection.select(hardware_source=mode);helpers=[p for p in d['source_paths'] if Path(p).name=='DiagnoseOriginalHostMoePhaseV5.scala'];self.assertEqual(helpers,[d['helper']]);self.assertEqual(len(d['source_paths']),162 if mode!='legacy' else 159)
 def test_cancel_source_unique(self):
  d=selection.select(hardware_source='gdn-chunk32-abort-v2');self.assertEqual(sum(Path(p).name=='CancellableHeldDecoupledOfferV1.scala' for p in d['source_paths']),1)
 def test_reject_old_nonabort_selector(self):
  with self.assertRaises(ValueError):selection.select(hardware_source='gdn-chunk32-v1')
 def test_reject_unknown_selector(self):
  for s in ('gdn32','profile1','transposed-tile-address-v1'):
   with self.assertRaises(ValueError):selection.select(hardware_source=s)
 def test_reject_old_artifact(self):
  old=selection.select();new=selection.select(hardware_source='gdn-chunk32-abort-v2')
  self.assertNotEqual(old['generation_identity'],new['generation_identity'])
  with self.assertRaises(ValueError):selection.require_new_artifact(new['generation_identity'],old['generation_identity'])
 def test_single_bank_and_reviewed_leaf(self):
  adapter=S('UnifiedMoeSharedArithmeticAdapterV5.scala');self.assertEqual(adapter.count('Module(new UnifiedVectorElement32BankV4)'),1)
  self.assertEqual(selection.sha(O/'source/GdnRuntimeChunkExecuteOwner32V1.scala'),'1a8c82194c349379aac78c5675e75b7d3327575e11c872c6f79428bff53e0ebf')
 def test_compile_time_exclusive(self):
  s=S('GdnRuntimeChunkSelectedExecuteV1.scala');self.assertIn('if(enableChunk32)',s);self.assertEqual(s.count('Module(new GdnRuntimeChunkExecuteOwner32V1)'),1);self.assertEqual(s.count('Module(new GdnRuntimeChunkExecuteOwnerV8)'),1)
  for n in ('HostBlockTopV4.scala','QwenOwnerProtocol.scala','GdnRuntimeChunkLeafCollection.scala'):self.assertIn('enableChunk32:Boolean=false',S(n))
 def test_retained_actual_counts(self):
  s=S('UnifiedMoeSharedArithmeticAdapterV5.scala')
  for x in ('val vectorIssue=bank.io.request.fire;val vectorReturn=bank.io.result.fire','val vectorAccept=varb.io.out.fire','bank.io.result.bits.identity.asUInt===vTag.asUInt','issued(i):=issued(i)+1.U','returned(i):=returned(i)+1.U'):self.assertIn(x,s)
 def test_drain_includes_new_path(self):
  s=S('HostRuntimeChunkWiringV9.scala')
  for x in ('!chunk32Pending && !chunk32Offer.held && !p.vector32.request.valid && !p.vector32.result.valid','a.io.status(slots(i)).counts.returned===leases(i).lease.expectedOperations.pad(33)','val slots=if(enableChunk32)Seq(8,10,12)else Seq(8,10)'):self.assertIn(x,s)
 def test_base_files_unchanged(self):
  d=json.loads((O/'MODEL_SOURCE_OVERLAY.json').read_text())
  for r in d['changes']:self.assertEqual(selection.sha(selection.DEFAULT_BASE/r['base_path']),r['base_sha256'])
 def test_source_bracket_balance(self):
  for p in (O/'source').glob('*.scala'):
   s=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',p.read_text(),flags=re.S);stack=[]
   for c in s:
    if c in '({[':stack.append(c)
    elif c in ')}]':self.assertTrue(stack,p.name);self.assertEqual(stack.pop(),{')':'(',']':'[','}':'{'}[c],p.name)
   self.assertFalse(stack,p.name)
if __name__=='__main__':unittest.main(verbosity=2)
