import ast,copy,json,pathlib,resource,shutil,tempfile,types,unittest,argparse,sys,hashlib
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
P=pathlib.Path
D=P(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--repo',type=P,required=True);ap.add_argument('--driver',type=P);ap.add_argument('--candidate-dir',type=P,default=D);ARGS,REST=ap.parse_known_args()
DRIVER=ARGS.driver or ARGS.repo/'candidates/five_profile_execution_v3_20261029T0148/host_axi_driver_non_dpi_final_dump.cpp'
raw=(D/'BASELINE_FUNCTION_AST.json').read_bytes()
if hashlib.sha256(raw).hexdigest()!='0f5e5f9ba761329c5dcb9d9ea19c7e1ecf203836daab3fe1076370e26c128bf1':raise ValueError('pinned baseline AST fixture')
BASELINE=json.loads(raw);sys.path.insert(0,str(ARGS.candidate_dir.resolve()))
import connect_bundle as c
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);self.build=self.root/'frontend';self.d=self.build/'frozen_artifact';self.d.mkdir(parents=True)
  self.identity=dict(run_id=40862676969,artifact_name='mock-only',source_commit='5302e25382bf5a6dc8020e787e45e40988488953',launch_commit='efd271a45ec75befbd389c374fbc314768436b6f',launch_manifest_path='ci_launch/fixed_frontend_r7_20261029_once.json',launch_manifest_blob_sha='9d87613d9c3c076314996fd1b043b7f233ed94ca')
  for name in ('binary','sv','source_manifest','tool_manifest'):(self.d/(name+'.json')).write_text('{}')
  shutil.copyfile(DRIVER,self.d/'driver.json')
  def rel(name):v=c.pin(self.d/(name+'.json'));v['path']=name+'.json';return v
  common={n:rel(n) for n in ('binary','sv','source_manifest','driver')};tool=rel('tool_manifest')
  receipt=dict(source_commit=self.identity['source_commit'],launch_commit=self.identity['launch_commit'],tool_manifest_sha256=tool['sha256'],config_only=False,software_arithmetic_substitution=False,**{k+'_sha256':v['sha256'] for k,v in common.items()})
  (self.d/'build_receipt.json').write_text(json.dumps(receipt));common['build_receipt']=rel('build_receipt')
  self.f=dict(schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2',profiles=list(range(5)),artifact_identity=self.identity,tool_manifest=tool,common=common,layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE')
  self.mf=self.d/'frozen_artifact.json';self.mf.write_text(json.dumps(self.f));self.result=self.build/'BUILD_ONLY_RESULT.json'
  self.result.write_text(json.dumps(dict(status='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS',scope='CHISEL_TEST_BACKEND_PREPARATION_NOT_FINAL_RTL_REPLAY',artifact=dict(manifest=c.pin(self.mf),files=7,expanded_bytes=sum(p.stat().st_size for p in self.d.iterdir()),scope='ONE_SHARED_BINARY_FROZEN_NOT_UPLOADED_NOT_EXECUTED'))))
  abi=self.root/'STARTUP_ABI.json';abi.write_text('{"mock":true}')
  self.args=types.SimpleNamespace(artifact_manifest=self.mf,artifact_manifest_sha256=c.consumer.sha(self.mf),local_build_result=self.result,local_build_result_sha256=c.consumer.sha(self.result),expected_run_id=self.identity['run_id'],expected_launch_commit=self.identity['launch_commit'],expected_source_commit=self.identity['source_commit'],p0_bindings=None,p0_bindings_sha256=None,consumption_evidence=None,consumption_evidence_sha256=None,local_runtime_abi=abi,local_runtime_abi_sha256=c.consumer.sha(abi))
  from unittest.mock import patch
  self.abi_mock=patch.object(c.consumer,'verify_runtime_abi',return_value={'scope':'MOCK_ABI_NOT_EXECUTED'});self.abi_check=self.abi_mock.start();self.addCleanup(self.abi_mock.stop)
 def bundle(self,i):
  self.args.profile=i;out=self.root/f'p{i}';out.mkdir();p=dict(id=i)
  for name in ('runtime','views','reference_result','provider_receipt'):
   f=out/(name+'.txt');f.write_text('MOCK_METADATA_NOT_NUMERICAL');p[name]=c.pin(f)
  doc=dict(schema='SINGLE_PROFILE_RUNTIME_BUNDLE_V1',hardware_executed=False,raw_payloads_upload_allowed=False,profiles=[p],limits=dict(wall_seconds=20000,address_space_bytes=12*1024**3,cpu_seconds=18000,file_bytes=64*1024**2,max_active_cycles=1000000000))
  (out/'runtime_bundle.json').write_text(json.dumps(doc));return out,doc
 def test_four_real_load_binding_paths(self):
  common=[]
  for i in (1,2,3,4):
   out,old=self.bundle(i);before=(out/'runtime_bundle.json').read_bytes();c.preflight(self.args);r=c.connect(self.args,out);v=json.loads((out/'runtime_bundle.v3.json').read_text())
   self.assertEqual(v['profiles'],old['profiles']);self.assertEqual(v['limits'],old['limits']);self.assertEqual((out/'runtime_bundle.json').read_bytes(),before);self.assertFalse(r['hardware_executed']);self.assertFalse(r['numerical_pass']);self.assertIn(str(out/'runtime_bundle.v3.json'),r['consumer_argv']);common.append(r['artifact_manifest_sha256'])
  self.assertEqual(len(set(common)),1)
 def test_wrong_selected(self):
  _,old=self.bundle(1)
  with self.assertRaises(ValueError):c.base(old,2)
 def test_no_exception_for_other_profiles(self):
  out,_=self.bundle(3);self.args.p0_bindings=self.root/'no'
  with self.assertRaises(ValueError):c.connect(self.args,out)
  self.assertFalse((out/'runtime_bundle.v3.json').exists())
 def test_p0_missing_evidence_before_materialization(self):
  self.args.profile=0
  with self.assertRaises(ValueError):c.preflight(self.args)
  self.assertFalse((self.root/'p0').exists())
 def test_missing_p0_mapping_no_publish(self):
  out,_=self.bundle(0);bindings=self.root/'bindings.json';bindings.write_text('{}');evidence=self.root/'evidence.json';evidence.write_text('{}')
  self.args.p0_bindings=bindings;self.args.p0_bindings_sha256=c.consumer.sha(bindings);self.args.consumption_evidence=evidence;self.args.consumption_evidence_sha256=c.consumer.sha(evidence)
  with self.assertRaisesRegex(ValueError,'mapping absent'):c.preflight(self.args)
  self.assertFalse((out/'runtime_bundle.v3.json').exists())
 def test_limit_not_weakened(self):
  out,old=self.bundle(2);old['limits']['wall_seconds']=10;(out/'runtime_bundle.json').write_text(json.dumps(old))
  with self.assertRaises(ValueError):c.connect(self.args,out)
  self.assertTrue((out/'runtime_bundle.v3.UNADMITTED.json').exists());self.assertFalse((out/'runtime_bundle.v3.json').exists())
 def test_external_ref_rejected(self):
  out,old=self.bundle(4);f=self.root/'external.json';f.write_text('{}');old['profiles'][0]['reference_result']=c.pin(f);(out/'runtime_bundle.json').write_text(json.dumps(old))
  with self.assertRaises(ValueError):c.connect(self.args,out)
 def test_wrong_samejob_run(self):
  self.args.profile=2;self.args.expected_run_id=1
  with self.assertRaises(ValueError):c.preflight(self.args)
 def test_main_preflight_precedes_any_runtime_or_payload(self):
  import prepare,sys
  from unittest.mock import patch
  out=self.root/'fresh'
  with patch.object(sys,'argv',['prepare','--repo',str(self.root),'--output',str(out),'--profile','0']),patch.object(prepare,'sources'),patch.object(c,'preflight',side_effect=ValueError('BLOCKED source')),patch.object(prepare,'run') as run:
   with self.assertRaisesRegex(ValueError,'BLOCKED source'):prepare.main()
   run.assert_not_called();self.assertFalse(out.exists())
 def test_abi_failure_before_materialization(self):
  self.args.profile=1;self.abi_check.side_effect=ValueError('ABI drift')
  with self.assertRaisesRegex(ValueError,'ABI drift'):c.preflight(self.args)
 def test_shared_consumer_math_and_policy_unchanged(self):
  here=ARGS.candidate_dir.resolve()
  def fs(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
  a=BASELINE['consumer']['functions'];b={k:hashlib.sha256(v.encode()).hexdigest()for k,v in fs(here/'consumer/run_compare.py').items()}
  for key in ('records','reference','token_major','expected','compare','router_compare','load_binding','artifact_identity','verify_frozen'):self.assertEqual(a[key],b[key],key)
  policy_tree=ast.parse((here/'consumer/run_compare.py').read_text());policy_fn=next(n for n in policy_tree.body if isinstance(n,ast.FunctionDef) and n.name=='coverage_policy')
  current=hashlib.sha256((here/'consumer/observation_contract.py').read_bytes()).hexdigest()
  for node in ast.walk(policy_fn):
   if isinstance(node,ast.Constant) and node.value==current:node.value='7086710e79d0f1d93a8b48b26e8a7f5da136296171ec436e4567a9a80b9fa579'
  self.assertEqual(a['coverage_policy'],hashlib.sha256(ast.dump(policy_fn,include_attributes=False).encode()).hexdigest())
  # Only intended execute change is explicitly clean startup environment.
  tree=ast.parse((here/'consumer/run_compare.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
  call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='Popen')
  env=next(k for k in call.keywords if k.arg=='env');call.keywords.remove(env)
  self.assertEqual(a['execute'],hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest())
 def test_preflight_same_length_sv_drift(self):
  self.args.profile=1;(self.d/'sv.json').write_text('[]')
  with self.assertRaisesRegex(ValueError,'pin mismatch'):c.preflight(self.args)
 def test_preflight_other_profile_exception_rejected(self):
  self.args.profile=4;self.args.p0_bindings=self.root/'notallowed'
  with self.assertRaisesRegex(ValueError,'BEFORE materialization'):c.preflight(self.args)
 def test_original_materializer_functions_unchanged(self):
  here=ARGS.candidate_dir.resolve()
  def fs(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
  a=BASELINE['prepare']['functions'];b={k:hashlib.sha256(v.encode()).hexdigest()for k,v in fs(here/'prepare.py').items()}
  for name in a:
   if name not in ('main','materialize'):self.assertEqual(a[name],b[name],name)

  raw=(D/'FFF882_MATERIALIZE_AST.json').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'9cca6028d8fd354f579f859e449696611474f1f10523fcb413dd3147c0047cf9')
  frozen=json.loads(raw)
  fn=next(n for n in ast.parse((here/'prepare.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='materialize')
  self.assertEqual([x.arg for x in fn.args.args],['repo','out','runtimes','i','shared_selected'])
  self.assertEqual([ast.dump(x) for x in fn.args.defaults],[ast.dump(ast.Constant(value=None))])
  branch=fn.body[1]
  self.assertIsInstance(branch,ast.If)
  self.assertEqual(ast.dump(branch.test),ast.dump(ast.parse('shared_selected is None',mode='eval').body))
  expected=ast.parse("rt=shared_selected;need(set(rt)=={RUNTIME[i]},'shared selected original runtime only');r=rt[RUNTIME[i]]").body
  self.assertEqual([ast.dump(x) for x in branch.orelse],[ast.dump(x) for x in expected])
  def body_sha(nodes):return hashlib.sha256('\n'.join(ast.dump(x,include_attributes=False) for x in nodes).encode()).hexdigest()
  self.assertEqual(body_sha(fn.body[2:]),frozen['payload_to_bundle_ast_sha256'])
  self.assertEqual(body_sha([fn.body[0],*branch.body]),frozen['original_prelude_ast_sha256'])
  # Recover the exact original isolated function, not a new permissive whole hash.
  original=copy.deepcopy(fn);original.args.args.pop();original.args.defaults=[];original.body=[original.body[0],*original.body[1].body,*original.body[2:]]
  restored=hashlib.sha256(ast.dump(original,include_attributes=False).encode()).hexdigest()
  self.assertEqual(restored,frozen['original_function_ast_sha256'])
  self.assertEqual(restored,a['materialize'])
if __name__=='__main__':unittest.main(argv=['test_connection',*REST],verbosity=2)
