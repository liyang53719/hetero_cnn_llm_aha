import unittest,copy,pathlib,importlib.util
P=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('guard',P/'validate_launch.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class Launch(unittest.TestCase):
 def setUp(self):
  self.sha='a'*40;self.head='b'*40;self.e={'ref':'refs/heads/main','before':self.sha,'after':self.head};self.m={'schema':g.SCHEMA,'source_sha':self.sha,'nonce':g.NONCE};self.diff='A\t'+g.LAUNCH+'\n'
 def check(self,**kw):
  d=dict(event=self.e,manifest=self.m,attempt='1',head=self.head,parent=self.sha,diff=self.diff);d.update(kw);return g.validate(**d)
 def test_exact(self):self.assertEqual(self.check(),self.sha)
 def test_retry(self):
  with self.assertRaises(ValueError):self.check(attempt='2')
 def test_other_branch(self):
  with self.assertRaises(ValueError):self.check(event=dict(self.e,ref='refs/heads/other'))
 def test_stale_parent(self):
  with self.assertRaises(ValueError):self.check(parent='c'*40)
 def test_modified_launch(self):
  with self.assertRaises(ValueError):self.check(diff='M\t'+g.LAUNCH+'\n')
 def test_extra_file(self):
  with self.assertRaises(ValueError):self.check(diff=self.diff+'A\tother\n')
 def test_extra_scope(self):
  with self.assertRaises(ValueError):self.check(manifest=dict(self.m,artifact_name='illegal'))
 def test_schema(self):
  with self.assertRaises(ValueError):self.check(manifest=dict(self.m,schema='BUILD_ARTIFACT'))
 def test_nonce(self):
  with self.assertRaises(ValueError):self.check(manifest=dict(self.m,nonce='old'))
 def test_sha(self):
  with self.assertRaises(ValueError):self.check(manifest=dict(self.m,source_sha='a'*39))
 def test_workflow_scope(self):
  text=(P.parents[1]/'.github/workflows/hetero-public21-downowner-protocol.yml').read_text()
  self.assertNotIn('upload-artifact',text);self.assertNotIn('workflow_dispatch',text);self.assertNotIn('GH_TOKEN',text);self.assertIn('timeout-minutes: 120',text);self.assertIn('timeout-minutes: 110',text);self.assertIn('job_budget_seconds=7200',text);self.assertIn('paths: ['+g.LAUNCH+']',text);self.assertEqual(text.count('actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683'),2)
if __name__=='__main__':unittest.main()
