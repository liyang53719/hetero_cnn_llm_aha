"""Source-only R2 integration checks. No compiler, models, downloads or DUT run."""
import ast, hashlib, importlib.util, json, pathlib, unittest
D=pathlib.Path(__file__).resolve().parent;R=D.parent.parent;N=D/'numeric';M=R/'candidates/ci_frontend_materialization_r2_20261029';P=R/'candidates/ci_frontend_pipeline_r2_20261029'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class SourceIntegration(unittest.TestCase):
 def test_closure(self):
  rows=json.loads((D/'SOURCE_PINS.json').read_text())['files'];self.assertEqual(len(rows),len({r['path'] for r in rows}))
  for r in rows:self.assertEqual(((R/r['path']).stat().st_size,sha(R/r['path'])),(r['bytes'],r['sha256']))
 def test_shared155(self):
  m=module('observer_fixed_sources',M/'fixed_sources.py');original=json.loads((R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text());paths=m.checked_paths(R,M/'FIXED_SOURCE_OVERLAY_R2.json',original)
  self.assertEqual(len(paths),155);self.assertEqual(len({pathlib.Path(p).name for p in paths}),155)
 def test_tampered_selection_rejected(self):
  m=module('observer_fixed_sources_negative',M/'fixed_sources.py')
  with self.assertRaises(ValueError):m.validate_overlay((M/'FIXED_SOURCE_OVERLAY_R2.json').read_bytes()+b' ',{})
 def test_reference_real_path(self):
  self.assertIn('independent_block_reference_prepare_v3_20261028T2312',(D/'runtime/reference_job.py').read_text())
  self.assertEqual(sha(R/'candidates/independent_block_reference_prepare_v3_20261028T2312/run_reference.py'),'d4f779881ebea182c747064fa159da7379fc45802232f04d04c013fe3d0aabd2')
 def test_connection_pins(self):
  for p,h in json.loads((N/'CONNECTION_OWNED_SOURCE_PINS.json').read_text()).items():self.assertEqual(sha(N/p),h)
 def test_owned_p0_contract(self):
  c=module('observer_p0_corrector',N/'correct_observation_policy.py');c.contract()
  old=json.loads((R/'candidates/same_job_materialization_20261029/consumer/LOCKED_SOURCE_CONTRACT.json').read_text());new=json.loads((N/'LOCKED_SOURCE_CONTRACT.json').read_text())
  self.assertEqual({k for k in old['sources'] if old['sources'][k]!=new['sources'][k]},{'host_top','host_commands','owner_kernel','resident','bridge','driver'})
  self.assertIn("actual_observation='UNOBSERVED'",(N/'correct_observation_policy.py').read_text())
 def test_producer_pins(self):
  d=module('observer_dependency_proof',N/'driver_dependency_proof.py');self.assertEqual((N/'driver_dependency_proof.py').read_bytes(),(P/'driver_dependency_proof.py').read_bytes())
  for name,h in d.PRODUCER_IMPLEMENTATION_PINS.items():self.assertEqual(h,sha(P/name))
  self.assertIn(sha(N/'driver_dependency_proof.py'),(N/'consumption_proof.py').read_text());self.assertIn(sha(N/'consumption_proof.py'),(N/'observation_contract.py').read_text());self.assertIn(sha(N/'observation_contract.py'),(N/'consumer_owned.py').read_text())
 def test_headers_actual_dependency(self):
  d=module('observer_dependency_negative',N/'driver_dependency_proof.py');driver='/owned/driver/host_axi_driver_non_dpi.cpp';known={str(pathlib.Path(driver).parent/n):h for n,h in d.OBSERVER_HEADER_PINS.items()};d.verify_observer_dependencies(list(known),driver,known)
  cases=[([],known),(list(known)+[next(iter(known))],known),(list(known),{k:'0'*64 for k in known}),(['/else/'+pathlib.Path(k).name for k in known],known)]
  for paths,pins in cases:
   with self.assertRaises(ValueError):d.verify_observer_dependencies(paths,driver,pins)
if __name__=='__main__':unittest.main()
