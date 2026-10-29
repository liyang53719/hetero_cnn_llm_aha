import gzip,json,pathlib,tempfile,unittest,ast
from safe_diagnostics import compiler_errors
D=pathlib.Path(__file__).resolve().parent.parent/'ci_frontend_pipeline_r2_20261029'
class Tests(unittest.TestCase):
 def test_order_and_dependency(self):
  s=(D/'one_job_entry_fixed_r2.py').read_text();self.assertLess(s.index("stage('helper_compile'"),s.index("stage('original_high'"));self.assertLess(s.index("stage('compile155'"),s.index("stage('helper_compile'"))
  line=next(x for x in s.splitlines() if "stage('helper_compile'" in x);self.assertIn("'-classpath',basecp",line);self.assertNotIn('original_high',line)
 def test_expected_threaded_not_relearned(self):
  s=(D/'PortableHostHighSimulationEmitter.scala').read_text();self.assertIn('postHigh(high.circuit,fifoChanged,acceptedModules("MatrixResultFifo"))',s);self.assertIn('PortableHostMatrixResultFifoMemoryLowering(original,expectedCanonical)',s)
 def test_specific_error_visible_not_secret(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log';src='/repo/A.scala'
   with gzip.open(p,'wb') as f:f.write((src+':44: error: not enough arguments\nUnspecified value parameter expectedCanonical.\n call(original)\nTOKEN secret\n').encode())
   r=compiler_errors({'argv':[src]},p);self.assertEqual(r[0]['line'],44);self.assertIn('expectedCanonical',r[0]['compiler_error']);self.assertNotIn('TOKEN',json.dumps(r));self.assertNotIn('/repo',json.dumps(r))
 def test_unowned_and_secret_headers_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log'
   with gzip.open(p,'wb') as f:f.write(b'/foreign/A.scala:1: error: hidden\n/repo/A.scala:2: error: token=ghp_SECRET\n')
   self.assertEqual(compiler_errors({'argv':['/repo/A.scala']},p),[])
 def test_oversize_error_omitted(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log'
   with gzip.open(p,'wb') as f:f.write(('/repo/A.scala:1: error: '+'x'*1200).encode())
   self.assertEqual(compiler_errors({'argv':['/repo/A.scala']},p),[])
 def test_multibyte_total_json_bound(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log'
   with gzip.open(p,'wb') as f:f.write((''.join('/repo/A.scala:'+str(i)+': error: '+'界'*150+'\n' for i in range(10))).encode())
   r=compiler_errors({'argv':['/repo/A.scala']},p);self.assertLessEqual(len(json.dumps(r).encode('utf-8')),4096)
 def test_continuation_absolute_path_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log'
   with gzip.open(p,'wb') as f:f.write(b'/repo/A.scala:1: error: missing\n  file /private/path/data.scala\n')
   self.assertEqual(compiler_errors({'argv':['/repo/A.scala']},p),[])
if __name__=='__main__':unittest.main()
