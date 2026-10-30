import ast, importlib.util,json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[2];M=ROOT/'candidates/ci_frontend_materialization_r2_20261029';sys.path.insert(0,str(M))
import fresh_host as h
import inventory_runner_jdk as j
C=dict(schema='BOUNDED_FRESH_HOST_V1',run_id=42,source_commit='a'*40,launch_commit='b'*40)
E=dict(GITHUB_RUN_ID='42',GITHUB_SHA='b'*40,GITHUB_RUN_ATTEMPT='1',ImageVersion='20261025.353.1')
class Tests(unittest.TestCase):
 def test_contract_new_image_identity_only(self):self.assertEqual(h.validate_contract(C,C,E),C)
 def test_wrong_source(self):
  with self.assertRaises(ValueError):h.validate_contract(C,{**C,'source_commit':'c'*40},E)
 def test_retry_denied(self):
  with self.assertRaises(ValueError):h.validate_contract(C,C,{**E,'GITHUB_RUN_ATTEMPT':'2'})
 def test_unknown_field(self):
  with self.assertRaises(ValueError):h.validate_contract({**C,'cpu_policy':'fallback'},C,E)
 def test_wrong_launch(self):
  with self.assertRaises(ValueError):h.validate_contract(C,C,{**E,'GITHUB_SHA':'c'*40})
 def test_missing_dependency(self):
  with self.assertRaises(ValueError):h.dependency_paths('libjvm.so => not found\n')
 def test_dependency_root(self):
  with self.assertRaises(ValueError):h.dependency_paths('libx.so => /tmp/untrusted/libx.so (0xff)')
 def test_concrete_loader(self):self.assertEqual(h.dependency_paths('/lib64/ld-linux-x86-64.so.2 (0xff)'),['/lib64/ld-linux-x86-64.so.2'])
 def test_injection(self):
  for k in h.INJECTION:
   with self.subTest(k=k),self.assertRaises(ValueError):h.reject_injection({k:'/tmp/injected'})
 def test_legacy_jdk_image_gate(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,E,clear=True):
   pathlib.Path(d,'release').write_text('JAVA_VERSION="21.0.13"\nJAVA_RUNTIME_VERSION="21.0.13+9"\nIMPLEMENTOR="Eclipse Adoptium"\nOS_ARCH="x86_64"\n')
   with self.assertRaises(j.InventoryFailure) as got:j.inventory(d)
   self.assertEqual(got.exception.code,'RUNNER_IMAGE_MISMATCH')
 def test_fresh_jdk_vendor_not_waived(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,E,clear=True):
   pathlib.Path(d,'release').write_text('JAVA_VERSION="21.0.13"\nJAVA_RUNTIME_VERSION="21.0.13+9"\nIMPLEMENTOR="OTHER"\nOS_ARCH="x86_64"\n')
   with self.assertRaises(j.InventoryFailure) as got:j.inventory(d,C)
   self.assertEqual(got.exception.code,'JDK_RELEASE_IDENTITY_MISMATCH')
 def test_contract_hash_drift(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,E,clear=True):
   p=pathlib.Path(d,'contract.json');p.write_text(json.dumps(C));digest=h.sha(p);self.assertEqual(h.load_contract(p,digest,C),C);p.write_text('{}')
   with self.assertRaises(ValueError):h.load_contract(p,digest,C)
 def test_source_wiring(self):
  b=(ROOT/'candidates/same_job_execution_20261030/controller/bootstrap_samejob.py').read_text()
  self.assertLess(b.index("stage('fresh_host'"),b.index("os.execve(py,command,env)"));self.assertIn("if fresh is None:stage('compile_tools'",b)
  self.assertIn("bound['pins'].update(host['pins'])",b);self.assertNotIn("bound['compile_aliases'].update(host['aliases'])",b)
  flow=(ROOT/'candidates/same_job_execution_20261030/controller/flow.py').read_text();self.assertIn("profile_policy.require_cpu(b,P('/proc/cpuinfo').read_text().split())",flow);self.assertIn('matrix_macs\']==4096',flow)
  build=(ROOT/'candidates/ci_frontend_pipeline_r2_20261029/one_job_build_only.py').read_text();self.assertIn("b.get('fresh_host_aliases',{})",build);self.assertIn("stage('sv_identity'",build)
 def test_all_candidates_parse_without_execution(self):
  for p in (ROOT/'candidates').rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
 def test_integrated_profile_cpu_contract(self):
  p=ROOT/'candidates/same_job_execution_20261030/profile_policy.py';spec=importlib.util.spec_from_file_location('tested_cpu_policy',p);policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
  with self.assertRaisesRegex(ValueError,'AVX512'):policy.require_cpu({},[])
  policy.require_cpu({'execution_policy':policy.policy(policy.DEFER)},[])
  self.assertEqual(policy.policy(policy.DEFER)['cpu_avx512_observation'],'NOT_ASSERTED_BY_SELECTION')
if __name__=='__main__':unittest.main()
