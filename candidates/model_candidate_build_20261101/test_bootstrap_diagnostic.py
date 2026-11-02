import ast,contextlib,copy,hashlib,importlib.util,io,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('bootstrap_diag',D/'bootstrap_model_candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

# Exact inverse of the independently reviewed read-only build branch only.
FIRST_FAULT_INVERSE = [(" a.add_argument('--first-fault-readonly',action='store_true')\n", '', '793e0c515eb48d727f4d62ab5139a4cb7e257b12945a8e645338732df0ba26c5'), (" stage('binding',[py,'-B',str(C/'materialize_model_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')]+(['--first-fault-readonly'] if v.first_fault_readonly else []))\n", " stage('binding',[py,'-B',str(C/'materialize_model_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')])\n", '81aac29514dd880e221e6451ec0b30b0759ed77bd195e057492d4e0091593960')]
def first_fault_inverse(text):
 text=terminal_inverse(text)
 for added,original,expected in FIRST_FAULT_INVERSE:
  if hashlib.sha256(added.encode()).hexdigest()!=expected or text.count(added)!=1:raise ValueError("unique exact first-fault addition")
  text=text.replace(added,original,1)
 return text

TERMINAL_INVERSE = [(" a.add_argument('--terminal-finite-readonly',action='store_true')\n", '', '22099f59b102782ebe15919440dd236925559d975836763ce6f323b073610382'), (" need(not(v.first_fault_readonly and v.terminal_finite_readonly),'one explicit readonly mode')\n", '', '80a77b5eedcf7e06500ae1acfb039e4da046e602dcfa32fb248576706d0ce231'), (" stage('binding',[py,'-B',str(C/'materialize_model_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')]+(['--first-fault-readonly'] if v.first_fault_readonly else [])+(['--terminal-finite-readonly'] if v.terminal_finite_readonly else []))\n", " stage('binding',[py,'-B',str(C/'materialize_model_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')]+(['--first-fault-readonly'] if v.first_fault_readonly else []))\n", 'bd38c8d1fa2269a18e7504aff93fd512dc12b3b30d5a7b3c64c01737e3b394ec')]
TERMINAL_BASE_AST_SHA = '5588a1d0ffd238b160307f8c368e0a13f0fa6a02aba8a301f9ee6737922aff33'
def terminal_inverse(text):
 for added,original,expected in TERMINAL_INVERSE:
  if hashlib.sha256(added.encode()).hexdigest()!=expected or text.count(added)!=1:raise ValueError('unique exact terminal addition')
  text=text.replace(added,original,1)
 try:tree=ast.parse(text)
 except SyntaxError as e:raise ValueError('original first-fault bootstrap syntax')from e
 if hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()!=TERMINAL_BASE_AST_SHA:raise ValueError('original first-fault bootstrap AST')
 return text

class Tests(unittest.TestCase):
 def test_terminal_inverse_rejects_duplicate_mutation(self):
  text=(D/'bootstrap_model_candidate.py').read_text();added=TERMINAL_INVERSE[0][0]
  with self.assertRaises(ValueError):terminal_inverse(text+added)
  with self.assertRaises(ValueError):terminal_inverse(text.replace(added,added.replace('terminal-finite','wrong-terminal',1),1))
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.w=pathlib.Path(self.tmp.name)
 def project(self,r,name='jars'):return json.loads(m.bootstrap_stage_diagnostic(name,r,self.w/'absent'/'RESULT.json'))
 def test_source_ast_preserved(self):
  source=first_fault_inverse((D/'bootstrap_model_candidate.py').read_text())
  self.assertEqual(source.count("C/'restore_model_inputs.py'"),2)
  source=source.replace("'--download-jars','--status-json',str(W/'MODEL_JAR_STATUS.json')","'--download-jars'")
  tree=ast.parse(source.replace("C/'restore_model_inputs.py'","R/'candidates/fresh_original_top_recovery_20261028/restore_inputs.py'"))
  class Strip(ast.NodeTransformer):
   def visit_FunctionDef(self,n):
    if n.name in {'bootstrap_stage_diagnostic','record_bootstrap_diagnostic','project_jar_status','read_jar_status'}:return None
    return self.generic_visit(n)
   def visit_Assign(self,n):
    if any(isinstance(t,ast.Name)and t.id in {'BUILD_STAGE_NAMES','BUILD_ERROR_CODES','JAR_STATUS_REASONS'}for t in n.targets):return None
    return self.generic_visit(n)
   def visit_Expr(self,n):
    if isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='record_bootstrap_diagnostic':return None
    return self.generic_visit(n)
  got=hashlib.sha256(ast.dump(Strip().visit(tree),include_attributes=False).encode()).hexdigest()
  self.assertEqual(got,'3143794d8eb7f3d1b1024407e308cac87f3c539c988aa81c357b8c06d5d64ddc')
 def test_prelaunch_no_directory(self):
  r={'worker_started':False,'native_exit':None,'errors':['ValueError: locked memory gate'],'cleanup_proof':None,'log_capture':{},'elapsed_seconds':0.1,'observed_peak_rss':0}
  before=copy.deepcopy(r);out=io.StringIO()
  with contextlib.redirect_stdout(out):m.record_bootstrap_diagnostic('jars',r,self.w)
  d=json.loads((self.w/'jars_SUPERVISOR_RETURN_DIAGNOSTIC.json').read_text());self.assertEqual(d['error_categories'],['PRELAUNCH_MEMORY_GATE']);self.assertIsNone(d['native_exit']);self.assertIsNone(d['receipt_sha256']);self.assertFalse(d['cleanup_complete']);self.assertEqual(r,before);self.assertFalse((self.w/'stage_jars').exists());self.assertLess(len(out.getvalue().encode()),8192)
 def test_unknown_no_leak(self):
  d=self.project({'errors':['secret=abc /private/path token=ghp_test'],'argv':['private'],'native_exit':1});raw=json.dumps(d)
  self.assertEqual(d['error_categories'],['UNCLASSIFIED_SUPERVISOR_ERROR']);self.assertNotIn('private',raw);self.assertNotIn('ghp_',raw);self.assertNotIn('secret',raw)
 def test_native_not_oom_inferred(self):
  d=self.project({'native_exit':1,'errors':[]});self.assertEqual(d['error_categories'],[]);self.assertEqual(d['native_exit'],1)
 def test_missing_error_is_unknown(self):self.assertEqual(self.project({})['error_categories'],['MALFORMED_ERROR_LIST'])
 def test_bound_counts_and_nan(self):
  d=self.project({'elapsed_seconds':float('nan'),'observed_peak_rss':2**54,'native_exit':True,'errors':[{'raw':'secret'}]*257});self.assertIsNone(d['elapsed_seconds']);self.assertIsNone(d['observed_peak_rss']);self.assertIsNone(d['native_exit']);self.assertIn('ERROR_LIST_TRUNCATED',d['error_categories'])
 def test_receipt_hash(self):
  p=self.w/'RESULT.json';p.write_bytes(b'receipt');d=json.loads(m.bootstrap_stage_diagnostic('jdk',{},p));self.assertEqual(d['receipt_sha256'],hashlib.sha256(b'receipt').hexdigest())
 def test_unknown_stage_no_path(self):
  out=io.StringIO()
  with contextlib.redirect_stdout(out):m.record_bootstrap_diagnostic('../private',{},self.w)
  self.assertIn('UNKNOWN_STAGE',out.getvalue());self.assertNotIn('private',out.getvalue());self.assertEqual(list(self.w.iterdir()),[])
 def test_existing_local_not_overwrite(self):
  p=self.w/'jars_SUPERVISOR_RETURN_DIAGNOSTIC.json';p.write_text('retained')
  out=io.StringIO()
  with contextlib.redirect_stdout(out):m.record_bootstrap_diagnostic('jars',{},self.w)
  self.assertEqual(p.read_text(),'retained');self.assertIn('LOCAL_WRITE_UNAVAILABLE',out.getvalue())
 def test_exact_stage_names(self):self.assertEqual(m.BUILD_STAGE_NAMES,('jdk','compile_tools','jars','verilator','idma','matrix','fresh_host','binding'))
 def test_strict_completion_projection(self):
  d=self.project({'native_exit':0,'errors':[],'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}});self.assertTrue(d['cleanup_complete']);self.assertTrue(d['pipe_eof_observed']);self.assertTrue(d['gzip_finalized']);self.assertFalse(d['numerical_pass'])
 def jar(self):return dict(schema='MODEL_CANDIDATE_JAR_INPUT_STATUS_V1',status='SOURCE_AND_ALL_JAR_BYTES_VERIFIED',reason=None,jar_index=None,http_status=None,source_count=159,required_jar_count=107,verified_jar_count=107,download_requested=True,verify_only=False,compiler_executed=False,numerical_pass=False)
 def test_jar_valid(self):self.assertEqual(m.project_jar_status(self.jar()),self.jar())
 def test_jar_unknown_field_rejected(self):
  d=self.jar();d['url']='private'
  with self.assertRaises(ValueError):m.project_jar_status(d)
 def test_jar_reason_invalid_rejected(self):
  d=self.jar();d.update(status='INCOMPLETE',reason='private exception')
  with self.assertRaises(ValueError):m.project_jar_status(d)
 def test_jar_oversize_unavailable(self):
  p=self.w/'MODEL_JAR_STATUS.json';p.write_text('private'+(' '*2048));raw=m.read_jar_status(p);self.assertIn('UNAVAILABLE',raw);self.assertNotIn('private',raw)
 def test_jar_invalid_json_unavailable(self):
  p=self.w/'MODEL_JAR_STATUS.json';p.write_text('private invalid');self.assertIn('UNAVAILABLE',m.read_jar_status(p));self.assertNotIn('private',m.read_jar_status(p))
 def test_jar_http_bounded(self):
  d=self.jar();d.update(status='INCOMPLETE',reason='JAR_HTTP_ERROR',http_status=503,jar_index=5,verified_jar_count=5);self.assertEqual(m.project_jar_status(d),d)
  d['http_status']=True
  with self.assertRaises(ValueError):m.project_jar_status(d)
 def test_jar_only(self):
  p=self.w/'MODEL_JAR_STATUS.json';p.write_text(json.dumps(self.jar()));o=io.StringIO()
  with contextlib.redirect_stdout(o):m.record_bootstrap_diagnostic('jdk',{},self.w)
  self.assertNotIn('MODEL_JAR_STATUS ',o.getvalue())
 def test_first_fault_inverse_rejects_duplicate_or_mutated_addition(self):
  text=(D/'bootstrap_model_candidate.py').read_text();added=FIRST_FAULT_INVERSE[0][0]
  with self.assertRaises(ValueError):first_fault_inverse(text+added)
  with self.assertRaises(ValueError):first_fault_inverse(text.replace(added,added.replace('first-fault','wrong-fault',1),1))
if __name__=='__main__':unittest.main()
