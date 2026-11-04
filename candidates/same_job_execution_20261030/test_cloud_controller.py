"""Isolated synthetic controller tests, never a native runtime/DUT/artifact PASS."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,time,types,unittest
from unittest.mock import patch
import os
D=pathlib.Path(os.environ.get('FIRST_FAULT_LEGACY_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parent))).resolve()
spec=importlib.util.spec_from_file_location('cloud_flow',D/'controller/cloud_flow.py');flow=importlib.util.module_from_spec(spec);spec.loader.exec_module(flow)
spec=importlib.util.spec_from_file_location('cloud_prepare',D/'prepare_cloud_execution.py');prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
class Tests(unittest.TestCase):
 def test_real_stage_cloud_and_mode_from_cli_initial_binding(self):
  # Only candidate-review authority is synthetic in the shared document
  # fixture. The actual cloud_budget.admit and execution_mode.admit run.
  import test_stage_coverage
  h=test_stage_coverage.Stage();h.setUp()
  try:
   initial=dict(h.b);initial.pop('execution_mode');initial.pop('stage_coverage_budget')
   args=types.SimpleNamespace(stage_coverage_budget=pathlib.Path(h.b['stage_coverage_budget']['path']),stage_coverage_budget_sha256=h.b['stage_coverage_budget']['sha256'])
   roles=prepare.stage_coverage_input(args)
   self.assertEqual(roles['execution_mode'],'STAGE_COVERAGE_DIAGNOSTIC')
   initial.update(roles)
   approved=h.cloud.admit(initial);prepare.preserve_stage_coverage_input(initial,approved)
   initial.update(approved)
   admitted=h.mode.admit(initial)
   self.assertEqual(admitted['profile_seconds']['4'],605)
   self.assertEqual(admitted['reviewed_budget_sha256'],roles['stage_coverage_budget']['sha256'])
   # Recreate the original cycle bug exactly: pin present but no initial mode.
   broken=dict(initial);broken.pop('execution_mode')
   with self.assertRaisesRegex(ValueError,'stage budget forbidden'):h.cloud.admit(broken)
  finally:h.tearDown()
 def test_p0_reuse_requires_paired_stage_and_exact_independent_approval(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'reuse.json';p.write_text('{"SYNTHETIC":true}')
   a=types.SimpleNamespace(p0_provider_reuse=p)
   with self.assertRaisesRegex(ValueError,'paired P0'):prepare.stage_coverage_input(a)
   a.p0_provider_reuse_sha256=prepare.sha(p)
   with self.assertRaisesRegex(ValueError,'explicit diagnostic mode'):prepare.stage_coverage_input(a)
   a.stage_coverage_budget=p;a.stage_coverage_budget_sha256=prepare.sha(p)
   roles=prepare.stage_coverage_input(a);self.assertEqual(roles['p0_provider_reuse'],flow.pin(p))
   prepare.preserve_stage_coverage_input(roles,dict(roles))
   bad=dict(roles,p0_provider_reuse=dict(roles['p0_provider_reuse'],sha256='0'*64))
   with self.assertRaisesRegex(ValueError,'independently approved stage input'):prepare.preserve_stage_coverage_input(roles,bad)
 def test_p0_data_root_never_comes_from_binding_document_parent(self):
  tree=ast.parse((D/'controller/cloud_flow.py').read_text())
  rows=[n for n in ast.walk(tree)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='roots'for t in n.targets)]
  self.assertTrue(rows)
  for row in rows:
   self.assertNotIn("'p0_provider_reuse'",ast.unparse(row))
  run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run')
  expected=ast.parse("""
if 'p0_provider_reuse'in b:
 need('p0_provider_reuse_verified'in imported,'P0 pure data roots verified before watch admission');roots.extend(imported['p0_provider_reuse_verified']['roots']);roots=list(dict.fromkeys(roots))
""").body[0]
  self.assertEqual(sum(ast.dump(n,include_attributes=False)==ast.dump(expected,include_attributes=False)for n in run.body),1)
 def test_real_cloud_approval_matches_cli_p0_reuse_pin(self):
  import test_stage_coverage
  h=test_stage_coverage.Stage();h.setUp()
  try:
   reuse=h.h.put('P0_SYNTHETIC_BINDING',{'scope':'SYNTHETIC_PIN_ONLY_NOT_METADATA_ADMISSION'})
   h.b['p0_provider_reuse']=reuse;h.doc['p0_provider_reuse']=reuse;h.ap['p0_provider_reuse_sha256']=reuse['sha256'];h.h.reapprove()
   initial=dict(h.b);initial.pop('execution_mode');initial.pop('stage_coverage_budget');initial.pop('p0_provider_reuse')
   a=types.SimpleNamespace(stage_coverage_budget=pathlib.Path(h.b['stage_coverage_budget']['path']),stage_coverage_budget_sha256=h.b['stage_coverage_budget']['sha256'],p0_provider_reuse=pathlib.Path(reuse['path']),p0_provider_reuse_sha256=reuse['sha256'])
   initial.update(prepare.stage_coverage_input(a));approved=h.cloud.admit(initial);prepare.preserve_stage_coverage_input(initial,approved)
   self.assertEqual(approved['p0_provider_reuse'],reuse)
   h.ap['p0_provider_reuse_sha256']='0'*64;h.h.reapprove();initial['execution_approval']=h.b['execution_approval']
   with self.assertRaisesRegex(ValueError,'approved exact p0_provider_reuse'):h.cloud.admit(initial)
  finally:h.tearDown()
 def test_real_p0_metadata_checker_is_only_root_authority(self):
  # Real metadata checker + real fixed source/program hashes, sparse synthetic
  # data stat only. No mocked checker response and no weight data hashing.
  import shutil
  fixture_spec=importlib.util.spec_from_file_location('controller_p0_fixture',D/'numeric/test_support_p0_reuse.py')
  fixture=importlib.util.module_from_spec(fixture_spec);fixture_spec.loader.exec_module(fixture)
  with tempfile.TemporaryDirectory()as t:
   f=fixture.build_fixture(pathlib.Path(t));b=dict(f['context']);pin=f['pin'];provider=pathlib.Path(f['document']['provider_root'])
   package=pathlib.Path(t)/'checker';(package/'numeric').mkdir(parents=True);(package/'controller').mkdir()
   checker=package/'numeric/p0_provider_data_reuse.py';shutil.copyfile(D/'numeric/p0_provider_data_reuse.py',checker)
   b.update(p0_provider_reuse=pin,pins={str(checker):flow.sha(checker)})
   approved=dict(execution_mode='STAGE_COVERAGE_DIAGNOSTIC',p0_provider_reuse=pin)
   with patch.object(flow,'D',package/'controller'):
    v=flow.verified_p0_provider_reuse(b,approved,True)
    self.assertEqual(v['watch_scope'],'PURE_PROVIDER_AND_FINITE_EVIDENCE_V1');self.assertEqual(v['roots'],[str(provider),f['document']['evidence_root']]);self.assertNotIn(str(pathlib.Path(pin['path']).parent),v['roots']);self.assertNotIn(str(provider.parent),v['roots'])
    with self.assertRaisesRegex(ValueError,'approved candidate'):flow.verified_p0_provider_reuse(b,approved,False)
    with self.assertRaisesRegex(ValueError,'independent approved pin'):flow.verified_p0_provider_reuse(b,dict(approved,p0_provider_reuse={}),True)
    (provider/'input_only'/'forbidden-output.bin').write_bytes(b'x')
    with self.assertRaisesRegex(ValueError,'extra file'):flow.verified_p0_provider_reuse(b,approved,True)
 def test_stage_basis_metadata_requires_existing_watched_domain(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);control=root/'control';control.mkdir();outside=root/'outside';outside.mkdir()
   evidence=control/'review';evidence.write_text('{}');p=control/'stage';p.write_text(json.dumps({'basis':{'independent_budget_review':flow.pin(evidence),'calibration_summary':flow.pin(evidence)}}))
   b=dict(execution_mode='STAGE_COVERAGE_DIAGNOSTIC',stage_coverage_budget=flow.pin(p))
   flow.stage_budget_watch_coverage(b,[str(control)])
   extra=outside/'summary';extra.write_text('{}');p.write_text(json.dumps({'basis':{'calibration_summary':flow.pin(extra)}}));b['stage_coverage_budget']=flow.pin(p)
   with self.assertRaisesRegex(ValueError,'inside admitted watched'):flow.stage_budget_watch_coverage(b,[str(control)])
 def test_stage_budget_cli_pair_and_real_hash(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'stage.json';p.write_text('{"synthetic":true}')
   a=types.SimpleNamespace(stage_coverage_budget=p)
   with self.assertRaisesRegex(ValueError,'paired stage coverage'):prepare.stage_coverage_input(a)
   a.stage_coverage_budget_sha256=prepare.sha(p);row=prepare.stage_coverage_input(a)['stage_coverage_budget']
   self.assertEqual(row,flow.pin(p));a.stage_coverage_budget_sha256='0'*64
   with self.assertRaises(ValueError):prepare.stage_coverage_input(a)
   self.assertEqual(prepare.stage_coverage_input(types.SimpleNamespace()),{})
 def test_independently_approved_stage_pin_must_equal_cli(self):
  row={'path':'/synthetic/stage','bytes':2,'sha256':'a'*64}
  approved={'execution_mode':'STAGE_COVERAGE_DIAGNOSTIC','stage_coverage_budget':row}
  prepare.preserve_stage_coverage_input({'stage_coverage_budget':row},approved)
  for b in ({},{'stage_coverage_budget':dict(row,sha256='b'*64)}):
   with self.assertRaises(ValueError):prepare.preserve_stage_coverage_input(b,approved)
  for mode in ('BOUNDED_CALIBRATION','FULL_BLOCK_ACCEPTANCE'):
   with self.assertRaises(ValueError):prepare.preserve_stage_coverage_input({'stage_coverage_budget':row},{'execution_mode':mode})
 def test_stage_transport_never_full_even_if_qualification_passes(self):
  for q in ({'status':'INCOMPLETE','numerical_pass':False},{'status':'PASS_FIVE_FULL128_EXACT_REFERENCE','numerical_pass':True}):self.assertEqual(flow.transport_code('STAGE_COVERAGE_DIAGNOSTIC',q),2)
 def test_stage_reservations_use_admitted_windows_not_calibration_placeholder(self):
  q=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600,calibration_seconds=dict.fromkeys(map(str,range(5)),300))
  b=dict(budgets=q,job_budget_seconds=43200,execution_mode='STAGE_COVERAGE_DIAGNOSTIC')
  short=flow.reservations(b,{'profile_seconds':q['calibration_seconds']})
  long=flow.reservations(b,{'profile_seconds':dict.fromkeys(map(str,range(5)),4000)})
  self.assertEqual(long[0],short[0]);self.assertEqual(long[1]-short[1],5*3700);self.assertEqual(long[2]-short[2],5*3700)

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
 def test_real_numeric_definition_import_in_clean_subprocess(self):
  import subprocess,sys
  code="""import pathlib,importlib.util,sys
E=pathlib.Path(sys.argv[1]);s=importlib.util.spec_from_file_location('flow_under_test',E/'controller/cloud_flow.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
pins={str(p):f.sha(p)for p in(E/'numeric').glob('*.py')};before=list(sys.path)
m=f.numeric_module('numeric_definition_only',E/'numeric/numeric_tail.py',pins)
if not callable(m.run) or sys.path!=before:raise RuntimeError('definition/path restoration failed')
print('REAL_DEFINITION_IMPORT_ONLY_OK')
"""
  result=subprocess.run([sys.executable,'-B','-c',code,str(D)],capture_output=True,text=True,timeout=30,check=True)
  self.assertEqual(result.stdout.strip(),'REAL_DEFINITION_IMPORT_ONLY_OK')
 def test_numeric_sibling_pin_fail_before_import(self):
  with patch.object(flow,'mod',side_effect=AssertionError('must not import')):
   with self.assertRaisesRegex(ValueError,'numeric sibling source pin'):flow.numeric_module('no_import',D/'numeric/numeric_tail.py',{})
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
 def test_stage_approval_without_explicit_cli_pin_never_publishes_identity(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);a,manifest=self.setup_inputs(root)
   policy=types.SimpleNamespace(FULL='FULL_FIVE_ORIGINAL_HOST_POLICY',policy=lambda _: {},require_source_pin=lambda _:None)
   modules={'cloud_identity_policy':policy,'cloud_identity_budget':types.SimpleNamespace(admit=lambda b:dict(execution_mode='STAGE_COVERAGE_DIAGNOSTIC',stage_coverage_budget={'synthetic':'not_cli_supplied'}))}
   with patch.object(prepare,'verify_source',return_value=(root,manifest,{})),patch.object(prepare,'load',side_effect=lambda name,path:modules[name]),patch.object(prepare.subprocess,'check_output',side_effect=AssertionError('no git before explicit input match')):
    with self.assertRaisesRegex(ValueError,'explicit CLI stage budget'):prepare.prepare_identity(a)
   self.assertFalse((root/'job-EXECUTOR_IDENTITY.json').exists());self.assertFalse(a.work.exists())
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
   modules={'cloud_identity_policy':policy,'cloud_identity_budget':types.SimpleNamespace(admit=lambda b:{'job_budget_seconds':43200,'execution_mode':'BOUNDED_CALIBRATION'},verify_host=lambda h,i:None),'cloud_identity_live':types.SimpleNamespace(verify_current=lambda i:observed.append(i)),'cloud_identity_mode':types.SimpleNamespace(admit=lambda b:{}),'cloud_identity_flow':types.SimpleNamespace(reservations=lambda b,m:(1,1,2)),'entry_selected_handoff':types.SimpleNamespace(verify=lambda *args:{'source_pins_sha256':flow.sha(manifest)})}
   helper=D/'numeric/artifact_handoff.py';pins={str(helper):flow.sha(helper)}
   with patch.object(prepare,'verify_source',return_value=(root,manifest,pins)),patch.object(prepare,'load',side_effect=lambda name,path:modules[name]),patch.object(prepare.subprocess,'check_output',return_value='a'*40):prepare.prepare_identity(a)
   identity=json.loads(a.executor_identity.read_text());self.assertEqual(identity['controller_pid'],os.getpid());self.assertEqual(identity,observed[0]);self.assertEqual(identity['host_identity_sha256'],a.host_identity_sha256);self.assertNotIn('run_id',identity);self.assertEqual(flow.sha(a.executor_identity),a.executor_identity_sha256)

class ReferenceReuseEntry(unittest.TestCase):
 def test_reference_pair_and_approved_tree_cap(self):
  import argparse,tempfile,pathlib
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'input.json';p.write_text('{}')
   a=argparse.Namespace(stage_coverage_budget=p,stage_coverage_budget_sha256=prepare.sha(p),reference_data_reuse=p,reference_data_reuse_sha256=prepare.sha(p))
   b=prepare.stage_coverage_input(a);self.assertEqual(b['reference_data_reuse'],prepare.input_pin(p,prepare.sha(p)))
   approved=dict(b,aggregate_tree_cap_bytes=12037043872)
   prepare.preserve_stage_coverage_input(b,approved);self.assertEqual(b['aggregate_tree_cap_bytes'],12037043872)
   a.reference_data_reuse_sha256=None
   with self.assertRaises(ValueError):prepare.stage_coverage_input(a)
   a.reference_data_reuse_sha256=prepare.sha(p);a.stage_coverage_budget=None;a.stage_coverage_budget_sha256=None
   with self.assertRaises(ValueError):prepare.stage_coverage_input(a)

class ActualRuntimeBudgetJoin(unittest.TestCase):
 def test_generated_install_mode_fields_real_budget_and_reuse_admit(self):
  import shutil,test_stage_coverage
  h=test_stage_coverage.Stage();h.setUp();self.addCleanup(h.tearDown)
  r=h.e/'runtime';r.mkdir()
  for name in ('runtime_reuse.py','runtime_dependencies.py'):shutil.copyfile(D/'runtime'/name,r/name)
  shutil.copyfile(D/'profile_policy.py',h.e/'profile_policy.py')
  # Sole mocked authority is process liveness. Cloud/mode admission is actual.
  identity=h.e/'executor_identity.py';identity.write_text('def verify_owner(i):pass\ndef verify_current(i):pass\n')
  h.b['identity']['started_monotonic']=time.monotonic();h.b['job_started_monotonic']=h.b['identity']['started_monotonic']
  row=h.h.put('reference_reuse',{'ALL_SYNTHETIC':True});runtime=h.h.put('runtime_manifest',{'ALL_SYNTHETIC':True})
  h.b['reference_data_reuse']=row;h.doc['reference_data_reuse']=row;h.ap['reference_data_reuse_sha256']=row['sha256'];h.doc['aggregate_tree_cap_bytes']=12037043872
  h.doc.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=runtime)
  h.b['pins'].update({str(p):flow.sha(p)for p in (identity,r/'runtime_reuse.py')});h.reapprove()
  admitted=h.cloud.admit(h.b);h.b.update(admitted)
  base={k:h.b[k]for k in ('execution_context','identity','job_started_monotonic','job_budget_seconds','pins','cloud_budget','execution_approval','artifact_manifest','stage_resources','reserved_other_owner_bytes','runtime_reuse_manifest')}
  # Execute the production INSTALL construction and its actual reuse update,
  # not a separately invented field list. No runtime/stage process is invoked.
  h.b['shared_runtime_helper']='synthetic';job=h.h.d/'job';job.mkdir();(job/'runs/archives/output').mkdir(parents=True)
  ab=job/'ARCHIVES_BINDING.json';ab.write_text('{}')
  for name in ('RESULT.json','output/ARCHIVES.json'):(job/'runs/archives'/name).write_text('{}')
  tree=ast.parse((D/'controller/cloud_flow.py').read_text());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run')
  idx=next(i for i,n in enumerate(run.body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='install_binding'for t in n.targets))
  branch=run.body[idx+2];self.assertIsInstance(branch,ast.If)
  env=dict(flow.__dict__,b=h.b,execution_policy=flow.profile_policy.policy(flow.profile_policy.FULL),identity=h.b['identity'],limit=h.b['job_budget_seconds'],repo=h.h.d,owner_root=job/'materials',py='synthetic',supervisor_dir='synthetic',lock='synthetic',roots=[],ipins=h.b['pins'],archives_rows=[],started=h.b['job_started_monotonic'],q=h.b['budgets'],tail_reserved=1,job=job,runtime=r,ab=ab,archives=job/'runs/archives/output')
  exec(compile(ast.Module(body=[run.body[idx],run.body[idx+1],branch.body[0]],type_ignores=[]),'actual_install_binding','exec'),env)
  install=env['install_binding']
  reuse=flow.mod('real_runtime_admission_fixture',r/'runtime_reuse.py')
  self.assertEqual(reuse.admit(install)['aggregate_tree_cap_bytes'],12037043872)
  install.update(install_wall_seconds=180,owned_roots=[])
  self.assertEqual(reuse.phase_caps(install)['watch_tree_bytes'],12037043872)
  for missing in ('execution_mode','stage_coverage_budget','reference_data_reuse'):
   broken=dict(install);del broken[missing]
   with self.subTest(missing=missing),self.assertRaises((ValueError,KeyError)):reuse.admit(broken)
  broken=dict(install,aggregate_tree_cap_bytes=12037043873)
  with self.assertRaises(ValueError):reuse.admit(broken)
 def test_tighter_census_does_not_lower_free_reserve(self):
  cap=12037043872;s=dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,bytes=100,free_bytes=cap-100+(8<<30))
  got=flow.upfront_disk_admission(s,tree_cap=cap);self.assertEqual(got['free_reserve_bytes'],8<<30)
  s['free_bytes']-=1
  with self.assertRaises(ValueError):flow.upfront_disk_admission(s,tree_cap=cap)
  for invalid in (True,12037043873):
   with self.assertRaises(ValueError):flow.upfront_disk_admission(s,tree_cap=invalid)

class ActualReferenceMetadataJoin(unittest.TestCase):
 def test_source_pinned_metadata_roots_are_actual_five_reference_dirs(self):
  helper=flow.mod('reference_metadata_fixture',D/'numeric/test_reference_data_reuse.py')
  with tempfile.TemporaryDirectory()as tmp:
   doc,row,b,out,save=helper.fixture(pathlib.Path(tmp))
   path=D/'numeric/reference_data_reuse.py';b.update(reference_data_reuse=row,pins={str(path):flow.sha(path)})
   budget=dict(execution_mode='STAGE_COVERAGE_DIAGNOSTIC',reference_data_reuse=row,aggregate_tree_cap_bytes=12037043872)
   actual=flow.verified_reference_data_reuse(b,budget,True)
   self.assertEqual(set(actual['roots']),{str(pathlib.Path(v['path']).parent)for v in doc['references'].values()})
   self.assertNotIn(str(pathlib.Path(row['path']).parent),actual['roots'])
   for bad in (dict(budget,reference_data_reuse=dict(row,sha256='0'*64)),dict(budget,aggregate_tree_cap_bytes=12037043873)):
    with self.assertRaises(ValueError):flow.verified_reference_data_reuse(b,bad,True)
   with self.assertRaises(ValueError):flow.verified_reference_data_reuse(b,budget,False)
   doc['references']['0']['path']=str(pathlib.Path(tmp)/'bogus.json');save();b['reference_data_reuse']=helper.core.pin(row['path']);budget['reference_data_reuse']=b['reference_data_reuse']
   with self.assertRaises((ValueError,FileNotFoundError)):flow.verified_reference_data_reuse(b,budget,True)
