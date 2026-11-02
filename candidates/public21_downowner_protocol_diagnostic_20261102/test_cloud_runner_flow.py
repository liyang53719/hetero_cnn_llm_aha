"""Actual runner main/CLI orchestration with mocked authorities and subprocesses.
No Java, Verilator, make, network or diagnostic hardware execution.
The end-to-end identity regression uses real isolated local Git commits and guard.
"""
import subprocess,contextlib,hashlib,importlib.util,io,json,os,resource,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
DEFAULT=HERE if (HERE/'run_cloud_b.py').exists()else HERE.parent/'public21_b_cloud_runner_candidate_20261102T0846/source/candidates/public21_downowner_protocol_diagnostic_20261102'
PACKAGE=Path(os.environ.get('PUBLIC21_B_TEST_SOURCE',str(DEFAULT))).resolve()
REL='candidates/public21_downowner_protocol_diagnostic_20261102'
ORDER=['jdk','compile_tools','jars','verilator_tools','fresh_host','compile','emit','ports','verilate','make','protocol']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class Flow(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.c=self.repo/REL;self.c.mkdir(parents=True);self.work=self.root/'work';self.calls=[];self.authority=[];self.mode=None
  for p in PACKAGE.iterdir():
   if p.is_file()and p.suffix in('.py','.scala','.json'):(self.c/p.name).write_bytes(p.read_bytes())
  self.k=self.repo/'candidates/model_candidate_build_20261101';self.d=self.repo/'candidates/ci_frontend_materialization_r2_20261029';self.s=self.repo/'candidates/ci_frontend_pipeline_r2_20261029';self.original=self.repo/'candidates/fresh_original_top_recovery_20261028'
  for p in(self.k,self.d,self.s,self.original):p.mkdir(parents=True,exist_ok=True)
  self.sources=[]
  for i in range(159):
   p=self.original/f'source/S{i}.scala';p.parent.mkdir(exist_ok=True);p.write_text('synthetic source '+str(i));self.sources.append(str(p))
  self.jars=[]
  for i in range(107):
   data=('synthetic jar '+str(i)).encode();self.jars.append(dict(maven_path=f'g/j{i}.jar',sha256=hashlib.sha256(data).hexdigest(),role='plugin'if i==106 else'classpath',bytes=len(data)))
  self.write(self.original/'SOURCE_AND_TOOLCHAIN_PINS.json',{'jars':self.jars})
  self.java=self.root/'jdk';(self.java/'bin').mkdir(parents=True);(self.java/'bin/java').write_text('synthetic JDK executable, never executed')
  self.sha='a'*40;self.launch='b'*40;self.identity=self.root/'identity.json';self.start=self.root/'start.json';self.event=self.root/'event.json'
  self.write(self.identity,dict(schema='PUBLIC21_DOWNOWNER_PROTOCOL_JOB_IDENTITY_V1',run_id=123,source_commit=self.sha,launch_commit=self.launch,launch_manifest_path='ci_launch/public21_downowner_protocol_driveorderfix_20261102_once.json',launch_manifest_blob_sha='c'*40,scope='PROTOCOL_ONLY_MOCK_MATRIX_VECTOR_DDR_NO_NUMERICAL_PASS_NO_ARTIFACT_TRANSFER'))
  self.write(self.start,dict(schema='PUBLIC21_DOWNOWNER_PROTOCOL_JOB_START_V1',run_id=123,launch_commit=self.launch,job_budget_seconds=7200,started_monotonic=time.monotonic()))
  self.write(self.event,dict(before=self.sha,after=self.launch,ref='refs/heads/main'))
  files={str(p.relative_to(self.repo)):digest(p)for p in self.c.iterdir()if p.is_file()and not p.name.startswith('test_')}
  self.scala=['Public21DownOwnerProtocolHarness.scala','Public21DownOwnerCrossWindowProtocolOnlySpec.scala','DirectJnaAdapter.scala','DirectBContextFactory.scala','Public21DownOwnerDirectDriver.scala','Public21DownOwnerEmitOnly.scala']
  self.write(self.c/'DIAGNOSTIC_SOURCE_PINS.json',dict(schema='PUBLIC21_B_SOURCE_PINS_V1',supervisor_directory=str(self.s.relative_to(self.repo)),compile_inventory=str((self.s/'inventory_compile_tools.py').relative_to(self.repo)),files=files,scala_sources=self.scala))
  backend=b'synthetic pinned backend';self.write(self.d/'VERILATOR_MANIFEST.json',{'files':[{'path':'usr/bin/verilator_bin','sha256':hashlib.sha256(backend).hexdigest()}]})
  # Every authoritative executable/helper role exists and is pinned, but mocked.
  for directory,names in [(self.d,['inventory_runner_jdk.py','fresh_host.py','materialize_verilator.py']),(self.k,['restore_model_inputs.py','candidate_generation_gate.py','GENERATION_CONTRACT.json','MODEL_SOURCE_OVERLAY.json']),(self.s,['inventory_compile_tools.py','supervise_multiroot.py','strict_cleanup.py','lossless_log.py'])]:
   for name in names:(directory/name).write_text('{}'if name.endswith('.json')else'# synthetic authority, never executed')
  if not(self.c/'BUDGET_CONTRACT.json').exists():self.write(self.c/'BUDGET_CONTRACT.json',{'synthetic':True})
  manifest=self.c/'DIAGNOSTIC_SOURCE_PINS.json';local=json.loads(manifest.read_text())
  local['files']={str(p.relative_to(self.repo)):digest(p)for directory in(self.c,self.d,self.k,self.s)for p in directory.iterdir()if p.is_file()and p!=manifest and not p.name.startswith('test_')}
  local['files'][str((self.original/'SOURCE_AND_TOOLCHAIN_PINS.json').relative_to(self.repo))]=digest(self.original/'SOURCE_AND_TOOLCHAIN_PINS.json');self.write(manifest,local)
  spec=importlib.util.spec_from_file_location('actual_runner_under_test',self.c/'run_cloud_b.py');self.runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.runner)
 def write(self,p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d))
 def execute(self,argv,out,lock,caps,env,pins,resource_gate):
  out=Path(out);name=out.name;self.calls.append(dict(name=name,argv=argv,caps=caps,env=env,pins=pins,gate=resource_gate))
  if self.mode=='prelaunch_memory_gate':
   return dict(native_exit=None,errors=['ValueError: locked memory gate'],cleanup_proof=None,log_capture=None)
  out.mkdir()
  w=self.work;top='Public21DownOwnerProtocolHarness'
  if name=='jdk':self.write(w/'jdk.json',dict(status='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION',old_pass_transfer=False,files=[dict(path='bin/java',bytes=(self.java/'bin/java').stat().st_size,sha256=digest(self.java/'bin/java'))]))
  elif name=='compile_tools':self.write(w/'compile-tools.json',dict(pins={},aliases={}))
  elif name=='jars':
   for i,row in enumerate(self.jars):
    p=self.original/'cache'/row['maven_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('synthetic jar '+str(i)).encode())
  elif name=='verilator_tools':
   p=w/'tools/verilator-package/usr/bin/verilator_bin';p.parent.mkdir(parents=True);p.write_bytes(b'synthetic pinned backend');(w/'tools/verilator').write_text('synthetic wrapper')
  elif name=='fresh_host':self.write(w/'host.json',dict(contract=json.loads((w/'FRESH_HOST_CONTRACT.json').read_text()),old_pass_transfer=False,pins={},aliases={}))
  elif name=='compile':(out/'Fixture.class').write_text('not bytecode')
  elif name=='emit':
   for suffix in('.lo.fir','.sv','-harness.cpp'):
    if not(self.mode=='missing_sv'and suffix=='.sv'):(w/'emitted'/(top+suffix)).write_text('synthetic emitted '+suffix)
  elif name=='ports':
   (w/'mapped').mkdir();self.write(w/'mapped/PORTS.json',{'synthetic':True});(w/'mapped/Public21DownOwnerDirectDriver.scala').write_bytes(b'mismatch'if self.mode=='driver_mismatch'else(self.c/'Public21DownOwnerDirectDriver.scala').read_bytes())
  elif name=='verilate':
   p=w/'emitted/verilated';p.mkdir();(p/('V'+top+'.mk')).write_text('synthetic makefile')
  elif name=='make':(w/'emitted/verilated'/('V'+top)).write_text('synthetic library')
  q=dict(native_exit=1 if self.mode=='strictfail'and name=='emit'else 0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True},elapsed_seconds=0.01,observed_peak_rss=1024,observed_cpu_seconds=0.01)
  self.write(out/'RESULT.json',q);return q
 def invoke(self,extra_cli=(),real_git=False):
  fresh=types.ModuleType('fresh_host');fresh.reject_injection=lambda e:self.authority.append('injection');fresh.validate_compile_inventory=lambda v:self.authority.append('compile_inventory')
  gen=types.ModuleType('candidate_generation_gate');gen.GENERATION_CONTRACT_SHA256='d'*64;gen.load_contract=lambda *a:self.authority.append('generation')or{};gen.checked_paths=lambda *a:list(self.sources)
  sup=types.ModuleType('supervise_multiroot');sup.execute=self.execute
  diag=types.ModuleType('diagnostics');diag.project=lambda *a:{'mock_projection':True,'numerical_pass':False}
  protocol=types.ModuleType('prepare_protocol_input');protocol.verify=lambda d,h:self.authority.append(('protocol_pin',h))
  modules={m.__name__:m for m in(fresh,gen,sup,diag,protocol)}
  env=dict(GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA=self.launch,GITHUB_EVENT_PATH=str(self.event),JAVA_HOME_21_X64=str(self.java))
  args=['run_cloud_b.py','--repo',str(self.repo),'--work',str(self.work),'--identity',str(self.identity),'--job-start',str(self.start),*extra_cli]
  oldpath=sys.path[:];self.stdout=io.StringIO()
  try:
   with contextlib.ExitStack() as stack:
    for c in (patch.dict(sys.modules,modules),patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',args),contextlib.redirect_stdout(self.stdout)):stack.enter_context(c)
    if not real_git:
     githead=stack.enter_context(patch.object(self.runner.subprocess,'check_output',return_value=self.sha+'\n'));gitdiff=stack.enter_context(patch.object(self.runner.subprocess,'run'))
    self.runner.main()
    if not real_git:githead.assert_called_once();gitdiff.assert_called_once()
  finally:sys.path[:]=oldpath
 def actual_guard_identity(self):
  # Workflow path -> actual guard.main -> real source checkout -> actual runner.main.
  # Only downstream tool authorities/stages remain the original explicit mocks.
  workflow=(PACKAGE.parents[1]/'.github/workflows/hetero-public21-downowner-protocol.yml').read_text()
  spec=importlib.util.spec_from_file_location('real_launch_guard_under_test',self.c/'validate_launch.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
  self.assertIn('paths: ['+guard.LAUNCH+']',workflow)
  self.assertIn('python3 -B '+REL+'/validate_launch.py',workflow)
  self.assertIn('python3 -B '+REL+'/run_cloud_b.py',workflow)
  def git(*args):return subprocess.check_output(['git','-C',str(self.repo),'-c','user.name=IdentityFixture','-c','user.email=fixture@example.invalid',*args],text=True,stderr=subprocess.PIPE).strip()
  git('init','--initial-branch=main');git('add','.');git('commit','-m','reviewed synthetic source');self.sha=git('rev-parse','HEAD')
  self.write(self.repo/guard.LAUNCH,dict(schema=guard.SCHEMA,source_sha=self.sha,nonce=guard.NONCE))
  git('add',guard.LAUNCH);git('commit','-m','single source-only activation');self.launch=git('rev-parse','HEAD')
  self.write(self.event,dict(before=self.sha,after=self.launch,ref='refs/heads/main'))
  self.write(self.start,dict(schema='PUBLIC21_DOWNOWNER_PROTOCOL_JOB_START_V1',run_id=123,launch_commit=self.launch,job_budget_seconds=7200,started_monotonic=time.monotonic()))
  output=self.root/'github_output';env=dict(GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_SHA=self.launch,GITHUB_EVENT_PATH=str(self.event),RUNNER_TEMP=str(self.root),GITHUB_OUTPUT=str(output),PATH='/usr/bin:/bin')
  with patch.dict(os.environ,env,clear=True),contextlib.chdir(self.repo):guard.main()
  self.identity=self.root/'public21-b-identity.json';actual=json.loads(self.identity.read_text())
  self.assertEqual(actual['source_commit'],self.sha);self.assertEqual(actual['launch_commit'],self.launch);self.assertEqual(actual['launch_manifest_blob_sha'],git('rev-parse','HEAD:'+guard.LAUNCH));self.assertEqual(output.read_text(),'source_sha='+self.sha+'\n')
  git('checkout','--detach',self.sha)
 def test_workflow_guard_real_git_identity_to_actual_runner(self):
  self.actual_guard_identity();self.invoke(real_git=True)
  self.assertEqual([x['name']for x in self.calls],ORDER)
 def test_actual_guard_identity_rejects_stale_runner_path_before_stages(self):
  self.actual_guard_identity();d=json.loads(self.identity.read_text());d['launch_manifest_path']='ci_launch/public21_downowner_protocol_20261102_once.json';self.write(self.identity,d)
  with self.assertRaisesRegex(ValueError,'launch boundary'):self.invoke(real_git=True)
  self.assertEqual(self.calls,[]);self.assertFalse(self.work.exists())
 def test_actual_main_positive_layout_and_pins(self):
  self.invoke();self.assertEqual([x['name']for x in self.calls],ORDER)
  final=json.loads((self.work/'FINAL_SAFE.json').read_text());self.assertFalse(final['numerical_pass']);self.assertTrue(final['protocol_driver_returned']);self.assertEqual(len(final['stages']),11)
  compile=next(c for c in self.calls if c['name']=='compile');self.assertTrue(all(s in compile['argv']for s in self.sources));self.assertTrue(all(str(self.c/n)in compile['argv']for n in self.scala));self.assertEqual(len([x for x in compile['pins']if x.endswith('.jar')]),107)
  ports=next(c for c in self.calls if c['name']=='ports');self.assertIn(str(self.work/'emitted/Public21DownOwnerProtocolHarness.sv'),ports['argv'])
  self.assertEqual((self.work/'mapped/Public21DownOwnerDirectDriver.scala').read_bytes(),(self.c/'Public21DownOwnerDirectDriver.scala').read_bytes())
  p=self.calls[-1];self.assertIn('heteronpu.continuous.Public21DownOwnerDirectMain',p['argv']);self.assertEqual(p['argv'][-5:],[str(self.work/'mapped/PORTS.json'),digest(self.work/'mapped/PORTS.json'),str(self.work/'emitted/verilated/VPublic21DownOwnerProtocolHarness'),digest(self.work/'emitted/verilated/VPublic21DownOwnerProtocolHarness'),str(self.work/'emitted')]);self.assertEqual(p['env']['P0_CLOSED_PROGRAM_MANIFEST'],str(self.c/'P0_PROTOCOL_INPUT.json'))
  for path in (self.c/'run_cloud_b.py',self.c/'Public21DownOwnerDirectDriver.scala',self.work/'mapped/Public21DownOwnerDirectDriver.scala',self.work/'emitted/Public21DownOwnerProtocolHarness.sv'):self.assertIn(str(path),p['pins'])
 def test_missing_sv_stops_before_ports(self):
  self.mode='missing_sv'
  with self.assertRaises(ValueError):self.invoke()
  self.assertEqual(self.calls[-1]['name'],'emit');self.assertFalse((self.work/'FINAL_SAFE.json').exists())
 def test_driver_mismatch_stops_before_verilate(self):
  self.mode='driver_mismatch'
  with self.assertRaisesRegex(ValueError,'driver body'):self.invoke()
  self.assertEqual(self.calls[-1]['name'],'ports');self.assertFalse((self.work/'FINAL_SAFE.json').exists())
 def test_strict_failure_stops_chain(self):
  self.mode='strictfail'
  with self.assertRaisesRegex(ValueError,'stage failed: emit'):self.invoke()
  self.assertEqual(self.calls[-1]['name'],'emit');self.assertFalse((self.work/'FINAL_SAFE.json').exists())
 def test_prelaunch_memory_gate_preserves_return_without_stage_receipt(self):
  self.mode='prelaunch_memory_gate'
  with self.assertRaisesRegex(ValueError,'stage failed: jdk'):self.invoke()
  self.assertEqual([x['name']for x in self.calls],['jdk'])
  self.assertFalse((self.work/'jdk').exists())
  self.assertFalse((self.work/'jdk/RESULT.json').exists())
  self.assertFalse((self.work/'FINAL_SAFE.json').exists())
  returned=self.work/'jdk_SUPERVISOR_RETURN.json'
  self.assertEqual(json.loads(returned.read_text()),dict(native_exit=None,errors=['ValueError: locked memory gate'],cleanup_proof=None,log_capture=None))
  lines=[x for x in self.stdout.getvalue().splitlines()if x.startswith('PUBLIC21_B_STAGE ')]
  self.assertEqual(len(lines),1);safe=json.loads(lines[0].split(' ',1)[1])
  self.assertEqual(safe['error_codes'],['MEMORY_GATE']);self.assertFalse(safe['receipt_available']);self.assertIsNone(safe['receipt_sha256'])
  self.assertEqual(safe['supervisor_return_sha256'],digest(returned));self.assertIsNone(safe['native_exit'])
  for key in ('strict_stage_success','cleanup_complete','pipe_eof','gzip_finalized','numerical_pass','production_fault_reproduced'):self.assertFalse(safe[key])
  self.assertEqual(json.loads((self.work/'jdk_SAFE.json').read_text()),safe)
 def test_missing_scala_source_pin_rejected(self):
  # Regression: all compiler source roles must be pinned before any stage.
  path=self.c/'DIAGNOSTIC_SOURCE_PINS.json';d=json.loads(path.read_text());d['files'].pop(str((self.c/self.scala[0]).relative_to(self.repo)));self.write(path,d)
  with self.assertRaises(ValueError):self.invoke()
 def test_missing_authority_role_classes_rejected(self):
  path=self.c/'DIAGNOSTIC_SOURCE_PINS.json';baseline=json.loads(path.read_text())
  representatives=[self.c/'prepare_direct_driver.py',self.c/'P0_PROTOCOL_INPUT.json',self.c/'BUDGET_CONTRACT.json',self.d/'inventory_runner_jdk.py',self.k/'restore_model_inputs.py',self.s/'supervise_multiroot.py',self.s/'inventory_compile_tools.py',self.original/'SOURCE_AND_TOOLCHAIN_PINS.json']
  for role in representatives:
   with self.subTest(role=role.name):
    local=json.loads(json.dumps(baseline));local['files'].pop(str(role.relative_to(self.repo)));self.write(path,local)
    self.work=self.root/('work_missing_'+role.name.replace('.','_'))
    with self.assertRaisesRegex(ValueError,'required runtime source role'):self.invoke()
    self.assertEqual(self.calls,[])
 def test_wrong_scala_role_order_rejected(self):
  path=self.c/'DIAGNOSTIC_SOURCE_PINS.json';d=json.loads(path.read_text());d['scala_sources'].reverse();self.write(path,d)
  with self.assertRaisesRegex(ValueError,'exact six'):self.invoke()
  self.assertEqual(self.calls,[])
 def test_missing_required_cli(self):
  with patch.object(sys,'argv',['run_cloud_b.py']),contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaises(SystemExit)as cm:self.runner.main()
  self.assertEqual(cm.exception.code,2);self.assertEqual(self.calls,[])
if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_AS,(256<<20,)*2);resource.setrlimit(resource.RLIMIT_CPU,(15,)*2);unittest.main(verbosity=2)
