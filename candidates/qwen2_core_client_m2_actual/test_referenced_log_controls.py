"""Pinned prior M2 checker with tiny synthetic logs; never actual log/model.
A synthetic pass cannot establish runtime provenance or raw memory/PV replay.
"""
import argparse,hashlib,importlib.util,sys,unittest
from pathlib import Path
PINS={'check_m2_log.py':'d875cabd39804dc35e9468b3d06eb8733246e9de404a87cbdd2f23b0b7daae6f','reference_events.py':'919f4bf7013ad46b0a11b3fe08f274403d18204a7f4c38f658c8b56b0a1b30a7','generate_reference.py':'9fe6c961e25661a1352568446b86b8c364b214229e7e93224c21b581d72dab5f','test_m2_contract.py':'924057e5923a37bff7cc6f2472b977c8f326c9c34f773a0c37bb982104abda89'}
def load(root):
 source=root/'candidates/qwen2_core_client_m2_build/source'
 for name,want in PINS.items():
  p=source/name
  if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=want:raise ValueError('frozen source mismatch '+name)
 sp=importlib.util.spec_from_file_location('frozen_M2_log_tests',source/'test_m2_contract.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
class Boundaries(unittest.TestCase):
 def test_synthetic_is_not_execution_or_MAC(self):
  r=f.c.check(f.fixture());self.assertFalse(r['runtime_provenance_verified']);self.assertFalse(r['matrix_numerical_pass']);self.assertFalse(r['full128_rtl_pass']);self.assertIsNone(r['matrix_mac_utilization'])
 def test_passive_assertion_not_raw_packet_replay(self):
  r=f.c.check(f.fixture());self.assertTrue(r['passive_memory_pv_assertions_are_harness_source_bound_not_external_transaction_trace'])
 def test_early_zero_max_rejected(self):
  with self.assertRaises(ValueError):f.c.check(f.fixture().replace(b'max=4286578688 ',b'max=0 ',1))
 def test_nonretire_score_is_diagnostic(self):
  r=f.c.check(f.fixture().replace(b'scoreWrite=false scoreIndex=0 scoreData=0 ',b'scoreWrite=false scoreIndex=0 scoreData=123 '));self.assertFalse(r['runtime_provenance_verified'])
 def test_no_extra_M3_tail(self):
  with self.assertRaises(ValueError):f.c.check(f.fixture()+b'VERILATOR_CORE_DONE case=normal_m3 completed=true\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2]);v=a.parse_args();sys.dont_write_bytecode=True;f=load(v.repo_root.resolve());suite=unittest.TestSuite(f.Contract(n) for n in ['test_good','test_mutations','test_unknown_and_missing','test_zero_port_allowed_scope']);suite.addTests(unittest.TestLoader().loadTestsFromTestCase(Boundaries));r=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(0 if r.wasSuccessful() else 1)
