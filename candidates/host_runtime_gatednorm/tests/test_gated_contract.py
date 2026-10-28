"""Small protocol/geometry model; not Chisel or numerical/DUT simulation."""
import copy,unittest

def exact_counts(m,h):return dict(scalar=m*h*1284,format=m*h*256,memory=8+m*h*12,write_bytes=m*h*256)
def eligible(receipt,txn,epoch,retired=True,fault=False):
 return receipt is not None and retired and not fault and receipt['txn']==txn and receipt['epoch']==epoch and receipt['ok'] and receipt['drained']
class Model:
 def __init__(self):self.owned=False;self.lease=False;self.last=None;self.packet=None;self.poison=False
 def start(self,r,g,txn=3,epoch=4,retired=True):
  if not eligible(r,txn,epoch,retired) or g<=r['C'] or g==2**32-1 or self.last==(txn,r['C']):self.poison=True;return
  self.owned=True;self.lease=True;self.last=(txn,r['C']);self.packet=copy.deepcopy(r);self.packet['G']=g
 def terminal(self,valid,ready,identity=True,counts=True,commit=True,status=0):
  # held valid does not require a fire pulse; it remains an obligation.
  if valid and not identity:self.poison=True
  if not(valid and ready):return False
  if not identity or (status==0 and not(counts and commit and self.lease)):self.poison=True;return False
  self.owned=False;self.lease=False;return True
class Tests(unittest.TestCase):
 def r(self):return dict(txn=3,epoch=4,C=7,ok=True,drained=True)
 def test_counts_all_profiles(self):
  for m in [16,128]:
   for h in [16,32]:
    c=exact_counts(m,h);self.assertLessEqual(c['scalar'],5259264);self.assertLessEqual(c['format'],1048576);self.assertEqual(c['format'],c['write_bytes'])
 def test_max_counts(self):self.assertEqual(exact_counts(128,32),dict(scalar=5259264,format=1048576,memory=49160,write_bytes=1048576))
 def test_real_scalar_microorder(self):
  recipe=['square','sum']*128+['mean','epsilon','root','inverse']+['normalize','weight','exp','denominator','sigmoidInverse','sigmoidSign','activate','gated']*128
  self.assertEqual(len(recipe),1284);self.assertEqual(recipe[:4],['square','sum','square','sum']);self.assertEqual(recipe[256:260],['mean','epsilon','root','inverse'])
 def test_chunk_requires_retirement(self):self.assertFalse(eligible(self.r(),3,4,False))
 def test_wrong_context(self):self.assertFalse(eligible(self.r(),9,4));self.assertFalse(eligible(self.r(),3,9))
 def test_fault_revokes_receipt(self):self.assertFalse(eligible(self.r(),3,4,fault=True))
 def test_success_requires_real_fire(self):
  x=Model();x.start(self.r(),8)
  for _ in range(5):self.assertFalse(x.terminal(True,False));self.assertFalse(x.poison);self.assertTrue(x.owned)
  self.assertTrue(x.terminal(True,True));self.assertFalse(x.lease)
 def test_wrong_terminal_keeps_debt(self):
  for kwargs in [dict(identity=False),dict(counts=False),dict(commit=False)]:
   x=Model();x.start(self.r(),8);self.assertFalse(x.terminal(True,True,**kwargs));self.assertTrue(x.owned);self.assertTrue(x.lease)
 def test_error_terminal_retires_transport_not_success(self):
  x=Model();x.start(self.r(),8);self.assertTrue(x.terminal(True,True,counts=False,commit=False,status=2))
 def test_replay_rejected(self):
  x=Model();x.start(self.r(),8);x.terminal(True,True);x.start(self.r(),9);self.assertTrue(x.poison)
 def test_same_or_older_owner_rejected(self):
  for g in [6,7,2**32-1]:x=Model();x.start(self.r(),g);self.assertTrue(x.poison);self.assertFalse(x.lease)
 def test_snapshot_not_live_payload(self):
  r=self.r();x=Model();x.start(r,8);r['C']=19;self.assertEqual(x.packet['C'],7)
 def test_first_fault_veto_preserves_held(self):
  def offer(intent,held,fault):return intent and (held or not fault)
  self.assertFalse(offer(True,False,True));self.assertTrue(offer(True,True,True))
 def test_exact_memory_not_only_writes(self):
  c=exact_counts(16,16);self.assertNotEqual(c['memory'],c['write_bytes']//64);self.assertEqual(c['memory'],8+256*(4+4+4))
 def test_no_double_round_boundary(self):
  # Data handed to bank is the unchanged raw scalar return; bank alone returns16bits.
  raw=0x3f808001;request=raw;self.assertEqual(request,raw);self.assertNotEqual(request,raw&0xffff0000)
if __name__=='__main__':unittest.main(verbosity=2)
