import copy,importlib.util,json,pathlib,tempfile,time,unittest,sys,hashlib
from unittest.mock import patch
import validate_launch as g
import export_metadata as e
D=pathlib.Path(__file__).resolve().parent
class Guard(unittest.TestCase):
 def setUp(self):
  self.source='a'*40;self.head='b'*40;self.event=dict(ref='refs/heads/main',before=self.source,after=self.head)
  self.manifest=dict(schema='OBSERVER_FIXED4096_FRONTEND_QUALIFICATION_ONE_SHOT_V1',source_sha=self.source,profile='FIXED4096_OBSERVER8_SV_FRONTEND_SINGLE_DRIVER_TU_ONLY',nonce='observer_fixed4096_frontend_make_driver_20261030_once')
 def call(self,m=None,event=None,attempt='1',diff=None,parent=None):return g.validate(event or self.event,m or self.manifest,attempt,self.head,parent or self.source,diff if diff is not None else 'A\t'+g.LAUNCH+'\n')
 def test_positive(self):self.assertEqual(self.call(),self.source)
 def test_attempt_parent_modified_extra(self):
  for kw in (dict(attempt='2'),dict(parent='c'*40),dict(diff='M\t'+g.LAUNCH+'\n'),dict(diff='A\t'+g.LAUNCH+'\nM\tcode.py\n')):
   with self.assertRaises(ValueError):self.call(**kw)
 def test_reject_old_ir_and_numerical_nonces(self):
  for nonce in ('observer_fixed155_original_ir_aggregate_scope_r3_20261030_once','observer_fixed155_original_ir_r2_20261030_once','qwen35_four_m128_freshhost_python_dso_r3_20261030_once','five_m128_samejob_diagnostic_r2_20261030_once'):
   with self.assertRaises(ValueError):self.call(m=dict(self.manifest,nonce=nonce))
   with self.assertRaises(ValueError):self.call(diff='A\tci_launch/'+nonce+'.json\n')
 def test_schema_profile_source(self):
  for k,v in [('profile','NUMERIC'),('schema','old'),('source_sha','not_sha')]:
   with self.assertRaises(ValueError):self.call(m=dict(self.manifest,**{k:v}))
class Budget(unittest.TestCase):
 def test_complete_explicit_accounting(self):
  b=json.loads((D/'BUDGETS.json').read_text());self.assertEqual(len(b['prep_stages']),8);self.assertEqual(len(b['inner_stages']),16)
  for group in ('prep','inner'):
   self.assertEqual(sum(r['wall_seconds']for r in b[group+'_stages']),b[group+'_sum_wall']);self.assertEqual(sum(r['cleanup_seconds']for r in b[group+'_stages']),b[group+'_sum_cleanup'])
  self.assertEqual(b['prep_sum_wall']+b['prep_sum_cleanup'],b['prep_conservative_reservation'])
  self.assertEqual(b['inner_sum_wall']+b['inner_sum_cleanup']+b['inner_metadata_deadline_slack'],b['inner_seconds'])
  self.assertEqual(b['prep_conservative_reservation']+b['inner_seconds']+sum(x['seconds']for x in b['parent_phases']),b['execution_step_seconds'])
  self.assertEqual(b['execution_step_seconds']+sum(x['seconds']for x in b['workflow_other_steps']),b['whole_declared_envelope'])
  self.assertEqual(b['whole_declared_envelope']+b['unallocated_whole_job_slack'],21000);self.assertFalse(b['prep_all_maxima_completion_guaranteed'])
 def test_no_scope_expansion(self):
  s=(D/'prepare_and_run.py').read_text();self.assertIn("bound['job_started_monotonic']=v.job_started_monotonic",s);self.assertIn("bound['whole_job_budget_seconds']=21000",s);self.assertIn('+wall+30<1800',s)
  self.assertNotIn("str(P/'one_job_build_only.py')",s);self.assertIn("str(P/'frontend_qualify_only.py')",s)
  self.assertIn("e['GH_TOKEN']=os.environ['GH_TOKEN']",s);self.assertIn('os.execve(py,command,env)',s)
  for n in ('acquire_archives.py','acquire_resumable.py','numeric_tail.py','install_job.py'):self.assertNotIn(n,s)
 def test_workflow_exact_upload(self):
  w=(D.parents[1]/'.github/workflows/hetero-observer-frontend-qualification.yml').read_text()
  for x in (g.LAUNCH,'timeout-minutes: 350','timeout-minutes: 263','frontend-summary.json','frontend-qualification.json','cancel-in-progress: false'):self.assertIn(x,w)
  self.assertNotIn('observer-frontend-metadata/*',w);self.assertNotIn('continue-on-error',w)
class Export(unittest.TestCase):
 def setUp(self):
  self.identity=dict(run_id=7,artifact_name='hetero-observer-frontend-summary-7',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path=g.LAUNCH,launch_manifest_blob_sha='c'*40)
  self.clock=dict(schema='SAME_JOB_START_V1',job_budget_seconds=21000,started_monotonic=time.monotonic(),run_id=7,launch_commit='b'*40)
 def test_missing_is_unavailable_exact_two_files(self):
  with tempfile.TemporaryDirectory()as t:
   r=pathlib.Path(t);s=e.export(r,r/'work',self.identity,self.clock,r/'out');self.assertEqual(s['status'],'OBSERVATION_UNAVAILABLE');self.assertEqual({p.name for p in (r/'out').iterdir()},{'frontend-summary.json','frontend-qualification.json'});self.assertFalse(s['numerical_pass'])
 def test_failed_saved_stage_is_not_full(self):
  with tempfile.TemporaryDirectory()as t:
   r=pathlib.Path(t);p=r/'work/stage_jdk';p.mkdir(parents=True);(p/'RESULT.json').write_text(json.dumps(dict(native_exit=1,errors=['arbitrary private details not exported'],cleanup_proof={},log_capture={})))
   s=e.export(r,r/'work',self.identity,self.clock,r/'out');self.assertEqual(s['status'],'INCOMPLETE_NO_QUALIFICATION_RECEIPT');self.assertNotIn('private details',json.dumps(s));self.assertFalse(s['stages'][0]['strict_complete'])
 def test_clock_identity_and_symlink_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   r=pathlib.Path(t)
   with self.assertRaises(ValueError):e.export(r,r/'w',self.identity,dict(self.clock,run_id=8),r/'out')
   (r/'real').mkdir();(r/'link').symlink_to(r/'real')
   with self.assertRaises(ValueError):e.export(r,r/'link',self.identity,self.clock,r/'out')
 def test_duplicate_json_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'x';p.write_text('{"x":1,"x":2}')
   with self.assertRaises(ValueError):e.read(p,100)
 def test_no_lost_eof_complete(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'r';p.write_text(json.dumps(dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':False,'gzip_finalized':True})))
   self.assertFalse(e.stage(p,'x')['strict_complete'])
 def test_actual_projector_full_export_synthetic_24_receipts(self):
  # Synthetic only: exercise real producer projector and exact export allowlist.
  pipeline=D.parent/'ci_frontend_pipeline_r2_20261029';sys.path.insert(0,str(pipeline))
  import test_observer_frontend_qualification as fixture
  raw,_=fixture.fixture();raw['artifact_identity']=self.identity;raw['source_commit']=self.identity['source_commit']
  receipt=dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True},elapsed_seconds=1,observed_peak_rss=1024)
  with tempfile.TemporaryDirectory()as t:
   r=pathlib.Path(t);w=r/'work'
   for prefix,names in [('stage_',e.PREP),('frontend/',e.INNER)]:
    for name in names:
     p=w/(prefix+name);p.mkdir(parents=True);(p/'RESULT.json').write_text(json.dumps(receipt))
   (w/'frontend/FRONTEND_QUALIFICATION.json').write_text(json.dumps(raw))
   with patch.object(e,'checker',return_value=fixture.m),patch.object(fixture.m,'GLOBAL_MK_SHA',hashlib.sha256(b'SYNTHETIC_GLOBAL_MAKE_TEST_ONLY\n').hexdigest()):
    s=e.export(r,w,self.identity,self.clock,r/'out');self.assertEqual(s['status'],'FRONTEND_QUALIFICATION_OBSERVED_UNREVIEWED')
    self.assertEqual(len(s['stages']),24);self.assertFalse(s['sv_accepted']);self.assertFalse(s['numerical_pass'])
    self.assertLess(sum(p.stat().st_size for p in (r/'out').iterdir()),e.CAP)
    # A complete raw metadata document cannot hide one failed native receipt.
    bad=dict(receipt,native_exit=1);(w/'frontend/driver_tu_only/RESULT.json').write_text(json.dumps(bad))
    s=e.export(r,w,self.identity,self.clock,r/'out_reject');self.assertEqual(s['status'],'METADATA_REJECTED')
 def test_pinned_projector_import(self):
  m=e.checker(D.parents[1]);self.assertTrue(callable(m.project_qualification))
if __name__=='__main__':unittest.main()
