import unittest
from dataclasses import replace
from edge_model import Inputs,evaluate,original_fixed_points,loan_edge
class Edges(unittest.TestCase):
 def test_original_reachable_error_has_no_fixed_point(self):
  self.assertEqual(original_fixed_points(Inputs(raw_error=True)),[])
  self.assertEqual(len(original_fixed_points(Inputs(binary=False,raw_error=True))),1)
 def test_error_consumes_same_edge(self):
  for binary in (False,True):
   r=evaluate(Inputs(binary=binary,raw_error=True));self.assertTrue(r['valid'] and r['public_fire'] and r['raw_fire']);self.assertFalse(r['abort'] or r['write_valid'] or r['admit_new']);self.assertFalse(r['loan_active_next']);self.assertTrue(r['loan_poison_next'] and r['bridge_poison_next'])
 def test_normal_held_reply(self):
  for binary in (False,True):
   i=Inputs(binary=binary)
   for _ in range(127):
    r=evaluate(i);self.assertTrue(r['valid'] and r['loan_active_next']);self.assertFalse(r['public_fire'] or r['raw_fire'] or r['bad'] or r['abort'])
   r=evaluate(replace(i,write_ready=True));self.assertTrue(r['write_valid'] and r['public_fire']);self.assertFalse(r['loan_active_next'])
 def test_external_abort_private_vs_public_drain(self):
  r=evaluate(Inputs(external_abort=True));self.assertTrue(r['abort'] and r['raw_fire']);self.assertFalse(r['valid'] or r['public_fire'] or r['write_valid'] or r['loan_active_next'])
  r=evaluate(Inputs(binary=False,external_abort=True));self.assertTrue(r['abort'] and r['valid'] and r['public_fire']);self.assertFalse(r['write_valid'] or r['loan_active_next'])
 def test_abort_waits_for_accepted_result(self):
  r=evaluate(Inputs(external_abort=True,raw_valid=False));self.assertTrue(r['loan_active_next']);self.assertFalse(r['loan_drained'] or r['bridge_can_lock'] or r['coordinator_can_reply'])
  r=evaluate(Inputs(bridge_poison=True,loan_poison=True));self.assertTrue(r['raw_fire']);self.assertFalse(r['valid'] or r['loan_active_next'])
 def test_sticky_after_one_cycle_abort(self):
  r=evaluate(Inputs(external_abort=True));n=evaluate(Inputs(loan_active=False,raw_valid=False,bridge_poison=r['bridge_poison_next'],loan_poison=r['loan_poison_next']));self.assertTrue(n['abort'] and n['bad']);self.assertFalse(n['admit_new'] or n['public_fire'])
 def test_tile_error_blocks_writes_and_new_work(self):
  r=evaluate(Inputs(tile_valid=True,tile_error=True,write_ready=True));self.assertTrue(r['bad'] and r['public_fire']);self.assertFalse(r['write_valid'] or r['admit_new'])
 def test_terminal_requires_all_drained(self):
  i=Inputs(loan_active=False,raw_valid=False,bridge_poison=True,bridge_busy=False)
  self.assertTrue(evaluate(i)['coordinator_can_reply'])
  for n in [replace(i,tile_drained=False),replace(i,loan_active=True),replace(i,bridge_busy=True),replace(i,other_services_busy=True)]:self.assertFalse(evaluate(n)['coordinator_can_reply'])
 def test_legacy_abort_pending_then_public_retirement(self):
  i=Inputs(binary=False,external_abort=True,raw_valid=False)
  r=evaluate(i);self.assertTrue(r['loan_active_next']);self.assertFalse(r['raw_fire'] or r['coordinator_can_reply'])
  i=Inputs(binary=False,bridge_poison=True,loan_poison=True,raw_valid=False)
  for _ in range(17):
   r=evaluate(i);self.assertTrue(r['loan_active_next']);self.assertFalse(r['loan_drained'] or r['bridge_can_lock'])
  r=evaluate(replace(i,raw_valid=True));self.assertTrue(r['valid'] and r['ready'] and r['public_fire'] and r['raw_fire']);self.assertFalse(r['loan_active_next'] or r['write_valid'])
 def test_abort_and_error_same_edge(self):
  for binary in (False,True):
   r=evaluate(Inputs(binary=binary,external_abort=True,raw_error=True));self.assertTrue(r['raw_fire'] and r['bridge_poison_next'] and r['loan_poison_next']);self.assertEqual(r['public_fire'],not binary);self.assertFalse(r['loan_active_next'] or r['write_valid'] or r['admit_new'])
 def test_error_must_still_gate_write_immediately(self):
  i=Inputs(raw_error=True,write_ready=True);r=evaluate(i)
  naive_write=not(i.external_abort or i.bridge_poison) and r['valid']
  self.assertTrue(naive_write);self.assertFalse(r['write_valid'])
 def test_private_drain_independent_of_borrower_ready(self):
  self.assertEqual(loan_edge(True,True,False,True,True,False),(False,True,False,False))
  self.assertEqual(loan_edge(False,True,False,True,True,False),(True,False,False,True))
  self.assertEqual(loan_edge(False,True,True,True,True,True),(True,True,True,False))
if __name__=='__main__':unittest.main()
