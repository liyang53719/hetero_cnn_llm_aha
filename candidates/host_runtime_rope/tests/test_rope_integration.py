"""Small provenance/count/address models only, never hardware/numeric proof."""
from dataclasses import dataclass,replace
import unittest
@dataclass(frozen=True)
class Receipt:
 txn:int=0x100000001;epoch:int=0xfffe;host:tuple=(4,0x10000,0x1000000,0x2000000);owner:int=10
 role:int=0;m:int=128;heads:int=16;output:int=0x100000;status:int=0;committed:bool=True;ack:int=2097152

def eligible(r,txn,epoch,host,owner,role,m,heads,input_,both=True,qdone=False,last=None):
 return (both and r.txn==txn and r.epoch==epoch and r.host==host and r.owner<owner and r.owner!=0xffffffff and
         r.role==role and r.m==m and r.heads==heads and r.output==input_ and r.status==0 and r.committed and
         r.ack==m*heads*(1024 if role==0 else 512) and (role==0 or qdone) and
         (last is None or (txn,r.owner)>last))
def terminal(m,h,sa,sr,ma,mr,ack,status=0):
 return status!=0 or (sa==sr==m*h*192 and ma==mr==m*(2+16*h) and ack==m*h*512)
def legal(base,size,addr,write=False,mask=0,rights=True):
 return rights and addr%64==0 and addr+64<=1<<56 and base<=addr and addr+64<=base+size and mask==((1<<64)-1 if write else 0)
class Integration(unittest.TestCase):
 def setUp(self):self.r=Receipt()
 def ok(self,r=None,**kwargs):
  d=dict(txn=self.r.txn,epoch=self.r.epoch,host=self.r.host,owner=12,role=0,m=128,heads=16,input_=self.r.output);d.update(kwargs)
  return eligible(r or self.r,**d)
 def test_actual_ack(self):self.assertTrue(self.ok())
 def test_full_transaction(self):self.assertFalse(self.ok(txn=1))
 def test_full_host(self):self.assertFalse(self.ok(host=(4,0x10000,0x1000000,0x2000040)))
 def test_epoch(self):self.assertFalse(self.ok(epoch=0xffff))
 def test_owner_equal(self):self.assertFalse(self.ok(owner=10))
 def test_owner_older(self):self.assertFalse(self.ok(owner=9))
 def test_owner_reserved(self):self.assertFalse(self.ok(replace(self.r,owner=0xffffffff),owner=0x100000000))
 def test_replay(self):self.assertFalse(self.ok(last=(self.r.txn,self.r.owner)))
 def test_missing_k(self):self.assertFalse(self.ok(both=False))
 def test_bad_status(self):self.assertFalse(self.ok(replace(self.r,status=1)))
 def test_not_committed(self):self.assertFalse(self.ok(replace(self.r,committed=False)))
 def test_missing_gate_ack(self):self.assertFalse(self.ok(replace(self.r,ack=1048576)))
 def test_other_head_count(self):self.assertFalse(self.ok(heads=8))
 def test_other_role(self):self.assertFalse(self.ok(role=1))
 def test_other_input(self):self.assertFalse(self.ok(input_=self.r.output+64))
 def test_k_requires_q_ack(self):
  r=replace(self.r,role=1,heads=2,ack=131072)
  self.assertFalse(self.ok(r,role=1,heads=2));self.assertTrue(self.ok(r,role=1,heads=2,qdone=True))
 def test_q16_terminal(self):self.assertTrue(terminal(128,16,393216,393216,33024,33024,1048576))
 def test_k2_terminal(self):self.assertTrue(terminal(128,2,49152,49152,4352,4352,131072))
 def test_missing_scalar(self):self.assertFalse(terminal(128,16,393216,393215,33024,33024,1048576))
 def test_missing_mem(self):self.assertFalse(terminal(128,16,393216,393216,33024,33023,1048576))
 def test_wrong_mem_geometry(self):self.assertFalse(terminal(128,16,393216,393216,33025,33025,1048576))
 def test_missing_write_ack(self):self.assertFalse(terminal(128,16,393216,393216,33024,33024,1048512))
 def test_failure_not_success(self):self.assertTrue(terminal(128,16,1,1,1,1,0,status=1))
 def test_memory_bounds(self):
  self.assertTrue(legal(0x100000,1048576,0x1fffc0,True,(1<<64)-1))
  self.assertFalse(legal(0x100000,1048576,0x200000,True,(1<<64)-1))
  self.assertFalse(legal(0x100000,1048576,0x100000,True,0))
  self.assertFalse(legal(0x100000,1048576,0x100000,rights=False))
 def test_trig_fullallocation(self):
  self.assertTrue(legal(0x300000,256*128,0x307fc0));self.assertFalse(legal(0x300000,256*128,0x308000))
if __name__=='__main__':unittest.main()
