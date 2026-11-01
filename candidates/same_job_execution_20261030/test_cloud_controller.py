"""Isolated synthetic controller tests, never a native runtime/DUT/artifact PASS."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,time,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cloud_flow',D/'controller/cloud_flow.py');flow=importlib.util.module_from_spec(spec);spec.loader.exec_module(flow)
spec=importlib.util.spec_from_file_location('cloud_prepare',D/'prepare_cloud_execution.py');prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
class Tests(unittest.TestCase):
 def test_optional_adaptation_input_pair_rejected_before_loading(self):
  a=types.SimpleNamespace(executor_adaptation=pathlib.Path('/nonexistent'))
  with self.assertRaisesRegex(ValueError,'paired executor_adaptation'):prepare.adaptation_inputs(a,{})
 def test_legacy_adaptation_inputs_empty(self):self.assertEqual(prepare.adaptation_inputs(types.SimpleNamespace(),{}),{})
 def test_source_review_uses_explicit_adapter_not_equal_catalog(self):
  identity={'source_commit':'b'*40};builder={'source_commit':'a'*40};record={}
  def verify(*args,**kw):record.update(args=args,kw=kw)
  with tempfile.TemporaryDirectory()as t:
   manifest=pathlib.Path(t)/'SOURCE_PINS.json';manifest.write_text('{}');roles={'executor_adaptation':{'synthetic':True}}
   with patch.object(prepare,'load',return_value=types.SimpleNamespace(verify=verify)):
    prepare.reviewed_source({'builder_identity':builder,'source_pins_sha256':'old'},identity,roles,manifest,pathlib.Path(t))
   self.assertEqual(record['args'],(roles['executor_adaptation'],builder,identity));self.assertEqual(record['kw']['current_source_pins_pin']['sha256'],prepare.sha(manifest))
   with self.assertRaises(ValueError):prepare.reviewed_source({'source_pins_sha256':'old'},identity,{},manifest,pathlib.Path(t))
 def test_real_admitted_inputs_adapted_handoff_and_fail_closed(self):
  with tempfile.TemporaryDirectory()as t:
   repo=pathlib.Path(t);e=repo/'E';controller=e/'controller';controller.mkdir(parents=True);(e/'numeric').mkdir()
   for n in ('cloud_budget.py','executor_identity.py','execution_mode.py','executor_adaptation.py','numeric/artifact_handoff.py','numeric/workspace_loader.py','numeric/runtime_abi_owned.py','SOURCE_PINS.json'):(e/n).write_text('{}')
   def put(n,d):
    p=repo/n;p.write_text(json.dumps(d));return flow.pin(p)
   identity=dict(source_commit='b'*40,started_monotonic=1);builder=dict(source_commit='a'*40)
   budget={k:None for k in ('runtime_mode','archive_mode','runtime_reuse_manifest','job_budget_seconds','budgets','dut_rss_bytes','dut_address_space_bytes','numeric_reserved_increment_bytes','reserved_other_owner_bytes','consumer_address_space_bytes','stage_resources','execution_mode','full_block_budget')}
   budget.update(executor_adaptation=put('adapter',{}),workspace_loader=put('loader',{}))
   b=dict(budget,execution_context='CLOUD_EXECUTOR_V1',identity=identity,executor_identity=identity,job_started_monotonic=1,artifact_identity=builder,repo=str(repo),pins={str(e/n):flow.sha(e/n)for n in ('cloud_budget.py','executor_identity.py','execution_mode.py','executor_adaptation.py','numeric/artifact_handoff.py','numeric/workspace_loader.py','numeric/runtime_abi_owned.py')},executor_identity_pin=put('identity',identity),artifact_manifest=put('artifact',{'common':{'binary':{'path':'host','sha256':'h'}},'tool_manifest':{'path':'tool','sha256':'t'}}),builder_handoff=put('handoff',{}),cloud_budget=put('budget',{'host_identity':{}}),source_pins=flow.pin(e/'SOURCE_PINS.json'))
   seen=[];imported={'builder_identity':builder,'source_pins_sha256':'old-distinct-catalog'}
   def handoff(*args,**kw):self.assertEqual(kw,{'executor_adaptation':b['executor_adaptation']});seen.append('handoff');return imported
   def adaptation(*args,**kw):self.assertEqual(args,(b['executor_adaptation'],builder,identity));self.assertEqual(kw['current_source_pins_pin'],b['source_pins']);seen.append('adaptation')
   verified=dict(root=str(repo/'libs'),artifact_manifest_sha256=b['artifact_manifest']['sha256'],builder_source_commit=builder['source_commit'])
   def loader(*args):
    self.assertEqual(args[:5],(b['workspace_loader'],repo/'host','h',repo/'tool','t'));seen.append('loader');return verified
   modules={'actual_cloud_workspace_loader':types.SimpleNamespace(verify=loader),'actual_cloud_runtime_abi':types.SimpleNamespace(elf_info=lambda _:None),'actual_cloud_budget':types.SimpleNamespace(admit=lambda _:budget,verify_host=lambda *a:None),'actual_cloud_identity':types.SimpleNamespace(verify_current=lambda _:None),'actual_imported_artifact':types.SimpleNamespace(verify=handoff),'actual_executor_adaptation':types.SimpleNamespace(verify=adaptation)}
   with patch.object(flow,'D',controller),patch.object(flow,'mod',side_effect=lambda name,path:modules[name]),patch.object(flow.subprocess,'check_output',return_value='b'*40):
    self.assertEqual(flow.admitted_inputs(b),(budget,dict(imported,workspace_loader_verified=verified)));self.assertEqual(seen,['handoff','adaptation','loader'])
    with patch.object(modules['actual_executor_adaptation'],'verify',side_effect=ValueError('forbidden source diff')):
     with self.assertRaisesRegex(ValueError,'forbidden source diff'):flow.admitted_inputs(b)
    b['workspace_loader']={'different':True}
    with self.assertRaisesRegex(ValueError,'binding reviewed workspace_loader'):flow.admitted_inputs(b)
 def test_upfront_disk_reserves_only_remaining_aggregate_growth(self):
  snap=dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,bytes=4<<30,free_bytes=20_180_000_000)
  self.assertLess(snap['free_bytes'],flow.TREE+(8<<30))
  result=flow.upfront_disk_admission(snap);self.assertEqual(result['required_free_bytes'],flow.TREE-(4<<30)+(8<<30))
  for change in ({'bytes':flow.TREE+1},{'bytes':True},{'complete':False},{'free_bytes':result['required_free_bytes']-1}):
   with self.assertRaises(ValueError):flow.upfront_disk_admission(dict(snap,**change))
  with self.assertRaises(ValueError):flow.upfront_disk_admission(dict(snap,bytes=0))
  full=dict(snap,bytes=flow.TREE,free_bytes=(8<<30)-1)
  with self.assertRaises(ValueError):flow.upfront_disk_admission(full)
 def test_actual_budget_none_gate_precedes_process_and_work(self):
  pins={str(D/n):flow.sha(D/n) for n in ('cloud_budget.py','executor_identity.py','execution_mode.py')}
  with patch.object(flow.subprocess,'check_output',side_effect=AssertionError('no git yet')),patch.object(pathlib.Path,'mkdir',side_effect=AssertionError('no work')):
   with self.assertRaisesRegex(ValueError,'OPERATOR_APPROVED_EXECUTION_INPUT_REQUIRED'):
    flow.run({'execution_context':'CLOUD_EXECUTOR_V1','pins':pins},pathlib.Path('/tmp/nonexistent'),'a'*64)
 def test_no_ci_or_backend_in_cloud_flow(self):
  text=(D/'controller/cloud_flow.py').read_text()
  for forbidden in ('GITHUB_RUN_ID','GITHUB_SHA','21000','bootstrap_samejob','build_after_first_runtime','build_result=','q[\'build\']'):
   self.assertNotIn(forbidden,text)
  self.assertIn('early_build_seconds=0',text);self.assertNotIn('after_first_install=',text)
 def test_reviewed_total_not_ci_ceiling(self):
  q=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600,calibration_seconds={str(i):300 for i in range(5)})
  b=dict(budgets=q,job_budget_seconds=43200)
  _,_,total=flow.reservations(b,{'profile_seconds':{str(i):6000 for i in range(5)}})
  self.assertGreater(total,21000);self.assertLessEqual(total,43200)
  b['job_budget_seconds']=total-1
  with self.assertRaises(ValueError):flow.reservations(b,{'profile_seconds':{str(i):6000 for i in range(5)}})
 def test_original_resource_caps_preserved(self):
  self.assertEqual(flow.stage_policy('reference',180)['rss_bytes'],3<<30);self.assertEqual(flow.stage_policy('reference',180)['cpu_seconds'],1200)
  self.assertEqual(flow.stage_policy('archives',600)['rss_bytes'],256<<20)
 def test_admitted_reference_role_not_original3GiB(self):
  roles={'reference':{'rss_bytes':2<<30,'as_bytes':2<<30}}
  resource=flow.stage_policy('reference',180,roles);self.assertEqual(resource['rss_bytes'],2<<30);self.assertEqual(resource['as_bytes'],2<<30);self.assertEqual(resource['cpu_seconds'],1200)
  roles['reference']['rss_bytes']=4<<30
  with self.assertRaises(ValueError):flow.stage_policy('reference',180,roles)
 def test_independent_input_pin(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'receipt';p.write_text('{}');h=flow.sha(p)
   self.assertEqual(prepare.input_pin(p,h)['sha256'],h)
   with self.assertRaises(ValueError):prepare.input_pin(p,'a'*64)
   link=p.with_name('link');link.symlink_to(p)
   with self.assertRaises(ValueError):prepare.input_pin(link,h)
 def test_binding_scope_and_deadline_before_output(self):
  text=(D/'prepare_cloud_execution.py').read_text()
  self.assertLess(text.index('flow.admitted_inputs(b)'),text.index("binding.open('x')"))
  self.assertLess(text.index('flow.reservations(b,mode)'),text.index("binding.open('x')"))
  for key in ('executor_identity=identity','source_pins=dict(','artifact_identity=frozen','cloud_budget=roles'):self.assertIn(key,text)
if __name__=='__main__':unittest.main()

class IdentityEntryTests(unittest.TestCase):
 def setup_inputs(self,root):
  manifest=root/'SOURCE_PINS.json';manifest.write_text('{}')
  a=types.SimpleNamespace(repo=root,work=root/'job',executor_identity=None,executor_identity_sha256=None)
  for role in ('host_identity','builder_handoff','artifact_manifest','cloud_budget','execution_approval'):
   p=root/(role+'.json');p.write_text(json.dumps({'source_commit':'a'*40,'execution_id':'11111111-1111-4111-8111-111111111111'} if role=='execution_approval' else {'host_identity':{}} if role=='cloud_budget' else {}));setattr(a,role,p);setattr(a,role+'_sha256',flow.sha(p))
  return a,manifest
 def test_unapproved_new_identity_never_written(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);a,manifest=self.setup_inputs(root)
   policy=types.SimpleNamespace(FULL='FULL_FIVE_ORIGINAL_HOST_POLICY',policy=lambda _: {},require_source_pin=lambda _:None)
   def denied(_):raise ValueError('operator approval denied')
   modules={'cloud_identity_policy':policy,'cloud_identity_budget':types.SimpleNamespace(admit=denied)}
   with patch.object(prepare,'verify_source',return_value=(root,manifest,{})),patch.object(prepare,'load',side_effect=lambda name,path:modules[name]),patch.object(prepare.subprocess,'check_output',side_effect=AssertionError('no git before approval')):
    with self.assertRaisesRegex(ValueError,'operator approval denied'):prepare.prepare_identity(a)
   self.assertFalse((root/'job-EXECUTOR_IDENTITY.json').exists())
 def test_mock_approved_launcher_uses_this_process_not_builder(self):
  import os
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);a,manifest=self.setup_inputs(root);observed=[]
   policy=types.SimpleNamespace(FULL='FULL_FIVE_ORIGINAL_HOST_POLICY',policy=lambda _: {},require_source_pin=lambda _:None)
   modules={'cloud_identity_policy':policy,'cloud_identity_budget':types.SimpleNamespace(admit=lambda b:{'job_budget_seconds':43200},verify_host=lambda h,i:None),'cloud_identity_live':types.SimpleNamespace(verify_current=lambda i:observed.append(i)),'cloud_identity_mode':types.SimpleNamespace(admit=lambda b:{}),'cloud_identity_flow':types.SimpleNamespace(reservations=lambda b,m:(1,1,2)),'cloud_identity_handoff':types.SimpleNamespace(verify=lambda *args:{'source_pins_sha256':flow.sha(manifest)})}
   with patch.object(prepare,'verify_source',return_value=(root,manifest,{})),patch.object(prepare,'load',side_effect=lambda name,path:modules[name]),patch.object(prepare.subprocess,'check_output',return_value='a'*40):prepare.prepare_identity(a)
   identity=json.loads(a.executor_identity.read_text());self.assertEqual(identity['controller_pid'],os.getpid());self.assertEqual(identity,observed[0]);self.assertEqual(identity['host_identity_sha256'],a.host_identity_sha256);self.assertNotIn('run_id',identity);self.assertEqual(flow.sha(a.executor_identity),a.executor_identity_sha256)
