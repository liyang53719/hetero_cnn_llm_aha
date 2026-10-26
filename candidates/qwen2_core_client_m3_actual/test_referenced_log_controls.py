"""Pinned prior M3 checker with tiny synthetic logs; never actual log/model.
A synthetic pass cannot establish runtime provenance or raw memory/PV replay.
"""
import argparse,hashlib,importlib.util,sys,unittest,tempfile
from pathlib import Path
PINS={'check_m3_log.py': {'repo_path': 'candidates/qwen2_core_client_m3_build/source/check_m3_log.py', 'sha256': '8ecf9295b0c9659a114d76efe311dc35696b52eacb423364746636dc89f8ae54'}, 'reference_events.py': {'repo_path': 'candidates/qwen2_core_client_m2_build/source/reference_events.py', 'sha256': '919f4bf7013ad46b0a11b3fe08f274403d18204a7f4c38f658c8b56b0a1b30a7'}, 'generate_reference.py': {'repo_path': 'candidates/qwen2_core_client_m3_build/source/generate_reference.py', 'sha256': '997f9380fc34460fb3e50205cd178d1a6c96455f9c4693b7daf507230d02d893'}, 'test_m3_contract.py': {'repo_path': 'candidates/qwen2_core_client_m3_build/source/test_m3_contract.py', 'sha256': '04289d947ede2b2907dc1bbc1bbe4fcb97f3c6dbf5b41646c4871d344c1f16c5'}}
def load(root,destination):
 for name,row in PINS.items():
  p=root/row['repo_path']
  if not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise ValueError('regular pinned source required')
  b=p.read_bytes()
  if hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('frozen source mismatch '+name)
  with (destination/name).open('xb') as f:f.write(b)
 sp=importlib.util.spec_from_file_location('frozen_M3_log_tests',destination/'test_m3_contract.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
class Boundaries(unittest.TestCase):
 def test_synthetic_is_not_execution_or_MAC(self):
  r=f.c.check(f.fixture());self.assertFalse(r['runtime_provenance_verified']);self.assertFalse(r['matrix_numerical_pass']);self.assertFalse(r['full128_rtl_pass']);self.assertIsNone(r['matrix_mac_utilization'])
 def test_passive_assertion_not_raw_packet_replay(self):
  r=f.c.check(f.fixture());self.assertTrue(r['passive_memory_pv_assertions_are_harness_source_bound_not_external_transaction_trace'])
 def test_early_zero_max_rejected(self):
  with self.assertRaises(ValueError):f.c.check(f.fixture().replace(b'max=4286578688 ',b'max=0 ',1))
 def test_nonretire_score_is_diagnostic(self):
  r=f.c.check(f.fixture().replace(b'scoreWrite=false scoreIndex=0 scoreData=0 ',b'scoreWrite=false scoreIndex=0 scoreData=123 '));self.assertFalse(r['runtime_provenance_verified'])
 def test_no_extra_M17_tail(self):
  with self.assertRaises(ValueError):f.c.check(f.fixture()+b'VERILATOR_CORE_DONE case=normal_m17 completed=true\n')
 def test_ordered_prefix_not_interchangeable(self):
  with self.assertRaises(ValueError):f.c.check(f.fixture().replace(b'targetPrefix=0,1,2',b'targetPrefix=0,2,1'))
 def test_third_probability_scalar_only(self):
  from fractions import Fraction
  self.assertEqual(f.r.rational_f32_rne(Fraction(1,3)),0x3eaaaaab);self.assertEqual(f.r.uniform_bf16(3),0x3eab)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2]);v=a.parse_args();sys.dont_write_bytecode=True
 with tempfile.TemporaryDirectory() as tmp:
  f=load(v.repo_root.resolve(),Path(tmp));suite=unittest.TestSuite(f.Contract(n) for n in ['test_good','test_mutations','test_unknown_and_missing','test_zero_port_allowed_scope']);suite.addTests(unittest.TestLoader().loadTestsFromTestCase(Boundaries));r=unittest.TextTestRunner(verbosity=2).run(suite)
 raise SystemExit(0 if r.wasSuccessful() else 1)
