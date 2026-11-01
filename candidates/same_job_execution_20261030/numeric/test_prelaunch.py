import ast,copy,json,os,pathlib,signal,tempfile,types,unittest,hashlib
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
source=ast.parse((D/'numeric_tail.py').read_text())
selected=[n for n in source.body if isinstance(n,ast.FunctionDef)and n.name in ('sha','save','complete','prelaunch_rejection','require_cleanup')or isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id.startswith('PRELAUNCH_')for t in n.targets)]
ns=dict(P=P,json=json,hashlib=hashlib,signal=signal)
exec(compile(ast.Module(body=selected,type_ignores=[]),'numeric_tail.py','exec'),ns)
class Held(Exception):pass

def receipt():
 return dict(argv=['synthetic'],caps={},cleanup_proof=None,elapsed_seconds=0.1,errors=['ValueError: locked memory gate'],limitations=[],native_exit=None,observed_cpu_seconds=0,observed_peak_rss=0,observed_processes=[],peak_file_bytes=0,peak_tree_bytes=0,reader_join_barrier={'complete':True,'alive':False,'reader_finally_done':False},scope='ORIGINAL_PROCESS_GROUP_AND_OBSERVED_DESCENDANTS_ONLY',status='FAIL_OR_INCOMPLETE',supervisor_cpu_scope='synthetic',supervisor_cpu_seconds=0.1,worker_started=False)

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);self.run=self.root/'absent';self.supervisor=self.root/'supervisor.py';self.supervisor.write_text('synthetic');self.marker=self.root/'HOLD.json'
 def held(self,r,run=None,source=None):
  with patch.object(signal,'pause',side_effect=Held),patch.dict(ns,sha=lambda p:ns['PRELAUNCH_SUPERVISOR_SHA']):
   with self.assertRaises(Held):ns['require_cleanup'](r,self.marker,self.run if run is None else run,self.supervisor if source is None else source)
  self.assertEqual(json.loads(self.marker.read_text())['status'],'HOLD_PARENT_LEASE_NO_CONTINUATION');self.marker.unlink()
  self.assertFalse(self.marker.with_name('PRELAUNCH_REJECTED_'+self.marker.name).exists())
 def test_exact_prelaunch_three_errors(self):
  for error in ns['PRELAUNCH_ERRORS']:
   r=receipt();r['errors']=[error]
   with patch.dict(ns,sha=lambda p:ns['PRELAUNCH_SUPERVISOR_SHA']):
    with self.assertRaisesRegex(ValueError,'before worker launch; INCOMPLETE'):ns['require_cleanup'](r,self.marker,self.run,self.supervisor)
   marker=self.marker.with_name('PRELAUNCH_REJECTED_'+self.marker.name);self.assertFalse(self.marker.exists());self.assertFalse(self.run.exists());self.assertFalse(json.loads(marker.read_text())['numerical_pass']);marker.unlink()
 def test_unknown_or_started_evidence_holds(self):
  changes=[{'worker_started':0},{'worker_started':True},{'native_exit':0},{'cleanup_proof':{}},{'observed_processes':[{'pid':1}]},{'observed_processes':()}, {'owner_identity':None},{'log_capture':None},{'errors':['ValueError: leader identity mismatch']},{'errors':['ValueError: locked memory gate','extra']},{'observed_peak_rss':1},{'reader_join_barrier':{'complete':True,'alive':False,'reader_finally_done':True}},{'reader_join_barrier':{'complete':1,'alive':0,'reader_finally_done':False}},{'unknown_process_identity':1}]
  for delta in changes:
   with self.subTest(delta=delta):r=receipt();r.update(delta);self.held(r)
 def test_existing_run_and_dangling_symlink_hold(self):
  self.run.mkdir();self.held(receipt());self.run.rmdir();self.run.symlink_to(self.root/'missing');self.held(receipt())
 def test_post_popen_pre_flag_failure_holds(self):
  self.run.mkdir();(self.run/'frontend.log.gz').write_bytes(b'')
  r=receipt();r['errors']=['ValueError: leader verification'];self.held(r)
 def test_missing_arguments_or_bad_source_hold(self):
  with patch.object(signal,'pause',side_effect=Held):
   with self.assertRaises(Held):ns['require_cleanup'](receipt(),self.marker)
  self.marker.unlink()
  with patch.object(signal,'pause',side_effect=Held):
   with self.assertRaises(Held):ns['require_cleanup'](receipt(),self.marker,self.run,self.supervisor)
 def test_complete_unchanged(self):
  r={'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  ns['require_cleanup'](r,self.marker);self.assertFalse(self.marker.exists())
 def test_actual_retained_return_and_source_order(self):
  if not os.environ.get('ACTUAL_RETURN')or not os.environ.get('SUPERVISOR_SOURCE'):self.skipTest('optional actual read-only evidence paths not supplied')
  actual=P(os.environ['ACTUAL_RETURN']);supervisor=P(os.environ['SUPERVISOR_SOURCE'])
  self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(),'c89287a9aa298fc602d172b6cab4b6ff2653730989fc4517250d339ad3495fa9')
  r=json.loads(actual.read_text());actual_run=actual.parent.parent/'runs'/actual.name.removesuffix('_SUPERVISOR_RETURN.json');self.assertTrue(ns['prelaunch_rejection'](r,actual_run,supervisor));self.assertTrue(ns['prelaunch_rejection'](r,self.run,supervisor))
  text=supervisor.read_text();self.assertEqual(ns['sha'](supervisor),ns['PRELAUNCH_SUPERVISOR_SHA'])
  self.assertLess(text.index("'locked memory gate'"),text.index('run.mkdir()'));self.assertLess(text.index("'locked disk gate'"),text.index('run.mkdir()'));self.assertLess(text.index("'prelaunch work deadline'"),text.index('run.mkdir()'));self.assertLess(text.index('run.mkdir()'),text.index('p=subprocess.Popen('));self.assertLess(text.index('p=subprocess.Popen('),text.index("report['worker_started']=True"))
 def test_all_other_production_ast_unchanged(self):
  t=copy.deepcopy(source)
  t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef)and n.name=='prelaunch_rejection')and not(isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id.startswith('PRELAUNCH_')for x in n.targets))]
  old=ast.parse("def require_cleanup(r,marker):\n if not complete(r):\n  save(marker,dict(status='HOLD_PARENT_LEASE_NO_CONTINUATION'))\n  while True:signal.pause()\n").body[0]
  t.body=[old if isinstance(n,ast.FunctionDef)and n.name=='require_cleanup'else n for n in t.body]
  for n in ast.walk(t):
   if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_cleanup':n.args=n.args[:2]
  self.assertEqual(hashlib.sha256(ast.dump(t,include_attributes=False).encode()).hexdigest(),'d9dac3f15753fab0b3a137a9baee460061b0f15c9a3a6a8d777631793573d171')
 def test_actual_stage_passes_real_output_and_supervisor_source(self):
  calls=[n for n in ast.walk(source)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require_cleanup']
  self.assertEqual(len(calls),1);self.assertEqual(ast.unparse(calls[0].args[2]),'run_dir');self.assertEqual(ast.unparse(calls[0].args[3]),'P(supervisor.__file__)')
if __name__=='__main__':unittest.main()
