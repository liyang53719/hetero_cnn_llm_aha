"""Pure exact production-function tests; not live admission or DUT qualification."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,types,unittest
W=pathlib.Path(__file__).resolve().parent;D=W/'source'if (W/'source/prepare_cloud_execution.py').is_file()else W
def load(path):
 m=types.ModuleType('pure');m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
mode=load(D/'execution_mode.py');policy=load(D/'profile_policy.py')
def need(x,m):
 if not x:raise ValueError(m)
def selected(path,names,extra):
 tree=ast.parse(path.read_text());parts=[x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))and x.name in names]
 need(len(parts)==len(names),'exact function set');ns={'need':need,**extra};exec(compile(ast.Module(body=parts,type_ignores=[]),str(path),'exec'),ns);return ns
class Test(unittest.TestCase):
 def setUp(self):self.a={'mode':mode.FIRST_FAULT,'profile_seconds':{'0':10800},'profile_max_active_cycles':{'0':1500000},'reviewed_budget_sha256':'a'*64,'diagnostic_profiles':[0]}
 def test_exact_selection_and_legacy(self):
  f=selected(D/'numeric/numeric_tail.py',{'execution_profiles'},{'profile_policy':policy,'execution_mode':mode})['execution_profiles']
  self.assertEqual(f({},self.a),[0]);self.assertEqual(f({},dict(self.a,mode=mode.STAGE)),list(range(5)))
  for diag in [[1],[0,1],[False],[]]:
   with self.assertRaises((ValueError,IndexError)):f({},dict(self.a,diagnostic_profiles=diag))
  with self.assertRaises(ValueError):f({'execution_policy':policy.policy(policy.DEFER)},self.a)
 def test_conservative_reservation(self):
  f=selected(D/'controller/cloud_flow.py',{'reservations'}, {})['reservations']
  q=dict(archives=180,weights=180,install=600,owner_bind=180,reference=600,provider=180,parent=600,calibration_seconds={str(i):300 for i in range(5)})
  b=dict(execution_mode=mode.FIRST_FAULT,budgets=q,job_budget_seconds=30000)
  m,t,total=f(b,self.a);self.assertEqual(t,10800+7*180+11*120+1530+600);self.assertEqual(total,m+t)
  with self.assertRaises(ValueError):f(dict(b,job_budget_seconds=total-1),self.a)
  with self.assertRaises(ValueError):f(dict(b,execution_mode=mode.STAGE),self.a)
 def test_consumer_argv_no_legacy_override(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=pathlib.Path(tmp)/'binding';p.write_text('{}');pin=dict(path=str(p),bytes=2,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
   def checked(x):need(x==pin,'actual tiny binding');return p
   f=selected(D/'numeric/numeric_tail.py',{'execution_command'},{'D':D/'numeric','execution_mode':mode,'material':types.SimpleNamespace(checked=checked)})['execution_command']
   b=dict(execution_context='CLOUD_EXECUTOR_V1',controller_binding=pin)
   argv,wall=f(['python',str(D/'numeric/consumer_owned.py')],b,self.a,0)
   self.assertEqual(wall,10830);self.assertEqual(argv[-4:],['--cloud-binding',str(p),'--cloud-binding-sha256',pin['sha256']]);self.assertNotIn('--stage-coverage-budget',argv)
   with self.assertRaises(ValueError):f(argv,b,self.a,0)
   with self.assertRaises(ValueError):f(['python',str(D/'numeric/consumer_owned.py')],b,self.a,1)
 def test_exact_mode_metadata(self):
  f=selected(D/'numeric/numeric_tail.py',{'mode_budget_fields'},{'execution_mode':mode})['mode_budget_fields']
  self.assertEqual(f(self.a),dict(full_budget_sha256=None,stage_budget_sha256=None,first_fault_document_sha256='a'*64,diagnostic_profiles=[0],not_selected_profiles=[1,2,3,4]))
 def test_explicit_preparation(self):
  f=selected(D/'prepare_cloud_execution.py',{'stage_coverage_input'},{'input_pin':lambda p,h,*a:dict(path=str(p),sha256=h)})['stage_coverage_input']
  a=types.SimpleNamespace(execution_mode=mode.FIRST_FAULT,model_candidate_review='review')
  self.assertEqual(f(a),{'execution_mode':mode.FIRST_FAULT})
  a.stage_coverage_budget='other';a.stage_coverage_budget_sha256='b'*64
  with self.assertRaises(ValueError):f(a)
 def test_reject_budget_mode_mismatch(self):
  f=selected(D/'prepare_cloud_execution.py',{'preserve_stage_coverage_input'}, {})['preserve_stage_coverage_input']
  with self.assertRaises(ValueError):f({},dict(execution_mode=mode.FIRST_FAULT))
  with self.assertRaises(ValueError):f(dict(execution_mode=mode.FIRST_FAULT),dict(execution_mode=mode.STAGE))
 def test_actual_flow_save_to_original_summary_scope_gate(self):
  source=ast.parse((D/'controller/cloud_flow.py').read_text());run=next(n for n in source.body if isinstance(n,ast.FunctionDef)and n.name=='run')
  calls=[n for n in ast.walk(run)if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='save'and any(isinstance(x,ast.Constant)and x.value=='FLOW_RESULT.json'for x in ast.walk(n.value.args[0]))]
  self.assertEqual(len(calls),1)
  summary=ast.parse((D/'summarize_cloud_execution.py').read_text());gates=[n for n in ast.walk(summary)if isinstance(n,ast.If)and isinstance(n.test,ast.Name)and n.test.id=='candidate'and any(isinstance(x,ast.Constant)and x.value=='actual flow candidate scope'for x in ast.walk(n))]
  self.assertEqual(len(gates),1)
  actual=selected(D/'controller/cloud_flow.py',{'save','pin','sha'},{'P':pathlib.Path,'json':json,'hashlib':hashlib})
  old='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL';new='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
  for selected_mode,candidate,want in [(mode.FIRST_FAULT,True,new),(mode.CALIBRATION,True,old),(mode.STAGE,True,old),(mode.FULL,True,old),(mode.CALIBRATION,False,'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL')]:
   with self.subTest(mode=selected_mode,candidate=candidate),tempfile.TemporaryDirectory()as tmp:
    job=pathlib.Path(tmp);bp=job/'binding.json';bp.write_text('{}');np=job/'numeric.json';np.write_text('{}');p=actual['pin'](bp)
    b={key:p for key in ('source_pins','executor_identity_pin','builder_handoff','artifact_manifest','cloud_budget','execution_approval','stage_coverage_budget')}
    if candidate:b['model_candidate_review']=p
    ns=dict(actual,job=job,b=b,identity={},builder={},limit=22200,binding_path=bp,admission=dict(self.a,mode=selected_mode),code=2,qualification={'status':'INCOMPLETE','numerical_pass':False},execution_policy={},history=[],imported={},disk_admission={},numeric_path=np)
    exec(compile(ast.fix_missing_locations(ast.Module(body=calls,type_ignores=[])),'actual_controller_flow_save','exec'),ns)
    flow=json.loads((job/'FLOW_RESULT.json').read_text());self.assertEqual(flow['scope'],want)
    gate=dict(need=need,candidate=candidate,flow=flow,b=b,review={'scope':want})
    exec(compile(ast.fix_missing_locations(ast.Module(body=gates,type_ignores=[])),'actual_summary_scope_gate','exec'),gate)
    if selected_mode==mode.FIRST_FAULT:
     flow['scope']=old
     with self.assertRaisesRegex(ValueError,'actual flow candidate scope'):exec(compile(ast.fix_missing_locations(ast.Module(body=gates,type_ignores=[])),'actual_summary_scope_gate','exec'),gate)
if __name__=='__main__':unittest.main()
