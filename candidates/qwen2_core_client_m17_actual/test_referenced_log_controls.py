"""Pinned prior M17 checker with tiny synthetic logs; never actual log/model.
A synthetic pass cannot establish runtime provenance or raw memory/PV replay.
"""
import argparse,hashlib,importlib.util,sys,unittest,tempfile
from pathlib import Path
PINS={'check_m17_log.py': {'repo_path': 'candidates/qwen2_core_client_m17_build/source/check_m17_log.py', 'sha256': 'e379a79163c3cf6807861cb46f445b2261ec455d34208f49299ddfc58a810d58'}, 'reference_events.py': {'repo_path': 'candidates/qwen2_core_client_m17_build/source/reference_events.py', 'sha256': 'd3a8c8ffe1b8e6f81955a19f5945cb1c65f6c831630fa7dc23ff724b2182a0af'}, 'generate_reference.py': {'repo_path': 'candidates/qwen2_core_client_m17_build/source/generate_reference.py', 'sha256': '595fa8fc9a5ae11e87a86253ca2a765b1e73821148233239de4805a17231f677'}, 'test_m17_contract.py': {'repo_path': 'candidates/qwen2_core_client_m17_build/source/test_m17_contract.py', 'sha256': '0b28af87de22ee08016524ce63574be5853e535464088da039d57420a94307c2'}}
def load(root,destination):
 for name,row in PINS.items():
  p=root/row['repo_path']
  if not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise ValueError('regular pinned source required')
  b=p.read_bytes()
  if hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('frozen source mismatch '+name)
  with (destination/name).open('xb') as f:f.write(b)
 sp=importlib.util.spec_from_file_location('frozen_M17_log_tests',destination/'test_m17_contract.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
class Boundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.raw=f.fixture()
 def test_synthetic_is_not_execution_or_MAC(self):
  r=f.c.check(self.raw);self.assertFalse(r['runtime_provenance_verified']);self.assertFalse(r['matrix_numerical_pass']);self.assertFalse(r['full128_rtl_pass']);self.assertIsNone(r['matrix_mac_utilization'])
 def test_passive_assertion_not_raw_packet_replay(self):
  self.assertTrue(f.c.check(self.raw)['passive_memory_pv_assertions_are_harness_source_bound_not_external_transaction_trace'])
 def test_tail_selected_is_local_zero(self):
  lines=self.raw.splitlines();i=next(i for i,x in enumerate(lines) if b'keyBase=16' in x);lines[i]=lines[i].replace(b'selected=0',b'selected=16')
  with self.assertRaises(ValueError):f.c.check(b'\n'.join(lines)+b'\n')
 def test_nonretire_score_is_diagnostic(self):
  r=f.c.check(self.raw.replace(b'scoreWrite=false scoreIndex=0 scoreData=0 ',b'scoreWrite=false scoreIndex=0 scoreData=123 '));self.assertFalse(r['runtime_provenance_verified'])
 def test_no_extra_M18_case(self):
  with self.assertRaises(ValueError):f.c.check(self.raw+b'VERILATOR_CORE_DONE case=normal_m18 completed=true\n')
 def test_ordered_prefix_not_interchangeable(self):
  with self.assertRaises(ValueError):f.c.check(self.raw.replace(b'targetPrefix=0,1,2',b'targetPrefix=0,2,1'))
 def test_seventeenth_probability_scalar_only(self):
  from fractions import Fraction
  self.assertEqual(f.r.rational_f32_rne(Fraction(1,17)),0x3d70f0f1);self.assertEqual(f.r.uniform_bf16(17),0x3d71)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2]);v=a.parse_args();sys.dont_write_bytecode=True
 with tempfile.TemporaryDirectory() as tmp:
  f=load(v.repo_root.resolve(),Path(tmp));suite=unittest.TestLoader().loadTestsFromTestCase(f.Log);suite.addTests(unittest.TestLoader().loadTestsFromTestCase(Boundaries));r=unittest.TextTestRunner(verbosity=2).run(suite)
 raise SystemExit(0 if r.wasSuccessful() else 1)
