import unittest,tempfile,pathlib,json,hashlib
from frontend_telemetry import typed_metrics,native_options,output_inventory,PREFIXES
class Tests(unittest.TestCase):
 def test_typed_errors_metrics_no_private_text(self):
  r={'observed_cpu_seconds':319.44,'errors':['InterruptedError: signal 14','ValueError: sampled observed aggregate RSS cap','ValueError: input pin mismatch /private/token'],'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'raw_bytes':90476672,'raw_sha256':'a'*64,'warning_histogram':{'WIDTHEXPAND':215780},'pipe_eof_observed':False}}
  v=typed_metrics(r);self.assertEqual(v['supervisor_reason_codes'],['SUPERVISOR_ALARM_SIGNAL_14','RSS_CAP','INPUT_PIN_DRIFT']);self.assertEqual(v['capture_census']['warning_histogram'],{'WIDTHEXPAND':215780});self.assertNotIn('/private',json.dumps(v));self.assertEqual(v['observed_cpu_seconds'],319.44)
 def test_malformed_and_nonfinite(self):
  v=typed_metrics({'observed_cpu_seconds':float('nan'),'caps':[],'errors':{},'log_capture':[]});self.assertNotIn('observed_cpu_seconds',v)
 def test_native_options_keep_semantics_not_paths(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/(PREFIXES[2]+'__hierMkArgs.f');data=b'--cc --top-module TransposedDenseDownOwner --output-split 2048 --output-split-cfuncs 256 +incdir+/private/path /private/a.sv\n';p.write_bytes(data);v=native_options(d)[0];self.assertEqual(v['args_sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(v['options']['--output-split'],[2048]);self.assertFalse(v['options']['--exe']);self.assertNotIn('/private',json.dumps(v))
 def test_inventory_complete_and_symlink_refusal(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'A.cpp').write_text('synthetic only');r=output_inventory(p);self.assertEqual(r['files'],1);self.assertTrue(r['status'].startswith('COMPLETE'));self.assertEqual(r['largest_files'][0]['sha256'],hashlib.sha256(b'synthetic only').hexdigest());(p/'link').symlink_to(p/'A.cpp');self.assertTrue(output_inventory(p)['status'].startswith('INCOMPLETE'))
 def test_summary_fallback_keeps_failure_cpu_eof(self):
  from summarize_frontend import encode_summary
  x={'stages':[{'stage':'frontend','native_exit':None,'error_count':1,'compiler_errors':['x'*100000],'telemetry':{'observed_cpu_seconds':319.44,'supervisor_cpu_seconds':99,'supervisor_reason_codes':['SUPERVISOR_ALARM_SIGNAL_14'],'cleanup_status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','capture_census':{'raw_bytes':90476672,'pipe_eof_observed':False,'gzip_finalized':True,'capture_cap_hit':False}}}]}
  raw=encode_summary(x);v=json.loads(raw);self.assertLessEqual(len(raw.encode()),65536);self.assertTrue(v['summary_truncation']);r=v['stages'][0];self.assertEqual(r['native_exit'],None);self.assertEqual(r['telemetry']['observed_cpu_seconds'],319.44);self.assertFalse(r['telemetry']['capture_census']['pipe_eof_observed']);self.assertEqual(r['telemetry']['supervisor_reason_codes'],['SUPERVISOR_ALARM_SIGNAL_14'])
 def test_native_repeated_flags_bounded(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/(PREFIXES[2]+'__hierMkArgs.f');p.write_text('--threads 1 '*10000+'--top-module A '*10000);v=native_options(d)[0];self.assertEqual(len(v['options']['--threads']),8);self.assertEqual(len(v['options']['--top-module']),8);self.assertEqual(set(v['truncated_option_lists']),{'--threads','--top-module'});self.assertLess(len(json.dumps(v)),4096)
if __name__=='__main__':unittest.main()
