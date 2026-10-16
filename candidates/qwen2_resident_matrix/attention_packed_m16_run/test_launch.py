"""Cold control tests: no Torch, native library, reference or numerical job."""
import hashlib,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
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
  self.assertEqual(next(k.value.value for k in calls[0].keywords if k.arg=='wall_budget'),900)
 def test_default_cli_does_not_launch(self):
  argv=[]
  for key in ('source-root','origin','preparation-workspace','compile-receipt','compile-origin','workspace','python','contract-sha256'):argv.extend(['--'+key,'placeholder'])
  with patch.object(L,'load_contract',return_value=({},{})),patch.object(L,'launch',side_effect=AssertionError('execution')):
   self.assertEqual(L.main(argv),0)
 def repair_chain(self):
  base=dict(schema=1,profile='qwen2-public-pv16-packed-m16-linked-v1',execution_scope='ORIGINAL_M16_PUBLIC21',sources={'base.py':'1'*64},own={'own.py':'2'*64},generated={},inputs={'base.py':'1'*64,'own.py':'2'*64},targets=[])
  repair=dict(schema=1,prior_pins=L.digest(L.encoded(base)),own={L.REPAIR+n:'3'*64 for n in ('prepare.py','test_host_job.py','README.md')},generated={'candidates/qwen2_resident_matrix/attention_packed_m16/profile.py':'4'*64,'candidates/qwen2_resident_matrix/attention_packed_observation/pins.json':'5'*64,L.PREFIX+'pins.json':'6'*64})
  contract=dict(schema=1,profile=L.PROFILE,status='REVIEWED_SOURCE_EXECUTION_REQUIRES_ROOT_GATE',own_sources={n:'7'*64 for n in ('launch.py','driver.py','terminal_validator.py','test_launch.py','test_terminal_validator.py','README.md')},support_sources={'support.py':'8'*64},entry_pins_sha256=L.digest(L.encoded(base)),repair_pins_sha256=L.digest(L.encoded(repair)),runtime_entry_pins_sha256='6'*64,origin_commit='a'*40,python={},work_seconds=924,cleanup_seconds=5,outer_seconds=930,numeric_seconds=900,claims={k:False for k in L.FLAGS})
  return contract,base,repair
 def test_repair_chain_derived_runtime(self):
  c,b,r=self.repair_chain()
  with patch.object(L,'bounded_json',side_effect=[(L.encoded(v),v) for v in (c,b,r)]),patch.object(L,'verify_map'):
   _,actual=L.load_contract(L.digest(L.encoded(c)),Path('/synthetic'))
  self.assertEqual(set(actual['inputs']),{'base.py','own.py',*r['own']});self.assertEqual(actual['generated'],{k:v for k,v in r['generated'].items() if k!=L.PREFIX+'pins.json'})
 def test_repair_chain_rejects_wrong_prior(self):
  c,b,r=self.repair_chain();r['prior_pins']='9'*64;c['repair_pins_sha256']=L.digest(L.encoded(r))
  with patch.object(L,'bounded_json',side_effect=[(L.encoded(v),v) for v in (c,b,r)]),patch.object(L,'verify_map'),self.assertRaises(ValueError):L.load_contract(L.digest(L.encoded(c)),Path('/synthetic'))
 def test_repair_chain_rejects_unbound_runtime(self):
  c,b,r=self.repair_chain();c['runtime_entry_pins_sha256']='9'*64
  with patch.object(L,'bounded_json',side_effect=[(L.encoded(v),v) for v in (c,b,r)]),patch.object(L,'verify_map'),self.assertRaises(ValueError):L.load_contract(L.digest(L.encoded(c)),Path('/synthetic'))
 def test_repair_chain_rejects_extra_target(self):
  c,b,r=self.repair_chain();r['generated']['arbitrary.py']='9'*64;c['repair_pins_sha256']=L.digest(L.encoded(r))
  with patch.object(L,'bounded_json',side_effect=[(L.encoded(v),v) for v in (c,b,r)]),patch.object(L,'verify_map'),self.assertRaises(ValueError):L.load_contract(L.digest(L.encoded(c)),Path('/synthetic'))
 def test_contract_false_claims(self):
  self.assertEqual(L.FLAGS,('full_29_node_acceptance','rtl_execution','hardware_recipe_acceptance','useful_wall_mac_90_percent'))
if __name__=='__main__':unittest.main()
