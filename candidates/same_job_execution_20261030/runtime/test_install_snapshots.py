import importlib.util,json,pathlib,tempfile,time,unittest
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
def module(name):
 path=D/(name+'.py')
 if not path.is_file()and name=='summarize_same_job':path=D.parent/(name+'.py') # published runtime/test vs parent summary
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
i=module('install_job');s=module('summarize_same_job')
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.work=P(self.tmp.name).resolve();self.root=self.work/'materials';(self.root/'results').mkdir(parents=True);self.b=dict(lock=str(self.work/'lock'),owned_roots=[str(self.work)],install_wall_seconds=180,metadata_wall_seconds=120,remaining_job_reservation_seconds=100,job_started_monotonic=time.monotonic());self.sample=dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,roots=['/PRIVATE/not-exported'],bytes=123,files=3,entries=5,free_bytes=10**10,symlinks_not_followed=1,started_monotonic=10.,finished_monotonic=11.,elapsed_seconds=1.)
 def tearDown(self):self.tmp.cleanup()
 def snap(self,when='before',fn=None,native=None):return i.snapshot(self.root,'qwen35_35b',when,self.b,fn or (lambda *a,**kw:self.sample),1,native)
 def good(self):return dict(cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture=dict(pipe_eof_observed=True,gzip_finalized=True))
 def test_complete_safe_fields(self):
  self.snap();r=s.install_snapshots(self.work)[0];self.assertEqual(r['bytes'],123);self.assertEqual(r['free_bytes'],10**10);self.assertEqual(r['symlinks_not_followed'],1);self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(r['scope'],'WHOLE_JOB_AND_REPO_INODE_DEDUPLICATED')
 def test_failed_native_cleanup_complete_still_observes(self):
  r=self.good();r.update(native_exit=None,errors=['original failure']);out=self.snap('after',native=r);self.assertEqual(out['status'],'COMPLETE');self.assertEqual(out['observation'],'AFTER_CLEANUP_NOT_FAILURE_INSTANT')
 def test_cleanup_none_never_scans(self):
  def no(*a,**kw):raise AssertionError('must not census')
  r=self.snap('after',fn=no,native=dict(cleanup_proof=None));self.assertEqual(r['reason'],'CLEANUP_OR_EOF_UNPROVEN');self.assertNotIn('bytes',r)
 def test_missing_native_never_scans(self):
  self.assertEqual(self.snap('after')['status'],'UNAVAILABLE')
 def test_entry_cap_no_false_zero(self):
  def bad(*a,**kw):raise ValueError('entry census cap')
  r=self.snap(fn=bad);self.assertEqual(r['reason'],'CENSUS_ENTRY_CAP');self.assertNotIn('bytes',r);self.assertEqual(s.install_snapshots(self.work)[0]['status'],'UNAVAILABLE')
 def test_timeout(self):
  def bad(*a,**kw):raise ValueError('census deadline')
  self.assertEqual(self.snap(fn=bad)['reason'],'CENSUS_DEADLINE')
 def test_exception_private_path_not_exported(self):
  def bad(*a,**kw):raise OSError('/PRIVATE/secret')
  r=self.snap(fn=bad);self.assertEqual(r['reason'],'CENSUS_UNAVAILABLE');self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(len(r['error_sha256']),64)
 def test_over_limit_observation_not_admission_pass(self):
  self.sample['bytes']=12_081_306_273;r=self.snap();self.assertEqual(r['bytes'],12_081_306_273);self.assertEqual(r['resource_peak_qualification'],'INCOMPLETE_SAMPLED');self.assertFalse('PASS'in json.dumps(r))
 def test_deadline_slack_preserves_native_reservation(self):
  self.b['job_started_monotonic']=time.monotonic()-20900;self.assertEqual(self.snap()['reason'],'NO_UNRESERVED_DEADLINE_SLACK')
 def test_lock_busy(self):
  with open(self.b['lock'],'a+b')as f:
   i.fcntl.flock(f,i.fcntl.LOCK_EX|i.fcntl.LOCK_NB);self.assertEqual(self.snap()['reason'],'OWNERSHIP_LOCK_BUSY')
 def test_missing_field_invalid_preserves_summary(self):
  self.snap();p=self.root/'results/install_qwen35_35b_before_RESOURCE.json';r=json.loads(p.read_text());del r['free_bytes'];p.write_text(json.dumps(r));v=s.summarize(self.work,{});self.assertEqual(v['installation_resource_snapshots'][0]['status'],'INVALID_FIELDS');self.assertEqual(v['stages'],[]);self.assertFalse(v['numeric_pass'])
 def test_bool_count_invalid(self):
  self.sample['entries']=True;self.assertEqual(self.snap()['status'],'UNAVAILABLE')
 def test_summary_time_nan_rejected(self):
  self.snap();p=self.root/'results/install_qwen35_35b_before_RESOURCE.json';r=json.loads(p.read_text());r['elapsed_seconds']=float('nan');p.write_text(json.dumps(r));self.assertEqual(s.install_snapshots(self.work)[0]['status'],'INVALID_FIELDS')
 def test_huge_integer_snapshot_preserves_stage(self):
  self.snap();p=self.root/'results/install_qwen35_35b_before_RESOURCE.json';r=json.loads(p.read_text());r['bytes']=10**400;p.write_text(json.dumps(r));self.assertLess(p.stat().st_size,4096)
  stage=self.work/'runs/archives';stage.mkdir(parents=True);(stage/'RESULT.json').write_text(json.dumps(dict(native_exit=0,errors=[],cleanup_proof=None,log_capture=None)))
  with patch.object(s,'stage_resources',return_value={'fixture_original_stage':True}):v=s.summarize(self.work,{})
  self.assertEqual(v['installation_resource_snapshots'][0]['status'],'INVALID_FIELDS');self.assertEqual(len(v['stages']),1);self.assertEqual(v['stages'][0]['phase'],'archive');self.assertEqual(v['stages'][0]['native_exit'],0);self.assertLessEqual(len(s.encode(v).encode()),65536)
 def test_snapshot_bound(self):
  p=self.root/'results/install_qwen35_35b_before_RESOURCE.json';p.write_text('x'*4097);self.assertEqual(s.install_snapshots(self.work)[0]['status'],'INVALID_FIELDS')
 def test_summary_fallback_keeps_snapshot_fields(self):
  self.snap();v=s.summarize(self.work,{});v['build']={'stages':[dict(stage='host',telemetry={'supervisor_reason_codes':['OTHER']},diagnostics='x'*70000)]};r=json.loads(s.encode(v));self.assertEqual(r['installation_resource_snapshots'][0]['free_bytes'],10**10);self.assertLessEqual(len(s.encode(r).encode()),65536)
 def test_wiring_unchanged_execute_call_and_finally(self):
  t=(D/'install_job.py').read_text();self.assertIn('finally:\n   snapshot(root,k,\'after\'',t);self.assertIn("snapshot(root,k,'before'",t);self.assertIn("min_available_memory':4<<30,'min_disk_free':8<<30",t)
if __name__=='__main__':unittest.main()
