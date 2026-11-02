"""Real local Git guard + prepare.run; extracted exact bootstrap/materializer statements.
No download/EDA/tool inventory. Resource admission and source-catalog setup mocked.
The materializer's unrelated provider/JDK inventory is NOT exercised.
"""
import argparse, ast, copy, hashlib, importlib.util, json, os, pathlib, shutil, subprocess, sys, tempfile, time, types, unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent
ROOT=D.parents[1]
FLAG='--first-fault-readonly'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
policy=load('_entry_policy',D/'first_fault_policy.py')
guard=load('_entry_guard',D/'validate_model_launch.py')
def execute_nodes(nodes,env):
 exec(compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy(nodes),type_ignores=[])),'<exact-production-statements>','exec'),env)
def function(path,name):
 return next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef)and x.name==name)
class EntryFlow(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=pathlib.Path(self.t.name).resolve();self.repo=self.root/'repo';self.repo.mkdir();self.c=self.repo/'candidates/model_candidate_build_20261101';self.c.mkdir(parents=True)
  doc=policy.decode_contract((D/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes())
  for row in doc.values():
   if type(row)is dict and 'repo_path'in row:self.copy(row['repo_path'])
  for rel in [policy.CONTRACT_REPO_PATH,policy.SOURCE_CONTRACT_REPO_PATH,'candidates/split_build_only_20261031/TRANSFER_APPROVAL.json'] :self.copy(rel)
  for n in ['prepare_model_build.py','bootstrap_model_candidate.py','materialize_model_binding.py','validate_model_launch.py','first_fault_policy.py']:shutil.copyfile(D/n,self.c/n)
  self.git('init','-q');self.git('config','user.email','fixture@example.invalid');self.git('config','user.name','Local fixture');self.git('add','.');self.git('commit','-qm','source fixture');self.source=self.git('rev-parse','HEAD').strip()
  launch=self.repo/guard.LAUNCH;launch.parent.mkdir();launch.write_text(json.dumps(dict(schema=guard.SCHEMA,source_sha=self.source,nonce=guard.NONCE,transfer_approval_sha256=guard.ACCEPTED_TRANSFER_APPROVAL_SHA256)))
  self.git('add',guard.LAUNCH);self.git('commit','-qm','only launch');self.head=self.git('rev-parse','HEAD').strip();self.event=self.root/'event.json';self.event.write_text(json.dumps(dict(ref='refs/heads/main',before=self.source,after=self.head)))
  self.env=dict(os.environ,GITHUB_EVENT_PATH=str(self.event),GITHUB_RUN_ATTEMPT='1',GITHUB_SHA=self.head,GITHUB_RUN_ID='1234567',RUNNER_TEMP=str(self.root),GITHUB_OUTPUT=str(self.root/'outputs'))
 def copy(self,rel):
  p=self.repo/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,p)
 def git(self,*args):return subprocess.check_output(['git','-C',str(self.repo),*args],text=True,stderr=subprocess.PIPE)
 def identity(self):
  subprocess.run([sys.executable,'-B',str(self.c/'validate_model_launch.py')],cwd=self.repo,env=self.env,check=True,capture_output=True)
  p=self.root/'hetero-split-build-identity.json';i=json.loads(p.read_text())
  self.assertEqual(i['source_commit'],self.source);self.assertEqual(i['launch_commit'],self.head);self.assertEqual(i['launch_manifest_blob_sha'],self.git('rev-parse','HEAD:'+guard.LAUNCH).strip())
  self.git('checkout','-q','--detach',self.source)
  return p,i
 def prepare(self,flag):
  ip,identity=self.identity();m=load('_entry_prepare_'+str(flag),self.c/'prepare_model_build.py');clock=self.root/'clock.json';clock.write_text(json.dumps(dict(schema='SPLIT_BUILD_JOB_START_V1',job_budget_seconds=9000,run_id=identity['run_id'],launch_commit=identity['launch_commit'],started_monotonic=time.monotonic())))
  a=argparse.Namespace(repo=self.repo,work=self.root/'work',identity=ip,job_start=clock,first_fault_readonly=flag)
  orig=pathlib.Path.read_text
  def read(p,*args,**kw):return 'MemAvailable: 999999999 kB\n' if str(p)=='/proc/meminfo' else orig(p,*args,**kw)
  fresh=types.SimpleNamespace(validate_contract=lambda *a:None,reject_injection=lambda *a:None)
  with mock.patch.dict(os.environ,self.env,clear=True),mock.patch.object(m,'source_pins',return_value='a'*64),mock.patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=1<<50)),mock.patch.object(m.platform,'machine',return_value='x86_64'),mock.patch.object(m.sys,'version_info',(3,12)),mock.patch.object(pathlib.Path,'read_text',read),mock.patch.dict(sys.modules,{'fresh_host':fresh}),mock.patch.object(m.os,'execve')as ex:
   m.run(a)
  self.assertEqual(ex.call_count,1);argv=ex.call_args.args[1];self.assertEqual(argv[argv.index('--reviewed-repo-sha')+1],identity['source_commit']);return argv
 def bootstrap_args(self,argv):
  f=function(self.c/'bootstrap_model_candidate.py','main');nodes=[]
  for n in f.body:
   if isinstance(n,ast.Global):continue
   nodes.append(n)
   if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='v'for t in n.targets):break
  env=dict(argparse=argparse,pathlib=pathlib)
  with mock.patch.object(sys,'argv',['bootstrap']+argv[3:]):execute_nodes(nodes,env)
  v=env['v'];calls=[];binding=[n for n in f.body if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='stage'and isinstance(n.value.args[0],ast.Constant)and n.value.args[0].value=='binding'];self.assertEqual(len(binding),1)
  env.update(v=v,stage=lambda *a:calls.append(a),py=sys.executable,C=self.c,R=self.repo,P=self.repo/'pipeline',W=self.root/'bootstrap',java=self.root/'java')
  execute_nodes(binding,env);return calls[0][1],v
 def materialize_selector(self,flag):
  # Execute exact production selector statements, not a rewritten imitation.
  f=function(self.c/'materialize_model_binding.py','main')
  select=[n for n in f.body if isinstance(n,ast.If)and ast.unparse(n.test)=='v.first_fault_readonly'];self.assertEqual(len(select),1)
  final=[n for n in f.body if isinstance(n,ast.If)and ast.unparse(n.test)=='diagnostic is not None'and any(isinstance(x,ast.Assign)and any(isinstance(t,ast.Subscript)and ast.unparse(t)=='b[\'first_fault_driver_contract\']'for t in x.targets)for x in n.body)];self.assertEqual(len(final),1)
  doc=policy.load_source_contract(self.repo);b=dict(repo=str(self.repo),driver=str(self.repo/doc['legacy_driver']['repo_path']),generation_contract=str(self.repo/doc['hardware_generation_contract']['repo_path']),generation_contract_sha256=doc['hardware_generation_contract']['sha256'],model_source_contract='legacy-default',pins={str(p):policy.sha(p)for p in self.repo.rglob('*')if p.is_file()and '.git'not in p.parts})
  env=dict(v=argparse.Namespace(first_fault_readonly=flag),R=self.repo,diagnostic=None,driver=pathlib.Path(b['driver']),b=b)
  with mock.patch.dict(sys.modules,{'first_fault_policy':policy}):
   execute_nodes(select,env);b['driver']=str(env['driver']);execute_nodes(final,env)
  return b
 def test_real_guard_prepare_bootstrap_to_first_fault_policy(self):
  argv=self.prepare(True);self.assertEqual(argv.count(FLAG),1);binding,v=self.bootstrap_args(argv);self.assertTrue(v.first_fault_readonly);self.assertEqual(binding.count(FLAG),1);b=self.materialize_selector(True);self.assertIsNotNone(policy.binding_policy(b));self.assertNotEqual(policy.expected_driver_sha(b),policy.LEGACY_DRIVER_SHA)
 def test_legacy_no_selector_remains_original(self):
  argv=self.prepare(False);self.assertNotIn(FLAG,argv);binding,v=self.bootstrap_args(argv);self.assertFalse(v.first_fault_readonly);self.assertNotIn(FLAG,binding);b=self.materialize_selector(False);self.assertNotIn('first_fault_driver_contract',b);self.assertEqual(policy.expected_driver_sha(b),policy.LEGACY_DRIVER_SHA)
 def test_stale_nonce_real_git_guard_rejects(self):
  p=self.repo/guard.LAUNCH;d=json.loads(p.read_text());d['nonce']='five_m128_model_candidate_previous_once';p.write_text(json.dumps(d));self.git('add',guard.LAUNCH);self.git('commit','--amend','--no-edit','-q');head=self.git('rev-parse','HEAD').strip();self.env['GITHUB_SHA']=head;self.event.write_text(json.dumps(dict(ref='refs/heads/main',before=self.source,after=head)))
  r=subprocess.run([sys.executable,'-B',str(self.c/'validate_model_launch.py')],cwd=self.repo,env=self.env,capture_output=True);self.assertNotEqual(r.returncode,0);self.assertFalse((self.root/'hetero-split-build-identity.json').exists())
 def test_selector_omission_cannot_authorize_diagnostic_driver(self):
  self.identity();b=self.materialize_selector(True);del b['first_fault_driver_contract'];self.assertEqual(policy.expected_driver_sha(b),policy.LEGACY_DRIVER_SHA);self.assertNotEqual(policy.sha(b['driver']),policy.expected_driver_sha(b))
  tree=ast.parse((D/'one_job_model_candidate.py').read_text());gate=[n for n in ast.walk(tree)if isinstance(n,ast.Expr)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Name)and n.value.func.id=='need'and len(n.value.args)>1 and isinstance(n.value.args[1],ast.Constant)and n.value.args[1].value=='fixed final-state driver'];self.assertEqual(len(gate),1)
  with self.assertRaises(ValueError):execute_nodes(gate,dict(b=b,need=policy.need,expected_driver_sha=policy.expected_driver_sha))
 def test_corrupted_selector_rejected_by_real_policy(self):
  self.identity();b=self.materialize_selector(True);b['first_fault_driver_contract']['sha256']='0'*64
  with self.assertRaises(ValueError):policy.binding_policy(b)
 def test_workflow_exact_guard_checkout_flag_and_nonce(self):
  text=(ROOT/'.github/workflows/hetero-five-m128-model-candidate-build.yml').read_text();self.assertIn('paths: ['+guard.LAUNCH+']',text);self.assertIn('ref: ${{ steps.launch.outputs.source_sha }}',text);self.assertIn('validate_model_launch.py',text)
  command=text.split('python3 -B candidates/model_candidate_build_20261101/prepare_model_build.py',1)[1].split('- name:',1)[0];self.assertEqual(command.count(FLAG),1)
  # A removed selector is detected by this workflow contract, not accepted as a diagnostic build.
  with self.assertRaises(AssertionError):self.assertEqual(command.replace(FLAG,'').count(FLAG),1)
 def test_materializer_cli_exposes_false_default_true_selector(self):
  f=function(D/'materialize_model_binding.py','main');nodes=[]
  for n in f.body:
   nodes.append(n)
   if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='v'for t in n.targets):break
  # Inventory is intentionally outside this parser-only test.
  required=['--repo','--expected-repo-sha','--pipeline','--jdk-inventory','--java','--tools','--idma','--matrix','--binding','--output']
  args=sum(([x,'placeholder']for x in required),[])
  for tail,want in [([],False),([FLAG],True)]:
   env=dict(argparse=argparse,pathlib=pathlib)
   with mock.patch.object(sys,'argv',['materializer']+args+tail):execute_nodes(nodes,env)
   self.assertEqual(env['v'].first_fault_readonly,want)
if __name__=='__main__':unittest.main()
