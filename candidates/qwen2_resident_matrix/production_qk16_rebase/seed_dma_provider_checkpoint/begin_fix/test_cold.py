import unittest
from model import audit,solve
class Cold(unittest.TestCase):
 def test_exhaustive(self):self.assertEqual(audit()['two_leaf_mask_combinations'],3072)
 def test_same_edge_seed_priority(self):
  r=solve(2,True,False,3,3,3,3,0)[0];self.assertEqual(r['accepted'],[True,True]);self.assertEqual(r['issue'],[False,False])
 def test_partial_selected(self):self.assertEqual(solve(2,True,False,1,1,1,3,0)[0]['accepted'],[True,False])
 def test_one_selected_not_quiet(self):self.assertEqual(solve(2,True,False,3,3,1,3,0)[0]['accepted'],[False,False])
 def test_abort_poison_or_held_ack_admission_block(self):
  for split in [False,True]:self.assertFalse(any(solve(2,True,False,3,0,3,3,3,split)[0]['accepted']))
 def test_held_backpressure(self):
  for _ in range(127):self.assertFalse(any(solve(2,True,False,3,3,0,3,0,True)[0]['accepted']))
 def test_ready_only_difference(self):
  old=solve(1,False,True,1,1,1,1,0)[0];new=solve(1,False,True,1,1,1,1,0,True)[0];self.assertFalse(old['ready'][0]);self.assertTrue(new['ready'][0]);self.assertEqual(old['issue'],new['issue'])
class SourceCold(unittest.TestCase):
 def test_source_protections(self):
  from pathlib import Path
  p=Path(__file__).resolve().parent/'source/rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv';s=p.read_text()
  self.assertIn('!input_write_o&&!pre_write_o&&!mul_write_o&&!post_write_o&&!output_write_o;',s)
  self.assertIn('seed_begin_valid_i&&!quiescent',s);self.assertIn('reserved_q&&!quiescent',s)
  self.assertIn('seed_begin_valid_i||seed_beat_valid_i||seed_commit_valid_i',s)
  self.assertIn('assign seed_hold_o=reserved_q||ack_valid_q;',s)
 def test_exact_statement_delta(self):
  from pathlib import Path
  import json,hashlib,re
  p=Path(__file__).resolve().parent;pins=json.loads((p/'SOURCE_PINS.json').read_text());n=next(n for n in pins if n.endswith('bf16_context_front_control5_rev8b_b_candidate.sv'));old=(p.parent/n).read_text();new=(p/'source/rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv').read_text()
  self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),pins[n])
  new=new.replace('quiescent,begin_quiescent,','quiescent,').replace('&&begin_quiescent;','&&quiescent;')
  new=re.sub(r'    // BEGIN valid already.*?    assign identity_matches=', '    assign identity_matches=',new,flags=re.S)
  self.assertEqual(old,new)
if __name__=='__main__':unittest.main()
