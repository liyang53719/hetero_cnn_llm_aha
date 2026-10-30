import ast,hashlib,json,pathlib,tempfile,time,types,unittest,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
P=ROOT/'candidates/ci_frontend_pipeline_r2_20261029'
sys.path.insert(0,str(ROOT/'candidates/ci_frontend_materialization_r2_20261029'));import fresh_host as h
class Tests(unittest.TestCase):
 def test_nested_pins_twins(self):
  a=P/'driver_dependency_proof.py';b=ROOT/'candidates/same_job_materialization_20261029/consumer/driver_dependency_proof.py';self.assertEqual(a.read_bytes(),b.read_bytes())
  tree=ast.parse(a.read_text());pins=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PRODUCER_IMPLEMENTATION_PINS' for t in n.targets)))
  self.assertEqual(pins['one_job_build_only.py'],hashlib.sha256((P/'one_job_build_only.py').read_bytes()).hexdigest())
  conn=json.loads((ROOT/'candidates/same_job_materialization_20261029/CONNECTION_SOURCE_PINS.json').read_text());self.assertEqual(conn['consumer/driver_dependency_proof.py'],hashlib.sha256(b.read_bytes()).hexdigest())
 def test_final_stage_alias_retarget_fails(self):
  # Execute ONLY extracted orchestration with fake supervisor. No native inventory/build.
  source=ast.parse((P/'one_job_build_only.py').read_text());stage=next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name=='stage')
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);a=root/'a';b=root/'b';a.write_text('a');b.write_text('b');alias=root/'alias';alias.symlink_to(a)
   def need(x,m):
    if not x:raise ValueError(m)
   def fake(*args,**kwargs):alias.unlink();alias.symlink_to(b);return {'native_exit':0,'errors':[]}
   env=dict(pathlib=pathlib,time=time,need=need,b={'fresh_host_aliases':{str(alias):str(a)},'jdk_aliases':[],'materialized_roots':[],'pins':{}},disk_gate=lambda:None,job_budget=21000,start=time.monotonic(),out=root,repo=root,env={},supervise=types.SimpleNamespace(execute=fake),lock=root/'lock',stages=[])
   exec(compile(ast.Module(body=[stage],type_ignores=[]),'extracted-stage','exec'),env)
   with self.assertRaisesRegex(ValueError,'after stage'):env['stage']('last_stage',['not-executed'])
 def test_bootstrap_finally_covers_binding(self):
  p=ROOT/'candidates/same_job_execution_20261030/controller/bootstrap_samejob.py';source=p.read_text();tree=ast.parse(source);stage=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='stage')
  tries=[n for n in ast.walk(stage) if isinstance(n,ast.Try)]
  self.assertTrue(any(n.finalbody and 'check_fresh_aliases()' in ast.unparse(n.finalbody) for n in tries))
  self.assertLess(source.index("fresh_aliases=dict(host['aliases'])"),source.index("stage('binding'"))
 def test_gnu_missing_library_even_exit_zero(self):
  record=dict(schema='INSTALLED_GNU_BUILD_TOOLS_V1',qualification='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS',compile_tools={'cc1plus':'/usr/bin/cc1plus'},dynamic_dependencies={'cc1plus':'libmpc.so => not found'})
  with self.assertRaisesRegex(ValueError,'unresolved GNU'):h.validate_compile_inventory(record)
  record['dynamic_dependencies']['cc1plus']='libmpc.so => /lib/x86_64-linux-gnu/libmpc.so (0xff)';self.assertEqual(h.validate_compile_inventory(record),record)
 def test_jdk_context_only_trusted_roots(self):
  with tempfile.TemporaryDirectory() as d:
   home=pathlib.Path(d)/'jdk';(home/'lib/server').mkdir(parents=True)
   self.assertEqual(h.jdk_query_context(home),{'LD_LIBRARY_PATH':str(home/'lib/server')+':'+str(home/'lib')})
   (home/'lib/server').rmdir();(home/'lib/server').symlink_to(pathlib.Path(d))
   with self.assertRaisesRegex(ValueError,'inventoried home'):h.jdk_query_context(home)
 def test_jdk_context_not_build_environment(self):
  source=(ROOT/'candidates/ci_frontend_materialization_r2_20261029/fresh_host.py').read_text()
  self.assertIn("context=jdk_context if p.is_relative_to(jh) and p.suffix=='.so' else {}",source)
  boot=(ROOT/'candidates/same_job_execution_20261030/controller/bootstrap_samejob.py').read_text()
  self.assertNotIn('LD_LIBRARY_PATH',boot);self.assertIn('fresh_host.validate_compile_inventory',boot)
 def test_native_failure_metadata_is_fixed(self):
  r=h.failure_metadata(ValueError('unresolved ELF dependency /secret/never-upload'));self.assertEqual(r['reason'],'ELF_DEPENDENCY_UNRESOLVED');self.assertNotIn('secret',json.dumps(r))
  self.assertEqual(h.failure_metadata(RuntimeError('/private/context'))['reason'],'UNCLASSIFIED_EXCEPTION')
 def test_parent_failure_receipt_is_bounded(self):
  source=ast.parse((ROOT/'candidates/same_job_execution_20261030/controller/bootstrap_samejob.py').read_text());fn=next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name=='parent_failure')
  with tempfile.TemporaryDirectory() as d:
   env=dict(W=pathlib.Path(d),fresh={},json=json);exec(compile(ast.Module(body=[fn],type_ignores=[]),'extracted-parent-receipt','exec'),env)
   env['parent_failure']('GNU_RUNTIME_ADMISSION','GNU_RUNTIME_DEPENDENCIES_UNQUALIFIED')
   p=pathlib.Path(d)/'FRESH_HOST_PARENT_FAILURE.json';r=json.loads(p.read_text());self.assertEqual(r['schema'],'FRESH_HOST_PARENT_FAILURE_V1');self.assertLess(p.stat().st_size,1024)
 def test_transitive_pin_closure(self):
  num=ROOT/'candidates/same_job_execution_20261030/numeric';con=ROOT/'candidates/same_job_materialization_20261029/consumer'
  for name in ('driver_dependency_proof.py','consumption_proof.py','observation_contract.py','run_compare.py'):self.assertEqual((num/name).read_bytes(),(con/name).read_bytes())
  self.assertEqual((num/'driver_dependency_proof.py').read_bytes(),(P/'driver_dependency_proof.py').read_bytes())
  for parent,name in ((num,'CONNECTION_OWNED_SOURCE_PINS.json'),(con.parent,'CONNECTION_SOURCE_PINS.json')):
   for rel,want in json.loads((parent/name).read_text()).items():
    f=parent/rel
    if f.is_file():self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),want)
  d=json.loads((num/'MANIFEST.json').read_text())
  for row in d['files']:
   f=num/row['path']
   if f.is_file():self.assertEqual((f.stat().st_size,hashlib.sha256(f.read_bytes()).hexdigest()),(row['bytes'],row['sha256']))
  self.assertNotIn('candidates/ci_frontend_pipeline_r2_20261029/one_job_build_only.py',json.loads((num/'UNCHANGED_SOURCE_ROLES.json').read_text()))
if __name__=='__main__':unittest.main()
