import ast,pathlib,unittest
import flow
D=pathlib.Path(__file__).resolve().parent
class T(unittest.TestCase):
 def binding(self):return {'budgets':dict(archives=600,weights=2400,install=120,owner_bind=120,reference=120,provider=120,build=7200,parent=600,calibration_seconds={str(i):300 for i in range(5)})}
 def test_all_five_bounded_calibration_plan(self):
  m,t,total=flow.reservations(self.binding());self.assertEqual(total,m+t+7200);self.assertLessEqual(total,21000)
 def test_no_5x20000(self):
  b=self.binding();b['budgets']['calibration_seconds']={str(i):20000 for i in range(5)}
  with self.assertRaises(ValueError):flow.reservations(b)
 def test_missing_profile(self):
  b=self.binding();b['budgets']['calibration_seconds'].pop('4')
  with self.assertRaises(ValueError):flow.reservations(b)
 def test_original_build_not_modified_or_nested(self):
  text=(D/'flow.py').read_text();self.assertIn("mod('actual_five_diagnostics'",text);self.assertIn("reference.run(rb,stage)",text);self.assertIn('bootstrap_samejob.py',text)
  tree=ast.parse(text)
  for n in ast.walk(tree):
   if isinstance(n,ast.Call):self.assertFalse(any(x.arg=='start_new_session' for x in n.keywords))
 def test_inherited_whole_job_clock(self):
  text=(D/'bootstrap_samejob.py').read_text();self.assertIn('v.job_started_monotonic',text);self.assertIn('v.remaining_tail_reserve_seconds',text);self.assertIn("bound['materialized_roots'].append",text)
if __name__=='__main__':unittest.main()
