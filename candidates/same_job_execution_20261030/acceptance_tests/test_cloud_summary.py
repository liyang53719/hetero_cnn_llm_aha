"""Synthetic receipts; source/handoff test seams do NOT authenticate any real build."""
import importlib.util,json,pathlib,tempfile,unittest,types,sys
from unittest.mock import patch
import test_safe_summary_join as base
D=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cloud_summary',D/'summarize_cloud_execution.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

class Tests(unittest.TestCase):
 def fixture(self,root,ids=range(5)):
  job=root/'job';job.mkdir();base.Tests().setup_fixture(job,ids);n=job/'materials/numeric'
  executor=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit='a'*40,execution_id='11111111-2222-4333-8444-555555555555',boot_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',controller_pid=123,start_tick=456,host_identity_sha256='d'*64,started_monotonic=1)
  builder=dict(base.ID);manifest=root/'frozen_artifact.json';manifest.write_text(json.dumps(dict(artifact_identity=builder,common={'binary':{'sha256':base.H}})));handoff=root/'HANDOFF.json';handoff.write_text('{}')
  approval=root/'APPROVAL.json';approval.write_text('{}');budget=root/'BUDGET.json';budget.write_text('{}')
  b=dict(job_root=str(job),identity=executor,execution_approval=s.pin(approval),cloud_budget=s.pin(budget),artifact_identity=builder,artifact_manifest=s.pin(manifest),builder_handoff=s.pin(handoff),execution_mode='BOUNDED_CALIBRATION',calibration_seconds={str(i):300 for i in range(5)})
  bp=root/'BINDING.json';bp.write_text(json.dumps(b));nf=n/'RESULT.json';nr=json.loads(nf.read_text())
  records=[]
  for i in ids:
   out=n/f'profile{i}/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text());original=dict(wall_seconds=20000,max_active_cycles=1000000000,address_space_bytes=12<<30)
   r.update(executor_identity=executor,builder_handoff_sha256=b['builder_handoff']['sha256'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],execution_admission=dict(execution_mode='BOUNDED_CALIBRATION',reviewed_budget_sha256=None,outer_cleanup_proof_required=True,original_limits=original,effective_limits=dict(original,wall_seconds=300,address_space_bytes=2<<30),scope='CALIBRATION_SAME_FULL_M128_STIMULUS'))
   r['resource_admission']=dict(consumer_pre_fork_soft_bytes=512<<20,consumer_pre_fork_hard_bytes=2<<30,consumer_after_popen_hard_bytes=512<<20,dut_hard_address_space_bytes=2<<30,group_rss_is_sampled=True)
   rp.write_text(json.dumps(r));record=base.d.verify(out,i,b['artifact_manifest']['sha256'],base.H,base.H,base.H,s.pin(n/f'runs/p{i}_dut/RESULT.json'));(n/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record));records.append(record)
  q=base.a.aggregate(records);nr.update(execution_mode='BOUNDED_CALIBRATION',full_budget_sha256=None,actual_dut_reports=records,qualification=q,status=q['status'],numerical_pass=q['numerical_pass']);nf.write_text(json.dumps(nr))
  flow=dict(identity=executor,execution_approval=b['execution_approval'],artifact_identity=builder,execution_binding=s.pin(bp),builder_handoff=b['builder_handoff'],artifact_manifest=b['artifact_manifest'],numeric_result=s.pin(nf),hardware_definitions=1,profiles=list(range(5)),execution_mode='BOUNDED_CALIBRATION',transport_exit_code=2,qualification=q,status=q['status']);(job/'FLOW_RESULT.json').write_text(json.dumps(flow));return job,bp
 def project(self,job,bp):
  original=s.load
  def loader(name,path):
   m=original(name,path)
   if name=='summary_cloud_handoff':m.verify=lambda *args:dict(source_pins_sha256='f'*64)
   if name=='summary_cloud_budget':m.admit=lambda binding:dict(execution_mode=binding['execution_mode'],full_block_budget=binding.get('full_block_budget'),consumer_address_space_bytes=512<<20,dut_address_space_bytes=2<<30)
   return m
  with patch.object(s,'source_guard',return_value='f'*64),patch.object(s,'load',side_effect=loader):return s.project(job,bp,s.sha(bp))
 def test_synthetic_five_receipts(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));r=self.project(job,bp);self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertFalse(r['final_rtl_executed']);self.assertNotIn(t,json.dumps(r))
 def test_four_incomplete(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t),range(1,5));r=self.project(job,bp);self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertFalse(r['numerical_pass'])
 def test_identity_or_mode_or_cleanup_rejected(self):
  for kind in ('executor','builder','mode','cleanup','resource','hard_claim'):
   with tempfile.TemporaryDirectory()as t:
    job,bp=self.fixture(pathlib.Path(t));p=job/'materials/numeric/profile0/material/dut_result/RESULT.json';r=json.loads(p.read_text())
    if kind=='executor':r['executor_identity']['execution_id']='22222222-2222-4333-8444-555555555555'
    if kind=='builder':r['artifact_identity']['run_id']=999
    if kind=='mode':r['execution_admission']['execution_mode']='FULL_BLOCK_ACCEPTANCE'
    if kind=='cleanup':r['execution_admission']['outer_cleanup_proof_required']=False
    if kind=='resource':r['resource_admission']['dut_hard_address_space_bytes']=12<<30
    if kind=='hard_claim':r['resource_admission']['group_rss_is_sampled']=False
    p.write_text(json.dumps(r))
    # Rebind every content pin so this exercises identity/mode gates, not merely
    # stale receipt rejection. Actual verifier still rechecks the original chain.
    n=job/'materials/numeric';record_path=n/'PROFILE_0_DIAGNOSTIC.json';record=json.loads(record_path.read_text());record['report']=s.pin(p);record_path.write_text(json.dumps(record));nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr['actual_dut_reports'][0]=record;nf.write_text(json.dumps(nr));ff=job/'FLOW_RESULT.json';flow=json.loads(ff.read_text());flow['numeric_result']=s.pin(nf);ff.write_text(json.dumps(flow))
    self.assertEqual(self.project(job,bp)['status'],'UNAVAILABLE')
 def test_source_guard_actual_bytes(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);d=root/'candidates/e';(d/'numeric').mkdir(parents=True)
   required=['executor_identity.py','cloud_budget.py','execution_mode.py','profile_policy.py','numeric/artifact_handoff.py','numeric/dut_evidence.py','numeric/required_acceptance.py']
   files=[];pins={}
   for name in required:
    p=d/name;p.write_text('synthetic source');pins[str(p)]=s.sha(p);files.append(dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=s.sha(p)))
   own=d/'summarize_cloud_execution.py';own.write_bytes(pathlib.Path(s.__file__).read_bytes());pins[str(own)]=s.sha(own);files.append(dict(path=str(own.relative_to(root)),bytes=own.stat().st_size,sha256=s.sha(own)))
   manifest=d/'SOURCE_PINS.json';manifest.write_text(json.dumps(dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=files)))
   binding=dict(source_pins=s.pin(manifest),pins=pins)
   with patch.object(s,'D',d),patch.object(s,'__file__',str(own)):
    self.assertEqual(s.source_guard(binding),s.sha(manifest))
    binding['retained_materials']={'path':'synthetic-only','bytes':1,'sha256':'0'*64}
    with self.assertRaises(ValueError):s.source_guard(binding)
    helper=d/'runtime/retained_materials.py';helper.parent.mkdir();helper.write_text('synthetic retained verifier')
    files.append(dict(path=str(helper.relative_to(root)),bytes=helper.stat().st_size,sha256=s.sha(helper)));manifest.write_text(json.dumps(dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=files)));binding['source_pins']=s.pin(manifest)
    with self.assertRaises(ValueError):s.source_guard(binding)
    pins[str(helper)]=s.sha(helper);self.assertEqual(s.source_guard(binding),s.sha(manifest))
    helper.write_text('drift')
    with self.assertRaises(ValueError):s.source_guard(binding)
    del binding['retained_materials'];helper.write_text('synthetic retained verifier')
    (d/required[0]).write_text('drift')
    with self.assertRaises(ValueError):s.source_guard(binding)
 def test_approval_mismatch_refused(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));ff=job/'FLOW_RESULT.json';f=json.loads(ff.read_text());f['execution_approval']['sha256']='9'*64;ff.write_text(json.dumps(f));self.assertEqual(self.project(job,bp)['status'],'UNAVAILABLE')
 def test_handoff_closure_mismatch_refused(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));original=s.load
   def loader(name,path):
    m=original(name,path)
    if name=='summary_cloud_handoff':m.verify=lambda *args:dict(source_pins_sha256='0'*64)
    return m
   with patch.object(s,'source_guard',return_value='f'*64),patch.object(s,'load',side_effect=loader):self.assertEqual(s.project(job,bp,s.sha(bp))['status'],'UNAVAILABLE')
 def test_real_closure_sized_binding_over64k(self):
  # Use actual current source inventory paths/hashes, not padding masquerading
  # as source pins. This test still mocks approval/hand-off authentication.
  doc=json.loads((D/'SOURCE_PINS.json').read_text());repo=D.parents[1]
  pins={str(repo/r['path']):r['sha256']for r in doc['files']}
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));b=json.loads(bp.read_text());b['pins']=pins;bp.write_text(json.dumps(b));self.assertGreater(bp.stat().st_size,65536);self.assertLessEqual(bp.stat().st_size,1<<20)
   ff=job/'FLOW_RESULT.json';f=json.loads(ff.read_text());f['execution_binding']=s.pin(bp);ff.write_text(json.dumps(f));result=self.project(job,bp)
   self.assertEqual(result['status'],'VERIFIED_REAGGREGATED');self.assertLessEqual(len(json.dumps(result).encode()),65536)
 def test_binding_over1m_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));b=json.loads(bp.read_text());b['oversize_fixture']='x'*(1<<20);bp.write_text(json.dumps(b));self.assertGreater(bp.stat().st_size,1<<20)
   self.assertEqual(self.project(job,bp)['status'],'UNAVAILABLE')
 def test_missing_flow_partial_native_failure_not_oom(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));(job/'FLOW_RESULT.json').unlink();r=job/'runs/weights/RESULT.json';r.parent.mkdir(parents=True);r.write_text(json.dumps(dict(native_exit=1,errors=['secret arbitrary error'],cleanup_proof={},log_capture={},elapsed_seconds=1.25,observed_peak_rss=1024)))
   result=self.project(job,bp);self.assertEqual(result['status'],'INCOMPLETE_EXECUTION');self.assertFalse(result['numerical_pass']);self.assertNotIn('secret',json.dumps(result));self.assertLessEqual(len(json.dumps(result).encode()),65536)
   stage=next(x for x in result['stages']if x['name']=='weights');self.assertEqual(stage['status'],'INCOMPLETE_NATIVE_STAGE');self.assertEqual(stage['resource_reason_codes'],[]);self.assertEqual(stage['errors_count'],1)
 def test_known_sampled_resource_only_and_malformed_unavailable(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));(job/'FLOW_RESULT.json').unlink();r=job/'materials/runs/qwen2/RESULT.json';r.parent.mkdir(parents=True);r.write_text(json.dumps(dict(native_exit=None,errors=['ValueError: sampled observed aggregate RSS cap'],cleanup_proof={},log_capture={})))
   result=self.project(job,bp);stage=next(x for x in result['stages']if x['name']=='qwen2');self.assertEqual(stage['resource_reason_codes'],['SAMPLED_RSS_CAP']);self.assertEqual(stage['status'],'RESOURCE_LIMIT_OBSERVED');self.assertFalse(result['numerical_pass'])
   r.write_text('{invalid');self.assertEqual(self.project(job,bp)['status'],'UNAVAILABLE')
 def test_reference_actual_fixed_paths_only(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));(job/'FLOW_RESULT.json').unlink()
   for i in range(5):
    p=job/f'materials/references/profile{i}/actual/RESULT.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(dict(native_exit=0,errors=[],cleanup_proof={},log_capture={},elapsed_seconds=i+1)))
   for rel in ('runs/reference0/RESULT.json','materials/references/profile5/actual/RESULT.json','materials/references/profile0/not_actual/RESULT.json'):
    p=job/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('not valid JSON and must not be read')
   r=self.project(job,bp);self.assertEqual(r['status'],'INCOMPLETE_EXECUTION');rows=[x for x in r['stages']if x['name'].startswith('reference')];self.assertEqual([x['name']for x in rows],[f'reference{i}'for i in range(5)]);self.assertEqual([x['elapsed_seconds']for x in rows],[1,2,3,4,5]);self.assertFalse(r['numerical_pass'])
 def retained_projection(self,job,bp,reject=False,budget_mismatch=False,wrong_scope=False):
  original=s.load;calls=[]
  def loader(name,path):
   if name=='summary_retained_materials':
    def verify(pin,b):
     calls.append((pin,b))
     if reject:raise ValueError('synthetic retained input evidence mismatch')
     return dict(payload={},weights={},references={},roots=[],scope='WRONG'if wrong_scope else s.RETAINED_SCOPE)
    return types.SimpleNamespace(verify=verify)
   m=original(name,path)
   if name=='summary_cloud_handoff':m.verify=lambda *args:dict(source_pins_sha256='f'*64)
   if name=='summary_cloud_budget':m.admit=lambda b:dict(execution_mode=b['execution_mode'],full_block_budget=b.get('full_block_budget'),consumer_address_space_bytes=512<<20,dut_address_space_bytes=2<<30,retained_materials=None if budget_mismatch else b['retained_materials'])
   return m
  with patch.object(s,'source_guard',return_value='f'*64),patch.object(s,'load',side_effect=loader):r=s.project(job,bp,s.sha(bp))
  return r,calls
 def retained_fixture(self,root,complete=False):
  job,bp=self.fixture(root);b=json.loads(bp.read_text());rp=root/'retained.json';rp.write_text('{}');b['retained_materials']=s.pin(rp);bp.write_text(json.dumps(b));fp=job/'FLOW_RESULT.json'
  if complete:
   f=json.loads(fp.read_text());f.update(execution_binding=s.pin(bp),retained_materials=b['retained_materials']);fp.write_text(json.dumps(f))
  else:fp.unlink()
  return job,bp,b
 def test_retained_partial_input_scope_and_no_live_owner(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp,b=self.retained_fixture(pathlib.Path(t))
   with patch('os.getpid',side_effect=AssertionError('old owner must not be needed')):r,calls=self.retained_projection(job,bp)
   self.assertEqual(r['status'],'INCOMPLETE_EXECUTION');self.assertFalse(r['numerical_pass']);self.assertEqual(r['retained_materials_sha256'],b['retained_materials']['sha256']);self.assertEqual(r['retained_materials_scope'],s.RETAINED_SCOPE);self.assertEqual(calls[0][0],b['retained_materials']);self.assertLessEqual(len(json.dumps(r).encode()),65536)
 def test_retained_reverification_budget_scope_rejected(self):
  for kwargs in (dict(reject=True),dict(budget_mismatch=True),dict(wrong_scope=True)):
   with tempfile.TemporaryDirectory()as t:
    job,bp,b=self.retained_fixture(pathlib.Path(t));r,_=self.retained_projection(job,bp,**kwargs);self.assertEqual(r['status'],'UNAVAILABLE');self.assertFalse(r['numerical_pass'])
 def test_retained_full_original_receipts_and_flow_pin_drift(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp,b=self.retained_fixture(pathlib.Path(t),complete=True);r,_=self.retained_projection(job,bp);self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertEqual(len(r['profiles']),5)
   fp=job/'FLOW_RESULT.json';f=json.loads(fp.read_text());f['retained_materials']['sha256']='0'*64;fp.write_text(json.dumps(f));r,_=self.retained_projection(job,bp);self.assertEqual(r['status'],'UNAVAILABLE');self.assertFalse(r['numerical_pass'])
 def test_missing_flow_requires_all_input_gates(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));(job/'FLOW_RESULT.json').unlink()
   self.assertEqual(s.project(job,bp,s.sha(bp))['status'],'UNAVAILABLE')
 def adaptation_fixture(self,root):
  job,bp=self.fixture(root);(job/'FLOW_RESULT.json').unlink();b=json.loads(bp.read_text());b['identity']['source_commit']='9'*40
  for key in ('executor_adaptation','workspace_loader'):
   p=root/(key+'.json');p.write_text('{}');b[key]=s.pin(p)
  b['source_pins']={'path':str(root/'SOURCE_PINS.json'),'bytes':1,'sha256':'f'*64};bp.write_text(json.dumps(b));return job,bp,b
 def adapted_projection(self,job,bp,reject=False,budget_mismatch=False):
  original=s.load;calls=[]
  def loader(name,path):
   if name=='summary_executor_adaptation':
    def verify(*args,**kw):
     calls.append((args,kw))
     if reject:raise ValueError('synthetic forbidden source delta')
    return types.SimpleNamespace(verify=verify)
   m=original(name,path)
   if name=='summary_cloud_handoff':
    def verify(*args,**kw):
     self.assertIn('executor_adaptation',kw);return dict(source_pins_sha256='8'*64)
    m.verify=verify
   if name=='summary_cloud_budget':m.admit=lambda b:dict(execution_mode=b['execution_mode'],full_block_budget=None,executor_adaptation=b['executor_adaptation'],workspace_loader=None if budget_mismatch else b['workspace_loader'],consumer_address_space_bytes=512<<20,dut_address_space_bytes=2<<30)
   return m
  with patch.object(s,'source_guard',return_value='f'*64),patch.object(s,'load',side_effect=loader):r=s.project(job,bp,s.sha(bp))
  return r,calls
 def complete_adapted_fixture(self,root):
  job,bp,b=self.adaptation_fixture(root);n=job/'materials/numeric';records=[]
  for i in range(5):
   out=n/f'profile{i}/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text());r.update(executor_identity=b['identity'],executor_adaptation_sha256=b['executor_adaptation']['sha256'],workspace_loader_sha256=b['workspace_loader']['sha256']);rp.write_text(json.dumps(r))
   record=base.d.verify(out,i,b['artifact_manifest']['sha256'],base.H,base.H,base.H,s.pin(n/f'runs/p{i}_dut/RESULT.json'));(n/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record));records.append(record)
  nf=n/'RESULT.json';nr=json.loads(nf.read_text());q=base.a.aggregate(records);nr.update(actual_dut_reports=records,qualification=q,status=q['status'],numerical_pass=q['numerical_pass']);nf.write_text(json.dumps(nr))
  flow=dict(identity=b['identity'],execution_approval=b['execution_approval'],artifact_identity=b['artifact_identity'],execution_binding=s.pin(bp),builder_handoff=b['builder_handoff'],artifact_manifest=b['artifact_manifest'],numeric_result=s.pin(nf),hardware_definitions=1,profiles=list(range(5)),execution_mode='BOUNDED_CALIBRATION',transport_exit_code=2,qualification=q,status=q['status'],executor_adaptation=b['executor_adaptation'],workspace_loader=b['workspace_loader']);(job/'FLOW_RESULT.json').write_text(json.dumps(flow));return job,bp,b
 def test_adapted_five_synthetic_original_evidence_chain(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp,b=self.complete_adapted_fixture(pathlib.Path(t));r,calls=self.adapted_projection(job,bp)
   self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertEqual(len(r['profiles']),5);self.assertEqual(r['builder_source_commit'],'a'*40);self.assertEqual(r['executor_source_commit'],'9'*40);self.assertFalse(r['final_rtl_executed']);self.assertEqual(r['transport_exit_code'],2)
 def test_any_consumer_adaptation_or_loader_drift_rebound_refused(self):
  for i in range(5):
   for key in ('executor_adaptation_sha256','workspace_loader_sha256'):
    with tempfile.TemporaryDirectory()as t:
     job,bp,b=self.complete_adapted_fixture(pathlib.Path(t));n=job/'materials/numeric';out=n/f'profile{i}/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text());r[key]='0'*64;rp.write_text(json.dumps(r))
     record=base.d.verify(out,i,b['artifact_manifest']['sha256'],base.H,base.H,base.H,s.pin(n/f'runs/p{i}_dut/RESULT.json'));(n/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record));nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr['actual_dut_reports'][i]=record;nf.write_text(json.dumps(nr));ff=job/'FLOW_RESULT.json';flow=json.loads(ff.read_text());flow['numeric_result']=s.pin(nf);ff.write_text(json.dumps(flow))
     result,_=self.adapted_projection(job,bp);self.assertEqual(result['status'],'UNAVAILABLE');self.assertFalse(result['numerical_pass'])
 def test_adaptation_has_distinct_real_source_labels_no_pass(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp,b=self.adaptation_fixture(pathlib.Path(t));r,calls=self.adapted_projection(job,bp)
   self.assertEqual(r['status'],'INCOMPLETE_EXECUTION');self.assertFalse(r['numerical_pass']);self.assertEqual(r['builder_source_commit'],'a'*40);self.assertEqual(r['executor_source_commit'],'9'*40)
   self.assertEqual(r['executor_adaptation_sha256'],b['executor_adaptation']['sha256']);self.assertEqual(r['workspace_loader_sha256'],b['workspace_loader']['sha256']);self.assertEqual(calls[0][1]['current_source_pins_pin'],b['source_pins']);self.assertEqual(calls[0][1]['repo'],s.D.parents[1])
 def test_adaptation_catalog_or_loader_approval_failure_unavailable(self):
  for reject,mismatch in ((True,False),(False,True)):
   with tempfile.TemporaryDirectory()as t:
    job,bp,b=self.adaptation_fixture(pathlib.Path(t));r,_=self.adapted_projection(job,bp,reject,mismatch);self.assertEqual(r['status'],'UNAVAILABLE')
 def test_different_source_without_adapter_refused(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp,b=self.adaptation_fixture(pathlib.Path(t));del b['executor_adaptation'];del b['workspace_loader'];bp.write_text(json.dumps(b));self.assertEqual(self.project(job,bp)['status'],'UNAVAILABLE')
 def test_unknown_full_budget_refused(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));b=json.loads(bp.read_text());b['execution_mode']='FULL_BLOCK_ACCEPTANCE';bp.write_text(json.dumps(b));self.assertEqual(self.project(job,bp)['status'],'UNAVAILABLE')
 def test_missing_and_untrusted_source_closure(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t));self.assertEqual(s.project(job,bp,s.sha(bp))['status'],'UNAVAILABLE');self.assertEqual(s.project(job,bp,'0'*64)['status'],'UNAVAILABLE')
 def test_no_live_owner_needed(self):
  with tempfile.TemporaryDirectory()as t:
   job,bp=self.fixture(pathlib.Path(t))
   with patch('os.getpid',side_effect=AssertionError('offline must not inspect current owner')):self.assertEqual(self.project(job,bp)['status'],'VERIFIED_REAGGREGATED')
if __name__=='__main__':unittest.main()
