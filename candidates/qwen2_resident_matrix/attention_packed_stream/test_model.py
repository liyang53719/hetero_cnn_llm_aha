import unittest
from .model import Client,Result
class Tests(unittest.TestCase):
 def begin(self,pv=False,count=16):
  c=Client(enabled=True);self.assertTrue(c.tick(start=(7,pv,count))['start_fire'])
  self.assertTrue(c.tick(group_ready=True)['group_fire']);return c
 def finish(self,c):
  tile=Result(payload=object())
  for _ in range(4):
   o=c.tick(result=tile);self.assertTrue(o['result_valid']);self.assertIs(o['result'],tile);self.assertFalse(o['result_fire'])
  self.assertTrue(c.tick(result=tile,result_ready=True)['result_fire'])
  self.assertTrue(c.tick(done=(7,False))['done_fire'])
  self.assertEqual(c.tick()['completion'],(7,False));c.tick(completion_ready=True);self.assertEqual(c.state,'idle')
 def test_default_off_quiet(self):
  c=Client()
  for _ in range(4):
   o=c.tick(start=(7,False,16),operand=0,group_ready=True,step_ready=True,abort=True)
   self.assertFalse(any(v for k,v in o.items() if k.endswith(('_fire','_valid','_ready'))));self.assertEqual(c.state,'idle')
 def test_qk_eight_final_only_and_input_stalls(self):
  c=self.begin()
  for i in range(8):
   held=c.tick(operand=i);self.assertFalse(held['step_fire']);self.assertEqual(c.index,i)
   o=c.tick(operand=i,step_ready=True);self.assertTrue(o['step_fire']);self.assertEqual(o['step'],(i,0,i==0,i==7,i==7,i==7))
  self.finish(c);self.assertEqual(c.counts,dict(groups=1,steps=8,results=1,done=1,completion=1))
 def test_pv_key16_pause_same_group(self):
  c=self.begin(True,17)
  for i in range(16):c.tick(operand=i,step_ready=True)
  for _ in range(3):self.assertFalse(c.tick(operand=16,pause=True,service_drained=False,step_ready=True)['pause_granted'])
  for _ in range(7):
   o=c.tick(operand=16,pause=True,service_drained=True,step_ready=True)
   self.assertTrue(o['pause_granted']);self.assertFalse(o['step_fire']);self.assertEqual((c.tag,c.index,c.counts['groups']),(7,16,1))
  self.assertEqual(c.tick(operand=16,step_ready=True)['step'],(16,0,False,True,True,True));self.finish(c)
 def test_pv_128(self):
  c=self.begin(True,128)
  for i in range(128):self.assertTrue(c.tick(operand=i,step_ready=True)['step_fire'])
  self.finish(c);self.assertEqual(c.counts['steps'],128)
 def test_bad_count_no_service_group(self):
  for pv,count in ((False,0),(False,17),(True,0),(True,129)):
   c=Client(enabled=True);c.tick(start=(7,pv,count));self.assertEqual(c.state,'reply');self.assertTrue(c.poison);self.assertEqual(c.counts['groups'],0)
 def test_index_fault_drains_group(self):
  c=self.begin();o=c.tick(operand=2,step_ready=True)
  self.assertTrue(o['operand_fire']);self.assertFalse(o['step_fire']);self.assertEqual(c.state,'draining')
  self.assertTrue(c.tick(done=(7,True))['done_fire']);self.assertTrue(c.tick()['completion'][1])
 def test_abort_opening_no_group_debt(self):
  c=Client(enabled=True);c.tick(start=(7,False,1));o=c.tick(abort=True,group_ready=True)
  self.assertFalse(o['group_fire']);self.assertEqual(c.state,'reply');self.assertTrue(c.poison)
 def test_abort_held_result_suppresses_publication(self):
  c=self.begin(True,1);c.tick(operand=0,step_ready=True);tile=Result(payload=object())
  o=c.tick(result=tile,result_ready=True,abort=True);self.assertFalse(o['result_valid']);self.assertFalse(o['result_fire'])
  self.assertTrue(c.tick(result=tile)['result_fire']);self.assertTrue(c.tick(done=(7,True))['done_fire'])
  c.tick(completion_ready=True);self.assertEqual(c.state,'locked')
 def test_abort_done_same_edge_no_lost_debt(self):
  c=self.begin(True,1);c.tick(operand=0,step_ready=True);c.tick(result=Result(),result_ready=True)
  self.assertTrue(c.tick(done=(7,False),abort=True)['done_fire']);self.assertEqual(c.state,'reply');self.assertTrue(c.poison)
 def test_foreign_done_does_not_retire(self):
  c=self.begin();o=c.tick(done=(8,True));self.assertFalse(o['done_fire']);self.assertEqual(c.state,'draining')
  for _ in range(3):self.assertFalse(c.tick(done=(8,True))['done_fire'])
  self.assertTrue(c.tick(done=(7,True))['done_fire']);self.assertTrue(c.poison)
 def test_bad_result_not_exposed(self):
  for r in (Result(context=1),Result(last=False),Result(error=True)):
   c=self.begin(True,1);c.tick(operand=0,step_ready=True);o=c.tick(result=r,result_ready=True)
   self.assertFalse(o['result_valid']);self.assertTrue(o['result_fire']);self.assertTrue(c.poison)
 def test_early_result_blocks_new_step(self):
  c=self.begin();o=c.tick(operand=0,step_ready=True,result=Result())
  self.assertFalse(o['step_fire']);self.assertEqual(c.state,'draining')
 def reply(self):
  c=self.begin(True,1);c.tick(operand=0,step_ready=True);c.tick(result=Result(),result_ready=True);c.tick(done=(7,False));return c
 def test_abort_held_completion_upgrades_error(self):
  c=self.reply();self.assertEqual(c.tick()['completion'],(7,False))
  o=c.tick(abort=True);self.assertEqual(o['completion'],(7,True));self.assertFalse(o['success_accepted'])
  self.assertEqual(c.tick()['completion'],(7,True));o=c.tick(completion_ready=True)
  self.assertFalse(o['success_accepted']);self.assertEqual(c.state,'locked')
 def test_abort_completion_ack_priority(self):
  c=self.reply();o=c.tick(abort=True,completion_ready=True)
  self.assertTrue(o['completion_fire']);self.assertEqual(o['completion'],(7,True))
  self.assertFalse(o['success_accepted']);self.assertEqual(c.state,'locked')
 def test_adversarial_done_and_result_preserves_consumed_done(self):
  c=self.begin(True,1);c.tick(operand=0,step_ready=True);c.tick(result=Result(),result_ready=True)
  o=c.tick(done=(7,False),result=Result());self.assertTrue(o['done_fire']);self.assertEqual(c.state,'reply')
  self.assertEqual(c.counts['done'],1);self.assertTrue(c.tick()['completion'][1])
if __name__=='__main__':unittest.main()
