import argparse,copy,hashlib,importlib.util,json,pathlib,shutil,tempfile,unittest
P=pathlib.Path;D=P(__file__).resolve().parent
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);c=self.root/'candidates/same_job_execution_20261030';c.mkdir(parents=True);shutil.copyfile(D/'summarize_same_job.py',c/'summarize_same_job.py');m=self.root/'candidates/ci_frontend_materialization_r2_20261029';m.mkdir();shutil.copyfile(REPO/'candidates/ci_frontend_materialization_r2_20261029/frontend_telemetry.py',m/'frontend_telemetry.py');s=importlib.util.spec_from_file_location('newsummary',c/'summarize_same_job.py');self.m=importlib.util.module_from_spec(s);s.loader.exec_module(self.m)
 def test_exact_two_known_reasons_and_resources(self):
  r=dict(errors=['ValueError: sampled aggregate writable-root cap']*2,peak_tree_bytes=12081306273,peak_file_bytes=1<<30,process_sample_count=3,process_sample_max_gap_seconds=8.5,caps=dict(watch_tree_bytes=12081306272,file_bytes=2<<30,per_process_cpu_seconds=180,per_process_as_bytes=4<<30),cleanup_proof=None,log_capture=None)
  v=self.m.stage_resources(r);self.assertEqual(v['supervisor_reason_codes'],['AGGREGATE_DISK_CAP']*2);self.assertEqual(v['peak_tree_bytes'],12081306273);self.assertEqual(v['caps']['file_bytes'],2<<30);self.assertEqual(v['cleanup_status'],'NOT_PROVEN');self.assertEqual(len(v['error_evidence']),2)
 def test_unknown_secret_and_path_not_echoed(self):
  r=dict(errors=['ValueError: Authorization Bearer fake-secret /private/file'],caps={});v=self.m.stage_resources(r);s=json.dumps(v);self.assertNotIn('fake-secret',s);self.assertNotIn('/private',s);self.assertEqual(v['supervisor_reason_codes'],['UNCLASSIFIED_SUPERVISOR_ERROR']);self.assertEqual(v['error_evidence'][0]['sha256'],hashlib.sha256(r['errors'][0].encode()).hexdigest())
 def test_null_actual_shapes(self):
  v=self.m.stage_resources(dict(errors=None,caps=None,cleanup_proof=None,log_capture=None));self.assertEqual(v['error_evidence'],[]);self.assertFalse(v['worker_started'])
 def test_bounded_errors_and_nonfinite(self):
  v=self.m.stage_resources(dict(errors=['ValueError: wall cap']*100,peak_tree_bytes=float('nan'),caps={'file_bytes':float('inf')}));self.assertTrue(v['errors_truncated']);self.assertEqual(len(v['error_evidence']),32);self.assertNotIn('peak_tree_bytes',v);self.assertNotIn('file_bytes',v['caps'])
 def test_summary_stage_integration(self):
  work=self.root/'work';p=work/'materials/runs/qwen35_35b';p.mkdir(parents=True);(p/'RESULT.json').write_text(json.dumps(dict(native_exit=None,errors=['ValueError: file cap'],caps={'file_bytes':2<<30},peak_file_bytes=(2<<30)+1,worker_started=True,cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})));v=self.m.summarize(work,{});self.assertEqual(v['stages'][0]['resources']['supervisor_reason_codes'],['FILE_CAP']);self.assertFalse(v['numeric_pass'])
 def test_size_fallback_keeps_real_nested_build_telemetry(self):
  telemetry=self.m.stage_resources(dict(errors=['ValueError: sampled aggregate writable-root cap']*2,peak_tree_bytes=12081306273,caps={'watch_tree_bytes':12081306272},cleanup_proof=None,log_capture=None))
  v=dict(build={'stages':[dict(stage='x',native_exit=None,error_count=2,telemetry=telemetry,diagnostics={'samples':['x'*70000]})]},stages=[])
  r=json.loads(self.m.encode(v));actual=r['build']['stages'][0]['telemetry']
  self.assertEqual(actual['supervisor_reason_codes'],['AGGREGATE_DISK_CAP']*2);self.assertEqual(actual['caps']['watch_tree_bytes'],12081306272);self.assertEqual(actual['peak_tree_bytes'],12081306273);self.assertEqual(actual['cleanup_status'],'NOT_PROVEN');self.assertLess(len(self.m.encode(r).encode()),65536)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=P,required=True);a,rest=p.parse_known_args();REPO=a.repo.resolve();unittest.main(argv=[__file__,*rest])
