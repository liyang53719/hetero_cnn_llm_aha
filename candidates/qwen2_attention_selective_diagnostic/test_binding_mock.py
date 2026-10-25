"""Stdlib observer-binding mocks only, not a real owner/NumPy/native cold run.

Use exact immutable R4 and reviewed source/code/lease helpers. Do not fork a
simplified lease sandbox or substitute this for the original negative suites.
"""
import argparse,ast,hashlib,importlib.util,json,os,resource,signal,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(1<<30,)*2);resource.setrlimit(resource.RLIMIT_CPU,(30,30));signal.alarm(45)
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--config',type=Path,required=True);parser.add_argument('--prior-harness',type=Path,required=True);parser.add_argument('--reviewed-tests-root',type=Path,required=True)
args,remaining=parser.parse_known_args();CONFIG=json.loads(args.config.read_text())
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
p=load('selective_binding',HERE/'selective_binding.py');art=load('artifacts',HERE/'artifacts.py')
original=load('_selective_reviewed_lease_fixture',args.reviewed_tests_root/'test_service_trace.py')
class Binding(unittest.TestCase):
 def setUp(self):self.saved={n:m for n,m in sys.modules.items() if n==p.PACKAGE or n.startswith(p.PACKAGE+'.') or n=='_selective_existing_project_code_gate'}
 def tearDown(self):
  for n in list(sys.modules):
   if n==p.PACKAGE or n.startswith(p.PACKAGE+'.') or n=='_selective_existing_project_code_gate':sys.modules.pop(n)
  sys.modules.update(self.saved)
 def test_normal_observer_only_full_module_code_binding(self):
  modules,receipt=p.load_candidate(CONFIG)
  self.assertEqual(set(modules),set(p.MODULES));self.assertFalse(receipt['ast_definition_test'])
  self.assertEqual({v['relative'] for v in receipt['module_exec_events']},{n+'.py' for n in p.MODULES})
  self.assertTrue(all(v['code_sha256'] and v['source_sha256'] for v in receipt['module_exec_events']))
  self.assertFalse(any(n.startswith('candidates.qwen2_resident_matrix') for n in sys.modules));self.assertNotIn('numpy',sys.modules)
 def test_pinned_candidate_source_drift_rejected(self):
  config=json.loads(json.dumps(CONFIG));path=str(Path(config['selective_root'])/'monitor.py');config['files'][path]['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'source drift'):p.load_candidate(config)
  self.assertNotIn(p.PACKAGE,sys.modules)
 def test_foreign_namespace_not_replaced(self):
  foreign=types.ModuleType(p.PACKAGE);sys.modules[p.PACKAGE]=foreign
  with self.assertRaisesRegex(ValueError,'fresh candidate'):p.load_candidate(CONFIG)
  self.assertIs(sys.modules[p.PACKAGE],foreign)
 def test_project_code_gate_reused_exact_origin(self):
  gate=p.load_source_gate(CONFIG)
  self.assertEqual(Path(gate.__file__),Path(CONFIG['project_code_gate_source']))
  self.assertEqual(gate.ProjectCodeGate.__enter__.__code__.co_filename,CONFIG['project_code_gate_source'])
  text=(HERE/'selective_binding.py').read_text();self.assertNotIn('class ProjectCodeGate',text)
 def test_exact_synthetic_namespace_registration_passes_existing_inventory(self):
  modules,receipt=p.load_candidate(CONFIG);inventory=load('_binding_inventory',HERE/'module_inventory.py')
  snapshot={n:m for n,m in sys.modules.items() if n==p.PACKAGE or n.startswith(p.PACKAGE+'.')}
  registration={p.PACKAGE:dict(kind='namespace_package',module=sys.modules[p.PACKAGE],paths=[CONFIG['selective_root']],allowed_children=list(p.MODULES),creator_source=str(HERE/'selective_binding.py'),creator_function=p.create_candidate_namespace)}
  report=inventory.collect_modules(snapshot,CONFIG['files'],namespaces={},synthetic=registration,registered_objects={})
  self.assertEqual(report['failures'],[])
  sys.modules[p.PACKAGE].foreign=types.ModuleType(p.PACKAGE+'.foreign');snapshot[p.PACKAGE+'.foreign']=sys.modules[p.PACKAGE].foreign
  report=inventory.collect_modules(snapshot,CONFIG['files'],namespaces={},synthetic=registration,registered_objects={})
  self.assertTrue(report['failures'])
 def make_fake_capture(self,modules):
  roles=('run','work','consume','matrix','op','tick','client');codes={}
  for name in roles:
   ns={};exec(compile('def '+name+'(): return 0','/fake/'+name,'exec'),ns);codes[name]=ns[name].__code__
  class FakeObservation:
   def __init__(self,owner,rows,base_fields,bindings,*,selective_lines=False):
    self.owner=owner;self.codes=codes;self.tool=None;self.closed=False;self.error=None;self.selective_lines=selective_lines;self.ast_test=False
   def monitor_masks(self):return {code:sys.monitoring.events.PY_RETURN|(0 if role in ('op','consume','tick') else sys.monitoring.events.LINE) for role,code in self.codes.items()}
   def _line(self,*a):pass
   def _return(self,*a):pass
   def __exit__(self,*a):self.stop();return False
  fake=dict(modules);fake['monitor']=types.SimpleNamespace(Observation=FakeObservation)
  capture=p.make_capture(fake,types.SimpleNamespace(state='idle',poison=False),2,None,{})
  return capture
 def test_actual_bridge_per_code_mask_install_and_cleanup_with_fake_owner(self):
  modules,receipt=p.load_candidate(CONFIG);mon=original.Monitor()
  with patch.object(sys,'monitoring',mon):
   cap=self.make_fake_capture(modules);cap.__enter__();before=p.mask_snapshot(cap,installed=True)
   cap.__exit__(None,None,None);after=p.mask_snapshot(cap,installed=False,previous=before)
   self.assertEqual((before['phase'],after['phase']),('installed','cleaned'));self.assertEqual(mon.slots,{})
   self.assertEqual(before['role_masks']['op'],mon.events.PY_RETURN)
   self.assertEqual(before['role_masks']['run'],mon.events.PY_RETURN|mon.events.LINE)
 def test_installed_mask_drift_is_not_accepted(self):
  modules,_=p.load_candidate(CONFIG);mon=original.Monitor()
  with patch.object(sys,'monitoring',mon):
   cap=self.make_fake_capture(modules);cap.__enter__();slot=cap.tool;code=cap.codes['op'];mon.locals[(slot,code)]=16
   with self.assertRaisesRegex(ValueError,'actual installed'):p.mask_snapshot(cap,installed=True)
   cap.stop();self.assertIsNotNone(cap.tool);self.assertEqual(mon.locals[(slot,code)],16)
 def test_remaining_foreign_cleanup_lease_is_not_accepted(self):
  modules,_=p.load_candidate(CONFIG);mon=original.Monitor()
  with patch.object(sys,'monitoring',mon):
   cap=self.make_fake_capture(modules);cap.__enter__();before=p.mask_snapshot(cap,installed=True)
   mon.slots[cap.tool]='foreign';cap.stop()
   with self.assertRaisesRegex(ValueError,'terminal cleanup'):p.mask_snapshot(cap,installed=False,previous=before)
   self.assertEqual(mon.slots[before['slot']],'foreign')
 def test_shared_real_driver_statements_are_ast_identical(self):
  old=ast.parse(args.prior_harness.read_text());new=ast.parse((HERE/'harness.py').read_text())
  oldfn=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner');newfn=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner')
  prior=next(n for n in oldfn.body if isinstance(n,ast.With));drive=next(n for n in newfn.body if isinstance(n,ast.FunctionDef) and n.name=='drive')
  start=next(i for i,n in enumerate(prior.body) if "actual owner job acceptance" in ast.unparse(n));before=prior.body[start:]
  start=next(i for i,n in enumerate(drive.body) if "actual owner job acceptance" in ast.unparse(n));after=drive.body[start:-1]
  self.assertEqual(ast.dump(ast.Module(body=before,type_ignores=[])),ast.dump(ast.Module(body=after,type_ignores=[])))
 def test_no_cost_probe_and_original_service_trace_constant(self):
  text=(HERE/'harness.py').read_text();self.assertNotIn('cost_probe',text);self.assertNotIn('SelectiveProbe',text)
  self.assertEqual(text.count('tracer=ServiceTrace(service,config,monitor.bind)'),1)
  self.assertIn("variant='off'",text);self.assertIn("candidate['bridge'].observe_driver",text)
 def test_terminal_reference_and_all_arm_raw_retention_static(self):
  text=(HERE/'worker.py').read_text()
  self.assertLess(text.index('control=compare_three'),text.index('guard.terminal=True'))
  self.assertLess(text.index('guard.terminal=True'),text.index('comparison=compare_original'))
  for item in ("'OUTPUT_'+str(index)","'SCORES_'+str(index)","'CAPTURE_'+str(index)","reference_out=out"):
   self.assertIn(item,text)
 def test_three_controls_include_both_on_pairs_and_fields(self):
  arms=[dict(observer_variant=v,terminal_acked=True,resources_released=True,capture_fields={'fake':i}) for i,v in enumerate(('off','original','selective_r4'))]
  arms[2].update(selective_binding={'status':'NORMAL_FULL_SOURCE_R4_BINDING_ONLY'},selective_masks=[{'phase':'installed'},{'phase':'cleaned'}]);pairs=[];fields=[]
  result=p.compare_three(arms,lambda a:pairs.append([x['observer_variant'] for x in a]) or 'PASS',lambda a,b:fields.append((a,b)))
  self.assertEqual(pairs,[['off','original'],['off','selective_r4']]);self.assertEqual(len(fields),1);self.assertFalse(result['performance_adopted'])
 def test_raw_serialization_exact_and_exclusive(self):
  with tempfile.TemporaryDirectory() as d:
   record=art.persist_words(d,'WORDS',[0x12345678,0x80000000]);self.assertEqual((Path(d)/record['file']).read_bytes(),bytes.fromhex('7856341200000080'))
   fields={'fake':dict(words=[1,2],observed=[1,0],frequency=[1,0],shape=[2])};r=art.persist_fields(d,'ARM',fields)
   self.assertEqual(r['fake']['frequency'],[1,0]);self.assertEqual((Path(d)/r['fake']['presence_file']).read_bytes(),b'\x01\x00')
   with self.assertRaises(FileExistsError):art.persist_words(d,'WORDS',[3])
 def test_original_reference_comparison_kept_exact(self):
  old=ast.parse(args.prior_harness.read_text());new=ast.parse((HERE/'harness.py').read_text())
  oldf=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='compare_fields');newf=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='compare_fields')
  self.assertEqual(ast.dump(oldf),ast.dump(newf))
 def test_cleanup_validation_is_excluded_from_clean_owner_interval(self):
  tree=ast.parse((HERE/'harness.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner')
  text=ast.unparse(fn)
  self.assertLess(text.index("stages.mark('actual_owner_job_through_terminal_ack_and_monitor_exit')"),text.index('mask_snapshot(capture, installed=False'))
  self.assertLess(text.index('mask_snapshot(capture, installed=True)'),text.index("stages.mark('monitor_enter')"))
  self.assertIn("stages.mark('post_timing_monitor_lifecycle_validation')",text)
 def test_all_three_reference_terminals_required_before_recipe_load(self):
  tree=ast.parse((HERE/'harness.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='compare_original')
  calls=[]
  def forbidden_path(*a):calls.append(a);raise AssertionError('oracle touched')
  scope=dict(need=p.need,Path=forbidden_path)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'reference_gate_fixture','exec'),scope)
  for missing in range(3):
   arms=[dict(terminal_acked=i!=missing,resources_released=True) for i in range(3)]
   with self.assertRaisesRegex(ValueError,'all three real terminals'):scope['compare_original']({},2,[],arms,reference_out='unused')
  for arms in ([],[dict(terminal_acked=True,resources_released=True)]*2,[dict(terminal_acked=True,resources_released=False)]*3):
   with self.assertRaisesRegex(ValueError,'all three real terminals'):scope['compare_original']({},2,[],arms,reference_out='unused')
  self.assertEqual(calls,[])
 def test_direct_reference_comparison_includes_selective_fields_and_outputs(self):
  text=(HERE/'harness.py').read_text();worker=(HERE/'worker.py').read_text()
  self.assertIn("compare_fields(arms[2]['capture_fields'],reference['fields'])",text)
  self.assertIn('comparison=compare_original(config,a.m,inputs,arms,reference_out=out)',worker)
  self.assertNotIn('reference_after_both_terminals',worker)
  self.assertEqual(CONFIG['observer_mode']['arms'],['off','original','selective_r4'])
 def test_source_gate_module_is_also_in_inventory(self):
  p.load_candidate(CONFIG);inventory=load('_gate_binding_inventory',HERE/'module_inventory.py')
  snapshot={'_selective_existing_project_code_gate':sys.modules['_selective_existing_project_code_gate']}
  result=inventory.collect_modules(snapshot,CONFIG['files'],namespaces={},synthetic={},registered_objects={})
  self.assertEqual(result['failures'],[])
 def test_runtime_isolation_payload_and_recipe_boundaries(self):
  tree=ast.parse((HERE/'worker.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Isolation')
  scope=dict(need=p.need,Path=Path,os=os);exec(compile(ast.Module(body=[cls],type_ignores=[]),'isolation_fixture','exec'),scope)
  guard=scope['Isolation'](CONFIG)
  oracle=CONFIG['oracle_harness'];qr=CONFIG['inputs']['qr']['path']
  guard.audit('open',(qr,'r',0))
  with self.assertRaisesRegex(ValueError,'independent reference before DUT terminal'):guard.audit('open',(oracle,'r',0))
  with self.assertRaisesRegex(ValueError,'reference/weight payload'):guard.audit('open',('/unapproved/reference.f32le','r',0))
  guard.terminal=True;guard.audit('open',(oracle,'r',0))
  with self.assertRaisesRegex(ValueError,'reference/weight payload'):guard.audit('open',('/unapproved/reference.f32le','r',0))
  for event,argv in [('ctypes.dlopen',('/unapproved/native.so',)),('socket.connect',()),('os.system',()),('import',('torch',))]:
   with self.assertRaises(ValueError):guard.audit(event,argv)
 def test_no_global_count_or_profiler_in_clean_entry(self):
  for name in ('harness.py','stage_clock.py','selective_binding.py','worker.py'):
   text=(HERE/name).read_text()
   self.assertNotIn('sys.setprofile(',text);self.assertNotIn('sys.settrace(',text);self.assertNotIn('SelectiveProbe(',text)
 def _exercise_real_driver_monitor_fault(self,enter_error=None,mask_error=None):
  modules,_=p.load_candidate(CONFIG);events=[];state={'service_error':None,'capture_error':None};receipts=[]
  class Context:
   def __enter__(self):return self
   def __exit__(self,*a):events.append('context_exit');return False
  class Capture(Context):
   def __enter__(self):
    if enter_error is not None:raise enter_error
    return self
  class Owner:
   state='idle';status=None
   def tick(self,**kw):
    if 'job' in kw:
     events.append(('job',state['capture_error'] is not None));return {'job_fire':True}
    if kw.get('response_ready'):
     events.append('terminal_ack');service.owner=None;return {'response_fire':True}
    self.state='finish';return {'memory_response_fire':False,'memory_fire':False}
  owner=Owner();service=types.SimpleNamespace(result=None,done=None,reset_required=False,owner=owner);scalar=types.SimpleNamespace(client=None)
  def snapshot(*a,**kw):
   if mask_error is not None:raise mask_error
   if enter_error is not None:raise ValueError('lease not installed after enter error')
   raise AssertionError('expected deliberate failure')
  tree=ast.parse((HERE/'harness.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner');drive=next(n for n in fn.body if isinstance(n,ast.FunctionDef) and n.name=='drive')
  scope=dict(candidate=modules,capture=Capture(),mask_receipts=receipts,mask_snapshot=snapshot,state=state,stages=types.SimpleNamespace(mark=lambda label:None),need=p.need,owner=owner,job=object(),output=[],scores={},counts={},sources=[],service=service,scalar=scalar,score_frame=lambda *a:None)
  code='def make_driver():\n    pending=None\n    held_checks=0\n'+''.join('    '+line+'\n' for line in ast.unparse(drive).splitlines())+'    return drive\n'
  exec(compile(code,'real_drive_fault_mock','exec'),scope);real_drive=scope['make_driver']()
  self.assertEqual(modules['bridge'].observe_driver(Context(),scope['capture'],real_drive,state),0)
  self.assertEqual(events[0],('job',True));self.assertIn('terminal_ack',events);self.assertIsNone(service.owner)
  self.assertEqual(receipts[0]['phase'],'installed_check_failed')
  # Execute the unchanged post-timing acceptance branch from the real harness.
  gate=next(n for n in fn.body if isinstance(n,ast.If) and 'candidate monitor lifetime failure' in ast.unparse(n))
  with self.assertRaisesRegex(ValueError,'candidate monitor lifetime failure'):exec(compile(ast.Module(body=[gate],type_ignores=[]),'real_post_terminal_gate_mock','exec'),scope)
  self.assertIn('terminal_ack',events)
 def test_capture_enter_failure_preserves_real_driver_terminal_before_rejection(self):
  self._exercise_real_driver_monitor_fault(enter_error=SystemExit('observer setup failure'))
 def test_installed_mask_failure_preserves_real_driver_terminal_before_rejection(self):
  self._exercise_real_driver_monitor_fault(mask_error=ValueError('mask drift'))
if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+remaining)
