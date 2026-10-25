"""Pinned existing checker + tiny synthetic logs only; no actual log or model.
These controls never establish runtime provenance or hardware acceptance.
"""
import argparse,hashlib,importlib.util,sys,unittest
from pathlib import Path
PINS={
 'check_m1_log.py':'2c6ccffb45308745e73372a31904606f8fc1b9ef97589753369bc7b0e4814f09',
 'generate_abi.py':'396bda736a78adb7cf4dab18342a4149d77934ba0fde26b2bfbff92cd5ea9ab8',
 'test_source_contract.py':'c1db395d0f899e0c0e7c1ec2ce7dae8c3343b1d9387bf012a279a206a8c4e123',
}
def load_frozen(root):
 source=root/'candidates/qwen2_core_client_codegen/source'
 for name,want in PINS.items():
  p=source/name
  if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=want:raise ValueError('frozen source mismatch '+name)
 spec=importlib.util.spec_from_file_location('frozen_original_log_synthetic_tests',source/'test_source_contract.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class DiagnosticBoundaries(unittest.TestCase):
 def test_negative_infinity_is_width_only_diagnostic(self):
  r=f.c.check(f.synthetic().replace(b'max=0 ',b'max=4286578688 '));self.assertFalse(r['runtime_provenance_verified']);self.assertFalse(r['matrix_numerical_pass'])
 def test_other_max_word_not_numeric_acceptance(self):
  r=f.c.check(f.synthetic().replace(b'max=0 ',b'max=2139095040 '));self.assertIsNone(r['matrix_mac_utilization'])
 def test_nonretire_score_is_diagnostic_only(self):
  r=f.c.check(f.synthetic().replace(b'scoreWrite=false scoreIndex=0 scoreData=0 ',b'scoreWrite=false scoreIndex=0 scoreData=123 '));self.assertFalse(r['full128_rtl_pass'])
 def test_four_hold_ports_synthetic_not_actual(self):
  raw=f.synthetic().replace(b'requestHoldChecks=1 ',b'requestHoldChecks=4 ').replace(b'(group,0),(memory,1),(pv,0),(step,0)',b'(group,1),(memory,1),(pv,1),(step,1)');r=f.c.check(raw);self.assertEqual(r['covered_request_hold_ports'],['group','memory','pv','step']);self.assertEqual(r['uncovered_request_hold_ports'],[]);self.assertFalse(r['runtime_provenance_verified'])
 def test_max_width_violation_rejected(self):
  with self.assertRaises(ValueError):f.c.check(f.synthetic().replace(b'max=0 ',b'max=4294967296 '))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2]);args=ap.parse_args();sys.dont_write_bytecode=True;f=load_frozen(args.repo_root.resolve());loader=unittest.TestLoader();suite=unittest.TestSuite([loader.loadTestsFromTestCase(f.EventContract),loader.loadTestsFromTestCase(DiagnosticBoundaries)]);r=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(0 if r.wasSuccessful() else 1)
