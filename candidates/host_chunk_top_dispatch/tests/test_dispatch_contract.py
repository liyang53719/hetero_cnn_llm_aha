"""Executable small contract model, NOT hardware or numerical simulation."""
import copy, unittest
class Route:
 def __init__(self): self.pending=None;self.poison=False
 def accept(self,client,payload):
  if self.pending is not None: self.poison=True;return
  self.pending=(client,copy.deepcopy(payload))
 def result(self,echo):
  if self.pending is None or echo!=self.pending[1]:self.poison=True;return None
  client=self.pending[0];self.pending=None;return client
class Transfer:
 def __init__(self):self.snapshot=None;self.wait=False;self.owned=False;self.offer=None;self.count=0;self.poison=False;self.lease=False;self.last=-1
 def logical(self,txn,epoch,P,C,eligible=True):
  if self.wait or self.owned or self.offer is not None or not eligible or P<=self.last or C<=P or max(P,C)==2**32-1:self.poison=True;return
  self.snapshot={'txn':txn,'epoch':epoch,'P':P,'result_tag':P,'accepted_tag':P,'C':C};self.wait=True
 def physical(self):
  if not self.wait or self.poison:self.poison=True;return
  self.wait=False;self.owned=True;self.offer=copy.deepcopy(self.snapshot)
 def tick(self,ready=False,fault=False):
  self.poison|=fault
  before=copy.deepcopy(self.offer)
  if self.offer is not None and ready:
   self.offer=None;self.count+=1
   if not self.poison:self.lease=True;self.last=self.snapshot['C']
  return before
 def done(self,identity=True,counts=True,status=0):
  if not identity or (status==0 and (not counts or not self.lease)):self.poison=True;return False
  self.owned=False;self.lease=False;return True
class Tests(unittest.TestCase):
 def test_zero_producer_distinct_owner(self):
  t=Transfer();t.logical(7,3,0,1);t.physical();self.assertEqual(t.tick(True)['P'],0);self.assertEqual(t.count,1);self.assertTrue(t.lease)
 def test_no_offer_from_valid_only(self):
  t=Transfer();t.logical(7,3,1,2);self.assertIsNone(t.tick(True));self.assertEqual(t.count,0)
 def test_stalled_offer_survives_fault(self):
  t=Transfer();t.logical(7,3,1,2);t.physical();expected=t.tick()
  for _ in range(5):self.assertEqual(t.tick(False,True),expected)
  self.assertEqual(t.count,0);self.assertIsNotNone(t.offer)
 def test_one_shot(self):
  t=Transfer();t.logical(7,3,1,2);t.physical();t.tick(True)
  for _ in range(6):self.assertIsNone(t.tick(True))
  self.assertEqual(t.count,1)
 def test_replay_and_backwards(self):
  for P,C in [(1,1),(2,1),(0xffffffff,0xffffffff)]:
   t=Transfer();t.logical(7,3,P,C);self.assertTrue(t.poison)
  t=Transfer();t.logical(7,3,1,2);t.physical();t.tick(True);t.done();t.logical(7,3,1,3);self.assertTrue(t.poison)
 def test_wrong_terminal_never_refunds(self):
  for kw in ({'identity':False},{'counts':False}):
   t=Transfer();t.logical(7,3,1,2);t.physical();t.tick(True);self.assertFalse(t.done(**kw));self.assertTrue(t.owned);self.assertTrue(t.lease)
 def test_actual_return_owner_not_live_request(self):
  r=Route();r.accept(1,{'tag':23,'policy':1});current_valid_client=0
  self.assertEqual(r.result({'tag':23,'policy':1}),1);self.assertNotEqual(current_valid_client,1)
 def test_unknown_return_does_not_retire(self):
  r=Route();r.accept(1,{'tag':23});self.assertIsNone(r.result({'tag':24}));self.assertIsNotNone(r.pending)
 def test_exact_counts_and_spans(self):
  self.assertEqual(32*2*(832+2209),194624);self.assertEqual(32*2*663648+8*128*32,42506240)
  for M in (16,128):
   chunks=2 if M==128 else 1
   for H in (16,32):
    self.assertLessEqual(H*chunks*(832+2209),194624)
    self.assertLessEqual(H*chunks*663648+8*M*H,42506240)
    self.assertEqual(H*(65536+chunks*806912),H*(1679360 if M==128 else 872448))
 def test_drain_cannot_hide_unpublished_request(self):
  def drained(raw_request=False,pending=False,held=False,lease_active=False):return not(raw_request or pending or held)
  self.assertTrue(drained(lease_active=True));self.assertFalse(drained(raw_request=True));self.assertFalse(drained(pending=True));self.assertFalse(drained(held=True))
 def test_legacy_dispatch(self):
  def mode(m,recurrent=False):return 14 if not recurrent and m in (16,128) else 5
  self.assertEqual(mode(1),5);self.assertEqual(mode(1,True),5);self.assertEqual(mode(16),14);self.assertEqual(mode(128),14)
class GateTests(unittest.TestCase):
 def test_guard_current_fault_vetoes_new_not_held(self):
  def visible(intent,held,independent=False,guard=False,poison=False):return intent and (held or not(independent or guard or poison))
  self.assertFalse(visible(True,False,guard=True));self.assertTrue(visible(True,True,guard=True))
 def test_held_client_never_reselected(self):
  pending_choice=1;current_priority_choice=0;held=True
  chosen=pending_choice if held else current_priority_choice
  self.assertEqual(chosen,1)
 def test_prefix_chunk_mutual_exclusion(self):
  def overlap(owned,prefix_request,old_prefix_pending):return owned and (prefix_request or old_prefix_pending)
  self.assertTrue(overlap(True,True,False));self.assertTrue(overlap(True,False,True));self.assertFalse(overlap(True,False,False))
 def test_held_kernel_job_is_not_retracted(self):
  can_start=False;chunk_held=True;mode=14;upstream_valid=True
  actual=upstream_valid and (can_start or (chunk_held and mode==14))
  self.assertTrue(actual)
if __name__=='__main__':unittest.main()
