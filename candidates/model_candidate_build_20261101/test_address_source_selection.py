# Only historical source/AST assertions use the exact finite-layer inverse.
# Runtime tests still import and execute the actual candidate implementations.
import pathlib as _finite_pathlib, importlib.util as _finite_importlib
_finite_path=_finite_pathlib.Path(__file__).resolve().parents[2]/'candidates/model_candidate_build_20261101/finite_watchdog_test_inverse.py'
_finite_spec=_finite_importlib.spec_from_file_location('finite_watchdog_test_inverse',_finite_path)
_finite_module=_finite_importlib.module_from_spec(_finite_spec);_finite_spec.loader.exec_module(_finite_module)
prior_text=_finite_module.prior_text;prior_sha=_finite_module.prior_sha
"""Source/metadata-only exact source-selection and packaging joins; no EDA/DUT.
Fixtures copy public Scala/contract bytes only. No runtime/model data is read.
"""
import argparse,ast,copy,hashlib,importlib.util,json,os,pathlib,shutil,sys,tempfile,time,types,unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent;R=D.parents[1];N=R/'candidates/transposed_tile_address_fix_20261103'
sys.path.insert(0,str(D))
import candidate_generation_gate as gate
import candidate_dependency_proof as proof
import pack_model_candidate as pack
import prepare_model_build as prepare
import restore_model_inputs as restore
import test_first_fault_entry_flow as flow

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+'\n');return p

class Selection(unittest.TestCase):
 def test_legacy_default_and_exact_new_source_delta(self):
  old=gate.selected_inputs(R);new=gate.selected_inputs(R,gate.ADDRESS_SOURCE)
  self.assertEqual(old['contract_sha256'],'3354827c1c9d2ac167b3b325dc07acbd50ea663ddd384dddfea1b1d037ae3851')
  self.assertEqual(old['overlay'],D/'MODEL_SOURCE_OVERLAY.json');self.assertEqual(new['overlay'],N/'MODEL_SOURCE_OVERLAY.json')
  original=json.loads((R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
  for selected in (old,new):self.assertEqual(len(gate.checked_paths(R,selected['overlay'],original,selected['contract'])),159)
  o=json.loads(old['overlay'].read_text());n=json.loads(new['overlay'].read_text())
  self.assertEqual([r['name']for r,p in zip(n['files'],o['files'])if r!=p],['TransposedDenseBanks.scala'])
  self.assertEqual(len(n['changed_names']),8);self.assertEqual(155-len(n['changed_names']),147);self.assertEqual(n['added_names'],o['added_names'])
  self.assertEqual({k:v for k,v in new['contract'].items()if k!='source_overlay_sha256'},{k:v for k,v in old['contract'].items()if k!='source_overlay_sha256'})
 def test_no_observed_hash_authorization_or_arbitrary_selector(self):
  for name in ('../else','TRANSPOSED','',None,True,'candidates/transposed_tile_address_fix_20261103'):
   with self.subTest(name=name),self.assertRaises(ValueError):gate.selected_inputs(R,name)
  with tempfile.TemporaryDirectory()as t:
   p=write(pathlib.Path(t)/'GENERATION_CONTRACT.json',dict(gate.selected_inputs(R)['contract'],source_overlay_sha256='a'*64))
   with self.assertRaisesRegex(ValueError,'source review not frozen'):gate.load_contract(p,sha(p))
 def test_diagnostic_combinations_reject_before_inputs(self):
  for flags in ((True,False),(False,True),(True,True)):
   with self.subTest(flags=flags),self.assertRaises(ValueError):gate.selected_inputs(pathlib.Path('/absent'),gate.ADDRESS_SOURCE,*flags)
   with self.assertRaises(ValueError):prepare.run(argparse.Namespace(hardware_source=gate.ADDRESS_SOURCE,first_fault_readonly=flags[0],terminal_finite_readonly=flags[1]))
 def test_both_restore_paths_are_source_inventory_only(self):
  with mock.patch.object(restore,'acquire',side_effect=AssertionError('no download')):
   for name in gate.SOURCE_CHOICES:
    r=restore.run(verify_only=True,hardware_source=name);self.assertEqual(r['status'],'SOURCE_AND_JAR_INVENTORY_VERIFIED_ONLY');self.assertEqual(r['source_count'],159);self.assertFalse(r['compiler_executed'])
  self.assertEqual(restore.GENERATION_GATE_SHA256,sha(D/'candidate_generation_gate.py'))
 def test_actual_prepare_bootstrap_materializer_selector_join(self):
  e=flow.EntryFlow(methodName='runTest');e.setUp();self.addCleanup(e.doCleanups);ip,identity=e.identity()
  m=flow.load('_address_prepare',e.c/'prepare_model_build.py');clock=write(e.root/'clock.json',dict(schema='SPLIT_BUILD_JOB_START_V1',job_budget_seconds=9000,run_id=identity['run_id'],launch_commit=identity['launch_commit'],started_monotonic=time.monotonic()))
  args=argparse.Namespace(repo=e.repo,work=e.root/'work',identity=ip,job_start=clock,first_fault_readonly=False,terminal_finite_readonly=False,hardware_source=gate.ADDRESS_SOURCE)
  original=pathlib.Path.read_text
  def read(p,*a,**k):return 'MemAvailable: 999999999 kB\n'if str(p)=='/proc/meminfo'else original(p,*a,**k)
  fresh=types.SimpleNamespace(validate_contract=lambda *a:None,reject_injection=lambda *a:None)
  with mock.patch.dict(os.environ,e.env,clear=True),mock.patch.object(m,'source_pins',return_value='a'*64),mock.patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=1<<50)),mock.patch.object(m.platform,'machine',return_value='x86_64'),mock.patch.object(m.sys,'version_info',(3,12)),mock.patch.object(pathlib.Path,'read_text',read),mock.patch.dict(sys.modules,{'fresh_host':fresh}),mock.patch.object(m.os,'execve')as ex:m.run(args)
  argv=ex.call_args.args[1];self.assertEqual(argv[argv.index('--hardware-source')+1],gate.ADDRESS_SOURCE)
  binding,v=e.bootstrap_args(argv);self.assertEqual(v.hardware_source,gate.ADDRESS_SOURCE);self.assertEqual(binding[binding.index('--hardware-source')+1],gate.ADDRESS_SOURCE)
  f=flow.function(D/'bootstrap_model_candidate.py','main');jars=[n for n in f.body if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='stage'and n.value.args[0].value=='jars'];calls=[]
  flow.execute_nodes(jars,dict(stage=lambda *a:calls.append(a),py=sys.executable,C=D,W=e.root,v=v));jarargv=calls[0][1];self.assertEqual(jarargv[jarargv.index('--hardware-source')+1],gate.ADDRESS_SOURCE)
  f=flow.function(D/'materialize_model_binding.py','main');nodes=[]
  for n in f.body:
   nodes.append(n)
   if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='v'for t in n.targets):break
  with mock.patch.object(sys,'argv',['materializer']+binding[3:]):env=dict(argparse=argparse,pathlib=pathlib);flow.execute_nodes(nodes,env)
  select=[n for n in f.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='selection'for t in n.targets)]
  env.update(R=R,selected_inputs=gate.selected_inputs);flow.execute_nodes(select,env);self.assertEqual(env['selection']['overlay'],N/'MODEL_SOURCE_OVERLAY.json')
 def test_bootstrap_and_materializer_reject_mixed_selector_before_work(self):
  f=flow.function(D/'bootstrap_model_candidate.py','main')
  reject=[n for n in f.body if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='need'and any(isinstance(a,ast.Constant)and a.value=='new hardware cannot use unchanged-SV diagnostic contracts'for a in n.value.args)]
  self.assertEqual(len(reject),1)
  material=flow.function(D/'materialize_model_binding.py','main');select=[n for n in material.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='selection'for t in n.targets)]
  for ff,term in ((True,False),(False,True)):
   v=argparse.Namespace(hardware_source=gate.ADDRESS_SOURCE,first_fault_readonly=ff,terminal_finite_readonly=term)
   with self.assertRaises(ValueError):flow.execute_nodes(reject,dict(v=v,need=gate.need))
   with self.assertRaises(ValueError):flow.execute_nodes(select,dict(v=v,R=pathlib.Path('/absent'),selected_inputs=gate.selected_inputs))

class BindingAndPack(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.repo=pathlib.Path(t.name)/'repo';self.repo.mkdir()
  selected=gate.selected_inputs(R,gate.ADDRESS_SOURCE);original=json.loads((R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
  paths=list(map(pathlib.Path,gate.checked_paths(R,selected['overlay'],original,selected['contract'])))
  paths += [selected['overlay'],selected['contract_path'],D/'GENERATION_CONTRACT.json',D/'MODEL_SOURCE_OVERLAY.json',D/'MODEL_CANDIDATE_PRECONDITIONS.json',D/'candidate_generation_gate.py',R/'candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json',R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json',R/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json',R/'candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp']
  for p in set(paths):q=self.repo/p.relative_to(R);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
  files=[p for p in self.repo.rglob('*')if p.is_file()];cat=write(self.repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=[dict(path=str(p.relative_to(self.repo)),bytes=p.stat().st_size,sha256=sha(p))for p in files]))
  selected=gate.selected_inputs(self.repo,gate.ADDRESS_SOURCE);self.overlay=selected['overlay'];pins={str(p):sha(p)for p in files+[cat]};self.catalog=cat
  self.b=dict(repo=str(self.repo),hardware_source=gate.ADDRESS_SOURCE,generation_contract=str(selected['contract_path']),generation_contract_sha256=selected['contract_sha256'],fixed_source_overlay=str(self.overlay),pins=pins,unchanged_module_contract=str(self.repo/'candidates/model_candidate_build_20261101/MODEL_CANDIDATE_PRECONDITIONS.json'),host_port_contract=str(self.repo/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json'),driver=str(self.repo/'candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),candidate_status='UNREVIEWED_MODEL_BUILD',numeric_execution_authorized=False)
  self.closure=dict(generation_contract_sha256=gate.ADDRESS_GENERATION_CONTRACT_SHA256,source_overlay=dict(bytes=self.overlay.stat().st_size,sha256=sha(self.overlay)),source_count=159,source_pins_sha256=sha(cat))
  self.obs=dict(source_closure=self.closure)
  self.source=dict(generation_input_pins=pins,fixed_source_overlay=str(self.overlay),model_candidate_observation=self.obs,model_candidate_build_evidence=dict(fixed_source_overlay=dict(path=str(self.overlay),bytes=self.overlay.stat().st_size,sha256=sha(self.overlay),text=self.overlay.read_text())))
 def test_real_selected_binding_and_pack_source_identity(self):
  gate.require_generation_binding(self.b);pack.address_source_identity(self.source,self.obs)
 def test_path_identity_omission_and_wrong_source_rejected(self):
  for key,value in [('hardware_source','legacy'),('generation_contract',str(self.repo/'candidates/model_candidate_build_20261101/GENERATION_CONTRACT.json')),('generation_contract_sha256',gate.GENERATION_CONTRACT_SHA256),('fixed_source_overlay',str(self.repo/'candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json'))]:
   b=copy.deepcopy(self.b);b[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):gate.require_generation_binding(b)
  b=copy.deepcopy(self.b);del b['hardware_source']
  with self.assertRaises(ValueError):gate.require_generation_binding(b)
  target=self.repo/'candidates/transposed_tile_address_fix_20261103/source/TransposedDenseBanks.scala';target.write_bytes(target.read_bytes()+b'\n')
  with self.assertRaises(ValueError):gate.require_generation_binding(self.b)
 def test_selected_source_and_catalog_must_be_pinned(self):
  bank=str(self.repo/'candidates/transposed_tile_address_fix_20261103/source/TransposedDenseBanks.scala')
  for path in (bank,str(self.catalog)):
   b=copy.deepcopy(self.b);b['pins'].pop(path)
   with self.subTest(path=path),self.assertRaises(ValueError):gate.require_generation_binding(b)
  cat=json.loads(self.catalog.read_text());cat['files']=[r for r in cat['files']if r['path']!='candidates/transposed_tile_address_fix_20261103/source/TransposedDenseBanks.scala'];write(self.catalog,cat);self.b['pins'][str(self.catalog)]=sha(self.catalog)
  with self.assertRaises(ValueError):gate.require_generation_binding(self.b)
 def test_pack_new_generation_overlay_cannot_cross_bind(self):
  for key,value in [('generation_contract_sha256',gate.GENERATION_CONTRACT_SHA256),('source_overlay',dict(bytes=1,sha256=gate.LEGACY_OVERLAY_SHA256)),('source_count',158)]:
   c=copy.deepcopy(self.closure);c[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):pack.address_generation_observation(c)
  for field in ('generation_input_pins','fixed_source_overlay','model_candidate_build_evidence'):
   s=copy.deepcopy(self.source);s.pop(field)
   with self.subTest(field=field),self.assertRaises(ValueError):pack.address_source_identity(s,self.obs)
  with self.assertRaises(ValueError):pack.address_source_identity(self.source,self.obs,True)
 def test_actual_pack_generation_join_rejects_bad_binding_or_catalog(self):
  f=flow.function(D/'pack_model_candidate.py','_pack_impl');nodes=[n for n in f.body if isinstance(n,ast.If)and 'address_generation_observation'in ast.unparse(n.test)];self.assertEqual(len(nodes),1)
  env=dict(address_generation_observation=pack.address_generation_observation,original=self.b,b=copy.deepcopy(self.b),obs=self.obs,overlay=self.overlay,need=pack.need,P=pathlib.Path,sha=sha,ADDRESS_GENERATION_SHA=pack.ADDRESS_GENERATION_SHA,source_generation=pack.source_generation,SOURCE_GENERATIONS=pack.SOURCE_GENERATIONS,SUPPLY_GENERATION_SHA=pack.SUPPLY_GENERATION_SHA)
  flow.execute_nodes(nodes,env)
  env['b']['hardware_source']='legacy'
  with self.assertRaises(ValueError):flow.execute_nodes(nodes,env)
  env['b']=copy.deepcopy(self.b);env['obs']=copy.deepcopy(self.obs);env['obs']['source_closure']['source_pins_sha256']='f'*64
  with self.assertRaises(ValueError):flow.execute_nodes(nodes,env)
 def test_legacy_modes_retain_exact_prediagnostic_producer_bytes(self):
  self.source['generation_input_pins']=dict(self.source['generation_input_pins'])
  self.source['generation_input_pins'][str(self.repo/'candidates/model_candidate_build_20261101/candidate_generation_gate.py')]=proof.SELECTOR_IMPLEMENTATION_PINS['candidates/model_candidate_build_20261101/candidate_generation_gate.py']
  self.source['fixed_source_overlay']=str(self.repo/'candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json')
  self.closure['generation_contract_sha256']=gate.GENERATION_CONTRACT_SHA256;self.closure['source_overlay']['sha256']=gate.LEGACY_OVERLAY_SHA256
  for mode in (None,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V1'},{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V2'}):
   selected=proof.selector_producer_policy(self.source,mode)
   with self.subTest(mode=mode):
    self.assertIsNotNone(selected)
    for rel,h in selected.items():
     # This test intentionally selects retained pre-diagnostic producer modes.
     if rel.endswith('/one_job_model_candidate.py'):self.assertEqual(h,'7e04700f063728cf1df376a563565830f7e1544f8b2e439b507cc649975749ff')
     else:self.assertEqual(prior_sha(R/rel),h,rel)
  b=copy.deepcopy(self.b);b.update(hardware_source='legacy',generation_contract=str(self.repo/'candidates/model_candidate_build_20261101/GENERATION_CONTRACT.json'),generation_contract_sha256=gate.GENERATION_CONTRACT_SHA256,fixed_source_overlay=self.source['fixed_source_overlay']);gate.require_generation_binding(b)
  del b['hardware_source'];gate.require_generation_binding(b)
 def test_selector_producer_map_is_exact_and_old_map_retained(self):
  for rel,h in proof.SELECTOR_IMPLEMENTATION_PINS.items():
   if rel.endswith('/one_job_model_candidate.py'):self.assertEqual(h,'7e04700f063728cf1df376a563565830f7e1544f8b2e439b507cc649975749ff')
   else:self.assertEqual(prior_sha(R/rel),h)
  for rel,h in proof.FINITE_STAGE_DIAGNOSTIC_REVISION.items():self.assertEqual(prior_sha(R/rel),h)
  self.source['generation_input_pins'][str(self.repo/'candidates/model_candidate_build_20261101/candidate_generation_gate.py')]=proof.SELECTOR_IMPLEMENTATION_PINS['candidates/model_candidate_build_20261101/candidate_generation_gate.py']
  self.assertEqual(proof.selector_producer_policy(self.source,None),proof.SELECTOR_IMPLEMENTATION_PINS)
  for mutate in (lambda s:s['generation_input_pins'].update({str(self.repo/'candidates/model_candidate_build_20261101/candidate_generation_gate.py'):'0'*64}),lambda s:s['model_candidate_observation']['source_closure'].update(generation_contract_sha256='0'*64),lambda s:s.update(fixed_source_overlay='/else/MODEL_SOURCE_OVERLAY.json')):
   s=copy.deepcopy(self.source);mutate(s)
   with self.assertRaises(ValueError):proof.selector_producer_policy(s,None)
  with self.assertRaises(ValueError):proof.selector_producer_policy(self.source,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V2'})
  self.assertIsNone(proof.selector_producer_policy({'generation_input_pins':{}},None))
  self.assertEqual(proof.OLD_CANDIDATE_IMPLEMENTATION_PINS,proof.CANDIDATE_IMPLEMENTATION_PINS)
  self.assertNotEqual(proof.SELECTOR_IMPLEMENTATION_PINS['candidates/model_candidate_build_20261101/candidate_generation_gate.py'],proof.TERMINAL_IMPLEMENTATION_PINS['candidates/model_candidate_build_20261101/candidate_generation_gate.py'])
  self.assertEqual(proof.LOCAL_PACK_READER_SHA,sha(D/'pack_model_candidate.py'))
if __name__=='__main__':unittest.main()
