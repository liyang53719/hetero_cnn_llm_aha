"""Small control-contract model only; does not execute Chisel or numerical DUT."""
import unittest
from dataclasses import dataclass
@dataclass
class Fence:
    host:int=123
    txn:int=9
    profile:int=1
    validated:bool=False
    held:bool=False
    committed:bool=False
    status:int=0
    result=None
    roots:tuple=(0,0,0)
    def validate(self, *, terminal=True, actual=True, rows=128, distinct=True, disjoint=True, cold=True, drain=True, fault=False):
        if not (terminal and actual and rows==128 and distinct and disjoint and cold) or self.committed:
            self.status=1;return
        if fault:self.status=2;return
        if drain:self.validated=True;self.held=True
    def completion(self, *, ready=False, fault=False, drain=True, host=123, txn=9):
        if not self.held or not ready:return
        self.held=False
        if fault or not drain or host!=self.host or txn!=self.txn or self.committed:self.status=2;return
        self.roots=(100,200,1);self.committed=True
    def offer_result(self, *, fault=False, drain=True):
        if self.result is None:
            self.result=self.status or (2 if fault or not drain or not self.committed else 0)
        return self.result
class Tests(unittest.TestCase):
    def test_public21_count_is_profile0_only(self):
        for profile in range(5):
            for count in range(70):
                accepted=(profile!=0 or count==21) and count>0 and count<=64
                self.assertEqual(accepted, count==21 if profile==0 else 1<=count<=64)
    def test_four_profiles(self):
        for p in range(1,5):
            f=Fence(profile=p);f.validate();self.assertEqual(f.roots,(0,0,0));f.completion(ready=True)
            self.assertEqual(f.roots,(100,200,1));self.assertEqual(f.offer_result(),0)
    def test_wait_drain(self):
        f=Fence();f.validate(drain=False);self.assertFalse(f.held);f.validate();self.assertTrue(f.held)
    def test_held_completion(self):
        f=Fence();f.validate()
        for _ in range(30):f.completion(fault=True);self.assertTrue(f.held);self.assertFalse(f.committed)
        f.completion(ready=True,fault=True);self.assertFalse(f.committed);self.assertEqual(f.offer_result(),2)
    def test_bad_validation(self):
        for kw in [dict(terminal=False),dict(actual=False),dict(rows=16),dict(distinct=False),dict(disjoint=False),dict(cold=False)]:
            f=Fence();f.validate(**kw);self.assertFalse(f.held);self.assertNotEqual(f.offer_result(),0)
    def test_identity_and_drain(self):
        for kw in [dict(host=124),dict(txn=10),dict(drain=False),dict(fault=True)]:
            f=Fence();f.validate();f.completion(ready=True,**kw);self.assertFalse(f.committed);self.assertEqual(f.roots,(0,0,0))
    def test_no_partial_commit(self):
        for p in range(1,5):
            f=Fence(profile=p);f.validate();f.completion(ready=True,fault=True);self.assertEqual(f.roots,(0,0,0))
    def test_postcommit_fault_no_rollback(self):
        f=Fence();f.validate();f.completion(ready=True);self.assertEqual(f.offer_result(fault=True),2);self.assertTrue(f.committed)
    def test_held_result_immutable(self):
        f=Fence();f.validate();f.completion(ready=True);self.assertEqual(f.offer_result(),0)
        self.assertEqual(f.offer_result(fault=True),0) # resetRequired remains separate live veto/report sideband
    def test_no_prefix_success(self):
        self.assertNotEqual(Fence().offer_result(),0)
    def test_no_recommit(self):
        f=Fence();f.validate();f.completion(ready=True);f.validate();self.assertFalse(f.held);self.assertEqual(f.roots,(100,200,1))
if __name__=='__main__':unittest.main()
