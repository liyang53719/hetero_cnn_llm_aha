"""Synthetic/source-only candidate safeguards; never build, emit, or execute DUT."""
import ast,copy,hashlib,importlib.util,json,pathlib,sys,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(D));sys.path.insert(0,str(D.parent/'ci_frontend_pipeline_r2_20261029'))
import candidate_generation_gate as gate
import candidate_diagnostic as diag
import validate_model_launch as launch
from candidate_observation import STAGES

def source(name):return (D/name).read_text()
class Contract(unittest.TestCase):
 def test_generation_requires_frozen_independent_contract(self):
  old=gate.GENERATION_CONTRACT_SHA256
  try:
   gate.GENERATION_CONTRACT_SHA256=None
   with self.assertRaises(ValueError):gate.load_contract(D/'GENERATION_CONTRACT.json','0'*64)
  finally:gate.GENERATION_CONTRACT_SHA256=old
 def test_real_overlay_selection_only(self):
  repo=D.parents[1];original=json.loads((repo/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text());contract=json.loads((D/'GENERATION_CONTRACT.json').read_text())
  rows=gate.checked_paths(repo,(D/'MODEL_SOURCE_OVERLAY.json').resolve(),original,contract);self.assertEqual(len(rows),159);self.assertEqual(len(set(rows)),159)
 def test_overlay_hash_drift_refused(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'overlay.json';p.write_text('{}')
   with self.assertRaises(ValueError):gate.checked_paths(D.parents[1],p,{'sources':[]},{'source_overlay_sha256':'0'*64})
 def test_fresh_single_A_only(self):
  sha='a'*40;head='b'*40;m={'schema':launch.SCHEMA,'nonce':launch.NONCE,'source_sha':sha,'transfer_approval_sha256':launch.ACCEPTED_TRANSFER_APPROVAL_SHA256};e={'ref':'refs/heads/main','before':sha,'after':head}
  self.assertEqual(launch.validate(e,m,'1',head,sha,'A\t'+launch.LAUNCH+'\n'),sha)
  for attempt,diff,parent in [('2','A\t'+launch.LAUNCH+'\n',sha),('1','M\t'+launch.LAUNCH+'\n',sha),('1','A\t'+launch.LAUNCH+'\n'+'A\tx\n',sha),('1','A\t'+launch.LAUNCH+'\n','c'*40)]:
   with self.assertRaises(ValueError):launch.validate(e,m,attempt,head,parent,diff)
 def test_stage_scope(self):
  self.assertEqual(len(STAGES),20);self.assertEqual(STAGES[0],'compile_model_sources');self.assertEqual(STAGES[-1],'host_link');self.assertNotIn('compile155',STAGES)
  s=source('one_job_model_candidate.py');self.assertNotIn('require_accepted_baseline',s);self.assertNotIn('ec70f911',s);self.assertNotIn('00897fd4',s)
  self.assertIn("require_generation_binding(b)",s);self.assertIn("stage('original_high'",s)
 def test_original_build_budget_and_cpu_policy(self):
  s=source('prepare_model_build.py');self.assertIn('BUILD_SECONDS=7200',s);self.assertIn('WHOLE_SECONDS=9000',s);self.assertIn('EXPORT_RESERVE_SECONDS=900',s)
  job=source('one_job_model_candidate.py');self.assertIn("job_budget=b.get('job_budget_seconds')",job);self.assertIn('0<job_budget<=7200',job)
  bootstrap=source('bootstrap_model_candidate.py');self.assertNotIn('21000',bootstrap);self.assertIn("<9000,'whole build-only deadline reserves export'",bootstrap)
  s=source('candidate_build_producer.py');self.assertIn("CPP_POLICY='CPP_O1_STRICT_V1'",s);self.assertIn("'CXXFLAGS=-O1 -fno-fast-math -ffp-contract=off'",s)
  self.assertNotIn("schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'",s)
 def test_original_single_pass_bytes(self):
  self.assertEqual(hashlib.sha256((D/'sv_inventory_single_pass.py').read_bytes()).hexdigest(),'685b15b4f9bee8d23ac25ffc7d26aa718d55621e5fe1b9b2f3519669f24768d4')
 def test_parse_all_published_python(self):
  for p in D.glob('*.py'):ast.parse(p.read_text(),filename=p.name)
class Diagnostics(unittest.TestCase):
 def row(self):return dict(schema='MODEL_CANDIDATE_DIAGNOSTIC_V1',stage='emit_host',status='REJECTED_UNREVIEWED',reason_code='DENSE_ACC_LOCAL_SHAPE',actual={'module_count':1060,'high_sha256':'a'*64},numerical_pass=False,post_build_structure_accepted=False)
 def test_exact_safe_diagnostic(self):self.assertEqual(diag.project(self.row(),'emit_host'),self.row())
 def test_raw_payload_and_acceptance_refused(self):
  for f in [lambda d:d.update(raw='secret'),lambda d:d['actual'].update(path='/private/secret'),lambda d:d.update(numerical_pass=True),lambda d:d.update(reason_code='secret value'),lambda d:d['actual'].update(module_count=True),lambda d:d['actual'].update(high_sha256='0'*63)]:
   d=self.row();f(d)
   with self.assertRaises(ValueError):diag.project(d,'emit_host')
 def test_missing_failure_receipt_safe_unavailable(self):
  with tempfile.TemporaryDirectory()as t:
   r=json.loads(diag.read_projection(pathlib.Path(t)/'absent','emit_host'));self.assertEqual(r['schema'],'MODEL_CANDIDATE_DIAGNOSTIC_UNAVAILABLE_V1');self.assertFalse(r['numerical_pass'])
if __name__=='__main__':unittest.main()
