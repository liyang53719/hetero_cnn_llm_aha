import ast,copy,gzip,hashlib,importlib.util,json,pathlib,tempfile,unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('ird',D/'original_ir_diagnostic.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=pathlib.Path(self.t.name);self.r=dict(native_exit=1,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
 def put(self,raw):
  (self.p/'frontend.log.gz').write_bytes(gzip.compress(raw.encode()if isinstance(raw,str)else raw))
 def read(self):return json.loads(m.project(self.p,self.r))
 def test_known(self):
  self.put('HOST_PHASE official.low.begin wall_ns=123 process_cpu_ns=456\nHOST_ARTIFACT original-high.fir bytes=100 sha256='+('a'*64)+'\nException in thread "main" firrtl2.transforms.CheckCombLoops$CombLoopException: secret net/path\n\tat firrtl2.transforms.CheckCombLoops.run(CheckCombLoops.scala:130)\n');d=self.read();self.assertTrue(d['scan_complete']);self.assertEqual(d['phases'][0]['phase'],'official.low.begin');self.assertEqual(d['exceptions'][0]['category'],'CHECK_COMB_LOOPS');self.assertEqual(d['stack'][0],dict(basename='CheckCombLoops.scala',function='run',line=130));self.assertNotIn('secret',json.dumps(d))
 def test_malicious(self):
  self.put('HOST_PHASE SECRET.begin wall_ns=1 process_cpu_ns=1\nHOST_ARTIFACT /private/token bytes=4 sha256='+('a'*64)+'\njava.lang.SecretToken: private\n\tat firrtl2.Secret.token(Secret.scala:5)\n<rawannotation secret>\n');d=self.read();self.assertEqual([d[x]for x in ('phases','artifacts','exceptions','stack')],[[],[],[],[]]);self.assertNotIn('private',json.dumps(d))
 def test_no_eof_never_opens(self):
  self.r['log_capture']['pipe_eof_observed']=False
  with mock.patch.object(m.gzip,'open',side_effect=AssertionError('must not open')):d=self.read()
  self.assertEqual(d['reason'],'CLOSED_CAPTURE_REQUIRED')
 def test_no_cleanup_never_opens(self):
  self.r['cleanup_proof']=None;self.assertEqual(self.read()['status'],'UNAVAILABLE')
 def test_missing_gzip(self):self.assertEqual(self.read()['reason'],'LOG_FILE_UNAVAILABLE')
 def test_bad_gzip(self):
  (self.p/'frontend.log.gz').write_bytes(b'private non gzip');d=self.read();self.assertEqual(d['reason'],'GZIP_INVALID');self.assertFalse(d['scan_complete']);self.assertNotIn('private',json.dumps(d))
 def test_truncated_gzip(self):
  self.put('HOST_PHASE elaborate.begin wall_ns=1 process_cpu_ns=2\n');p=self.p/'frontend.log.gz';p.write_bytes(p.read_bytes()[:-6]);self.assertEqual(self.read()['reason'],'GZIP_INVALID')
 def test_oversize_line(self):
  self.put('private'*(m.MAX_LINE//7+1));d=self.read();self.assertEqual(d['reason'],'SCAN_BOUND');self.assertFalse(d['scan_complete']);self.assertNotIn('private',json.dumps(d))
 def test_raw_cap(self):
  self.put('a\n'*100)
  with mock.patch.object(m,'MAX_RAW',30):self.assertEqual(self.read()['reason'],'SCAN_BOUND')
 def test_compressed_cap(self):
  self.put('x')
  with mock.patch.object(m,'MAX_COMPRESSED',2):self.assertEqual(self.read()['reason'],'LOG_FILE_UNAVAILABLE')
 def test_symlink_refused(self):
  self.put('x');p=self.p/'frontend.log.gz';p.rename(self.p/'target');p.symlink_to(self.p/'target');self.assertEqual(self.read()['reason'],'LOG_FILE_UNAVAILABLE')
 def test_oversize_known_output_bounded(self):
  rows=['HOST_ARTIFACT '+n+' bytes=100 sha256='+('f'*64)for n in sorted(m.ARTIFACTS)]
  rows+=['HOST_PHASE '+n+' wall_ns=1 process_cpu_ns=2'for n in sorted(m.PHASES)]
  rows += [x+': private'for x in m.EXCEPTIONS]
  rows += ['\tat firrtl2.X.secretFunction('+n+':100)'for n in m.FILES]
  self.put('\n'.join(rows)*5);raw=m.project(self.p,self.r);self.assertLessEqual(len(raw.encode()),8192);self.assertNotIn('secretFunction',raw);self.assertNotIn('private',raw)
 def test_require_enum_only(self):
  self.put('java.lang.IllegalArgumentException: requirement failed: SECRET\n');self.assertEqual(self.read()['exceptions'],[dict(exception_class='java.lang.IllegalArgumentException',category='REQUIREMENT_REJECTED')])
 def test_report_not_mutated(self):
  r=copy.deepcopy(self.r);self.put('x');self.read();self.assertEqual(r,self.r)
 def test_caller_ast_preserved(self):
  tree=ast.parse((D/'one_job_model_candidate.py').read_text())
  class Strip(ast.NodeTransformer):
   def visit_If(self,n):
    if ast.unparse(n.test)=="name == 'original_high'"and any(isinstance(x,ast.ImportFrom)and x.module=='original_ir_diagnostic'for x in n.body):return None
    return self.generic_visit(n)
  got=hashlib.sha256(ast.dump(Strip().visit(tree),include_attributes=False).encode()).hexdigest();self.assertEqual(got,'ddd182da38eb18363d491a68faca437e81010b4bf9abfa92cf91456b24cc544b')
if __name__=='__main__':unittest.main()
