import pathlib,unittest
import flow
D=pathlib.Path(__file__).resolve().parent
class T(unittest.TestCase):
 def test_explicit_policies(self):
  for name,limit,rss,addr in [('archives',512<<20,256<<20,1<<30),('weights',4<<30,512<<20,1<<30),('reference',160<<20,3<<30,8<<30)]:
   p=flow.stage_policy(name,1800);self.assertEqual((p['output_bytes'],p['rss_bytes'],p['as_bytes']),(limit,rss,addr))
  self.assertEqual(flow.stage_policy('reference',1800)['cpu_seconds'],1200)
 def test_unknown_policy(self):
  with self.assertRaises(ValueError):flow.stage_policy('generic',120)
 def test_actual_output_under_stage(self):
  s=(D/'flow.py').read_text();self.assertIn("archives=job/'runs/archives/output'",s);self.assertIn("payload=job/'runs/weights/output'",s);self.assertIn("tree_bytes=policy['output_bytes']",s)
  r=(D.parent/'runtime/reference_job.py').read_text();self.assertIn("dest=home/'actual/reference'",r);self.assertIn("output_root=home/'actual',resource_profile='reference'",r)
 def test_setup_deadlines_include_cleanup(self):
  s=(D/'bootstrap_samejob.py').read_text();self.assertIn("+wall+30<=v.maximum_build_seconds",s);self.assertIn("+wall+30+v.remaining_tail_reserve_seconds<21000",s)
if __name__=='__main__':unittest.main()
