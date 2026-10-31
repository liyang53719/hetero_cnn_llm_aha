"""Light source/mock qualification only, no Java or SV generation."""
import ast,copy,hashlib,json,os,pathlib,tempfile,unittest,sys
import contract as c
from validate_launch import validate,LAUNCH
R=pathlib.Path(os.environ.get('SV_ONLY_TEST_REPO',str(c.D.parents[1]))).resolve()
class ContractTests(unittest.TestCase):
 def test_budget(self):
  b=c.read(c.D/'BUDGETS.json');self.assertEqual(len(c.STAGES),15);self.assertEqual(sum(x[1]for x in c.STAGES),6360);self.assertEqual(6360+450+900+1320,9030);self.assertEqual(10800-9030,1770);self.assertLessEqual(max(x[2]for x in c.STAGES),6);self.assertEqual(b['internal_execution_seconds'],7710);self.assertEqual(b['execution_step_seconds'],129*60);self.assertEqual(b['execution_step_seconds']+1320,9060);self.assertEqual(b['declared_envelope_seconds'],9060);self.assertEqual(b['reserve_seconds'],1740)
 def test_unique_launch(self):
  m=dict(schema='OBSERVER_FIXED4096_SV_ONLY_DIFFERENCE_ONE_SHOT_V1',source_sha='a'*40,profile='FIXED4096_OLD_NEW_SV_ONLY_TWO_MODULE_DIFFERENCE',nonce='observer_fixed4096_sv_only_difference_20261031_scanfix_once');e=dict(before='a'*40,after='b'*40,ref='refs/heads/main')
  self.assertEqual(validate(e,m,'1','b'*40,'a'*40,'A\t'+LAUNCH+'\n'),'a'*40)
  with self.assertRaises(ValueError):validate(e,dict(m,nonce='observer_fixed4096_sv_only_difference_20261030_once'),'1','b'*40,'a'*40,'A\t'+LAUNCH+'\n')
  for args in [('2','b'*40,'a'*40,'A\t'+LAUNCH+'\n'),('1','b'*40,'c'*40,'A\t'+LAUNCH+'\n'),('1','b'*40,'a'*40,'M\t'+LAUNCH+'\n')]:
   with self.assertRaises(ValueError):validate(e,m,*args)
 def test_identity(self):
  x=dict(run_id=1,artifact_name='hetero-observer-sv-only-summary-1',source_commit='a'*40,launch_commit='b'*40,launch_manifest_blob_sha='c'*40,launch_manifest_path=LAUNCH);self.assertEqual(c.validate_identity(x),x)
  for key,value in [('run_id',True),('artifact_name','other'),('source_commit','b'*40),('launch_manifest_path','ci_launch/other.json')]:
   with self.assertRaises(ValueError):c.validate_identity(dict(x,**{key:value}))
 def test_old_new_source_exact(self):
  original=c.read(R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json')
  paths={s:c.source_paths(R,s,original)for s in ('old','new')};self.assertEqual(len(paths['old']),155);self.assertEqual(sum(a!=b for a,b in zip(paths['old'],paths['new'])),8)
 def test_duplicate_json(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'x';p.write_text('{"a":1,"a":2}')
   with self.assertRaises(ValueError):c.read(p)
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'x';p.write_text('{}');q=p.with_name('link');q.symlink_to(p)
   with self.assertRaises(ValueError):c.read(q)
 def test_output_create_new(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'x';c.write(p,{})
   with self.assertRaises(FileExistsError):c.write(p,{})
 def test_strict_receipt(self):
  r=dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture=dict(pipe_eof_observed=True,gzip_finalized=True));self.assertTrue(c.completed(r))
  missing=dict(r);missing.pop('errors');self.assertFalse(c.completed(missing))
  for k,v in [('native_exit',1),('errors',['bad']),('cleanup_proof',{}),('log_capture',{})]:self.assertFalse(c.completed(dict(r,**{k:v})))
 def test_helpers_old_pinned(self):
  plan=c.read(c.D/'INPUT_PLAN.json')
  for x in plan['helper_delta']:
   self.assertEqual(c.sha(c.D/'old_helpers'/x['name']),x['old_sha256']);self.assertEqual(c.sha(R/'candidates/ci_frontend_pipeline_r2_20261029'/x['name']),x['new_sha256'])
 def test_full_closure(self):self.assertGreaterEqual(len(c.closure(R)),644)
 def test_native_unresolved_and_injection(self):
  sys.path.insert(0,str(R/'candidates/ci_frontend_materialization_r2_20261029'));import fresh_host as f
  with self.assertRaises(ValueError):f.reject_injection({'LD_PRELOAD':'evil'})
  with self.assertRaises(ValueError):f.dependency_paths('libbad.so => not found\n')
 def test_alias_drift(self):
  sys.path.insert(0,str(R/'candidates/ci_frontend_pipeline_r2_20261029'));import supervise_multiroot as s
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t);(p/'a').write_text('a');(p/'b').write_text('b');(p/'link').symlink_to(p/'a');row=dict(path=str(p/'link'),link=str(p/'a'),target=str(p/'a'));s.verify_aliases([row]);(p/'link').unlink();(p/'link').symlink_to(p/'b')
   with self.assertRaises(ValueError):s.verify_aliases([row])
 def test_source_ast_no_heavy(self):
  for p in c.D.glob('*.py'):ast.parse(p.read_text())
  text=(c.D/'prepare_and_run.py').read_text();self.assertNotIn("stage('verilator'",text);self.assertNotIn("stage('matrix'",text);self.assertNotIn("stage('idma'",text);self.assertIn('DiagnoseOriginalHostMoePhaseV5',text);self.assertIn("'--materialization'",text)
 def test_stage_export_caps_and_telemetry(self):
  import export_metadata as e
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'RESULT.json';r=dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture=dict(pipe_eof_observed=True,gzip_finalized=True),caps=dict(wall_seconds=300,cleanup_seconds=30,rss_bytes=1<<30,max_entries=100000),elapsed_seconds=1.5,observed_peak_rss=50000)
   p.write_text(json.dumps(r));self.assertTrue(e.stage_row('jdk',p)['strict_complete'])
   for key,value in [('elapsed_seconds',float('nan')),('observed_peak_rss',True)]:
    p.write_text(json.dumps(dict(r,**{key:value})))
    with self.assertRaises(ValueError):e.stage_row('jdk',p)
   bad=copy.deepcopy(r);bad['caps']['rss_bytes']=2<<30;p.write_text(json.dumps(bad))
   with self.assertRaises(ValueError):e.stage_row('jdk',p)
 def test_source_closure_change_rejected(self):
  # Exact old/new hashes are immutable; no repin from generated metadata.
  self.assertEqual(c.NORMALIZED['old'],'6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5')
  self.assertEqual(c.NORMALIZED['new'],'ec70f91181b0422ca7cf2bc845a2a1f04c9d862f4f27d265c5a064a969058d72')
  self.assertEqual(c.CANONICAL['new'],'00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c')
 def test_runtime_projection_binding(self):
  import export_metadata as e
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);(d/'bin').mkdir();java=d/'bin/java';java.write_bytes(b'SYNTHETIC_NO_EXECUTION');h=c.sha(java)
   identity=dict(run_id=1,source_commit='a'*40,launch_commit='b'*40)
   r=dict(schema='SV_ONLY_JDK_PYTHON_IDENTITY_V1',old_pass_transfer=False,scope='IDENTITY_ONLY_NO_RUNTIME_CPU_OR_NUMERICAL_QUALIFICATION',contract=dict(schema='BOUNDED_FRESH_HOST_V1',**identity),pins={str(java):h},jdk=dict(status='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION',old_pass_transfer=False,version=dict(JAVA_VERSION='21.0.13',IMPLEMENTOR='Eclipse Adoptium',JAVA_RUNTIME_VERSION='21.0.13+9'),actual_runtime_properties={'java.vendor':'Eclipse Adoptium','java.runtime.version':'21.0.13+9','os.arch':'amd64'},files=[dict(path='bin/java',sha256=h)]))
   p=d/'runtime.json';p.write_text(json.dumps(r));out=e.project_runtime(p,c.sha(p),identity);self.assertEqual(out['java_sha256'],h);self.assertNotIn('pins',out)
   with self.assertRaises(ValueError):e.project_runtime(p,'0'*64,identity)
   with self.assertRaises(ValueError):e.project_runtime(p,c.sha(p),dict(identity,run_id=2))
   java.write_bytes(b'DRIFT')
   with self.assertRaises(ValueError):e.project_runtime(p,c.sha(p),identity)
if __name__=='__main__':unittest.main()
