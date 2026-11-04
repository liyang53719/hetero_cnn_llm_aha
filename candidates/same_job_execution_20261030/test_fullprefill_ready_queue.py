"""HOST ONLY: synthetic V3 queue admission, real FULL launch and summary paths.
No live DUT, model, production authorization, or externally useful approval.
"""
import ast,copy,json,pathlib,shutil,unittest
from unittest.mock import patch
import execution_mode as mode
import test_fullprefill_supervision as base
D=pathlib.Path(__file__).resolve().parent

def queue_doc(doc,selected=(0,2)):
 d=copy.deepcopy(doc);d['schema']=mode.FULL_V3_SCHEMA;d.pop('ready')
 d.update(selected_profiles=list(selected),queue_policy=mode.FULL_V3_QUEUE_POLICY)
 d['profiles']={i:dict(state='READY_FULL_PREFILL',watchdog=row)if int(i)in selected else dict(state='BLOCKED_NOT_RUN',reason='ALL_SYNTHETIC: wall/log capacity unresolved; independent analysis continues',analysis=d['basis']['cycle_analysis'])for i,row in d['profiles'].items()}
 return d

class QueueTests(unittest.TestCase):
 def setUp(self):
  self.f=base.FullPrefill();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.f.doc=queue_doc(self.f.doc)
 def admit(self,doc=None):return self.f.admit(doc)
 def test_selected_only_and_all_five_inventory(self):
  a=self.admit();self.assertEqual(a['budget_version'],3);self.assertEqual(mode.ready_queue_profiles(a),[0,2]);self.assertEqual(set(a['profile_seconds']),{'0','2'});self.assertEqual(set(a['blocked_profiles']),{'1','3','4'});self.assertEqual(a['mode'],mode.FULL)
  self.assertEqual(base.tail.execution_profiles(self.f.b,a),[0,2])
 def test_bad_selection_and_inventory(self):
  for selected in ([],[True],[0,0],[2,0],[-1],[5],['0'],list(range(6))):
   d=copy.deepcopy(self.f.doc);d['selected_profiles']=selected
   with self.subTest(selected=selected),self.assertRaises(ValueError):self.admit(d)
  for i in range(5):
   d=copy.deepcopy(self.f.doc);del d['profiles'][str(i)]
   with self.subTest(missing=i),self.assertRaises(ValueError):self.admit(d)
 def test_v2_not_relaxed_or_global_ready_claim(self):
  for change in ({'schema':mode.FULL_V2_SCHEMA},{'ready':True},{'queue_policy':'WAIT_FOR_P0_PASS'}):
   d=copy.deepcopy(self.f.doc);d.update(change)
   with self.assertRaises(ValueError):self.admit(d)
 def test_blocked_has_no_fake_executable_values(self):
  for change in ({'state':'PASS'},{'state':'READY_FULL_PREFILL'},{'reason':''},{'reason':False},{'wall_seconds':0},{'watchdog':{}},{'reason':'x'*4097}):
   d=copy.deepcopy(self.f.doc);d['profiles']['1'].update(change)
   with self.subTest(change=change),self.assertRaises(ValueError):self.admit(d)
  d=copy.deepcopy(self.f.doc);d['profiles']['1']['analysis']['sha256']='0'*64
  with self.assertRaises(ValueError):self.admit(d)
 def test_selected_keeps_every_original_finite_check(self):
  for key,val in [('wall_seconds',True),('wall_seconds',0),('wall_seconds',mode.FULL_V2_MAX_SECONDS+1),('cpu_seconds',86401),('max_active_cycles',1000000001),('log_raw_bytes',(16<<30)+1),('rss_telemetry_raw_bytes',(16<<30)+1),('summary_verification_wall_seconds',3601),('postprocess_cpu_seconds',301),('target_completed_commands',1)]:
   d=copy.deepcopy(self.f.doc);d['profiles']['0']['watchdog'][key]=val
   with self.subTest(key=key,val=val),self.assertRaises(ValueError):self.admit(d)
  d=copy.deepcopy(self.f.doc);d['profiles']['0']={'state':'BLOCKED_NOT_RUN','reason':'pending','analysis':d['basis']['cycle_analysis']}
  with self.assertRaises(ValueError):self.admit(d)
 def test_resources_identity_and_review_preserved(self):
  for key in ('artifact_manifest_sha256','model_candidate_review_sha256','driver_sha256','executor_source_pins_sha256'):
   d=copy.deepcopy(self.f.doc);d[key]='0'*64
   with self.subTest(key=key),self.assertRaises(ValueError):self.admit(d)
  for key,value in [('dut_rss_bytes',(2<<30)+1),('dut_address_space_bytes',2684354561),('consumer_address_space_bytes',1<<30),('reserved_other_owner_bytes',1)]:
   old=self.f.cloud[key];self.f.cloud[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.admit()
   self.f.cloud[key]=old
 def test_no_launch_outside_exact_selected(self):
  a=self.admit();old=dict(wall_seconds=20000,cpu_seconds=18000,max_active_cycles=1000000000,file_bytes=64<<20)
  for i in (1,3,4,True,'0'):
   with self.subTest(i=i),self.assertRaises(ValueError):mode.consumer_limits(old,a,i)
   with self.subTest(command=i),self.assertRaises(ValueError):base.tail.execution_command(['python',str(base.tail.D/'consumer_owned.py')],self.f.b,a,i)
  for i in (0,2):
   argv,_=base.tail.execution_command(['python',str(base.tail.D/'consumer_owned.py')],dict(full_block_budget=self.f.b['full_block_budget']),a,i)
   self.assertEqual(argv[argv.index('--execution-mode')+1],mode.FULL);self.assertIn('--full-block-budget',argv);self.assertNotIn('--stage-coverage-budget',argv);self.assertNotIn('--calibration-wall-seconds',argv)
 def test_admission_selection_not_expandable(self):
  a=self.admit()
  for mutate in (lambda x:x['selected_profiles'].append(1),lambda x:x['profile_seconds'].update({'1':1}),lambda x:x['blocked_profiles'].pop('1')):
   forged=copy.deepcopy(a);mutate(forged)
   with self.assertRaises(ValueError):mode.full_v2(forged)
 def test_lifecycle_only_selected_watchdogs(self):
  a=self.admit();b=dict(self.f.b,budgets=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600),job_budget_seconds=2000000)
  b['pins'][str(D/'execution_mode.py')]=mode.sha(D/'execution_mode.py')
  material,tail,total=base.flow.reservations(b,a)
  self.assertEqual(tail,sum(a['profile_seconds'].values())+2*4*300+7*180+11*120+1530+600)
  self.assertEqual(mode.dut_admission_seconds(a,0,600),mode.consumer_phase_seconds(a,0)+300+300+2*300+600)
  import resource
  from types import SimpleNamespace
  with patch.object(resource,'getrlimit',return_value=(-1,-1)),patch.object(resource,'getrusage',return_value=SimpleNamespace(ru_utime=0,ru_stime=0)),patch.object(resource,'setrlimit')as setlimit:
   mode.install_full_v2_parent_cpu_limit(a,total);setlimit.assert_called_once_with(resource.RLIMIT_CPU,(total,total))
 def test_one_ready_profile_needs_no_other_profile_completion(self):
  for selected in ((0,),(2,),(4,),tuple(range(5))):
   v2=base.FullPrefill();v2.setUp();self.addCleanup(v2.doCleanups);a=v2.admit(queue_doc(v2.doc,selected));self.assertEqual(mode.ready_queue_profiles(a),list(selected))
 def test_receipt_version_cannot_downgrade(self):
  a=self.admit();r=dict(execution_mode=mode.FULL,reviewed_budget_sha256=a['reviewed_budget_sha256'],budget_version=3,log_policy=mode.expected_log_policy(a,0),postprocess_limits=mode.host_phase_limits(a,0,'postprocess'))
  mode.verify_consumer_admission(a,r,0);r['budget_version']=2
  with self.assertRaises(ValueError):mode.verify_consumer_admission(a,r,0)

class QueueSummary(unittest.TestCase):
 setUp=base.ActualFullPrefillCallsites.setUp
 admit=base.ActualFullPrefillCallsites.admit
 project_summary=base.ActualFullPrefillCallsites.project_summary
 tail_poststage=base.ActualFullPrefillCallsites.tail_poststage
 def fixture(self,selected=(0,2)):
  base.ActualFullPrefillCallsites.summary_fixture(self)
  self.doc=queue_doc(self.doc,selected);self.admission=self.admit();self.sbinding['full_block_budget']=self.b['full_block_budget'];self.sbp.write_text(json.dumps(self.sbinding))
  import dut_evidence,required_acceptance
  n=self.sjob/'materials/numeric';records=[]
  for i in range(5):
   if i not in selected:
    shutil.rmtree(n/f'profile{i}');shutil.rmtree(n/f'runs/p{i}_dut');(n/f'PROFILE_{i}_DIAGNOSTIC.json').unlink();continue
   out=n/f'profile{i}/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text());r['execution_admission'].update(budget_version=3,reviewed_budget_sha256=self.admission['reviewed_budget_sha256']);rp.write_text(json.dumps(r))
   old=json.loads((n/f'PROFILE_{i}_DIAGNOSTIC.json').read_text());old['report']=self.summary.pin(rp);(n/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(old));records.append(old)
  q=required_acceptance.aggregate(records);nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr.update(full_budget_sha256=self.admission['reviewed_budget_sha256'],actual_dut_reports=records,qualification=q,status=q['status'],numerical_pass=q['numerical_pass'],**mode.queue_report_fields(self.admission));nf.write_text(json.dumps(nr))
  ff=self.sjob/'FLOW_RESULT.json';f=json.loads(ff.read_text());f.update(execution_binding=self.summary.pin(self.sbp),numeric_result=self.summary.pin(nf),execution_admission=self.admission,transport_exit_code=mode.transport_exit(mode.FULL,q),qualification=q,status=q['status']);ff.write_text(json.dumps(f))
 def project_summary_with_failure_evidence(self):
  # Synthetic positive case only. Keep production fail-closed behavior unchanged.
  import sys,tempfile
  events=[];previous=sys.gettrace()
  def trace(frame,event,arg):
   frame.f_trace_lines=False
   if event=='exception' and pathlib.Path(frame.f_code.co_filename).is_relative_to(D):
    kind,value,_=arg
    if kind not in (StopIteration,GeneratorExit):
     message=str(value)
     events.append(dict(file=frame.f_code.co_filename,function=frame.f_code.co_name,line=frame.f_lineno,exception_type=kind.__name__,message=message[:8192],message_truncated=len(message)>8192))
     if len(events)>128:del events[0]
   return trace
  try:
   sys.settrace(trace);result=self.project_summary()
  finally:sys.settrace(previous)
  if result.get('status')=='UNAVAILABLE':
   # This copy is deliberately not registered with unittest cleanup. Preserve
   # the original synthetic input/receipt bytes before fixture teardown.
   target=pathlib.Path(tempfile.mkdtemp(prefix='synthetic_fullprefill_summary_failure_'))
   shutil.copytree(self.f.fixture.root,target/'fixture',symlinks=True)
   sources={str(path):mode.sha(path)for path in (D/'execution_mode.py',D/'summarize_cloud_execution.py',D/'summary_progress.py',D/'numeric/dut_evidence.py',D/'numeric/full_log.py')}
   evidence=dict(scope='SYNTHETIC_TEST_ONLY_NO_DUT_OR_LAUNCH_AUTHORITY',result=result,exceptions=events,source_sha256=sources,original_fixture_root=str(self.f.fixture.root))
   path=target/'UNEXPECTED_SUMMARY_FAILURE.json';path.write_text(json.dumps(evidence,indent=2)+'\n')
   self.fail('Unexpected summary UNAVAILABLE; preserved evidence: '+str(path)+'; inner exceptions: '+json.dumps(events))
  return result
 def test_unexpected_summary_failure_retains_exact_reason_and_fixture(self):
  import sys,tempfile
  self.fixture();previous=sys.gettrace()
  def unavailable():
   try:raise ValueError('SYNTHETIC_EXPECTED_INNER_SUMMARY_REASON')
   except ValueError:return dict(status='UNAVAILABLE',numerical_pass=False)
  with tempfile.TemporaryDirectory()as tmp:
   target=pathlib.Path(tmp)/'retained';target.mkdir()
   with patch.object(self,'project_summary',side_effect=unavailable),patch('tempfile.mkdtemp',return_value=str(target)),self.assertRaisesRegex(AssertionError,'SYNTHETIC_EXPECTED_INNER_SUMMARY_REASON'):
    self.project_summary_with_failure_evidence()
   self.assertIs(sys.gettrace(),previous)
   evidence=json.loads((target/'UNEXPECTED_SUMMARY_FAILURE.json').read_text())
   self.assertEqual(evidence['result']['status'],'UNAVAILABLE')
   self.assertTrue(any(row['exception_type']=='ValueError' and row['message']=='SYNTHETIC_EXPECTED_INNER_SUMMARY_REASON' and row['message_truncated']is False for row in evidence['exceptions']))
   relative=self.sbp.relative_to(self.f.fixture.root)
   self.assertEqual((target/'fixture'/relative).read_bytes(),self.sbp.read_bytes())
 def test_real_selected_summary_not_five_pass(self):
  self.fixture();r=self.project_summary_with_failure_evidence();self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertFalse(r['numerical_pass']);self.assertEqual(r['transport_exit_code'],2);self.assertEqual(r['qualification']['status'],'INCOMPLETE');self.assertEqual(self.evidence_calls,2);self.assertEqual([p['profile']for p in r['profiles']],[0,2]);self.assertEqual(set(r['blocked_profiles']),{'1','3','4'});self.assertTrue(self.tail_poststage(0)['numerical_pass'])
 def test_all_five_actual_full_results_required_for_pass(self):
  self.fixture(tuple(range(5)));r=self.project_summary();self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertEqual(r['transport_exit_code'],0);self.assertEqual(self.evidence_calls,5);self.assertEqual(r['blocked_profiles'],{})
 def test_blocked_execution_artifact_rejected(self):
  self.fixture();(self.sjob/'materials/numeric/profile1').mkdir();self.assertEqual(self.project_summary()['status'],'UNAVAILABLE');self.assertEqual(self.evidence_calls,0)
 def test_incomplete_summary_still_reports_queue(self):
  self.fixture();(self.sjob/'FLOW_RESULT.json').unlink();r=self.project_summary();self.assertEqual(r['status'],'INCOMPLETE_EXECUTION');self.assertEqual(r['selected_profiles'],[0,2]);self.assertEqual(set(r['blocked_profiles']),{'1','3','4'});self.assertFalse(r['numerical_pass'])

class QueueActualAuthority(unittest.TestCase):
 def setUp(self):
  self.real=base.RealCloudCandidateV2Admission();self.real.setUp();self.addCleanup(self.real.doCleanups)
  f=self.real.f;c=self.real.c
  f.doc=queue_doc(f.doc);f.b['full_block_budget']=f.f.fixture.write('full-v3-real-chain.json',f.doc)
  cloud=json.loads(pathlib.Path(f.b['cloud_budget']['path']).read_text());cloud['full_block_budget']=f.b['full_block_budget'];f.b['cloud_budget']=c.put('real-v3-budget',cloud)
  approval=json.loads(pathlib.Path(f.b['execution_approval']['path']).read_text());approval['budget_sha256']=f.b['cloud_budget']['sha256'];f.b['execution_approval']=c.put('real-v3-approval',approval)
 def test_no_mock_external_approval_candidate_review_v3(self):
  a=mode.admit(self.real.f.b);self.assertEqual(a['budget_version'],3);self.assertEqual(mode.ready_queue_profiles(a),[0,2])
 def test_expanding_selected_document_requires_new_external_approval(self):
  f=self.real.f;d=copy.deepcopy(f.doc);d['selected_profiles']=[0,1,2];d['profiles']['1']=copy.deepcopy(d['profiles']['0']);f.b['full_block_budget']=f.f.fixture.write('unapproved-expansion.json',d)
  with self.assertRaises(ValueError):mode.admit(f.b)
 def test_changed_blocked_analysis_requires_external_approval(self):
  f=self.real.f;d=copy.deepcopy(f.doc);d['profiles']['1']['reason']='changed reason';f.b['full_block_budget']=f.f.fixture.write('unapproved-reason.json',d)
  with self.assertRaises(ValueError):mode.admit(f.b)


class FiniteQueueLogs(QueueTests):
 def rss_helper(self):
  import importlib.util
  path=D.parent/'ci_frontend_pipeline_r2_20261029/rss_telemetry.py'
  spec=importlib.util.spec_from_file_location('finite_queue_rss_telemetry',path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);return helper
 def setUp(self):
  super().setUp()
  for i,rss,raw in [('0',512<<20,7<<30),('2',1<<30,13<<30)]:
   self.f.doc['profiles'][i]['watchdog'].update(log_compressed_bytes=128<<20,rss_telemetry_compressed_bytes=rss,rss_telemetry_raw_bytes=raw)
 def test_exact_independent_caps_and_legacy_contract(self):
  import full_log
  rss_telemetry=self.rss_helper()
  a=self.admit()
  for i,rss,raw in [(0,512<<20,7<<30),(2,1<<30,13<<30)]:
   log=mode.expected_log_policy(a,i);telemetry=mode.expected_rss_telemetry_policy(a,i)
   self.assertEqual(log['compressed_bytes'],128<<20);self.assertEqual(telemetry['compressed_bytes'],rss);self.assertEqual(telemetry['raw_bytes'],raw)
   self.assertEqual(full_log.effective_policy(a,i,64<<20),log);self.assertEqual(rss_telemetry.policy(telemetry),telemetry)
   self.assertEqual(mode.full_v3_log_disk_bytes(a,i),(128<<20)+rss)
  self.assertEqual(mode.full_v3_log_disk_bytes(a),1792<<20)
  with self.assertRaises(ValueError):full_log.policy(dict(full_log.POLICY,compressed_bytes=128<<20))
  with self.assertRaises(ValueError):rss_telemetry.policy(dict(mode.FULL_V2_RSS_POLICY,compressed_bytes=512<<20))
  for selected in ((0,),(2,)):
   doc=copy.deepcopy(self.f.doc);doc['selected_profiles']=list(selected)
   for i in (0,2):
    if i not in selected:doc['profiles'][str(i)]=copy.deepcopy(doc['profiles']['1'])
   self.assertEqual(mode.ready_queue_profiles(self.admit(doc)),list(selected))
 def test_quotas_strict_finite_and_pair_required(self):
  for field,maximum in [('log_compressed_bytes',128<<20),('rss_telemetry_compressed_bytes',1<<30)]:
   for value in (True,False,0,-1,1.0,float('inf'),maximum+1):
    d=copy.deepcopy(self.f.doc);d['profiles']['0']['watchdog'][field]=value
    with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.admit(d)
   d=copy.deepcopy(self.f.doc);del d['profiles']['0']['watchdog'][field]
   with self.assertRaises(ValueError):self.admit(d)
  a=self.admit()
  for i in (1,3,4,True,'0'):
   with self.assertRaises(ValueError):mode.full_v3_log_disk_bytes(a,i)
 def test_production_stage_reserves_both_streams(self):
  import types,tempfile
  a=self.admit();tree=ast.parse((D/'numeric/numeric_tail.py').read_text())
  run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run')
  stage=next(n for n in run.body if isinstance(n,ast.FunctionDef)and n.name=='stage')
  with tempfile.TemporaryDirectory()as tmp:
   root=pathlib.Path(tmp);seen={};saved={}
   def execute(argv,path,lock,caps,env,pins,resource_gate):
    seen.update(caps=caps,gate=resource_gate);return dict(native_exit=0,errors=[])
   b=dict(provider_wall_seconds=180,environment={},reserved_parent_seconds=600,owned_roots=[str(root)],phase_extra_bytes=512<<20,job_started_monotonic=0,job_budget_seconds=3000000,tree_cap=base.flow.TREE,address_space_bytes=2684354560,rss_bytes=2<<30,python='/usr/bin/python3',lock=str(root/'lock'),reserved_other_owner_bytes=5<<30)
   ns=dict(out=root,b=b,owned_environment=lambda e,p:{},execution_mode=mode,admission=a,pins={},cloud={},save=lambda p,v:saved.update({p.name:copy.deepcopy(v)}),sha=lambda p:'a'*64,supervisor=types.SimpleNamespace(execute=execute,__file__=__file__),D=D/'numeric',require_cleanup=lambda *args:None,P=pathlib.Path,allstage=[],need=mode.need)
   exec(compile(ast.Module(body=[stage],type_ignores=[]),'actual_v3_stage','exec'),ns)
   for i,stream in [(0,640<<20),(2,1152<<20)]:
    ns['stage'](f'p{i}_dut',['/usr/bin/true'],seconds=100)
    body=saved[f'p{i}_dut.json'];caps=seen['caps']
    self.assertEqual(body['extra_bytes'],(512<<20)+stream);self.assertEqual(caps['tree_bytes'],(512<<20)+stream)
    self.assertEqual(body['write_file_bytes'],128<<20);self.assertEqual(caps['file_bytes'],2<<30)
    self.assertEqual(caps['min_free_disk_bytes'],8<<30);self.assertEqual(caps['watch_tree_bytes'],base.flow.TREE)
    self.assertEqual(seen['gate']['min_disk_free'],8<<30)
    self.assertEqual(caps['rss_telemetry_policy'],mode.expected_rss_telemetry_policy(a,i))
   b['aggregate_tree_cap_bytes']=b['tree_cap'];ns['stage']('startup_abi',['/usr/bin/true'],seconds=100)
   self.assertTrue(saved['startup_abi.json']['preserve_free_8gib']);self.assertEqual(saved['startup_abi.json']['extra_bytes'],512<<20);self.assertEqual(seen['caps']['min_free_disk_bytes'],8<<30)
 def test_v3_rss_lossless_receipt_roundtrip(self):
  import tempfile
  rss_telemetry=self.rss_helper()
  with tempfile.TemporaryDirectory()as tmp:
   path=pathlib.Path(tmp)/'rss_samples.jsonl.gz';policy=mode.expected_rss_telemetry_policy(self.admit(),2)
   writer=rss_telemetry.Writer(path,policy)
   sample=dict(elapsed=0,aggregate_rss_bytes=0,processes=[],MemAvailable_bytes=2<<30,reserve_below_1GiB_warning=False)
   for i in range(100):sample['elapsed']=i*.05;writer.write(json.dumps(sample)+'\n')
   writer.finish();writer.close();receipt=rss_telemetry.verify(path,writer.receipt(),policy,100)
   self.assertTrue(receipt['all_written_bytes_verified']);self.assertEqual(rss_telemetry.check_receipt(path,receipt,policy,100),receipt)
   with self.assertRaises(ValueError):rss_telemetry.check_receipt(path,receipt,dict(policy,compressed_bytes=512<<20),100)


class FiniteAggregateBudget(unittest.TestCase):
 def setUp(self):
  import time,cloud_budget
  self.cloud=cloud_budget;self.q=QueueActualAuthority();self.q.setUp();self.addCleanup(self.q.doCleanups)
  self.f=self.q.real.f;self.c=self.q.real.c;self.b=self.f.b
  self.b['pins'][str(D/'execution_mode.py')]=mode.sha(D/'execution_mode.py')
  self.doc=json.loads(pathlib.Path(self.b['cloud_budget']['path']).read_text())
  self.ap=json.loads(pathlib.Path(self.b['execution_approval']['path']).read_text())
  self.now=time.monotonic();self.snapshot=dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,roots=[str(self.c.d)],bytes=8<<30,free_bytes=12<<30,finished_monotonic=self.now)
  census=self.c.put('initial_census',self.snapshot)
  self.plan=dict(schema='FULL_PREFILL_FINITE_DISK_PLAN_V3',source_commit=self.b['identity']['source_commit'],artifact_manifest_sha256=self.b['artifact_manifest']['sha256'],full_block_budget_sha256=self.b['full_block_budget']['sha256'],initial_census=census,owned_roots=[str(self.c.d)],binding_preparation_bytes=1<<20,protected_existing_bytes=(8<<30)+(1<<20),selected_log_bytes=256<<20,profile_output_reservations={'0':dict(provider_bytes=95440896,reference_bytes=10659438),'2':dict(provider_bytes=20119,reference_bytes=7268772)},shared_output_reservations=dict(stage_logs_and_metadata_bytes=512<<20,cache_bytes=64<<20,final_evidence_bytes=(1<<30)-(512<<20)-(64<<20)-113389225))
  retained=self.c.put('finite_retained',dict(synthetic_only=True));self.b['retained_materials']=retained;self.doc['retained_materials']=retained;self.ap['retained_materials_sha256']=retained['sha256']
  self.doc.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=self.c.put('finite_runtime',dict(synthetic_only=True)))
  self.reapprove()
 def reapprove(self):
  remaining=sum(sum(v.values())for v in self.plan['profile_output_reservations'].values())+sum(self.plan['shared_output_reservations'].values())
  self.doc['aggregate_tree_cap_bytes']=self.plan['protected_existing_bytes']+self.plan['selected_log_bytes']+remaining
  self.doc['basis']['resource_audit']=self.c.put('finite_disk_audit',dict(fullprefill_disk_budget=self.plan,synthetic_only=True))
  self.b['cloud_budget']=self.c.put('finite_cloud_budget',self.doc);self.ap['budget_sha256']=self.b['cloud_budget']['sha256'];self.b['execution_approval']=self.c.put('finite_approval',self.ap)
 def test_real_authority_and_initial_stub_propagation(self):
  import prepare_cloud_execution as entry
  a=self.cloud.admit(self.b);self.assertEqual(a['fullprefill_disk_budget'],self.plan)
  entry.preserve_stage_coverage_input(self.b,a);self.assertEqual(self.b['aggregate_tree_cap_bytes'],self.doc['aggregate_tree_cap_bytes']);self.assertEqual(mode.admit(self.b)['budget_version'],3)
  stub=dict(self.b);stub.pop('aggregate_tree_cap_bytes');stub.pop('execution_mode');stub.pop('full_block_budget')
  self.assertEqual(self.cloud.admit(stub)['aggregate_tree_cap_bytes'],self.doc['aggregate_tree_cap_bytes'])
 def test_expanded_selected_logs_count_once_and_p2_independent(self):
  doc=copy.deepcopy(self.f.doc)
  for i,rss in [('0',512<<20),('2',1<<30)]:doc['profiles'][i]['watchdog'].update(log_compressed_bytes=128<<20,rss_telemetry_compressed_bytes=rss)
  self.b['full_block_budget']=self.doc['full_block_budget']=self.c.put('expanded_v3',doc);self.plan['full_block_budget_sha256']=self.b['full_block_budget']['sha256'];self.plan['selected_log_bytes']=1792<<20;self.reapprove()
  admitted=self.cloud.admit(self.b);self.assertEqual(admitted['aggregate_tree_cap_bytes'],(8<<30)+(1<<20)+(1792<<20)+(1<<30))
  doc['selected_profiles']=[2];doc['profiles']['0']=copy.deepcopy(doc['profiles']['1'])
  self.b['full_block_budget']=self.doc['full_block_budget']=self.c.put('independent_p2_v3',doc);self.plan['full_block_budget_sha256']=self.b['full_block_budget']['sha256'];self.plan['selected_log_bytes']=1152<<20
  removed=sum(self.plan['profile_output_reservations'].pop('0').values());self.plan['shared_output_reservations']['final_evidence_bytes']+=removed;self.reapprove()
  self.assertEqual(self.cloud.admit(self.b)['aggregate_tree_cap_bytes'],(8<<30)+(1<<20)+(1152<<20)+(1<<30))
 def test_exact_initial_and_fresh_actual_census(self):
  cap=self.doc['aggregate_tree_cap_bytes'];proof=self.cloud.fullprefill_disk_snapshot(self.plan,self.snapshot,cap,now=self.now)
  self.assertEqual(proof['remaining_output_bytes'],1<<30)
  result=base.flow.upfront_disk_admission(self.snapshot,tree_cap=cap,disk_plan=self.plan)
  self.assertEqual(result['free_reserve_bytes'],8<<30)
  for change in (dict(bytes=self.plan['protected_existing_bytes']+1),dict(roots=[]),dict(complete=False),dict(finished_monotonic=self.now-3),dict(finished_monotonic=self.now+1),dict(free_bytes=cap-self.snapshot['bytes']+(8<<30)-1)):
   with self.subTest(change=change),self.assertRaises(ValueError):self.cloud.fullprefill_disk_snapshot(self.plan,dict(self.snapshot,**change),cap,now=self.now)
  with self.assertRaises(ValueError):self.cloud.fullprefill_disk_snapshot(self.plan,self.snapshot,cap,now=self.now+601)
  with self.assertRaises(ValueError):base.flow.upfront_disk_admission(self.snapshot,tree_cap=cap)
 def test_real_filesystem_preparation_growth_is_reserved(self):
  import live_budget,time
  initial=live_budget.census([str(self.c.d)])
  self.plan['initial_census']=self.c.put('real_initial_census',initial)
  self.plan['protected_existing_bytes']=initial['bytes']+self.plan['binding_preparation_bytes']
  self.reapprove();self.c.put('final_invocation_binding',self.b)
  actual=live_budget.census([str(self.c.d)])
  self.assertGreater(actual['bytes'],initial['bytes']);self.assertLessEqual(actual['bytes'],self.plan['protected_existing_bytes'])
  approved=self.cloud.admit(self.b)
  # This test checks actual preparation byte accounting, not machine disk capacity.
  actual['free_bytes']=approved['aggregate_tree_cap_bytes']-actual['bytes']+(8<<30)
  proof=self.cloud.fullprefill_disk_snapshot(approved['fullprefill_disk_budget'],actual,approved['aggregate_tree_cap_bytes'],now=time.monotonic())
  self.assertEqual(proof['remaining_output_bytes'],1<<30)
 def test_missing_and_mismatched_review_rejected(self):
  original=copy.deepcopy(self.plan)
  for key,value in [('source_commit','f'*40),('artifact_manifest_sha256','f'*64),('full_block_budget_sha256','f'*64),('selected_log_bytes',1),('protected_existing_bytes',1),('binding_preparation_bytes',(16<<20)+1),('binding_preparation_bytes',True),('owned_roots',[]),('profile_output_reservations',{}),('shared_output_reservations',{}),('initial_census',None)]:
   self.plan=copy.deepcopy(original);self.plan[key]=value
   # Keep budget cap unchanged for malformed structures; independently repin audit and operator approval.
   self.doc['basis']['resource_audit']=self.c.put('finite_disk_audit',dict(fullprefill_disk_budget=self.plan));self.b['cloud_budget']=self.c.put('finite_cloud_budget',self.doc);self.ap['budget_sha256']=self.b['cloud_budget']['sha256'];self.b['execution_approval']=self.c.put('finite_approval',self.ap)
   with self.subTest(key=key),self.assertRaises((ValueError,TypeError)):self.cloud.admit(self.b)
  self.plan=original;self.reapprove();self.b['aggregate_tree_cap_bytes']=self.doc['aggregate_tree_cap_bytes']+1
  with self.assertRaises(ValueError):self.cloud.admit(self.b)
 def test_insufficient_lifetime_and_known_preparation_rejected(self):
  for key,value in [('provider_bytes',95440895),('reference_bytes',10659437)]:
   old=self.plan['profile_output_reservations']['0'][key];self.plan['profile_output_reservations']['0'][key]=value;self.reapprove()
   with self.assertRaises(ValueError):self.cloud.admit(self.b)
   self.plan['profile_output_reservations']['0'][key]=old
  self.plan['shared_output_reservations']['final_evidence_bytes']-=1;self.reapprove()
  with self.assertRaises(ValueError):self.cloud.admit(self.b)
 def test_old_approval_cannot_authorize_plan_change(self):
  self.plan['shared_output_reservations']['final_evidence_bytes']+=1
  self.doc['basis']['resource_audit']=self.c.put('unapproved_disk_audit',dict(fullprefill_disk_budget=self.plan));self.b['cloud_budget']=self.c.put('unapproved_disk_budget',self.doc)
  with self.assertRaises(ValueError):self.cloud.admit(self.b)
 def test_no_v1_v2_or_fresh_runtime_route(self):
  old=self.doc['full_block_budget'];legacy=copy.deepcopy(self.f.doc);legacy['schema']=mode.FULL_V2_SCHEMA
  self.doc['full_block_budget']=self.c.put('not_v3',legacy);self.reapprove()
  with self.assertRaises(ValueError):self.cloud.admit(self.b)
  self.doc['full_block_budget']=old;self.doc.update(runtime_mode='FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='DOWNLOAD_ORIGINAL_ARCHIVES',runtime_reuse_manifest=None);self.reapprove()
  with self.assertRaises(ValueError):self.cloud.admit(self.b)
 def test_actual_final_result_checks_all_lifetime_bytes(self):
  import types
  tree=ast.parse((D/'controller/cloud_flow.py').read_text());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run')
  node=next(n for n in run.body if isinstance(n,ast.If)and ast.unparse(n.test)=="'fullprefill_disk_budget' in budget"and any(isinstance(x,ast.Assign)and any(isinstance(y,ast.Name)and y.id=='final_bytes'for y in x.targets)for x in n.body))
  code=compile(ast.Module(body=[node],type_ignores=[]),'actual_final_disk_guard','exec');cap=self.doc['aggregate_tree_cap_bytes']
  for change,failed in [({},False),({'bytes':cap},True),({'free_bytes':8<<30},True)]:
   snapshot=dict(self.snapshot,**change);ns=dict(budget={'fullprefill_disk_budget':self.plan},flow_result={'status':'SYNTHETIC_ONLY'},json=json,need=mode.need,mod=lambda *args:types.SimpleNamespace(census=lambda *args,**kw:snapshot),census_path=D/'numeric/live_budget.py',roots=[str(self.c.d)],tree_cap=cap)
   if failed:
    with self.assertRaises(ValueError):exec(code,ns)
   else:exec(code,ns);self.assertGreater(ns['final_bytes'],0)
 def test_actual_runtime_and_locked_phase_floor(self):
  import importlib.util,types
  path=D/'runtime/runtime_reuse.py';spec=importlib.util.spec_from_file_location('finite_runtime_caps',path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
  budget=self.cloud.admit(self.b);binding=dict(stage_resources={'install':dict(as_bytes=2684354560,rss_bytes=2<<30)},install_wall_seconds=180,owned_roots=[str(self.c.d)],aggregate_tree_cap_bytes=budget['aggregate_tree_cap_bytes'])
  with patch.object(helper,'admit',return_value=budget):caps=helper.phase_caps(binding)
  self.assertEqual(caps['watch_tree_bytes'],budget['aggregate_tree_cap_bytes']);self.assertEqual(caps['min_free_disk_bytes'],8<<30);self.assertEqual(caps['rss_bytes'],2<<30)
  tree=ast.parse((D/'numeric/locked_phase.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main');node=next(n for n in main.body if isinstance(n,ast.If)and ast.unparse(n.test)=="'preserve_free_8gib' in b")
  code=compile(ast.Module(body=[node],type_ignores=[]),'actual_locked_floor','exec')
  for flag,free,failed in [(True,(8<<30)+(512<<20),False),(True,(8<<30)+(512<<20)-1,True),(False,12<<30,True)]:
   ns=dict(b=dict(preserve_free_8gib=flag,extra_bytes=512<<20),snapshot=dict(free_bytes=free))
   if failed:
    with self.assertRaises(ValueError):exec(code,ns)
   else:exec(code,ns)
 def test_caps_reject_bool_and_above_original(self):
  for value in (True,False,0,12081306273,float(12081306272)):
   self.doc['aggregate_tree_cap_bytes']=value;self.b['cloud_budget']=self.c.put('badcap_budget',self.doc);self.ap['budget_sha256']=self.b['cloud_budget']['sha256'];self.b['execution_approval']=self.c.put('badcap_approval',self.ap)
   with self.subTest(value=value),self.assertRaises(ValueError):self.cloud.admit(self.b)

if __name__=='__main__':unittest.main()
