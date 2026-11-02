"""Actual selected production functions + E/N/runtime admission; only /proc lease/time synthetic.
No supervisor, runtime import, acquisition, ELF, model, or user process is executed.
"""
import argparse,ast,contextlib,copy,json,os,pathlib,shutil,types,unittest
from unittest.mock import patch
from test_first_fault_real_join import RealJoin,D

def functions(path,names,ns=None):
 tree=ast.parse(path.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in names]
 if len(nodes)!=len(names):raise ValueError('exact production function set')
 out=dict(__file__=str(path),pathlib=pathlib,json=json,**(ns or {}));exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),out);return out
class Pipeline(RealJoin):
 def setUp(self):
  super().setUp();self.e=self.f['repo']/'candidates/same_job_execution_20261030'
  self.control=pathlib.Path(os.environ.get('FIRST_FAULT_CONTROLLER_SOURCE',str(D)))
  self.runtime_source=pathlib.Path(os.environ.get('FIRST_FAULT_RUNTIME_SOURCE',str(D/'runtime/runtime_reuse.py')))
  for name in ('prepare_cloud_execution.py','controller/cloud_flow.py','numeric/numeric_tail.py','numeric/consumer_owned.py'):
   target=self.e/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(self.control/name,target)
  self.identity_source=pathlib.Path(os.environ.get('FIRST_FAULT_IDENTITY_SOURCE',str(D/'executor_identity.py')))
  shutil.copyfile(self.identity_source,self.e/'executor_identity.py');(self.e/'runtime').mkdir();shutil.copyfile(self.runtime_source,self.e/'runtime/runtime_reuse.py')
  rows=[dict(self.n.pin(p),path=str(p.relative_to(self.f['repo'])))for p in sorted(self.f['repo'].rglob('*'))if p.is_file()]
  self.b['source_pins']=self.n.put(self.f['control']/'catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=rows));self.b['pins']={str(self.f['repo']/r['path']):r['sha256']for r in rows}
  boot='12345678-1234-1234-1234-123456789abc';host=json.loads(pathlib.Path(self.h.host['path']).read_text());host['boot_id']=boot;hp=self.h.put('host',host)
  identity=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit=self.f['artifact']['artifact_identity']['source_commit'],execution_id='22345678-1234-1234-1234-123456789abc',boot_id=boot,controller_pid=424242,start_tick=13,host_identity_sha256=hp['sha256'],started_monotonic=2)
  self.b['identity']=identity;self.b['executor_identity']=identity;self.b['executor_identity_pin']=self.n.put(self.f['control']/'executor.json',identity)
  self.b['builder_handoff']=self.h.put('handoff',{'synthetic_only':True})
  self.doc.update(source_commit=identity['source_commit'],host_identity=hp);self.ap.update(source_commit=identity['source_commit'],execution_id=identity['execution_id'],host_identity_sha256=hp['sha256']);self.approve()
  self.prepare=functions(self.e/'prepare_cloud_execution.py',{'need','sha','input_pin','stage_coverage_input','preserve_stage_coverage_input'},{'P':pathlib.Path,'hashlib':__import__('hashlib')})
  self.flow=functions(self.e/'controller/cloud_flow.py',{'runtime_admission_fields'})
  self.consumer=functions(self.e/'numeric/consumer_owned.py',{'need','sha','verify_frozen','cloud_invocation','executor_context','explicit_execution_admission'},{'hashlib':__import__('hashlib'),'WORKSPACE_LOADER':None})
  self.runtime=self.n.module(self.e/'runtime/runtime_reuse.py')
 @contextlib.contextmanager
 def synthetic_lease(self):
  real=pathlib.Path.read_text;identity=self.b['identity']
  def read(p,*a,**k):
   if str(p)=='/proc/sys/kernel/random/boot_id':return identity['boot_id']+'\n'
   if str(p)=='/proc/424242/stat':return '424242 (SYNTHETIC_TEST_ONLY) '+' '.join(['S']+['0']*18+['13'])
   return real(p,*a,**k)
  with patch.object(pathlib.Path,'read_text',read),patch('time.monotonic',return_value=100):yield
 def install_binding_from_actual_statements(self):
  approved=self.cloud.admit(self.b);b=dict(self.b,**approved)
  root=self.f['control'];ab=root/'archives_binding.json';self.n.put(ab,{'synthetic':True});job=root/'job'
  self.n.put(job/'runs/archives/RESULT.json',{'synthetic':True});archives=job/'archives';self.n.put(archives/'ARCHIVES.json',{'archives':[]})
  ns=dict(b=b,identity=b['identity'],execution_policy=self.n.module(self.e/'profile_policy.py').policy(),repo=self.f['repo'],owner_root=job/'materials',py='/synthetic/python',supervisor_dir='/synthetic/supervisor',lock='/synthetic/lock',roots=[],ipins=b['pins'],archives_rows=[],started=b['identity']['started_monotonic'],q=b['budgets'],tail_reserved=100,limit=b['job_budget_seconds'],runtime=self.e/'runtime',job=job,archives=archives,ab=ab,pin=self.n.pin,runtime_admission_fields=self.flow['runtime_admission_fields'])
  b['shared_runtime_helper']='/synthetic/shared_helper'
  tree=ast.parse((self.e/'controller/cloud_flow.py').read_text());run=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='run')
  pos=[i for i,x in enumerate(run.body)if isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='install_binding'for t in x.targets)]
  self.assertEqual(len(pos),1);i=pos[0];branch=run.body[i+2]
  self.assertIsInstance(branch,ast.If)
  nodes=[run.body[i],run.body[i+1],ast.If(test=branch.test,body=[branch.body[0]],orelse=[])]
  exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'actual_install_binding_construction','exec'),ns)
  return ns['install_binding']
 def argv_and_args(self):
  controller=self.n.put(self.f['control']/'controller_binding.json',self.b);b=dict(self.b,controller_binding=controller)
  tail=functions(self.e/'numeric/numeric_tail.py',{'need','execution_profiles','execution_command'},{'execution_mode':self.mode,'profile_policy':self.n.module(self.e/'profile_policy.py'),'D':self.e/'numeric','material':types.SimpleNamespace(checked=self.n.module(self.e/'runtime/runtime_reuse.py').checked)})
  admission=self.mode.admit(self.b);self.assertEqual(tail['execution_profiles'](b,admission),[0])
  generated=['python',str(self.e/'numeric/consumer_owned.py'),'--profile','0'];argv,wall=tail['execution_command'](generated,b,admission,0)
  parser=argparse.ArgumentParser();parser.add_argument('--profile',type=int);parser.add_argument('--execution-mode');parser.add_argument('--cloud-binding',type=pathlib.Path);parser.add_argument('--cloud-binding-sha256');args=parser.parse_args(argv[2:])
  for k in ('calibration_wall_seconds','full_block_budget','full_block_budget_sha256','stage_coverage_budget','stage_coverage_budget_sha256'):setattr(args,k,None)
  args.executor_identity=pathlib.Path(self.b['executor_identity_pin']['path']);args.executor_identity_sha256=self.b['executor_identity_pin']['sha256'];args.artifact_manifest=pathlib.Path(self.b['artifact_manifest']['path']);args.artifact_manifest_sha256=self.b['artifact_manifest']['sha256'];args.builder_handoff=pathlib.Path(self.b['builder_handoff']['path']);args.builder_handoff_sha256=self.b['builder_handoff']['sha256'];args.expected_source_commit=self.b['identity']['source_commit']
  return tail,b,admission,generated,argv,args
 def test_actual_prepare_runtime_tail_consumer_join(self):
  a=types.SimpleNamespace(execution_mode=self.mode.FIRST_FAULT,model_candidate_review=self.b['model_candidate_review']['path']);roles=self.prepare['stage_coverage_input'](a)
  self.assertEqual(roles,{'execution_mode':self.mode.FIRST_FAULT});self.prepare['preserve_stage_coverage_input'](roles,self.cloud.admit(self.b))
  ib=self.install_binding_from_actual_statements()
  with self.synthetic_lease():self.assertEqual(self.runtime.admit(ib)['diagnostic_profiles'],[0])
  tail,b,admission,generated,argv,args=self.argv_and_args()
  self.assertNotIn('--calibration-wall-seconds',argv);self.assertNotIn('--stage-coverage-budget',argv);self.assertNotIn('--full-block-budget',argv)
  with self.synthetic_lease():self.assertEqual(self.consumer['explicit_execution_admission'](args)[1],admission)
 def test_actual_prepare_identity_stub_source_catalog_before_cloud_admission(self):
  policy=self.n.module(self.e/'profile_policy.py');manifest=pathlib.Path(self.b['source_pins']['path'])
  roles={k:self.b[k]for k in ('builder_handoff','artifact_manifest','cloud_budget','execution_approval','retained_materials','model_candidate_review','execution_mode')}
  tree=ast.parse((self.e/'prepare_cloud_execution.py').read_text());fun=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='prepare_identity')
  positions=[i for i,x in enumerate(fun.body)if isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='stub'for t in x.targets)]
  self.assertEqual(len(positions),1);i=positions[0];self.assertIsInstance(fun.body[i+1],ast.If)
  ns=dict(identity=self.b['identity'],policy=policy,pins=self.b['pins'],roles=roles,repo=self.f['repo'],manifest=manifest,sha=self.n.sha)
  exec(compile(ast.Module(body=fun.body[i:i+2],type_ignores=[]),'actual_prepare_identity_stub','exec'),ns)
  stub=ns['stub'];self.assertEqual(stub['source_pins'],self.b['source_pins']);self.assertEqual(self.cloud.admit(stub)['diagnostic_profiles'],[0])
  for k in ('source_pins','repo'):
   bad=dict(stub);bad.pop(k)
   with self.subTest(missing=k),self.assertRaises((ValueError,KeyError)):self.cloud.admit(bad)
 def test_actual_consumer_otherprofile_mode_override_rejected(self):
  _,_,_,_,_,args=self.argv_and_args()
  for field,value in [('profile',1),('execution_mode',self.mode.CALIBRATION),('calibration_wall_seconds',1),('stage_coverage_budget',pathlib.Path('/synthetic'))]:
   a=copy.copy(args);setattr(a,field,value)
   with self.subTest(field=field),self.synthetic_lease(),self.assertRaises(ValueError):self.consumer['explicit_execution_admission'](a)
 def test_runtime_missing_mode_or_review_rejected(self):
  ib=self.install_binding_from_actual_statements()
  for key in ('execution_mode','model_candidate_review','source_pins'):
   bad=dict(ib);bad.pop(key)
   with self.subTest(key=key),self.synthetic_lease(),self.assertRaises((ValueError,KeyError)):self.runtime.admit(bad)
if __name__=='__main__':unittest.main()
