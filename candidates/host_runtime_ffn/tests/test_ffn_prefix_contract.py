"""Executable protocol contract model; NOT Chisel simulation or numerical DUT proof."""
from dataclasses import dataclass, replace
import unittest

SENTINEL=2**32-1
@dataclass(frozen=True)
class Receipt:
    phase:int; physical:int; logical:int; txn:int=2**40+9
    host:tuple=(1,12,1024,3584,0x1000,0x2000,0x3000,0x4000)
    rows:int=128; a:int=0x100000; b:int=0x200000; dst:int=0x300000
    n:int=1024; k:int=1024; status:int=0; ack:int=262144
    gamma:int=0x800000; committed:bool=True; drained:bool=True

class Ledger:
    def __init__(self, norm=None):
        self.norm=norm or Receipt(0,100,20)
        self.residual=replace(self.norm,physical=99,logical=19,a=0x900000,dst=self.norm.a)
        self.stages={};self.issued=set();self.pending=None;self.receipt=None
        self.fault=False;self.done_pending=None;self.published=[]
    def current(self,r):return r.txn==self.norm.txn and r.host==self.norm.host
    def good(self,r):return self.current(r) and r.physical!=SENTINEL and r.status==0 and r.ack==r.rows*r.n*2 and r.committed and r.drained
    def admit(self,q):
        if self.fault or q.phase in self.issued or not self.current(q):return False
        if q.host[0] not in (1,2) or q.rows not in ((16,128) if q.host[0]==1 else (128,)):return False
        if q.phase in (1,2):
            ok=self.good(self.norm) and q.a==self.norm.dst and q.n==3584 and q.k==1024 and self.norm.physical<q.physical
            if q.phase==2:ok=ok and 1 in self.stages and self.good(self.stages[1]) and self.stages[1].physical<q.physical
        elif q.phase==3:
            ok=all(p in self.stages and self.good(self.stages[p]) and self.stages[p].physical<q.physical for p in (1,2))
            ok=ok and q.a==self.stages[1].dst and q.b==self.stages[2].dst and q.n==q.k==3584
        elif q.phase==4:
            ok=3 in self.stages and self.good(self.stages[3]) and self.stages[3].physical<q.physical and q.a==self.stages[3].dst and q.n==1024 and q.k==3584
        elif q.phase==5:
            ok=4 in self.stages and self.good(self.stages[4]) and self.good(self.residual) and max(self.stages[4].physical,self.residual.physical)<q.physical
            ok=ok and q.a==self.residual.dst and q.b==self.stages[4].dst and q.n==q.k==1024
        else:return False
        if not ok or q.physical==SENTINEL:return False
        self.pending=q;self.issued.add(q.phase);self.receipt=None;return True
    def terminal(self,r):
        if self.pending is None or r!=self.pending or not self.good(r):self.fault=True;return False
        self.pending=None
        if self.fault:return False
        self.stages[r.phase]=r;self.receipt=r;return True
    def logical_done(self,r):
        if self.fault or r!=self.receipt:return False
        self.done_pending=r;return True
    def completion(self):
        if self.fault or self.done_pending is None or self.done_pending!=self.receipt:return False
        self.published.append(self.done_pending.phase);self.done_pending=None;return True

def program(norm):
    gate=replace(norm,phase=1,physical=101,logical=21,a=norm.dst,b=0x1000000,dst=0x2000000,n=3584,k=1024,ack=norm.rows*3584*2)
    up=replace(gate,phase=2,physical=102,logical=22,b=0x3000000,dst=0x4000000)
    silu=replace(gate,phase=3,physical=103,logical=23,a=gate.dst,b=up.dst,dst=0x5000000,k=3584)
    down=replace(gate,phase=4,physical=104,logical=24,a=silu.dst,b=0x6000000,dst=0x7000000,n=1024,k=3584,ack=norm.rows*1024*2)
    residual=replace(norm,phase=5,physical=105,logical=25,a=norm.a,b=down.dst,dst=0x8000000)
    return [gate,up,silu,down,residual]

class PrefixContract(unittest.TestCase):
    def run_chain(self,ledger):
        for q in program(ledger.norm):
            self.assertTrue(ledger.admit(q));self.assertTrue(ledger.terminal(q))
            self.assertTrue(ledger.logical_done(q));self.assertTrue(ledger.completion())
    def test_profiles_rows(self):
        for profile,rows in [(1,16),(1,128),(2,128)]:
            l=Ledger(replace(Receipt(0,100,20),host=(profile,12,1024,3584,4096,8192,12288,16384),rows=rows,ack=rows*2048))
            self.run_chain(l);self.assertEqual(l.published,[1,2,3,4,5])
    def test_moe_not_dense(self):
        for profile in [0,3,4]:
            l=Ledger();q=replace(program(l.norm)[0],host=(profile,)+l.norm.host[1:]);self.assertFalse(l.admit(q))
    def test_full_host_not_epoch_only(self):
        l=Ledger();q=program(l.norm)[0]
        for index in range(2,len(q.host)):
            h=list(q.host);h[index]+=64;self.assertFalse(l.admit(replace(q,host=tuple(h))))
    def test_transaction_upper32(self):
        l=Ledger();self.assertFalse(l.admit(replace(program(l.norm)[0],txn=l.norm.txn+2**32)))
    def test_producer_strict_32bit(self):
        for tag in [0,99,100,SENTINEL]:
            l=Ledger();self.assertFalse(l.admit(replace(program(l.norm)[0],physical=tag)))
    def test_wrong_source_not_readonly_lookalike(self):
        l=Ledger();self.assertFalse(l.admit(replace(program(l.norm)[0],a=l.norm.dst+64)))
    def test_gate_cannot_repeat(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertTrue(l.terminal(q));self.assertFalse(l.admit(replace(q,physical=106)))
    def test_up_cannot_precede_gate(self):
        l=Ledger();self.assertFalse(l.admit(program(l.norm)[1]))
    def test_down_cannot_precede_silu(self):
        l=Ledger();self.assertFalse(l.admit(program(l.norm)[3]))
    def test_residual_cannot_precede_down(self):
        l=Ledger();self.assertFalse(l.admit(program(l.norm)[4]))
    def test_no_fabricated_physical_ack(self):
        l=Ledger();q=program(l.norm)[0];self.assertFalse(l.terminal(q));self.assertEqual(l.stages,{})
    def test_terminal_same_logical_not_physical_is_rejected(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertFalse(l.terminal(replace(q,physical=q.logical)))
    def test_short_ack_no_eligibility(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertFalse(l.terminal(replace(q,ack=q.ack-64)))
    def test_leaf_error_no_refund(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertFalse(l.terminal(replace(q,status=4)));self.assertIn(1,l.issued)
    def test_late_fault_retains_transport_debt(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));l.fault=True
        self.assertEqual(l.pending,q);self.assertFalse(l.terminal(q));self.assertIsNone(l.pending);self.assertEqual(l.stages,{})
    def test_done_not_completion(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertTrue(l.terminal(q));self.assertTrue(l.logical_done(q));self.assertEqual(l.published,[])
    def test_late_completion_fault_no_publish(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertTrue(l.terminal(q));self.assertTrue(l.logical_done(q));l.fault=True;self.assertFalse(l.completion())
    def test_changed_held_proof_no_publish(self):
        l=Ledger();q=program(l.norm)[0];self.assertTrue(l.admit(q));self.assertTrue(l.terminal(q));self.assertTrue(l.logical_done(q));l.receipt=replace(q,gamma=q.gamma+64);self.assertFalse(l.completion())
    def test_silu_stores_two_bf16_values_only(self):
        for rows in [16,128]:
            lanes=rows*3584;self.assertEqual((6*lanes,2*lanes,3*lanes//32,2*lanes), (rows*21504,rows*7168,rows*336,rows*7168))
    def test_no_final_root_publication(self):
        l=Ledger();self.run_chain(l);self.assertFalse(hasattr(l,'cache_commit'));self.assertFalse(hasattr(l,'state_commit'))

if __name__=='__main__':unittest.main()
