import argparse,pathlib,sys,tempfile,json,gzip,hashlib,unittest
class Test(unittest.TestCase):
 def test_failed_link_full_error_and_sanitized_admission(self):
  with tempfile.TemporaryDirectory()as d:
   root=pathlib.Path(d);p=root/'frontend/host_link';p.mkdir(parents=True);raw=b'/job/generated.cpp:8: error: io_token_valid missing\n';z=gzip.compress(raw);(p/'frontend.log.gz').write_bytes(z)
   c=dict(raw_sha256=hashlib.sha256(raw).hexdigest(),compressed_sha256=hashlib.sha256(z).hexdigest(),raw_bytes=len(raw),compressed_bytes=len(z),lines=1,error_lines=0,pipe_eof_observed=True,gzip_finalized=True,capture_cap_hit=False)
   (p/'RESULT.json').write_text(json.dumps(dict(native_exit=2,errors=[],elapsed_seconds=1,observed_peak_rss=1,log_capture=c,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'))))
   (root/'frontend/BUILD_ADMISSION_FAILURE.json').write_text(json.dumps(dict(phase='run',exception_class='ValueError',sanitized_error=dict(message='stage failed host_link',raw_message_sha256='a'*64,raw_message_bytes=22))))
   r=m.build_summary(root,'a'*40);data=m.encode_build_summary(r)
   self.assertFalse(r['completed']);self.assertEqual(r['stages'][0]['build_errors']['matched_compiler_link_lines'],1);self.assertNotIn('/job/',data);self.assertIn('host_link',data);self.assertLessEqual(len(data.encode()),65536)
 def test_size_fallback_preserves_failure(self):
  rows=[dict(stage='host_link',native_exit=2,telemetry=dict(supervisor_reason_codes=[],capture_census=dict(error_lines=0,pipe_eof_observed=True)),build_errors=dict(status='VERIFIED_COMPLETE_CAPTURE',samples=[dict(error_text='x'*4000)]*8))for _ in range(5)]
  r=json.loads(m.encode_build_summary(dict(stages=rows,completed=False)));self.assertTrue(r['build_diagnostics_truncated']);self.assertTrue(all(x['native_exit']==2 for x in r['stages']));self.assertFalse(r['completed'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--materialization-dir',type=pathlib.Path,required=True);v,rest=a.parse_known_args();sys.path.insert(0,str(v.materialization_dir.resolve()));import summarize_build_only as m;unittest.main(argv=['test']+rest)
