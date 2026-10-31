"""Light identity/deadline tests only, not runtime install or execution authority."""
import hashlib,importlib.util,json,os,pathlib,tempfile,time,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent

def load(name,file):
 s=importlib.util.spec_from_file_location(name,D/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
installer=load('cloud_installer','install_job.py');owner=load('cloud_owner','owner_fresh.py')
def fixture():
 helper=D.parent/'executor_identity.py';started=time.monotonic()
 identity=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit='a'*40,execution_id='11111111-1111-4111-8111-111111111111',boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),controller_pid=os.getpid(),start_tick=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),host_identity_sha256='b'*64,started_monotonic=started)
 return dict(execution_context='CLOUD_EXECUTOR_V1',reserved_other_owner_bytes=5<<30,job_budget_seconds=43200,job_started_monotonic=started,stage_resources={'install':{'rss_bytes':2<<30,'as_bytes':2<<30},'reference':{'rss_bytes':2<<30,'as_bytes':2<<30}},identity=identity,pins={str(helper):hashlib.sha256(helper.read_bytes()).hexdigest()})
class Tests(unittest.TestCase):
 def test_actual_identity_helper_current_without_github(self):
  b=fixture()
  with patch.dict(os.environ,{},clear=True):self.assertEqual(installer.verify_controller_identity(b),43200)
 def test_changed_pid_and_boot_rejected(self):
  for key,value in [('controller_pid',1),('boot_id','22222222-2222-4222-8222-222222222222')]:
   b=fixture();b['identity'][key]=value
   with self.assertRaises(ValueError):installer.verify_controller_identity(b)
 def test_clock_not_reset(self):
  b=fixture();b['job_started_monotonic']+=1
  with self.assertRaises(ValueError):installer.verify_controller_identity(b)
  with self.assertRaises(ValueError):owner.identity(b['identity'],b)
 def test_helper_pin_required(self):
  b=fixture();b['pins']={}
  with self.assertRaises(ValueError):installer.verify_controller_identity(b)
  with self.assertRaises(ValueError):owner.identity(b['identity'],b)
 def test_owner_context_deadline_roundtrip(self):
  b=fixture();self.assertEqual(owner.identity(b['identity'],b),b['identity']);self.assertEqual(owner.context_fields(b),installer.context_fields(b))
 def test_ci_clock_cannot_be_changed_via_new_field(self):
  self.assertEqual(installer.job_limit({'job_budget_seconds':43200}),21000)
  self.assertEqual(owner.context_fields({}),{})
 def test_budget_type_bounds_unknown_context(self):
  for v in (None,True,0,-1,float('inf'),2**31):
   b=fixture();b['job_budget_seconds']=v
   with self.assertRaises(ValueError):installer.job_limit(b)
   with self.assertRaises(ValueError):owner.context_fields(b)
  with self.assertRaises(ValueError):installer.job_limit({'execution_context':'FAKE'})
 def test_cloud_snapshot_uses_admitted_budget_not_ci21000(self):
  import test_install_snapshots as old
  case=old.Tests();case.setUp()
  try:
   case.b.update(execution_context='CLOUD_EXECUTOR_V1',reserved_other_owner_bytes=5<<30,job_budget_seconds=43200,job_started_monotonic=time.monotonic()-22000)
   self.assertEqual(case.snap()['status'],'COMPLETE')
  finally:case.tearDown()
 def test_cloud_build_callback_rejected_before_native(self):
  b=fixture();policy=pathlib.Path(installer.profile_policy.__file__).resolve();b['pins'][str(policy)]=hashlib.sha256(policy.read_bytes()).hexdigest();b.update(schema='FRESH_JOB_RUNTIME_CONTROLLER_V1',early_build_seconds=10)
  with self.assertRaisesRegex(ValueError,'no build callback'):installer.run(b,pathlib.Path('/tmp/not-created'),'a'*64,lambda: self.fail('callback invoked'))
 def test_cloud_owner_actual_receipt_chain_and_context_tamper(self):
  import test_owner_fresh as old
  case=old.Tests();case.setUp()
  try:
   cloud=fixture();case.b.update({k:v for k,v in cloud.items()if k!='pins'});case.b['pins'].update(cloud['pins'])
   for key in case.b['runtimes']:
    cap=case.b['runtimes'][key]['caps'];cap.update(rss_bytes=cloud['stage_resources']['install']['rss_bytes'],per_process_as_bytes=cloud['stage_resources']['install']['as_bytes'])
    native=pathlib.Path(case.entries[key]['native']['path']);doc=json.loads(native.read_text());doc['caps']=cap;case.entries[key]['native']=old.write(native,doc)
   old.write(case.bp,case.b)
   index=json.loads(case.index.read_text());index.update(identity=cloud['identity'],entries=case.entries,binding=old.pin(case.bp),**owner.context_fields(cloud));old.write(case.index,index)
   m=old.m;row=m.bind(case.bp,old.pin(case.bp)['sha256'],case.index,old.pin(case.index)['sha256'],case.root/'cloud-owner');manifest,_=m.verify(row['path'],row['sha256'],case.root)
   self.assertEqual(manifest['execution_context'],'CLOUD_EXECUTOR_V1');self.assertEqual(manifest['job_budget_seconds'],43200);self.assertFalse(manifest['numerical_qualified'])
   index['job_budget_seconds']=43201;old.write(case.index,index)
   with self.assertRaises(ValueError):case.evidence()
  finally:case.doCleanups()
 def test_unknown_owner_reserve_cannot_drop(self):
  for value in (None,0,True,4<<30,6<<30):
   b=fixture();b['reserved_other_owner_bytes']=value
   with self.assertRaises(ValueError):installer.job_limit(b)
   with self.assertRaises(ValueError):owner.context_fields(b)
 def test_cloud_role_limits_and_original_ci(self):
  b=fixture();self.assertEqual(installer.install_resources(b),{'rss_bytes':2<<30,'as_bytes':2<<30})
  self.assertEqual(installer.install_resources({}),{'rss_bytes':3<<30,'as_bytes':4<<30})
  for value in (True,0,4<<30):
   b=fixture();b['stage_resources']['install']['rss_bytes']=value
   with self.assertRaises(ValueError):installer.install_resources(b)
   with self.assertRaises(ValueError):owner.context_fields(b)
 def test_bind_gate_adds_own_rss_and_preserves_ci(self):
  caps={'rss_bytes':256<<20}
  self.assertEqual(installer.bind_resource_gate({},caps)['min_available_memory'],1<<30)
  self.assertEqual(installer.bind_resource_gate(fixture(),caps)['min_available_memory'],(256<<20)+(1<<30)+(5<<30))
 def test_original_ci_environment_identity(self):
  b={'identity':{'run_id':123,'source_commit':'a'*40,'launch_commit':'b'*40}}
  with patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_SHA':'b'*40,'GITHUB_RUN_ATTEMPT':'1'},clear=True):self.assertEqual(installer.verify_controller_identity(b),21000)
if __name__=='__main__':unittest.main()
