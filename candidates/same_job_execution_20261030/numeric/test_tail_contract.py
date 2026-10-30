import ast,json,pathlib,time,unittest
import numeric_tail as n
class T(unittest.TestCase):
 def binding(self):
  return dict(schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,upload_payloads=False,final_rtl_replay=False,references={str(i):{}for i in range(5)},calibration_seconds={str(i):100 for i in range(5)},job_started_monotonic=time.monotonic(),reserved_material_seconds=7*120+1320,reserved_cleanup_seconds=1530,reserved_parent_seconds=120,tree_cap=12081306272,rss_bytes=1<<30,address_space_bytes=12<<30,phase_extra_bytes=1<<20,provider_wall_seconds=120)
 def test_complete_round(self):n.validate(self.binding())
 def test_not_5x20k(self):
  b=self.binding();b['calibration_seconds']={str(i):20000 for i in range(5)}
  with self.assertRaises(ValueError):n.validate(b)
 def test_no_smallhardware(self):
  b=self.binding();b['matrix_macs']=512
  with self.assertRaises(ValueError):n.validate(b)
 def test_no_missing_profile(self):
  b=self.binding();b['profiles']=list(range(4))
  with self.assertRaises(ValueError):n.validate(b)
 def test_phase_no_session(self):
  tree=ast.parse(pathlib.Path(n.__file__).with_name('locked_phase.py').read_text())
  calls=[x.func.attr for x in ast.walk(tree)if isinstance(x,ast.Call)and isinstance(x.func,ast.Attribute)]
  self.assertNotIn('setsid',calls);self.assertNotIn('Popen',calls);self.assertIn('execve',calls)
if __name__=='__main__':unittest.main()
