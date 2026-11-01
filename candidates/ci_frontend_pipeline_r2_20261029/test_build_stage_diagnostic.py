import ast,hashlib,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
s=(D/'one_job_build_only.py').read_text();t=ast.parse(s)
names={'BUILD_STAGE_NAMES','BUILD_ERROR_CODES','build_stage_diagnostic','sha'}
keep=[n for n in t.body if isinstance(n,ast.FunctionDef)and n.name in names or isinstance(n,ast.Assign)and any(isinstance(q,ast.Name)and q.id in names for q in n.targets)]
ns={'pathlib':pathlib,'hashlib':hashlib,'json':json};exec(compile(ast.Module(body=keep,type_ignores=[]),'<reviewed-functions>','exec'),ns)
class Test(unittest.TestCase):
 def project(self,r,name='host_archive'):
  with tempfile.TemporaryDirectory()as td:
   p=pathlib.Path(td)/'RESULT.json';p.write_text(json.dumps(r));return json.loads(ns['build_stage_diagnostic'](name,r,p))
 def test_actual_shape(self):
  r={'native_exit':2,'worker_started':True,'errors':[],'elapsed_seconds':300.5,'caps':{'wall_seconds':3600},'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  q=self.project(r);self.assertEqual(q['native_exit'],2);self.assertEqual(q['error_categories'],[]);self.assertTrue(q['cleanup_complete']);self.assertFalse(q['numerical_pass']);self.assertEqual(len(q['receipt_sha256']),64)
 def test_each_exact_error(self):
  for error,code in ns['BUILD_ERROR_CODES'].items():self.assertEqual(self.project({'errors':[error]})['error_categories'],[code])
 def test_no_raw(self):
  secret='SECRET_TEST_ONLY';q=self.project({'errors':['ValueError: '+secret],'argv':[secret],'caps':{'unknown':secret},'cleanup_proof':{'raw':secret},'processes':[secret]},secret)
  self.assertNotIn(secret,json.dumps(q));self.assertEqual(q['stage'],'UNKNOWN_STAGE');self.assertEqual(q['error_categories'],['UNCLASSIFIED_SUPERVISOR_ERROR'])
 def test_no_substring_guess(self):
  self.assertEqual(self.project({'errors':['ValueError: wall cap garbage']})['error_categories'],['UNCLASSIFIED_SUPERVISOR_ERROR'])
 def test_malformed(self):
  for val in (None,True,'x',{}):self.assertEqual(self.project({'errors':val})['error_categories'],['MALFORMED_ERROR_LIST'])
 def test_nonfinite_and_bool(self):
  for val in (True,float('nan'),float('inf'),-1,2**1024):
   q=self.project({'elapsed_seconds':val,'native_exit':True,'errors':[]});self.assertIsNone(q['elapsed_seconds']);self.assertIsNone(q['native_exit'])
 def test_bounded_errors(self):
  q=self.project({'errors':['unknown']*1000});self.assertIn('ERROR_LIST_TRUNCATED',q['error_categories']);self.assertLess(len(json.dumps(q)),8192)
 def test_absent_receipt(self):
  q=json.loads(ns['build_stage_diagnostic']('host_archive',{},pathlib.Path('/nonexistent/RESULT.json')));self.assertIsNone(q['receipt_sha256'])
 def test_wrong_cleanup(self):
  self.assertFalse(self.project({'errors':[],'cleanup_proof':{'status':'COMPLETE'}})['cleanup_complete'])
 def test_only_projection_insert(self):
  baseline_ast_sha256='51aef6ad20a9c179a11db73f2e1f2139d9e76aa4575c08d19c92a4008636f00b' # exact published 4255/43e4 original orchestration AST
  # Remove exactly the helper definitions and single approved print from new AST;
  # all executable build logic/caps/argv/strict checks must equal old AST.
  after=ast.parse(s)
  after.body=[n for n in after.body if not(isinstance(n,ast.FunctionDef)and n.name=='build_stage_diagnostic' or isinstance(n,ast.Assign)and any(isinstance(q,ast.Name)and q.id in {'BUILD_STAGE_NAMES','BUILD_ERROR_CODES'}for q in n.targets))]
  class Strip(ast.NodeTransformer):
   count=0
   def visit_Expr(self,n):
    if isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='print'and n.value.args and isinstance(n.value.args[0],ast.BinOp)and isinstance(n.value.args[0].left,ast.Constant)and n.value.args[0].left.value=='BUILD_STAGE_DIAGNOSTIC ':
     self.count+=1;return None
    return self.generic_visit(n)
  strip=Strip();after=strip.visit(after);self.assertEqual(strip.count,1);self.assertEqual(hashlib.sha256(ast.dump(after).encode()).hexdigest(),baseline_ast_sha256)
if __name__=='__main__':unittest.main()
