"""Abstract source-offer transition only; not Chisel/DUT."""
import unittest
from dataclasses import dataclass
@dataclass(frozen=True)
class State:
 issue:bool=True;prefix:bool=True;reset:bool=False;guard_ready:bool=False;job:tuple=(14,128,16,0x100000,0xc2)
def step(s,fixed=True):
 valid=s.issue
 ready=s.guard_ready and not s.reset
 fire=valid and ready
 failed=s.issue and s.reset and (not s.prefix if fixed else True)
 return valid,fire,State(issue=s.issue and not failed and not fire,prefix=s.prefix,reset=s.reset,guard_ready=s.guard_ready,job=s.job)
class Held(unittest.TestCase):
 def test_original_failure(self):
  s=State(reset=True);valid,fire,n=step(s,False)
  self.assertTrue(valid);self.assertFalse(fire);self.assertFalse(n.issue)
 def test_first_offer_under_fault_retained(self):
  s=State(reset=True);valid,fire,n=step(s)
  self.assertTrue(valid);self.assertFalse(fire);self.assertTrue(n.issue);self.assertEqual(n.job,s.job)
 def test_previously_held_preserved(self):
  s=State()
  for _ in range(5):valid,fire,s=step(s);self.assertTrue(valid);self.assertFalse(fire)
  s=State(reset=True,job=s.job)
  for _ in range(5):valid,fire,s=step(s);self.assertTrue(valid);self.assertFalse(fire);self.assertTrue(s.issue)
 def test_no_fake_completion(self):self.assertTrue(step(State(reset=True))[2].issue)
 def test_legacy_unchanged(self):self.assertFalse(step(State(prefix=False,reset=True))[2].issue)
 def test_clean_acceptance(self):self.assertTrue(step(State(guard_ready=True))[1]);self.assertFalse(step(State(guard_ready=True))[2].issue)
 def test_fault_blocks_acceptance(self):self.assertFalse(step(State(reset=True,guard_ready=True))[1])
 def test_no_physical_debt_refund(self):
  # The source has not fired; neither model manufactures a physical receipt.
  self.assertFalse(step(State(reset=True))[1]);self.assertFalse(step(State(reset=True),False)[1])
if __name__=='__main__':unittest.main()
