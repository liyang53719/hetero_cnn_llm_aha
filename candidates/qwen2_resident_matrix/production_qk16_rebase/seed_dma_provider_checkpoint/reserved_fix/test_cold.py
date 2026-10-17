import hashlib,json,unittest
from pathlib import Path
from model import audit,boundary
P=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_all(self):self.assertEqual(audit()['combinations'],65536)
 def test_exact_delta(self):
  pins=json.loads((P/'SOURCE_PINS.json').read_text());key=next(x for x in pins if x.endswith('.sv'));old=(P.parent/key).read_text();new=(P/'source/rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv').read_text()
  self.assertEqual(hashlib.sha256(old.encode()).hexdigest(),pins[key])
  for name in ['seed_beat_ready_o','seed_commit_ready_o']:
   a=f'assign {name}=reserved_q&&!ack_valid_q&&!poison_q&&!seed_abort_i&&begin_quiescent;';self.assertEqual(new.count(a),1);new=new.replace(a,a.replace('&&begin_quiescent;','&&quiescent;'))
  self.assertEqual(new,old)
 def test_early(self):
  bits=(False,True,True,True,True,True,False,False,False,False,True,True,True,True);v=boundary(bits,32,True);self.assertFalse(v['beat_ready']);self.assertFalse(v['commit_ready']);self.assertTrue(v['fault'])
 def test_busy_still_fault(self):
  bits=(False,False,False,False,False,False,True,False,False,False,True,True,True,True);self.assertTrue(boundary(bits,0,True)['fault'])
 def test_simultaneous_valid_illegal(self):
  bits=(True,True,True,True,True,True,True,False,False,False,True,True,True,True);v=boundary(bits,32,True);self.assertTrue(v['fault']);self.assertFalse(v['write']);self.assertFalse(v['commit'])
 def test_abort_blocks(self):
  bits=(False,True,True,True,True,True,True,False,False,True,True,True,True,True);v=boundary(bits,32,True);self.assertFalse(v['beat_ready']);self.assertFalse(v['commit_ready']);self.assertFalse(v['issue'])
 def test_ack_hold(self):
  bits=(False,True,False,True,True,True,True,True,False,False,True,True,True,True);v=boundary(bits,0,True);self.assertTrue(v['ack_valid']);self.assertTrue(v['hold']);self.assertFalse(v['write'])
 def test_negative_control(self):
  bits=(False,False,False,True,True,True,True,False,False,False,True,True,True,True);self.assertNotEqual(boundary(bits,0,False,True),boundary(bits,0,True,True))
if __name__=='__main__':unittest.main()
