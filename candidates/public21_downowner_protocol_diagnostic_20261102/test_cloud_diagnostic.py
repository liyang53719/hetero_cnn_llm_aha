import ast,gzip,hashlib,importlib.util,json,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('b_finite_diag',D/'diagnostics.py');diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
spec=importlib.util.spec_from_file_location('b_cloud_runner',D/'run_cloud_b.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
class Tests(unittest.TestCase):
 def receipt(self,p,raw):
  p.write_bytes(gzip.compress(raw));return {'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True,'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'compressed_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}
 def test_closed_projection(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'log.gz';r=self.receipt(p,b'B_WINDOW_ACCEPTED ordinal=1 tick=3 ng=0 slot=0\njava.lang.OutOfMemoryError: Java heap space /SECRET\n')
   o=diag.project(p,r);self.assertEqual(o['reasons'],['JAVA_HEAP_SPACE']);self.assertEqual(len(o['checkpoints']),1);self.assertNotIn('SECRET',json.dumps(o))
 def test_compile_source_projection(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'log.gz';r=self.receipt(p,b'/secret/root/Allowed.scala:72: error: not found: type SECRET_TYPE\n/secret/root/Other.scala:3: error: message\njava.lang.UnsatisfiedLinkError: /secret/library\n')
   o=diag.project(p,r,['Allowed.scala']);self.assertEqual(o['source_errors'],[dict(source='Allowed.scala',line=72,code='NOT_FOUND_TYPE')]);self.assertNotIn('secret',json.dumps(o));self.assertNotIn('SECRET_TYPE',json.dumps(o));self.assertIn('UNSATISFIED_LINK',o['reasons'])
 def test_malformed_records(self):
  for line in ['B_WINDOW_ACCEPTED ordinal=1 tick=3 ng=0 slot=/secret','B_WINDOW_ACCEPTED ordinal=1 tick=3 ng=0 slot=0 extra=1','B_WINDOW_ACCEPTED ordinal=1 tick=3 ng=0 slot=0 slot=0','B_WINDOW_ACCEPTED ordinal=1 tick=3 ng=0 slot=999999999999999999999']:
   self.assertIsNone(diag.parse(line))
 def test_missing_eof_and_drift(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'log.gz';r=self.receipt(p,b'')
   r['log_capture']['pipe_eof_observed']=False;self.assertEqual(diag.project(p,r)['status'],'UNAVAILABLE')
   r['log_capture']['pipe_eof_observed']=True;r['log_capture']['raw_sha256']='0'*64;self.assertEqual(diag.project(p,r)['status'],'UNAVAILABLE')
 def test_line_cap(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'log.gz';r=self.receipt(p,b'x'*65537);self.assertEqual(diag.project(p,r)['status'],'UNAVAILABLE')
 def test_strict_all_bits(self):
  r={'native_exit':0,'errors':[],'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  self.assertTrue(runner.strict(r))
  for k in ('pipe_eof_observed','gzip_finalized'):
   q=json.loads(json.dumps(r));q['log_capture'][k]=False;self.assertFalse(runner.strict(q))
 def test_budget_totals(self):
  self.assertEqual(sum(w for _,w,_ in runner.MAIN),4320);self.assertEqual(sum(w+30 for _,w,_ in runner.MAIN)+1800+60,6360);self.assertEqual(runner.WHOLE,7200);self.assertLess(6360,6600)
 def test_budget_contract(self):
  b=json.loads((D/'BUDGET_CONTRACT.json').read_text());self.assertEqual(b['whole_job_seconds'],runner.WHOLE);self.assertEqual(b['main_phase_wall_seconds'],{n:w for n,w,r in runner.MAIN});self.assertEqual(b['main_phase_rss_gib'],{n:r for n,w,r in runner.MAIN});self.assertFalse(b['artifact_upload_permitted']);self.assertEqual(b['stage_run_directory_tree_bytes'],2000000000);self.assertNotIn('per_stage_tree_bytes',b);self.assertIn('NOT stage_run_directory_tree_bytes',b['shared_emitted_outputs_scope'])
  tree=ast.parse((D/'run_cloud_b.py').read_text());caps=[n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='caps' for t in n.targets)];self.assertEqual(len(caps),1);kw={x.arg:x.value for x in caps[0].keywords};self.assertEqual(ast.literal_eval(kw['tree_bytes']),b['stage_run_directory_tree_bytes']);self.assertEqual(ast.unparse(kw['watch_tree_bytes']),'TREE');self.assertEqual(ast.unparse(kw['extra_watch_roots']),'[str(W), str(R)]');self.assertEqual(runner.TREE,b['aggregate_watched_tree_bytes']);self.assertIn("emitted = W / 'emitted'",ast.unparse(tree))
 def test_emit_checkpoints(self):
  for s in ['B_EMIT_ONLY_BEFORE_ELAB backend_started=false native_loaded=false','B_EMIT_ONLY_LOW_AND_HARNESS_DONE backend_started=false','B_EMIT_ONLY_COMPLETE backend_started=false native_loaded=false protocol_executed=false']:self.assertIsNotNone(diag.parse(s))
 def test_scope_and_no_upload(self):
  t=ast.parse((D/'run_cloud_b.py').read_text());calls=[n for n in ast.walk(t) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='stage']
  names=[n.args[0].value for n in calls if n.args and isinstance(n.args[0],ast.Constant)]
  self.assertEqual(set(names),runner.PHASES);self.assertEqual(len(names),len(runner.PHASES))
  self.assertNotIn('GH_TOKEN',(D/'run_cloud_b.py').read_text());self.assertNotIn('upload-artifact',(D/'run_cloud_b.py').read_text())
 def test_fixed_compile_and_backend(self):
  s=(D/'run_cloud_b.py').read_text();self.assertIn("len(sources)==159",s);self.assertIn("'OPT_FAST=-O0','OPT_SLOW=-O0','OPT_GLOBAL=-O0'",s);self.assertIn("'--coverage-user'",s);self.assertNotIn('--disable-all-randomization',s)
if __name__=='__main__':unittest.main()
