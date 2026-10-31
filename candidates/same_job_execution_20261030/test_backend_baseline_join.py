"""Reviewed observation-baseline production join source checks; no compiler, reference or DUT execution."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,unittest,sys
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent;R=D.parents[1];P=R/'candidates/ci_frontend_pipeline_r2_20261029';M=R/'candidates/ci_frontend_materialization_r2_20261029'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class Tests(unittest.TestCase):
 def test_actual_ports_and_historical85(self):
  old=load(P/'HOST_PORTS.json');new=load(P/'OBSERVER_HOST_PORTS_122.json');self.assertEqual(len(old),85);self.assertEqual(len(new),122)
  self.assertTrue(all(new[k]==v for k,v in old.items()));extra={k:v for k,v in new.items()if k not in old};self.assertTrue(all(v[0]=='output' for v in extra.values()));self.assertEqual(sum(v[1] for v in extra.values()),948)
 def test_history_preserved(self):
  self.assertEqual(sha(M/'fixed-canonical-baseline.tsv'),'90464ff45917c1b853c7d1b36e67dd5e43b5503b7fa0583704ee615c08919533');self.assertEqual(sha(M/'C7_MODULE_FINGERPRINTS.json'),'0d80da62c042b5da4f2879525d4660df957579a169295a5844deb0d953f2067a')
 def test_actual_canonical(self):
  f=R/'candidates/observer_ir_only_20261030/evidence/run41114764250/observed-canonical.tsv';self.assertEqual(sha(f),'00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c');self.assertIn(str(f.relative_to(R)),(D/'controller/bootstrap_samejob.py').read_text())
 def test_real_module_observation_pending(self):
  x=load(M/'OBSERVER_MODULE_FINGERPRINTS_PENDING.json');self.assertEqual(len(x['modules']),92);self.assertEqual(x['normalized_sha256'],'ec70f91181b0422ca7cf2bc845a2a1f04c9d862f4f27d265c5a064a969058d72');self.assertEqual(x['source_run_id'],41118989254)
 def test_actual_proof_review_limited_acceptance(self):
  g=module('accepted_observer_gate',P/'observer_baseline_gate.py');d=g.require_accepted_baseline(M)
  self.assertTrue(d['ready']);self.assertFalse(d['numerical_pass']);self.assertFalse(d['final_rtl_pass'])
  self.assertEqual(g.ACCEPTED_PROOF_SHA256,'f88769ed00ab2dd052752e6ade9cf67f37f7c6f9d4ede64723e5441ca609835c')
 def test_missing_actual_evidence_rejected(self):
  g=module('missing_evidence_gate',P/'observer_baseline_gate.py')
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);(p/'OBSERVER_BASELINE_ACCEPTANCE.json').write_bytes((M/'OBSERVER_BASELINE_ACCEPTANCE.json').read_bytes())
   with self.assertRaisesRegex(ValueError,'actual evidence source pin'):g.require_accepted_baseline(p)
 def test_removed_review_still_not_ready(self):
  g=module('missing_review_gate',P/'observer_baseline_gate.py')
  with patch.object(g,'ACCEPTED_REVIEW_SHA256',None):
   with self.assertRaisesRegex(ValueError,'NOT_READY'):g.require_accepted_baseline(M)
 def test_json_ready_cannot_authorize(self):
  g=module('pending_observer_gate2',P/'observer_baseline_gate.py')
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);x=load(M/'OBSERVER_BASELINE_ACCEPTANCE.json');x['ready']=True;(p/'OBSERVER_BASELINE_ACCEPTANCE.json').write_text(json.dumps(x))
   with self.assertRaisesRegex(ValueError,'source pin'):g.require_accepted_baseline(p)
 def test_gate_before_build_and_admission(self):
  for path,func in [(P/'one_job_build_only.py','main'),(P/'conditional_admission.py','admit_build'),(M/'materialize_frontend_binding.py','main')]:
   tree=ast.parse(path.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==func);calls=[n for n in ast.walk(node)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_accepted_baseline'];self.assertEqual(len(calls),1)
 def test_exact_122_field_both_ends(self):
  for p in [P/'build_producer.py',P/'conditional_admission.py']:
   s=p.read_text();self.assertIn('header_122_observation_ports_and_driver_ABI_reviewed',s);self.assertNotIn('header_85_ports_and_driver_ABI_reviewed',s)
 def test_full5_requires_next_host(self):
  s=(R/'.github/workflows/hetero-five-m128-samejob-calibration-local-data.yml').read_text();self.assertIn('--execution-policy FULL_FIVE_ORIGINAL_HOST_POLICY',s);self.assertIn('--fresh-host-profile',s);self.assertIn('avx512f',(D/'runtime/runtime_phase.py').read_text())
 def test_no_activation(self):self.assertFalse((R/'ci_launch/five_m128_observer_backend_freshhost_20261030_once.json').exists())
 def test_unchanged_resource_mode(self):
  self.assertEqual(load(D/'BUDGETS.json')['calibration_seconds'],{str(i):300 for i in range(5)});self.assertIn('BOUNDED_CALIBRATION',(D/'controller/flow.py').read_text())
 def test_actual_outer_entry_precedes_all_work(self):
  # No valid binding or stage callback is supplied: pending must be the first decision.
  sys.path.insert(0,str(P))
  original_read=pathlib.Path.read_bytes
  def missing_baseline(path):
   return b'{}'if path.name=='OBSERVER_BASELINE_ACCEPTANCE.json'else original_read(path)
  for name,path,fn,args in [('prepare',D/'prepare_and_run.py','run',(object(),)),('flow',D/'controller/flow.py','run',({},None,None)),('bootstrap',D/'controller/bootstrap_samejob.py','main',()),('buildprepare',P/'build_producer.py','prepare',({},)),('buildrun',P/'build_producer.py','run',({},None)),('conditionalprepare',P/'conditional_binary_producer.py','prepare',({},)),('conditionalrun',P/'conditional_binary_producer.py','run',({},None)),('conditionaladmit',P/'conditional_binary_producer.py','admit_build',({},None,None,None,None))]:
   with self.subTest(entry=name),patch.object(pathlib.Path,'read_bytes',missing_baseline),patch('subprocess.run',side_effect=AssertionError('must not execute subprocess')),patch('subprocess.check_output',side_effect=AssertionError('must not inspect/acquire tool')):
    m=module('pending_'+name,path)
    with self.assertRaisesRegex(ValueError,'observer baseline source pin'):getattr(m,fn)(*args)
if __name__=='__main__':unittest.main()
