"""Input gates and bounded acquisition mocks only; no network/JVM/DUT."""
import contextlib,hashlib,importlib.util,io,json,pathlib,ssl,tempfile,unittest,urllib.error
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('candidate_jar_restore_tested',D/'restore_model_inputs.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.data=b'synthetic exact jar';self.row=dict(maven_path='a/b.jar',url='https://repo.maven.apache.org/maven2/a/b.jar',bytes=len(self.data),sha256=hashlib.sha256(self.data).hexdigest(),role='classpath')
 def test_verified_existing_bytes_no_network(self):
  p=self.root/'a/b.jar';p.parent.mkdir();p.write_bytes(self.data)
  with patch.object(m.urllib.request,'urlopen',side_effect=AssertionError('no network')):m.acquire(self.root,self.row,True)
 def test_missing_no_download_rejected(self):
  with patch.object(m.urllib.request,'urlopen',side_effect=AssertionError('no network')):
   with self.assertRaisesRegex(m.Rejected,'JAR_MISSING'):m.acquire(self.root,self.row,False)
 def test_download_exact_bytes_mock(self):
  with patch.object(m.urllib.request,'urlopen',return_value=io.BytesIO(self.data))as f:m.acquire(self.root,self.row,True)
  f.assert_called_once_with(self.row['url'],timeout=60);self.assertEqual((self.root/'a/b.jar').read_bytes(),self.data)
 def test_wrong_content_not_committed(self):
  with patch.object(m.urllib.request,'urlopen',return_value=io.BytesIO(b'wrong')):
   with self.assertRaisesRegex(m.Rejected,'JAR_CONTENT_REJECTED'):m.acquire(self.root,self.row,True)
  self.assertFalse((self.root/'a/b.jar').exists())
 def test_existing_drift_rejected_not_overwritten(self):
  p=self.root/'a/b.jar';p.parent.mkdir();p.write_bytes(b'bad')
  with self.assertRaisesRegex(m.Rejected,'JAR_CONTENT_REJECTED'):m.acquire(self.root,self.row,True)
  self.assertEqual(p.read_bytes(),b'bad')
 def test_symlink_rejected(self):
  target=self.root/'else';target.mkdir();(self.root/'a').symlink_to(target,target_is_directory=True)
  with self.assertRaisesRegex(m.Rejected,'JAR_CACHE_REJECTED'):m.acquire(self.root,self.row,True)
 def test_original_classpath_plugin_alias_is_not_deduplicated(self):
  rows=[dict(self.row,maven_path=f'group/jar{i}.jar',url=f'https://repo.maven.apache.org/maven2/group/jar{i}.jar')for i in range(106)];rows.append(dict(rows[45],role='plugin'))
  self.assertEqual(m.inventory({'jars':rows}),rows)
  rows[-1]['sha256']='0'*64
  with self.assertRaisesRegex(m.Rejected,'JAR_INVENTORY_REJECTED'):m.inventory({'jars':rows})
 def status(self,error):
  with patch.object(m,'source_inputs',side_effect=error):return m.run(True)
 def test_safe_failure_enums_and_no_exception_text(self):
  cases=[(m.Rejected('SOURCE_OR_CONTRACT_REJECTED'),'SOURCE_OR_CONTRACT_REJECTED'),(urllib.error.HTTPError('https://secret.invalid',403,'secret',None,None),'JAR_HTTP_ERROR'),(urllib.error.URLError('secret'),'JAR_NETWORK_ERROR'),(TimeoutError('secret'),'JAR_TIMEOUT'),(OSError('secret'),'JAR_IO_ERROR'),(RuntimeError('secret'),'UNCLASSIFIED_FAILURE')]
  for e,reason in cases:
   with self.subTest(reason=reason):r=self.status(e);self.assertEqual(r['reason'],reason);self.assertEqual(r['status'],'INCOMPLETE');self.assertNotIn('secret',json.dumps(r));self.assertFalse(r['compiler_executed']);self.assertFalse(r['numerical_pass']);self.assertLess(len(json.dumps(r)),2048)
 def test_verify_only_does_not_acquire(self):
  with patch.object(m,'source_inputs',return_value=(self.root,{},list(range(159)),{})),patch.object(m,'inventory',return_value=[self.row]*107),patch.object(m,'acquire',side_effect=AssertionError('no jar reads')):r=m.run(verify_only=True)
  self.assertEqual(r['status'],'SOURCE_AND_JAR_INVENTORY_VERIFIED_ONLY');self.assertEqual(r['verified_jar_count'],0);self.assertEqual(r['source_count'],159)
 def test_failure_status_json_and_exit_nonzero(self):
  target=self.root/'status.json'
  with patch('sys.argv',['restore','--download-jars','--status-json',str(target)]),patch.object(m,'source_inputs',side_effect=m.Rejected('SOURCE_OR_CONTRACT_REJECTED')),contextlib.redirect_stdout(io.StringIO())as out:self.assertEqual(m.main(),1)
  r=json.loads(target.read_text());self.assertEqual(r['reason'],'SOURCE_OR_CONTRACT_REJECTED');self.assertIn('MODEL_JAR_STATUS',out.getvalue());self.assertLess(target.stat().st_size,2048)
 def test_all_record_completion_is_not_compilation(self):
  with patch.object(m,'source_inputs',return_value=(self.root,{},list(range(159)),{})),patch.object(m,'inventory',return_value=[self.row]*107),patch.object(m,'acquire')as acquire:r=m.run(download=True)
  self.assertEqual(acquire.call_count,107);self.assertEqual(r['verified_jar_count'],107);self.assertEqual(r['status'],'SOURCE_AND_ALL_JAR_BYTES_VERIFIED');self.assertIsNone(r['jar_index']);self.assertFalse(r['compiler_executed']);self.assertFalse(r['numerical_pass'])
 def test_midstream_http_preserves_finite_progress(self):
  with patch.object(m,'source_inputs',return_value=(self.root,{},list(range(159)),{})),patch.object(m,'inventory',return_value=[self.row]*107),patch.object(m,'acquire',side_effect=[None,None,urllib.error.HTTPError('https://secret',503,'secret',None,None)]):r=m.run(download=True)
  self.assertEqual((r['verified_jar_count'],r['jar_index'],r['http_status']),(2,2,503));self.assertEqual(r['reason'],'JAR_HTTP_ERROR');self.assertNotIn('secret',json.dumps(r))
 def test_modes_mutually_exclusive(self):
  with patch('sys.argv',['restore','--download-jars','--verify-only']),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):m.main()
if __name__=='__main__':unittest.main()
