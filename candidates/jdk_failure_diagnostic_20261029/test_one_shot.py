import unittest
from validate_one_shot_launch import validate,LAUNCH
class T(unittest.TestCase):
 def setUp(self):
  self.s='1'*40;self.h='2'*40;self.e={'ref':'refs/heads/main','before':self.s,'after':self.h,'head_commit':{'id':self.h}};self.m={'schema':'JDK_DIAGNOSTIC_ONE_SHOT_V1','source_sha':self.s,'profile':'JDK_PREFLIGHT_DIAGNOSTIC_ONLY','nonce':'jdk_diagnostic_20261029_once'}
 def test_actions_payload_omits_changed_file_arrays(self):self.assertEqual(validate(self.e,self.m,'1',self.h,self.s,'A\t'+LAUNCH+'\n'),self.s)
 def test_modify_or_extra_file_rejected(self):
  for d in ['M\t'+LAUNCH+'\n','A\t'+LAUNCH+'\nM\tx\n']:
   with self.assertRaises(ValueError):validate(self.e,self.m,'1',self.h,self.s,d)
 def test_wrong_parent_and_rerun(self):
  for attempt,parent in [('2',self.s),('1','3'*40)]:
   with self.assertRaises(ValueError):validate(self.e,self.m,attempt,self.h,parent,'A\t'+LAUNCH+'\n')
if __name__=='__main__':unittest.main()
