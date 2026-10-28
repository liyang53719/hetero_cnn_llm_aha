"""Small authority/address/terminal models only, not hardware execution."""
import unittest
from dataclasses import dataclass,replace
@dataclass(frozen=True)
class Receipt:
 txn:int=0x100000002;epoch:int=65534;host:tuple=(2,0x1000,0x90000000);owner:int=10
 role:int=0;tokens:int=128;heads:int=8;status:int=0;output:int=0x100000;acked:int=128*8*1024

def eligible(r,txn,epoch,host,owner,role,tokens,heads,input_,last=None):
 return (r.txn==txn and r.epoch==epoch and r.host==host and r.owner<owner and r.owner!=0xffffffff and
         r.role==role and r.tokens==tokens and r.heads==heads and r.status==0 and r.output==input_ and
         r.acked==tokens*heads*(1024 if role==0 else 512) and
         (last is None or (txn,r.owner)>last))
def scalar_count(m,h,p):return m*h*({0xc1:1290,0xc2:1316}[p])
def legal_slot(kind,slot,stage,count):
 if kind==6:return slot==8 and stage==74 and 0<count<=2695168
 if kind==1:return slot in (8,9) and stage==69 and 0<count<=(1332736 if slot==8 else 262144)
 return False
def terminal_exact(held,physical,count,returned,accepted,mem_accept,mem_return,ack,expected_bytes,ok=True):
 return held==physical and (not ok or (count==returned==accepted and mem_accept==mem_return and ack==expected_bytes))
class Integration(unittest.TestCase):
 def setUp(self):self.r=Receipt()
 def good(self,r=None,**kw):
  d=dict(txn=self.r.txn,epoch=self.r.epoch,host=self.r.host,owner=14,role=0,tokens=128,heads=8,input_=self.r.output);d.update(kw)
  return eligible(r or self.r,**d)
 def test_real_receipt(self):self.assertTrue(self.good())
 def test_full64_txn_not_low32(self):self.assertFalse(self.good(txn=self.r.txn&0xffffffff))
 def test_epoch(self):self.assertFalse(self.good(epoch=65533))
 def test_full_host(self):self.assertFalse(self.good(host=(2,0x1000,0x90000040)))
 def test_owner_strict(self):self.assertFalse(self.good(owner=10))
 def test_bad_ack(self):self.assertFalse(self.good(replace(self.r,acked=self.r.acked-64)))
 def test_error(self):self.assertFalse(self.good(replace(self.r,status=5)))
 def test_role(self):self.assertFalse(self.good(role=1))
 def test_shape(self):self.assertFalse(self.good(heads=16))
 def test_pointer(self):self.assertFalse(self.good(input_=0x200000))
 def test_repeat_receipt(self):self.assertFalse(self.good(last=(self.r.txn,self.r.owner)))
 def test_counts(self):
  self.assertEqual(scalar_count(128,16,0xc1),2641920);self.assertEqual(scalar_count(128,16,0xc2),2695168)
  self.assertEqual(scalar_count(128,2,0xc2),336896)
 def test_not_norm_domain(self):self.assertFalse(legal_slot(1,8,74,2695168))
 def test_qk_no_format_or_vector_lease(self):
  self.assertTrue(legal_slot(6,8,74,2695168));self.assertFalse(legal_slot(6,9,74,1));self.assertFalse(legal_slot(6,10,74,1))
 def test_cap(self):self.assertFalse(legal_slot(6,8,74,2695169))
 def test_terminal_held_independent_of_fire(self):
  # A held result is exact even before doneFire; fire separately authorizes retire.
  self.assertTrue(terminal_exact(14,14,2695168,2695168,2695168,65544,65544,2097152,2097152))
 def test_missing_return_not_success(self):self.assertFalse(terminal_exact(14,14,10,9,10,20,20,512,512))
 def test_missing_gate_ack_not_success(self):self.assertFalse(terminal_exact(14,14,10,10,10,20,20,512,1024))
 def test_memory_contracts(self):
  self.assertEqual(8+32*128*16,65544);self.assertEqual(8+16*128*2,4104)
 def test_address_bounds(self):
  for m in (16,128):
   for h in (8,16):
    norm=m*h*512;inp=norm*2
    self.assertEqual(inp,m*h*1024);self.assertEqual(inp+norm+norm,4*norm)
if __name__=='__main__':unittest.main()
