import copy,importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
s=importlib.util.spec_from_file_location('summary',D/'summarize_same_job.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.work=P(self.tmp.name);(self.work/'build').mkdir();self.identity=dict(run_id=123,source_commit='a'*40,launch_commit='b'*40)
 def put(self,name,value):
  p=self.work/'build'/name;p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(value));return p
 def host(self):return dict(schema='BOUNDED_FRESH_HOST_IDENTITY_V1',contract=dict(schema='BOUNDED_FRESH_HOST_V1',**self.identity),qualification='IDENTITY_ONLY_PENDING_ORIGINAL_BUILD_AND_NUMERICAL_GATES',old_pass_transfer=False,pins={'/SECRET/tool':'c'*64},elf_dependencies=['SECRET'],environment={'SECRET':'SECRET'})
 def parent(self):return dict(schema='FRESH_HOST_PARENT_FAILURE_V1',status='FAILED',numeric_pass=False,phase='GNU_RUNTIME_ADMISSION',reason='GNU_RUNTIME_DEPENDENCIES_UNQUALIFIED')
 def native(self):return dict(schema='FRESH_HOST_NATIVE_FAILURE_V1',status='FAILED',numeric_pass=False,phase='BOUNDED_HOST_INVENTORY',reason='QUERY_TIMEOUT')
 def get(self):return m.fresh_host_projection(self.work,self.identity)
 def test_missing_unobserved(self):
  r=self.get();self.assertFalse(r['host_qualified']);self.assertFalse(r['numeric_pass'])
  for k in ('stage','identity','parent_failure','native_failure'):self.assertEqual(r[k]['state'],'UNOBSERVED_NOT_QUALIFIED')
 def test_identity_safe_projection(self):
  p=self.put('fresh-host.json',self.host());r=self.get()['identity'];self.assertEqual(r,dict(state='OBSERVED_IDENTITY_ONLY_NOT_QUALIFIED',receipt_sha256=m.sha(p),contract_identity_matches=True,pin_count=1));self.assertNotIn('SECRET',json.dumps(self.get()))
 def test_identity_tampering(self):
  for key,val in [('schema','wrong'),('qualification','PASS'),('old_pass_transfer',True),('pins',{}),('pins',{'/a':'notahash'})]:
   r=self.host();r[key]=val;self.put('fresh-host.json',r);self.assertEqual(self.get()['identity']['state'],'INVALID_NOT_QUALIFIED')
  for key,val in [('run_id',True),('run_id',124),('source_commit','b'*40),('launch_commit','d'*40),('schema','wrong')]:
   r=self.host();r['contract'][key]=val;self.put('fresh-host.json',r);self.assertEqual(self.get()['identity']['state'],'INVALID_NOT_QUALIFIED')
 def test_pin_count_cap(self):
  r=self.host();r['pins']={str(i):'c'*64 for i in range(10001)};self.put('fresh-host.json',r);self.assertEqual(self.get()['identity']['state'],'INVALID_NOT_QUALIFIED')
 def test_failure_exact_pairs_and_safe_fields(self):
  for phase,reason in [('GNU_RUNTIME_ADMISSION','GNU_RUNTIME_DEPENDENCIES_UNQUALIFIED'),('BOOTSTRAP_ALIAS','RUNTIME_ALIAS_REJECTED'),('HOST_RECEIPT_ADMISSION','FRESH_HOST_RECEIPT_REJECTED')]:
   r=self.parent();r.update(phase=phase,reason=reason,exception='SECRET');self.put('FRESH_HOST_PARENT_FAILURE.json',r);out=self.get();self.assertEqual(out['parent_failure']['reason'],reason);self.assertNotIn('SECRET',json.dumps(out))
  for reason in ('UNCLASSIFIED_EXCEPTION','ELF_DEPENDENCY_UNRESOLVED','ELF_DEPENDENCY_ROOT_REJECTED','SEARCH_PATH_INJECTION_REJECTED','CONTRACT_REJECTED','JDK_QUERY_ROOT_REJECTED','QUERY_TIMEOUT','QUERY_FAILED','FILESYSTEM_UNAVAILABLE'):
   r=self.native();r['reason']=reason;self.put('FRESH_HOST_NATIVE_FAILURE.json',r);self.assertEqual(self.get()['native_failure']['reason'],reason)
 def test_failure_invalid_not_success(self):
  for name,role,base in [('FRESH_HOST_PARENT_FAILURE.json','parent_failure',self.parent()),('FRESH_HOST_NATIVE_FAILURE.json','native_failure',self.native())]:
   for key,val in [('schema','wrong'),('status','PASS'),('numeric_pass',True),('phase','SECRET'),('reason','SECRET')]:
    r=dict(base,**{key:val});self.put(name,r);self.assertEqual(self.get()[role]['state'],'INVALID_NOT_QUALIFIED')
 def test_stage_process_only_and_cleanup_scalars(self):
  r=dict(native_exit=1,errors=['SECRET'],elapsed_seconds=3,observed_peak_rss=123,cleanup_proof={'status':'UNKNOWN'},log_capture={'pipe_eof_observed':False,'gzip_finalized':True},argv=['SECRET'])
  self.put('stage_fresh_host/RESULT.json',r)
  with patch.object(m,'stage_resources',return_value={'safe':'fixed-mock'})as resources:
   out=self.get()['stage'];resources.assert_called_once_with(r)
  self.assertEqual(out['native_exit'],1);self.assertFalse(out['cleanup_complete']);self.assertFalse(out['pipe_eof']);self.assertTrue(out['gzip_finalized']);self.assertNotIn('SECRET',json.dumps(out))
 def test_stage_invalid_and_projection_failure(self):
  for r in [{'native_exit':True},[],{}]:
   self.put('stage_fresh_host/RESULT.json',r);self.assertEqual(self.get()['stage']['state'],'INVALID_NOT_QUALIFIED')
  self.put('stage_fresh_host/RESULT.json',dict(native_exit=0,errors=[],cleanup_proof={},log_capture={}))
  with patch.object(m,'stage_resources',side_effect=ValueError('SECRET')):self.assertEqual(self.get()['stage'],{'state':'INVALID_NOT_QUALIFIED'})
 def test_oversize_and_symlink(self):
  for name,role,limit in [('fresh-host.json','identity',16<<20),('FRESH_HOST_NATIVE_FAILURE.json','native_failure',4096),('FRESH_HOST_PARENT_FAILURE.json','parent_failure',4096),('stage_fresh_host/RESULT.json','stage',16<<20)]:
   p=self.work/'build'/name;p.parent.mkdir(exist_ok=True)
   with p.open('wb')as f:f.truncate(limit+1)
   self.assertEqual(self.get()[role]['state'],'INVALID_NOT_QUALIFIED');p.unlink();p.symlink_to(self.work/'absent');self.assertEqual(self.get()[role]['state'],'INVALID_NOT_QUALIFIED');p.unlink()
 def test_vector_tag_and_64k_fallback(self):
  out=m.summarize(self.work,self.identity);self.assertEqual(out['vector_lanes'],32);self.assertEqual(out['vector_lanes_semantics'],'DECLARED_ARTIFACT_TAG_NOT_VERIFIED_PHYSICAL_ISSUE_LANES');self.assertIs(out['vector_ii1_verified'],False)
  out['build']={'stages':[{'telemetry':{},'private_long_field':'x'*70000}]};raw=m.encode(out);self.assertLessEqual(len(raw.encode()),65536);self.assertTrue(json.loads(raw)['optional_build_details_truncated'])
  with self.assertRaises(ValueError):m.encode({'unbounded':'x'*70000})
 def test_missing_cleanup_keeps_observed_exit_without_qualification(self):
  self.put('stage_fresh_host/RESULT.json',dict(native_exit=None,errors=['opaque'],cleanup_proof=None,log_capture=None))
  with patch.object(m,'stage_resources',return_value={'bounded':True}):r=self.get()['stage']
  self.assertEqual(r['state'],'OBSERVED_PROCESS_ONLY_NOT_QUALIFIED');self.assertIsNone(r['native_exit']);self.assertFalse(r['cleanup_complete']);self.assertFalse(r['pipe_eof'])
if __name__=='__main__':unittest.main(verbosity=2)
