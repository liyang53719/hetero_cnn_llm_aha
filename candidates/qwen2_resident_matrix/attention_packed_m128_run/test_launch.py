"""Cold control tests: no Torch, native library, reference or numerical job."""
import hashlib,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from contextlib import ExitStack,nullcontext
from types import SimpleNamespace
import ast
from . import launch as L

class ControlTests(unittest.TestCase):
 def test_typed_roundtrip_equality(self):
  self.assertTrue(L.same({'x':(1,2)},{'x':[1,2]}))
  for first,second in ((True,1),(1,1.0),(False,0)):
   with self.subTest(first=first,second=second):self.assertFalse(L.same({'x':first},{'x':second}))
 def test_duplicate_metadata(self):
  with self.assertRaises(ValueError):L.strict(b'{"a":1,"a":2}')
 def test_nonfinite(self):
  for word in ('NaN','Infinity','-Infinity','1e999'):
   with self.subTest(word=word),self.assertRaises(ValueError):L.strict(word.encode())
 def test_deep_metadata(self):
  with self.assertRaises(ValueError):L.strict(('['*42+'0'+']'*42).encode())
 def test_oversize(self):
  with self.assertRaises(ValueError):L.strict(b' '*(L.MAX_JSON+1))
 def test_atomic(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'x.json';L.atomic(path,{'a':1});L.atomic(path,{'a':2})
   self.assertEqual(L.bounded_json(path)[1],{'a':2});self.assertFalse(path.with_name('x.json.tmp').exists())
 def test_partial_file(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'x.json';path.write_bytes(b'{')
   with self.assertRaises(ValueError):L.bounded_json(path)
 def test_paths(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'x').write_bytes(b'x');(root/'alias').symlink_to(root/'x')
   with self.assertRaises(ValueError):L.safe(root/'alias')
   with self.assertRaises(ValueError):L.safe(root/'foo/../x')
 def test_source_drift(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'x').write_bytes(b'x');good={'x':L.digest(b'x')}
   self.assertEqual(L.verify_map(root,good),good);(root/'x').write_bytes(b'y')
   with self.assertRaises(ValueError):L.verify_map(root,good)
 def test_bad_source_names(self):
  with tempfile.TemporaryDirectory() as temp:
   for name in ('../x','/x','a//b','a/./b','a\\b'):
    with self.subTest(name=name),self.assertRaises(ValueError):L.verify_map(temp,{name:'0'*64})
 def test_source_digest_type(self):
  with tempfile.TemporaryDirectory() as temp:
   for value in (None,False,'G'*64,'a'*63):
    with self.subTest(value=value),self.assertRaises(ValueError):L.verify_map(temp,{'x':value})
 def test_environment(self):
  with patch.dict(os.environ,{},clear=True):
   env=L.clean_environment(Path('/tmp/control'));self.assertEqual(env['OMP_NUM_THREADS'],'4');self.assertEqual(env['GIT_NO_LAZY_FETCH'],'1');self.assertNotIn('SECRET',env)
  for key in L.OVERRIDES:
   with patch.dict(os.environ,{key:'1'},clear=True),self.assertRaises(ValueError):L.clean_environment(Path('/tmp/control'))
 def test_runtime_interpreter(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);py=root/'private/assets/venv/bin/python';py.parent.mkdir(parents=True);py.write_bytes(b'fake-executable-no-run')
   contract={'python':dict(implementation='CPython',version=[3,12,14],bytes=py.stat().st_size,sha256=L.sha_file(py))}
   self.assertEqual(L.runtime_python(root,py,contract),py)
   py.write_bytes(b'changed')
   with self.assertRaises(ValueError):L.runtime_python(root,py,contract)
 def test_runtime_path_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaises(ValueError):L.runtime_python(temp,Path(temp)/'other',{})
 def progress_fixture(self):return dict(schema=1,phase='numeric',ordinal=6,pid=123,elapsed_seconds=1.5,context_sha256='a'*64)
 def test_progress(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'p.json';v=self.progress_fixture();L.atomic(path,v)
   self.assertEqual(L.safe_progress(path,dict(child_pid=123,context_sha256='a'*64)),v)
 def test_progress_unknown(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'p.json';v=self.progress_fixture();v['payload']=[1];L.atomic(path,v)
   with self.assertRaises(ValueError):L.safe_progress(path,dict(child_pid=123,context_sha256='a'*64))
 def test_progress_stale_writer(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'p.json';v=self.progress_fixture();L.atomic(path,v)
   with self.assertRaises(ValueError):L.safe_progress(path,dict(child_pid=124,context_sha256='a'*64))
 def test_progress_bad_ordinal(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'p.json';v=self.progress_fixture();v['ordinal']=5;L.atomic(path,v)
   with self.assertRaises(ValueError):L.safe_progress(path,dict(child_pid=123,context_sha256='a'*64))
 def test_progress_bool_elapsed(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'p.json';v=self.progress_fixture();v['elapsed_seconds']=True;L.atomic(path,v)
   with self.assertRaises(ValueError):L.safe_progress(path,dict(child_pid=123,context_sha256='a'*64))
 def test_deadline_expired(self):
  with self.assertRaises(ValueError):
   with L.deadline(time.monotonic()-1):pass
 def test_deadline_control_process(self):
  code='''import sys,time\nsys.path.insert(0,sys.argv[1])\nfrom launch import deadline\ntry:\n with deadline(time.monotonic()+0.03):time.sleep(1)\nexcept TimeoutError:raise SystemExit(0)\nraise SystemExit(4)'''
  p=subprocess.run([sys.executable,'-I','-B','-c',code,str(L.HERE)],capture_output=True,timeout=3)
  self.assertEqual(p.returncode,0,p.stderr.decode())
 def test_child_unblocks_inherited_signals(self):
  code='''import signal,subprocess,sys\nblocked={signal.SIGALRM,signal.SIGTERM,signal.SIGINT}\nsignal.pthread_sigmask(signal.SIG_BLOCK,blocked)\nchild="import signal,sys;sys.path.insert(0,sys.argv[1]);import driver;raise SystemExit(3 if signal.pthread_sigmask(signal.SIG_BLOCK,set()) & {signal.SIGALRM,signal.SIGTERM,signal.SIGINT} else 0)"\np=subprocess.run([sys.executable,'-I','-B','-c',child,sys.argv[1]],timeout=2)\nraise SystemExit(p.returncode)'''
  p=subprocess.run([sys.executable,'-I','-B','-c',code,str(L.HERE)],capture_output=True,timeout=4)
  self.assertEqual(p.returncode,0,p.stderr.decode())
 def test_exact_isolated_driver_import(self):
  p=subprocess.run([sys.executable,'-I','-B',str(L.HERE/'driver.py'),'invalid'],capture_output=True,timeout=3)
  self.assertNotEqual(p.returncode,0);self.assertIn('exact child invocation',p.stderr.decode());self.assertNotIn('ModuleNotFoundError',p.stderr.decode())
 def test_one_original_run_call(self):
  import ast
  tree=ast.parse((L.HERE/'driver.py').read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='entry' and n.func.attr=='run']
  self.assertEqual(len(calls),1)
  self.assertEqual(next(k.value.value for k in calls[0].keywords if k.arg=='wall_budget'),2400)
 def test_default_cli_does_not_launch(self):
  argv=[]
  for key in ('source-root','origin','m16-prerequisite','compile-receipt','compile-origin','workspace','python','contract-sha256'):argv.extend(['--'+key,'placeholder'])
  with patch.object(L,'load_contract',return_value=({},{})),patch.object(L,'launch',side_effect=AssertionError('execution')):
   self.assertEqual(L.main(argv),0)
 def entry_chain(self):
  sources={f'file{i}.py':'1'*64 for i in range(344)}
  asset='candidates/qwen2_resident_matrix/attention_packed_m128_assets/pins.json';sources[asset]='2'*64
  base=dict(schema=1,profile='qwen2-public-pv16-packed-m128-linked-v1',execution_scope='ORIGINAL_M128_PUBLIC21',sources=sources,own={},generated={},inputs=dict(sources),targets=[])
  entry=L.digest(L.encoded(base));runtime=dict(sources);runtime[L.PREFIX+'pins.json']=entry
  contract=dict(schema=1,profile=L.PROFILE,status='PREPARED_SOURCE_EXECUTION_REQUIRES_ROOT_GATE',own_sources={n:'7'*64 for n in ('launch.py','driver.py','terminal_validator.py','test_launch.py','test_terminal_validator.py','README.md')},support_sources={'support.py':'8'*64},entry_pins_sha256=entry,assets_pins_sha256='2'*64,runtime_source_count=346,runtime_source_manifest_sha256=L.digest(L.compact(runtime)),origin_commit='a'*40,python={},work_seconds=2424,cleanup_seconds=5,outer_seconds=2430,numeric_seconds=2400,claims={k:False for k in L.FLAGS})
  return contract,base
 def load_fixture(self,c,b):
  with patch.object(L,'bounded_json',side_effect=[(L.encoded(v),v) for v in (c,b)]),patch.object(L,'verify_map'):
   return L.load_contract(L.digest(L.encoded(c)),Path('/synthetic'))
 def test_full_m128_chain(self):
  c,b=self.entry_chain();self.assertEqual(self.load_fixture(c,b),(c,b))
 def test_origin_assets_bound(self):
  c,b=self.entry_chain();c['assets_pins_sha256']='3'*64
  with self.assertRaises(ValueError):self.load_fixture(c,b)
 def test_runtime_count_strict(self):
  for count in (345,347,True,346.0):
   c,b=self.entry_chain();c['runtime_source_count']=count
   with self.subTest(count=count),self.assertRaises(ValueError):self.load_fixture(c,b)
 def test_runtime_manifest_bound(self):
  c,b=self.entry_chain();c['runtime_source_manifest_sha256']='3'*64
  with self.assertRaises(ValueError):self.load_fixture(c,b)
 def test_no_m16_profile_alias(self):
  c,b=self.entry_chain();b['profile']='qwen2-public-pv16-packed-m16-linked-v1';c['entry_pins_sha256']=L.digest(L.encoded(b))
  with self.assertRaises(ValueError):self.load_fixture(c,b)
 def test_budget_alias_rejected(self):
  for key,value in (('numeric_seconds',900),('work_seconds',2424.0),('cleanup_seconds',True),('outer_seconds',2431)):
   c,b=self.entry_chain();c[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.load_fixture(c,b)
 def test_large_report_control_remains_small(self):
  value={str(i):'x'*4096 for i in range(1300)}
  raw=L.encoded(value);self.assertGreater(len(raw),4*1024*1024)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'report.json';p.write_bytes(raw)
   with self.assertRaises(ValueError):L.bounded_json(p)
   self.assertEqual(L.terminal_report(p,value)[1],value)
 def test_report_strict_canonical_types(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'report.json';p.write_bytes(b'{"x":1}')
   self.assertEqual(L.terminal_report(p,{'x':1})[1],{'x':1})
   for value in (True,1.0):
    with self.subTest(value=value),self.assertRaises(ValueError):L.terminal_report(p,{'x':value})
   for raw in (b'{"x":1,"x":1}',b'{"x":NaN}',b'{'):
    p.write_bytes(raw)
    with self.assertRaises(ValueError):L.terminal_report(p,{'x':1})
 def test_report_oversize(self):
  from . import terminal_validator as V
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'report.json';p.write_bytes(b' '*(V.MAX_JSON+1))
   with self.assertRaises(ValueError):L.terminal_report(p,{})
 def test_isolated_parent_loads_exact_sibling_and_report(self):
  code="""import hashlib,runpy,sys
from pathlib import Path
ns=runpy.run_path(sys.argv[1],run_name='cold_isolated_parent')
terminal=ns['terminal_module']()
if Path(terminal.__file__).resolve()!=Path(sys.argv[1]).parent/'terminal_validator.py':raise SystemExit(7)
if hashlib.sha256(Path(terminal.__file__).read_bytes()).hexdigest()!=sys.argv[3]:raise SystemExit(8)
raw,value=ns['terminal_report'](sys.argv[2],{'x':1})
if value!={'x':1} or terminal.ROWS!=128:raise SystemExit(9)
for alias in (True,1.0):
 try:ns['terminal_report'](sys.argv[2],{'x':alias})
 except ValueError:pass
 else:raise SystemExit(10)
"""
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'synthetic.json';path.write_bytes(b'{"x":1}')
   proc=subprocess.run([sys.executable,'-I','-B','-c',code,str(L.HERE/'launch.py'),str(path),L.sha_file(L.HERE/'terminal_validator.py')],capture_output=True,timeout=3,cwd=d)
   self.assertEqual(proc.returncode,0,proc.stderr.decode())
 def test_parent_postflight_uses_verified_loader(self):
  tree=ast.parse((L.HERE/'launch.py').read_text())
  fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='launch')
  calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='terminal_module']
  self.assertEqual(len(calls),1)
 def test_exact_origin_only_admission_keywords(self):
  tree=ast.parse((L.HERE/'driver.py').read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='seal_manifest']
  self.assertEqual(len(calls),1)
  self.assertEqual({k.arg for k in calls[0].keywords},{'origin','m16_prerequisite','compile_receipt','compile_origin'})
  self.assertNotIn('produce(', (L.HERE/'driver.py').read_text())
 def test_genuine_clone_and_same_pid_exec(self):
  source=(L.HERE/'driver.py').read_text()
  self.assertIn("['git','clone','--no-hardlinks','--no-checkout'",source)
  self.assertIn("os.execv(context['python']",source)
  self.assertIn("'-I','-B'",source)
  self.assertIn("['git','show','HEAD:'+cpp]",source)
  tree=ast.parse((L.HERE/'launch.py').read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='Popen']
  self.assertEqual(len(calls),1)
 def mock_failure(self,*,existing=False,cleanup=True,wait_error=None,cancel_unblock=False,save_error=False,child_phase='numeric'):
  with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
   root=Path(d)
   for name in ('source','origin','prerequisite','compile_origin'):(root/name).mkdir()
   compiled=root/'BUILD.json';compiled.write_text('{}')
   work=root/'attempt'
   if existing:
    work.mkdir();(work/'summary.json').write_text('untouched');(work/'ATTEMPT_LOCK').write_text('owned')
   args=SimpleNamespace(source_root=str(root/'source'),origin=str(root/'origin'),m16_prerequisite=str(root/'prerequisite'),compile_receipt=str(compiled),compile_origin=str(root/'compile_origin'),workspace=str(work),python='/fixture/python',contract_sha256='a'*64)
   stack.enter_context(patch.object(L.sys,'flags',SimpleNamespace(optimize=0)))
   stack.enter_context(patch.object(L,'load_contract',return_value=({},{})))
   stack.enter_context(patch.object(L,'runtime_python',return_value=Path('/fixture/python')))
   stack.enter_context(patch.object(L,'deadline',side_effect=lambda stop:nullcontext(stop)))
   stack.enter_context(patch.object(L,'clean_environment',return_value={}))
   p=Mock();p.protected_cleanup.side_effect=lambda:nullcontext()
   sup=Mock();sup.enable_subreaper.return_value=object()
   child=Mock();child.wait.side_effect=wait_error or ValueError('private secret');child.terminate.return_value=cleanup;sup.Child.return_value=child
   stack.enter_context(patch.object(L,'support',return_value=(p,sup)))
   process=Mock(pid=42);spawn=stack.enter_context(patch.object(L.subprocess,'Popen',return_value=process))
   def mask(action,signals):
    if cancel_unblock and action==signal.SIG_SETMASK:
     self.assertTrue(sup.Child.called);raise InterruptedError('private cancel')
    return set()
   stack.enter_context(patch.object(L.signal,'pthread_sigmask',side_effect=mask))
   stack.enter_context(patch.object(L,'safe_progress',return_value={'phase':child_phase}))
   clock=[100.0];stack.enter_context(patch.object(L.time,'monotonic',side_effect=lambda:clock[0]))
   original=L.atomic
   def save(path,value):
    if save_error and path.name=='summary.json':raise OSError('private disk failure')
    return original(path,value)
   stack.enter_context(patch.object(L,'atomic',side_effect=save))
   value=L.launch(args)
   self.assertNotIn('private',json.dumps(value));self.assertNotIn('secret',json.dumps(value))
   if existing:
    spawn.assert_not_called();self.assertEqual((work/'summary.json').read_text(),'untouched');self.assertEqual((work/'ATTEMPT_LOCK').read_text(),'owned')
   else:
    spawn.assert_called_once();self.assertTrue(spawn.call_args.kwargs['start_new_session']);child.terminate.assert_called_once_with(105.0)
    self.assertTrue((work/'ATTEMPT_LOCK').is_file());self.assertFalse((work/'control/CHILD_COMPLETE.json').exists())
   return value
 def test_replay_never_overwrites_existing_evidence(self):self.assertEqual(self.mock_failure(existing=True)['status'],'FAILED')
 def test_failure_after_numerical_started_is_not_completed(self):
  v=self.mock_failure();self.assertTrue(v['numerical_run_started']);self.assertFalse(v['actual_chain_completion_verified']);self.assertEqual(v['status'],'FAILED')
 def test_failure_before_numerical_not_started(self):self.assertFalse(self.mock_failure(child_phase='admission')['numerical_run_started'])
 def test_cancel_after_spawn_is_owned_and_cleaned(self):self.assertEqual(self.mock_failure(cancel_unblock=True)['status'],'CANCELLED')
 def test_timeout_is_cleaned_with_receipt_reserve(self):self.assertEqual(self.mock_failure(wait_error=TimeoutError())['status'],'TIMEOUT')
 def test_cleanup_failure_never_passes(self):
  value=self.mock_failure(cleanup=False);self.assertEqual(value['status'],'FAILED_CLEANUP');self.assertFalse(value['cleanup_complete'])
 def test_publication_failure_never_claims_completion(self):
  value=self.mock_failure(save_error=True);self.assertEqual(value['status'],'FAILED_PUBLICATION');self.assertFalse(value['actual_chain_completion_verified'])
 def test_cleanup_deadline_reserves_receipt_second(self):
  tree=ast.parse((L.HERE/'launch.py').read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='terminate']
  self.assertEqual(len(calls),1)
  arg=ast.Expression(calls[0].args[0]);ast.fix_missing_locations(arg)
  with patch.object(L.time,'monotonic',return_value=2424):self.assertEqual(eval(compile(arg,'<cold>','eval'),{'time':L.time,'min':min,'outer':2430}),2429)
 def test_contract_false_claims(self):
  self.assertEqual(L.FLAGS,('full_29_node_acceptance','rtl_execution','hardware_recipe_acceptance','useful_wall_mac_90_percent'))
if __name__=='__main__':unittest.main()
