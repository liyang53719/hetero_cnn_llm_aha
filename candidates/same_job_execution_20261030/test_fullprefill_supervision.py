"""Synthetic finite-budget and lifecycle tests. No DUT or real admission is run."""
import ast,copy,importlib.machinery,importlib.util,json,pathlib,sys,unittest
from unittest.mock import patch
import execution_mode as mode
from test_candidate_full_budget import CandidateBudgetTests,undo_fullprefill_host_paths,FULL_PREFILL_HOST_PATHS
D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D/'numeric'))
import numeric_tail as tail
spec=importlib.util.spec_from_file_location('long_cloud_flow',D/'controller/cloud_flow.py');flow=importlib.util.module_from_spec(spec);spec.loader.exec_module(flow)
class FullPrefill(unittest.TestCase):
 def setUp(self):
  self.f=CandidateBudgetTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.b=self.f.b;self.doc=copy.deepcopy(self.f.doc)
  catalog=self.f.fixture.write('executor_catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=[]))
  self.b['source_pins']=catalog
  self.doc.update(schema=mode.FULL_V2_SCHEMA,budget_contract=mode.FULL_V2_CONTRACT,completion_guaranteed=False,executor_source_commit=self.b['identity']['source_commit'],executor_source_pins_sha256=catalog['sha256'],log_policy=dict(mode.FULL_V2_LOG_POLICY),rss_telemetry_policy=dict(mode.FULL_V2_RSS_POLICY))
  evidence=self.doc['basis']['independent_budget_review'];self.doc['basis']=dict(cycle_analysis=evidence,host_rate_evidence=evidence,independent_budget_review=evidence)
  self.doc['profiles']={str(i):dict(wall_seconds=(i+1)*86400,cpu_seconds=(i+1)*86400,max_active_cycles=(i+1)*10000000,log_raw_bytes=(i+1)*128*1024**2,rss_telemetry_raw_bytes=(i+1)*128*1024**2,**{phase+'_'+kind+'_seconds':300 for phase in mode.FULL_V2_HOST_PHASES for kind in ('wall','cpu')})for i in range(5)}
  self.cloud=dict(execution_mode=mode.FULL,dut_rss_bytes=2<<30,dut_address_space_bytes=2684354560,consumer_address_space_bytes=512<<20,reserved_other_owner_bytes=5<<30)
 def admit(self,doc=None):
  self.b['full_block_budget']=self.f.fixture.write('full_v2.json',doc or self.doc)
  original=importlib.machinery.SourceFileLoader.exec_module
  def load(loader,module):
   original(loader,module)
   if pathlib.Path(module.__file__).resolve()==(D/'cloud_budget.py').resolve():module.admit=lambda binding:dict(self.cloud,full_block_budget=binding['full_block_budget'])
  with patch.object(importlib.machinery.SourceFileLoader,'exec_module',load):return mode.admit(self.b)
 def test_actual_gate_and_ordinary_candidate_review_precede_v2(self):
  admission=self.admit();self.assertEqual(admission['mode'],mode.FULL);self.assertEqual(admission['budget_version'],2);self.assertFalse(admission['completion_guaranteed']);self.assertEqual(admission['profile_log_raw_bytes']['4'],5*128*1024**2)
  self.f.approval['model_candidate_review_sha256']='0'*64;self.b['execution_approval']=self.f.fixture.write('approval.json',self.f.approval)
  with self.assertRaisesRegex(ValueError,'review independently pinned'):self.admit()
 def test_no_complete_bound_or_rate_invented(self):
  admission=self.admit();self.assertNotIn('estimated_complete_active_cycles',admission)
  d=copy.deepcopy(self.doc);d['completion_guaranteed']=True
  with self.assertRaisesRegex(ValueError,'never guarantees'):self.admit(d)
 def test_all_five_required(self):
  d=copy.deepcopy(self.doc);del d['profiles']['4']
  with self.assertRaisesRegex(ValueError,'all five'):self.admit(d)
 def test_positive_finite_strict_ints_and_maxima(self):
  for key,value in [('wall_seconds',True),('wall_seconds',0),('wall_seconds',float('inf')),('wall_seconds',mode.FULL_V2_MAX_SECONDS+1),('cpu_seconds',86401),('cpu_seconds',0),('max_active_cycles',1000000001),('log_raw_bytes',(16<<30)+1)]:
   with self.subTest(key=key,value=value):
    d=copy.deepcopy(self.doc);d['profiles']['0'][key]=value
    with self.assertRaises(ValueError):self.admit(d)
 def test_31day_ceiling_is_not_default(self):
  d=copy.deepcopy(self.doc);d['profiles']['4'].update(wall_seconds=mode.FULL_V2_MAX_SECONDS,cpu_seconds=mode.FULL_V2_MAX_SECONDS,max_active_cycles=1000000000,log_raw_bytes=16<<30)
  self.assertEqual(self.admit(d)['profile_seconds']['4'],mode.FULL_V2_MAX_SECONDS)
 def test_no_legacy_shape_or_unknown_fields(self):
  for key,value in [('estimated_complete_active_cycles',1),('reset_watchdog',True),('target_completed_commands',1)]:
   d=copy.deepcopy(self.doc);d['profiles']['0'][key]=value
   with self.assertRaises(ValueError):self.admit(d)
 def test_resource_caps_not_expanded(self):
  for key,ceiling in (('dut_rss_bytes',2<<30),('dut_address_space_bytes',2684354560)):
   before=self.cloud[key];self.cloud[key]=ceiling
   self.assertEqual(self.admit()['budget_version'],2)
   self.cloud[key]=ceiling+1
   with self.assertRaisesRegex(ValueError,'RSS2GiB/AS2.5GiB'):self.admit()
   self.cloud[key]=before
 def test_executor_identity_and_catalog_bound(self):
  for key in ('executor_source_commit','executor_source_pins_sha256'):
   d=copy.deepcopy(self.doc);d[key]='0'*len(d[key])
   with self.assertRaises(ValueError):self.admit(d)
  pathlib.Path(self.b['source_pins']['path']).write_text('{}')
  with self.assertRaises(ValueError):self.admit()
 def test_missing_or_drifted_evidence_rejected(self):
  d=copy.deepcopy(self.doc);del d['basis']['cycle_analysis']
  with self.assertRaises(ValueError):self.admit(d)
  d=copy.deepcopy(self.doc);d['basis']['host_rate_evidence']['sha256']='0'*64
  with self.assertRaises(ValueError):self.admit(d)
 def test_exact_log_policy(self):
  for key,value in [('compressed_bytes',128<<20),('line_bytes',16384),('raw_bytes',float(16<<30))]:
   d=copy.deepcopy(self.doc);d['log_policy'][key]=value
   with self.assertRaises(ValueError):self.admit(d)
 def test_consumer_changes_only_time_cycle_budgets(self):
  admission=self.admit();old=dict(address_space_bytes=12<<30,file_bytes=64<<20,wall_seconds=20000,cpu_seconds=18000,max_active_cycles=1000000000);before=dict(old)
  new=mode.consumer_limits(old,admission,3)
  self.assertEqual(old,before);self.assertEqual(new,dict(old,wall_seconds=4*86400,cpu_seconds=4*86400,max_active_cycles=40000000))
 def test_no_cpu_raise_above_inherited_hard(self):
  admission=self.admit()
  for i in range(5):
   wall=admission['profile_seconds'][str(i)];self.assertEqual(mode.dut_parent_cpu_seconds(admission,i),wall+300+30);self.assertLessEqual(admission['profile_cpu_seconds'][str(i)],wall+30)
   argv,seconds=tail.execution_command(['python',str(tail.D/'consumer_owned.py')],dict(full_block_budget=self.b['full_block_budget']),admission,i)
   self.assertEqual(seconds,wall+300+30);self.assertNotIn('--calibration-wall-seconds',argv)
 def test_cpu_change_wired_to_actual_stage(self):
  source=(D/'numeric/numeric_tail.py').read_text();self.assertIn("per_process_cpu_seconds=execution_mode.dut_parent_cpu_seconds(admission,int(name[1:-4])) if name.endswith('_dut') else seconds+30",source)
  self.assertIn('cpu_seconds=execution_mode.dut_aggregate_cpu_seconds(admission,dut_profile,seconds)',source);self.assertIn('cleanup_seconds=30',source)
 def test_cloud_whole_lifecycle_reserves_all_five(self):
  admission=self.admit();b=dict(self.b,budgets=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600),job_budget_seconds=2000000)
  path=D/'execution_mode.py';b['pins'][str(path)]=mode.sha(path)
  material,tail_seconds,total=flow.reservations(b,admission)
  self.assertEqual(tail_seconds,sum(mode.profile_reserved_seconds(admission).values())+7*180+11*120+1530+600)
  b['job_budget_seconds']=total-1
  with self.assertRaisesRegex(ValueError,'reviewed deadline'):flow.reservations(b,admission)
 def test_unreviewed_long_reservations_still_rejected(self):
  b=dict(budgets=dict(archives=1,weights=1,install=1,owner_bind=1,reference=1,provider=1,parent=1),job_budget_seconds=2000000)
  for mode_name in (mode.CALIBRATION,mode.STAGE,mode.FIRST_FAULT,mode.FULL):
   with self.subTest(mode=mode_name),self.assertRaises(ValueError):flow.reservations(b,dict(mode=mode_name,profile_seconds=dict.fromkeys(map(str,range(5)),20001)))
 def test_forged_v2_nonfull_rejected(self):
  admission=self.admit()
  for mode_name in (mode.CALIBRATION,mode.STAGE,mode.FIRST_FAULT):
   admission['mode']=mode_name
   with self.assertRaises(ValueError):mode.profile_wall_ceiling(admission)
 def test_legacy_cpu_and_finite_exit_classification_unchanged(self):
  for mode_name in (mode.CALIBRATION,mode.STAGE,mode.FIRST_FAULT,mode.FULL):self.assertEqual(mode.dut_parent_cpu_seconds(dict(mode=mode_name),0),18000)
  for status,flag,code in [('INCOMPLETE',False,2),('FAIL_EXACT_REFERENCE',False,1),('PASS_FIVE_FULL128_EXACT_REFERENCE',True,0)]:self.assertEqual(mode.transport_exit(mode.FULL,dict(status=status,numerical_pass=flag)),code)
 def test_parent_lifecycle_cpu_finite_and_no_inherited_raise(self):
  import resource
  from types import SimpleNamespace
  admission=self.admit();usage=SimpleNamespace(ru_utime=1,ru_stime=1)
  with patch.object(resource,'getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)),patch.object(resource,'getrusage',return_value=usage),patch.object(resource,'setrlimit')as setlimit:
   result=mode.install_full_v2_parent_cpu_limit(admission,2000000);setlimit.assert_called_once_with(resource.RLIMIT_CPU,(2000000,2000000));self.assertFalse(result['inherited_hard_raised'])
  with patch.object(resource,'getrlimit',return_value=(18000,18000)),patch.object(resource,'setrlimit')as setlimit:
   with self.assertRaisesRegex(ValueError,'inherited CPU hard'):mode.install_full_v2_parent_cpu_limit(admission,2000000)
   setlimit.assert_not_called()
  for value in (True,0,-1,2**31,float('inf')):
   with self.assertRaises(ValueError):mode.install_full_v2_parent_cpu_limit(admission,value)
 def test_parent_cpu_ceiling_contains_every_child(self):
  with self.assertRaisesRegex(ValueError,'contains every'):mode.install_full_v2_parent_cpu_limit(self.admit(),86400)
 def test_parent_cpu_guard_precedes_job_and_stage_creation(self):
  source=(D/'controller/cloud_flow.py').read_text();self.assertLess(source.index('.install_full_v2_parent_cpu_limit('),source.index(' job.mkdir();'));self.assertIn("FULL_V2_PARENT_CPU_LIMIT.json",source)
 def test_autoidentity_v2_real_cloud_and_mode_admission(self):
  # Only live source/host/artifact transport are synthetic seams. Real cloud,
  # candidate, V2 budget, reservation and standard prepare_identity code run.
  import test_cloud_budget as cf,prepare_cloud_execution as entry
  from types import SimpleNamespace
  c=cf.Budget();c.setUp();self.addCleanup(c.tearDown)
  self.b['full_block_budget']=self.f.fixture.write('auto-full.json',self.doc)
  host=json.loads(pathlib.Path(c.host['path']).read_text());host['boot_id']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip();hostpin=c.put('actual-boot-synthetic-host',host)
  source=self.b['identity']['source_commit'];doc=copy.deepcopy(c.doc)
  doc.update(source_commit=source,host_identity=hostpin,artifact_manifest_sha256=self.b['artifact_manifest']['sha256'],model_candidate_review=self.b['model_candidate_review'],execution_mode=mode.FULL,resource_scope='FULL_BLOCK_MEASURED_RESOURCE_PLAN',full_block_budget=self.b['full_block_budget'],job_budget_seconds=2000000,dut_rss_bytes=2<<30,dut_address_space_bytes=2684354560)
  budget=c.put('auto-budget',doc);ap=dict(c.ap,purpose=mode.FULL,source_commit=source,artifact_manifest_sha256=self.b['artifact_manifest']['sha256'],model_candidate_review_sha256=self.b['model_candidate_review']['sha256'],budget_sha256=budget['sha256'],host_identity_sha256=hostpin['sha256'])
  approval=c.put('auto-approval',ap);handoff=c.put('transport-stub',{'synthetic':True})
  args=SimpleNamespace(repo=D.parents[1],work=self.f.fixture.root/'new-executor-work',executor_identity=None,executor_identity_sha256=None)
  for key,row in dict(host_identity=hostpin,builder_handoff=handoff,artifact_manifest=self.b['artifact_manifest'],cloud_budget=budget,execution_approval=approval,model_candidate_review=self.b['model_candidate_review']).items():setattr(args,key,pathlib.Path(row['path']));setattr(args,key+'_sha256',row['sha256'])
  pins=dict(self.b['pins'])
  for name in ('profile_policy.py','execution_mode.py','numeric/candidate_artifact_handoff.py'):pins[str(D/name)]=mode.sha(D/name)
  original=entry.load;seen=[]
  def load(name,path):
   module=original(name,path)
   if name=='cloud_identity_budget':module.verify_host=lambda *a:None
   if name=='cloud_identity_live':module.verify_current=lambda identity:identity
   if name=='cloud_identity_mode':
    admit=module.admit
    def check(binding):seen.append(dict(binding));return admit(binding)
    module.admit=check
   return module
  manifest=pathlib.Path(self.b['source_pins']['path'])
  with patch.object(entry,'verify_source',return_value=(D.parents[1],manifest,pins)),patch.object(entry,'load',side_effect=load),patch.object(entry.subprocess,'check_output',return_value=source+'\n'),patch.object(entry,'imported_handoff',return_value=dict(source_pins_sha256=self.b['source_pins']['sha256'])):
   entry.prepare_identity(args)
  self.assertEqual(len(seen),1);self.assertEqual(seen[0]['source_pins'],self.b['source_pins']);self.assertEqual(seen[0]['repo'],str(D.parents[1]));self.assertTrue(args.executor_identity.is_file());self.assertFalse(args.work.exists())
 def test_four_host_domains_have_separate_explicit_bounds(self):
  admission=self.admit()
  for phase in mode.FULL_V2_HOST_PHASES:
   self.assertEqual(mode.host_phase_limits(admission,0,phase),dict(wall_seconds=300,cpu_seconds=300))
   for field,value in ((phase+'_wall_seconds',3601),(phase+'_cpu_seconds',301),(phase+'_cpu_seconds',True)):
    doc=copy.deepcopy(self.doc);doc['profiles']['0'][field]=value
    with self.assertRaises(ValueError):self.admit(doc)
  self.assertEqual(mode.profile_reserved_seconds(admission)['0'],86400+4*300)
  self.assertEqual(mode.consumer_phase_seconds(admission,0),86400+300+30)
  self.assertEqual(mode.dut_aggregate_cpu_seconds(admission,0,123),86400+300+60)
  self.assertEqual(mode.dut_admission_seconds(admission,0,600),86400+300+30+300+300+5*300+600)
  for value in (0,True,601):
   with self.assertRaises(ValueError):mode.dut_admission_seconds(admission,0,value)
 def test_actual_perprofile_rss_policy(self):
  admission=self.admit();policy=mode.expected_rss_telemetry_policy(admission,3)
  self.assertEqual(policy,dict(mode.FULL_V2_RSS_POLICY,raw_bytes=4*128*1024**2,verification_wall_seconds=300,verification_cpu_seconds=300))
  for key,value in [('rss_telemetry_raw_bytes',(16<<30)+1),('rss_telemetry_verification_wall_seconds',3601)]:
   doc=copy.deepcopy(self.doc);doc['profiles']['0'][key]=value
   with self.assertRaises(ValueError):self.admit(doc)
 def test_report_v2_downgrade_or_policy_tamper_rejected(self):
  admission=self.admit();reported=dict(execution_mode=mode.FULL,reviewed_budget_sha256=admission['reviewed_budget_sha256'],budget_version=2,log_policy=mode.expected_log_policy(admission,0),postprocess_limits=mode.host_phase_limits(admission,0,'postprocess'))
  self.assertEqual(mode.verify_consumer_admission(admission,reported,0),reported['log_policy'])
  for key,value in [('budget_version',1),('budget_version',None),('log_policy',dict(reported['log_policy'],raw_bytes=1)),('postprocess_limits',dict(wall_seconds=300,cpu_seconds=301))]:
   bad=copy.deepcopy(reported);bad[key]=value
   with self.assertRaises(ValueError):mode.verify_consumer_admission(admission,bad,0)
  legacy=dict(mode=mode.FULL,reviewed_budget_sha256=admission['reviewed_budget_sha256'])
  with self.assertRaises(ValueError):mode.verify_consumer_admission(legacy,reported,0)
 def test_actual_tail_binds_before_evidence(self):
  source=(D/'numeric/numeric_tail.py').read_text();self.assertLess(source.index('execution_mode.verify_consumer_admission(admission,report.get('),source.index('diagnostic=dut_evidence.verify(*evidence_args'))
  self.assertIn('expected_log_policy=expected_log',source);self.assertIn("host_phase_limits(admission,i,'evidence_verification')",source)
 def test_host_budget_rejects_unbounded_and_nested_extension(self):
  import signal,time
  for wall,cpu in ((0,1),(True,1),(1,2),(86401,1),(1,float('inf'))):
   with self.assertRaises(ValueError):mode.host_verification_budget(wall,cpu)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
  with mode.host_verification_budget(2,2):
   before=signal.getitimer(signal.ITIMER_REAL)[0]
   with mode.host_verification_budget(3,3):self.assertLessEqual(signal.getitimer(signal.ITIMER_REAL)[0],before)
   self.assertLessEqual(signal.getitimer(signal.ITIMER_REAL)[0],before)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
 def test_host_budget_wall_timeout_restores_timers(self):
  import signal,time
  with self.assertRaises(mode.HostVerificationBudgetExceeded):
   with mode.host_verification_budget(1,1):time.sleep(2)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
 def test_host_budget_rejects_inherited_blocked_signals(self):
  import signal,time
  signals={signal.SIGALRM,signal.SIGPROF};previous=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
  try:
   before=time.monotonic()
   with self.assertRaisesRegex(ValueError,'unblocked'):
    with mode.host_verification_budget(1,1):self.fail('blocked watchdog body must never execute')
   self.assertLess(time.monotonic()-before,.5);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
   self.assertTrue(signals<=signal.pthread_sigmask(signal.SIG_BLOCK,set()))
  finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
 def test_host_budget_preserves_foreign_timer_and_pending_signal(self):
  import signal,os
  signals={signal.SIGALRM,signal.SIGPROF};old=signal.getsignal(signal.SIGALRM);calls=[];signal.signal(signal.SIGALRM,lambda *args:calls.append(True))
  try:
   signal.setitimer(signal.ITIMER_REAL,20)
   with self.assertRaisesRegex(ValueError,'unused or explicitly owned'):
    with mode.host_verification_budget(1,1):self.fail('foreign timer body must not execute')
   remaining,interval=signal.getitimer(signal.ITIMER_REAL);self.assertTrue(0<remaining<=20);self.assertEqual(interval,0);signal.setitimer(signal.ITIMER_REAL,0)
   previous=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
   try:
    os.kill(os.getpid(),signal.SIGALRM)
    with self.assertRaises(ValueError):
     with mode.host_verification_budget(1,1):self.fail('pending signal body must not execute')
    self.assertIn(signal.SIGALRM,signal.sigpending());self.assertEqual(calls,[]);signal.sigtimedwait({signal.SIGALRM},0)
   finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
  finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 def test_host_budget_drains_owned_expiry_before_restoring_handler(self):
  import signal,time
  signals={signal.SIGALRM,signal.SIGPROF};old={signum:signal.getsignal(signum)for signum in signals};calls=[]
  try:
   for signum in signals:signal.signal(signum,lambda *args:calls.append(True))
   with self.assertRaises(mode.HostVerificationBudgetExceeded):
    with mode.host_verification_budget(1,1):
     signal.pthread_sigmask(signal.SIG_BLOCK,signals);time.sleep(1.1)
   self.assertFalse(signals.intersection(signal.sigpending()));self.assertFalse(signals.intersection(signal.pthread_sigmask(signal.SIG_BLOCK,set())));self.assertEqual(calls,[])
   self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.));self.assertEqual(mode.host_verification_budget._active,[])
  finally:
   for signum,handler in old.items():signal.signal(signum,handler)
 def test_host_budget_nested_parent_expiry_is_not_swallowed(self):
  import signal,time
  with self.assertRaises(mode.HostVerificationBudgetExceeded):
   with mode.host_verification_budget(1,1):
    with mode.host_verification_budget(2,2):time.sleep(1.1)
  self.assertEqual(mode.host_verification_budget._active,[]);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
 def test_host_budget_cpu_watchdog_interrupts_nonreturning_body(self):
  import subprocess
  script="import sys;sys.path.insert(0,sys.argv[1]);import execution_mode as m\ntry:\n with m.host_verification_budget(3,1):\n  while True:pass\nexcept m.HostVerificationBudgetExceeded:print('CPU_BOUNDED')\n"
  result=subprocess.run([sys.executable,'-B','-c',script,str(D)],capture_output=True,text=True,timeout=6)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'CPU_BOUNDED')
 def test_host_budget_inner_expiry_preserves_live_outer_deadline(self):
  import signal,time
  with mode.host_verification_budget(3,3):
   before=signal.getitimer(signal.ITIMER_REAL)[0]
   with self.assertRaises(mode.HostVerificationBudgetExceeded):
    with mode.host_verification_budget(1,1):time.sleep(1.1)
   self.assertTrue(0<signal.getitimer(signal.ITIMER_REAL)[0]<before);self.assertEqual(len(mode.host_verification_budget._active),1)
  self.assertEqual(mode.host_verification_budget._active,[])
 def test_host_budget_rejects_timer_or_handler_mutation(self):
  import signal
  for mutate in (lambda:signal.signal(signal.SIGALRM,lambda *args:None),lambda:signal.setitimer(signal.ITIMER_REAL,100),lambda:signal.setitimer(signal.ITIMER_PROF,0)):
   with self.assertRaisesRegex(mode.HostVerificationBudgetExceeded,'ownership changed'):
    with mode.host_verification_budget(2,2):mutate()
   self.assertEqual(mode.host_verification_budget._active,[]);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
 def test_summary_wrapper_uses_original_lifecycle_and_host_scope(self):
  source=(D/'summarize_cloud_execution.py').read_text()
  for value in ('V2 summary reserve fits original lifecycle deadline',"profile_summary_verification_wall_seconds",'with mode.host_verification_budget(wall,cpu)',"host_phase_limits(admission,i,'summary_verification')",'expected_log_policy=expected_log','mode.verify_consumer_admission(admission,ea,i)'):self.assertIn(value,source)
 def test_actual_rss_receipt_policy_and_source_binding(self):
  helper_path=D.parent/'ci_frontend_pipeline_r2_20261029/rss_telemetry.py'
  spec=importlib.util.spec_from_file_location('rss_fixture',helper_path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
  admission=self.admit();policy=mode.expected_rss_telemetry_policy(admission,0);directory=self.f.fixture.root/'outer';directory.mkdir();path=directory/'rss_samples.jsonl.gz'
  writer=helper.Writer(path,policy);writer.write(json.dumps(dict(elapsed=1.0,aggregate_rss_bytes=1024,processes=[[1,2,3,1,1024,5,2048]],MemAvailable_bytes=8<<30,reserve_below_1GiB_warning=False))+'\n');writer.finish();writer.close();receipt=helper.verify(path,writer.receipt(),policy,1)
  caps=dict(wall_seconds=mode.consumer_phase_seconds(admission,0)+30,cleanup_seconds=30,cpu_seconds=mode.dut_aggregate_cpu_seconds(admission,0,0),per_process_cpu_seconds=mode.dut_parent_cpu_seconds(admission,0),rss_bytes=2<<30,per_process_as_bytes=2684354560,rss_telemetry_policy=policy)
  report=dict(caps=caps,rss_telemetry=receipt,process_sample_count=1);outer=directory/'RESULT.json'
  def pin_report(value):outer.write_text(json.dumps(value));return dict(path=str(outer),bytes=outer.stat().st_size,sha256=mode.sha(outer))
  pins={str(helper_path):mode.sha(helper_path)};outer_pin=pin_report(report)
  with mode.host_verification_budget(5,5):self.assertEqual(mode.verify_supervisor_telemetry(outer_pin,admission,0,helper_path.parent,pins),receipt)
  for key,value in [('wall_seconds',caps['wall_seconds']+1),('cpu_seconds',float(caps['cpu_seconds'])),('rss_telemetry_policy',dict(policy,verification_cpu_seconds=301))]:
   bad=copy.deepcopy(report);bad['caps'][key]=value
   with self.assertRaises(ValueError):mode.verify_supervisor_telemetry(pin_report(bad),admission,0,helper_path.parent,pins)
  bad=copy.deepcopy(report);del bad['rss_telemetry']
  with self.assertRaises(ValueError):mode.verify_supervisor_telemetry(pin_report(bad),admission,0,helper_path.parent,pins)
  with self.assertRaisesRegex(ValueError,'source-pinned'):mode.verify_supervisor_telemetry(pin_report(report),admission,0,helper_path.parent,{})
  data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
  with self.assertRaises(ValueError):mode.verify_supervisor_telemetry(pin_report(report),admission,0,helper_path.parent,pins)
 def test_allowlist_new_paths_exact_and_no_hardware(self):
  import executor_adaptation as adapter
  for path in FULL_PREFILL_HOST_PATHS:self.assertIn(adapter.PREFIX+path,adapter.ALLOWED_PATHS)
  for suffix in ('hardware.sv','driver.cpp','model.scala'):self.assertNotIn(adapter.PREFIX+suffix,adapter.ALLOWED_PATHS)
  tree=ast.parse((D/'executor_adaptation.py').read_text());undo_fullprefill_host_paths(self,tree)
  tree=ast.parse((D/'executor_adaptation.py').read_text());node=next(n for n in ast.walk(tree)if isinstance(n,ast.Tuple)and FULL_PREFILL_HOST_PATHS<={v.value for v in n.elts if isinstance(v,ast.Constant)});node.elts.append(ast.Constant(value='numeric/full_log.py'))
  with self.assertRaises(AssertionError):undo_fullprefill_host_paths(self,tree)


 def test_host_owned_mask_preserves_unrelated_changes(self):
  import signal
  initial=signal.pthread_sigmask(signal.SIG_BLOCK,set())
  try:
   for initially_blocked in (False,True):
    signal.pthread_sigmask(signal.SIG_BLOCK if initially_blocked else signal.SIG_UNBLOCK,{signal.SIGUSR1})
    with mode.host_verification_budget(5,5):
     signal.pthread_sigmask(signal.SIG_UNBLOCK if initially_blocked else signal.SIG_BLOCK,{signal.SIGUSR1})
    self.assertEqual(signal.SIGUSR1 in signal.pthread_sigmask(signal.SIG_BLOCK,set()),not initially_blocked)
  finally:signal.pthread_sigmask(signal.SIG_SETMASK,initial)
 def test_host_cross_thread_exit_preserves_owner_watchdogs(self):
  import signal,threading
  budget=mode.host_verification_budget(5,5)
  with budget:
   handlers={s:signal.getsignal(s)for s in (signal.SIGALRM,signal.SIGPROF)}
   timers={t:signal.getitimer(t)for t in (signal.ITIMER_REAL,signal.ITIMER_PROF)};observed={}
   def stop():
    signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGUSR1})
    before=signal.pthread_sigmask(signal.SIG_BLOCK,set())
    try:budget.__exit__(None,None,None)
    except ValueError:observed['rejected']=True
    observed['mask_preserved']=before==signal.pthread_sigmask(signal.SIG_BLOCK,set())
   thread=threading.Thread(target=stop);thread.start();thread.join(1)
   self.assertFalse(thread.is_alive());self.assertEqual(observed,dict(rejected=True,mask_preserved=True));self.assertTrue(budget.running)
   for sig,handler in handlers.items():self.assertIs(signal.getsignal(sig),handler)
   for timer,before in timers.items():
    after=signal.getitimer(timer);self.assertTrue(0<after[0]<=before[0]);self.assertEqual(after[1],before[1])
 def test_host_non_lifo_exit_preserves_nested_watchdogs(self):
  import signal
  with mode.host_verification_budget(5,5)as outer:
   with mode.host_verification_budget(4,4)as inner:
    handler=signal.getsignal(signal.SIGALRM);before=signal.getitimer(signal.ITIMER_REAL)
    with self.assertRaises(ValueError):outer.__exit__(None,None,None)
    self.assertIs(signal.getsignal(signal.SIGALRM),handler);self.assertTrue(0<signal.getitimer(signal.ITIMER_REAL)[0]<=before[0]);self.assertTrue(inner.running);self.assertTrue(outer.running)

 def test_host_reentrant_handler_preserves_unrelated_mask(self):
  import os,signal
  initial=signal.pthread_sigmask(signal.SIG_BLOCK,set());old_handler=signal.getsignal(signal.SIGUSR1);real=signal.pthread_sigmask
  try:
   for rejected_entry in (False,True):
    for initially_blocked in (False,True):
     with self.subTest(rejected_entry=rejected_entry,initially_blocked=initially_blocked):
      real(signal.SIG_UNBLOCK,{signal.SIGUSR1,signal.SIGALRM,signal.SIGPROF})
      real(signal.SIG_BLOCK if initially_blocked else signal.SIG_UNBLOCK,{signal.SIGUSR2})
      seen=[]
      def external_handler(signum,frame):
       real(signal.SIG_UNBLOCK if initially_blocked else signal.SIG_BLOCK,{signal.SIGUSR2});seen.append(signum)
      signal.signal(signal.SIGUSR1,external_handler)
      budget=mode.host_verification_budget(5,5)
      if rejected_entry:signal.setitimer(signal.ITIMER_REAL,20,1)
      else:budget.__enter__()
      original_restore=budget._restore_owned_mask;state=dict(restoring=False,injected=False)
      def restore():
       state['restoring']=True
       try:return original_restore()
       finally:state['restoring']=False
      def interleave(how,signals):
       snapshot=real(how,signals)
       if state['restoring']and not state['injected']:
        state['injected']=True;os.kill(os.getpid(),signal.SIGUSR1)
       return snapshot
      try:
       with patch.object(budget,'_restore_owned_mask',side_effect=restore),patch.object(signal,'pthread_sigmask',side_effect=interleave):
        if rejected_entry:
         with self.assertRaisesRegex(ValueError,'unused or explicitly owned'):budget.__enter__()
        else:budget.__exit__(None,None,None)
       self.assertEqual(seen,[signal.SIGUSR1]);self.assertTrue(state['injected'])
       self.assertEqual(signal.SIGUSR2 in real(signal.SIG_BLOCK,set()),not initially_blocked)
       self.assertFalse({signal.SIGALRM,signal.SIGPROF}&real(signal.SIG_BLOCK,set()))
       if rejected_entry:
        remaining,interval=signal.getitimer(signal.ITIMER_REAL);self.assertTrue(0<remaining<=20);self.assertEqual(interval,1)
       else:self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
       self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.));self.assertFalse(budget.running);self.assertEqual(mode.host_verification_budget._active,[])
      finally:signal.setitimer(signal.ITIMER_REAL,0);signal.setitimer(signal.ITIMER_PROF,0)
  finally:
   signal.signal(signal.SIGUSR1,old_handler);real(signal.SIG_SETMASK,initial)

 def test_host_raising_reentrant_restore_finishes_owned_bits(self):
  import os,signal
  class ExternalFailure(RuntimeError):pass
  owned={signal.SIGALRM,signal.SIGPROF};real=signal.pthread_sigmask
  initial=real(signal.SIG_BLOCK,set());old_usr1=signal.getsignal(signal.SIGUSR1)
  try:
   for kind in ('blocked_alarm','blocked_prof','foreign_timer','owned_start'):
    with self.subTest(kind=kind):
     real(signal.SIG_UNBLOCK,owned|{signal.SIGUSR1,signal.SIGUSR2})
     if kind.startswith('blocked_'):real(signal.SIG_BLOCK,{signal.SIGALRM if kind=='blocked_alarm'else signal.SIGPROF})
     if kind=='foreign_timer':signal.setitimer(signal.ITIMER_REAL,20,1)
     entry=real(signal.SIG_BLOCK,set());handlers={s:signal.getsignal(s)for s in owned};seen=[]
     def external_handler(signum,frame):
      real(signal.SIG_BLOCK,{signal.SIGUSR2});seen.append(signum)
      raise ExternalFailure('actual unrelated handler raised during owned-mask restoration')
     signal.signal(signal.SIGUSR1,external_handler)
     budget=mode.host_verification_budget(5,5);original_restore=budget._restore_owned_mask;state=dict(restoring=False,injected=False)
     def restore():
      state['restoring']=True
      try:return original_restore()
      finally:state['restoring']=False
     def interleave(how,signals):
      previous=real(how,signals)
      if state['restoring']and not state['injected']:
       state['injected']=True;os.kill(os.getpid(),signal.SIGUSR1)
      return previous
     try:
      with patch.object(budget,'_restore_owned_mask',side_effect=restore),patch.object(signal,'pthread_sigmask',side_effect=interleave):
       with self.assertRaises(ExternalFailure):budget.__enter__()
      self.assertEqual(seen,[signal.SIGUSR1]);self.assertFalse(budget.running);self.assertEqual(mode.host_verification_budget._active,[])
      self.assertEqual(real(signal.SIG_BLOCK,set()),entry|{signal.SIGUSR2});self.assertFalse(owned&signal.sigpending())
      for signum,handler in handlers.items():self.assertIs(signal.getsignal(signum),handler)
      if kind=='foreign_timer':
       remaining,interval=signal.getitimer(signal.ITIMER_REAL);self.assertTrue(0<remaining<=20);self.assertEqual(interval,1)
      else:self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
      self.assertEqual(signal.getitimer(signal.ITIMER_PROF),(0.,0.))
     finally:
      if budget.running:budget.__exit__(None,None,None)
      signal.setitimer(signal.ITIMER_REAL,0);signal.setitimer(signal.ITIMER_PROF,0)
  finally:signal.signal(signal.SIGUSR1,old_usr1);real(signal.SIG_SETMASK,initial)

class ActualFullPrefillCallsites(unittest.TestCase):
 setUp=FullPrefill.setUp
 admit=FullPrefill.admit
 """Synthetic five-profile receipt joins, actual cloud projection and tail body.
 Authentication/admission sources are synthetic seams; no DUT/model is run.
 """
 def summary_fixture(self):
  import time,types
  sys.path.insert(0,str(D/'acceptance_tests'))
  import test_cloud_summary as fixture,test_full_log as logs,full_log,required_acceptance as acceptance,dut_evidence as evidence
  from test_progress import line
  root=self.f.fixture.root/'actual_summary';root.mkdir();job,bp=fixture.Tests().fixture(root)
  self.summary=fixture.s;self.admission=self.admit();b=json.loads(bp.read_text());b.update(full_block_budget=self.b['full_block_budget'],execution_mode=mode.FULL,budgets={'parent':30},job_budget_seconds=10000000,supervisor_dir=str(D.parent/'ci_frontend_pipeline_r2_20261029'))
  b['identity'].update(boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),started_monotonic=time.monotonic()-1)
  b['model_candidate_review']=self.f.fixture.write('synthetic-review-summary.json',{'synthetic':True});b['source_pins']=self.b['source_pins'];b['repo']=str(D.parents[1])
  manifest=pathlib.Path(b['artifact_manifest']['path']);doc=json.loads(manifest.read_text());doc['schema']='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1';manifest.write_text(json.dumps(doc));b['artifact_manifest']=self.summary.pin(manifest)
  hp=pathlib.Path(b['supervisor_dir'])/'rss_telemetry.py';sp=importlib.util.spec_from_file_location('callsite_rss',hp);rss=importlib.util.module_from_spec(sp);sp.loader.exec_module(rss)
  b['pins']={str(p):mode.sha(p)for p in (hp,D/'summary_progress.py',D/'execution_mode.py')};bp.write_text(json.dumps(b));self.sbinding=b;self.sjob=job;self.sbp=bp
  n=job/'materials/numeric';records=[]
  for i in range(5):
   out=n/f'profile{i}/material/dut_result';rp=out/'RESULT.json';r=json.loads(rp.read_text());start=json.loads((out/f'profile{i}.started.json').read_text())
   policy=mode.expected_log_policy(self.admission,i);capture=logs.fixture(out/f'profile{i}.log',line(10),policy)
   capture.update(pid=start['pid'],consumer_pid=start['consumer_pid']);full_log.paths(out/f'profile{i}.log')[1].write_text(json.dumps(capture))
   original=dict(wall_seconds=20000,cpu_seconds=18000,max_active_cycles=1000000000,address_space_bytes=12<<30,file_bytes=64<<20)
   r.update(executor_identity=b['identity'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],model_candidate_review_sha256=b['model_candidate_review']['sha256'],candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL')
   r['execution_admission']=dict(execution_mode=mode.FULL,reviewed_budget_sha256=self.admission['reviewed_budget_sha256'],budget_version=2,log_policy=policy,postprocess_limits=mode.host_phase_limits(self.admission,i,'postprocess'),outer_cleanup_proof_required=True,scope='FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE',original_limits=original,effective_limits=dict(mode.consumer_limits(original,self.admission,i),address_space_bytes=2684354560))
   r['resource_admission']=dict(consumer_pre_fork_soft_bytes=512<<20,consumer_pre_fork_hard_bytes=2684354560,consumer_after_popen_hard_bytes=512<<20,dut_hard_address_space_bytes=2684354560,group_rss_is_sampled=True)
   r['profiles'][0].update(log_capture=capture,postprocess_observed=dict(wall_seconds=.01,cpu_seconds=.01,budget_exceeded=False));rp.write_text(json.dumps(r))
   outer=n/f'runs/p{i}_dut/RESULT.json';o=json.loads(outer.read_text());rss_policy=mode.expected_rss_telemetry_policy(self.admission,i);writer=rss.Writer(outer.with_name('rss_samples.jsonl.gz'),rss_policy)
   writer.write(json.dumps(dict(elapsed=1.0,aggregate_rss_bytes=1024,processes=[[1,2,3,1,1024,5,2048]],MemAvailable_bytes=8<<30,reserve_below_1GiB_warning=False))+'\n');writer.finish();writer.close();proof=rss.verify(writer.path,writer.receipt(),rss_policy,1)
   caps=dict(wall_seconds=mode.consumer_phase_seconds(self.admission,i)+30,cleanup_seconds=30,cpu_seconds=mode.dut_aggregate_cpu_seconds(self.admission,i,0),per_process_cpu_seconds=mode.dut_parent_cpu_seconds(self.admission,i),rss_bytes=2<<30,per_process_as_bytes=2684354560,rss_telemetry_policy=rss_policy)
   o.update(caps=caps,rss_telemetry=proof,process_sample_count=1,elapsed_seconds=1.0);outer.write_text(json.dumps(o))
   record=evidence.verify(out,i,b['artifact_manifest']['sha256'],fixture.base.H,fixture.base.H,fixture.base.H,self.summary.pin(outer),expected_log_policy=policy);(n/f'PROFILE_{i}_DIAGNOSTIC.json').write_text(json.dumps(record));records.append(record)
  q=acceptance.aggregate(records);nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr.update(execution_mode=mode.FULL,full_budget_sha256=self.admission['reviewed_budget_sha256'],actual_dut_reports=records,qualification=q,status=q['status'],numerical_pass=q['numerical_pass']);nf.write_text(json.dumps(nr))
  ff=job/'FLOW_RESULT.json';f=json.loads(ff.read_text());f.update(identity=b['identity'],execution_binding=self.summary.pin(bp),artifact_manifest=b['artifact_manifest'],model_candidate_review=b['model_candidate_review'],scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',numeric_result=self.summary.pin(nf),execution_mode=mode.FULL,transport_exit_code=0,qualification=q,status=q['status']);ff.write_text(json.dumps(f))
 def project_summary(self):
  import signal
  s=self.summary;original=s.load;self.evidence_calls=0
  def loader(name,path):
   module=original(name,path)
   if name=='summary_cloud_handoff':module.verify=lambda *a,**kw:dict(source_pins_sha256='f'*64)
   if name=='summary_candidate_admission':module.verify=lambda *a,**kw:dict(scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL')
   if name=='summary_cloud_budget':module.admit=lambda b:dict(execution_mode=mode.FULL,full_block_budget=b['full_block_budget'],consumer_address_space_bytes=512<<20,dut_address_space_bytes=2684354560)
   if name in ('summary_reserved_full_mode','summary_cloud_mode'):module.admit=lambda b:self.admission
   if name=='cloud_dut_evidence':
    verify=module.verify
    def bounded(*args,**kw):
     self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],0);self.assertGreater(signal.getitimer(signal.ITIMER_PROF)[0],0);self.evidence_calls+=1
     return verify(*args,**kw)
    module.verify=bounded
   return module
  with patch.object(s,'source_guard',return_value='f'*64),patch.object(s,'load',side_effect=loader):return s.project(self.sjob,self.sbp,s.sha(self.sbp))
 def rebind_report(self,i,mutate):
  n=self.sjob/'materials/numeric';rp=n/f'profile{i}/material/dut_result/RESULT.json';r=json.loads(rp.read_text());mutate(r);rp.write_text(json.dumps(r))
  recordp=n/f'PROFILE_{i}_DIAGNOSTIC.json';record=json.loads(recordp.read_text());record['report']=self.summary.pin(rp);recordp.write_text(json.dumps(record));nf=n/'RESULT.json';nr=json.loads(nf.read_text());nr['actual_dut_reports'][i]=record;nf.write_text(json.dumps(nr));ff=self.sjob/'FLOW_RESULT.json';f=json.loads(ff.read_text());f['numeric_result']=self.summary.pin(nf);ff.write_text(json.dumps(f))
 def tail_poststage(self,i):
  # Compile the exact actual post-stage production statements, not a replica.
  # Upstream acquisition/supervision is covered by its own host-only fixtures.
  import types,dut_evidence
  tree=ast.parse((D/'numeric/numeric_tail.py').read_text());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run');loop=next(n for n in run.body if isinstance(n,ast.For)and ast.unparse(n.iter)=='execution_profiles(b, admission)');withbody=next(n for n in loop.body if isinstance(n,ast.With)).body
  start=next(k for k,n in enumerate(withbody)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='report'for t in n.targets));stop=next(k for k in range(start,len(withbody))if isinstance(withbody[k],ast.If)and ast.unparse(withbody[k].test)=='cloud is not None')
  profile=self.sjob/f'materials/numeric/profile{i}/material';bundle=profile/'runtime_bundle.v3.json';bundle.write_text('{}');report=json.loads((profile/'dut_result/RESULT.json').read_text())
  ns=dict(json=json,P=pathlib.Path,profile=profile,i=i,admission=self.admission,execution_mode=mode,dut_evidence=dut_evidence,b=self.sbinding,out=self.sjob/'materials/numeric',manifest=pathlib.Path(self.sbinding['artifact_manifest']['path']),bundle=bundle,binary=report['common']['binary'],runtime_sha=json.loads((profile/f'dut_result/profile{i}.started.json').read_text())['runtime_sha256'],material=types.SimpleNamespace(pin=self.summary.pin),sha=lambda p:report['runtime_bundle_sha256']if pathlib.Path(p)==bundle else mode.sha(p))
  exec(compile(ast.Module(body=withbody[start:stop],type_ignores=[]),'actual_numeric_tail_poststage','exec'),ns);return ns['diagnostic']
 def test_actual_cloud_v2_projection_and_progress_with_real_gzip(self):
  self.summary_fixture();r=self.project_summary();self.assertEqual(r['status'],'VERIFIED_REAGGREGATED');self.assertTrue(r['numerical_pass']);self.assertEqual(self.evidence_calls,5)
  rows=r['full_prefill_progress']['profiles'];self.assertEqual(len(rows),5);self.assertTrue(all(row['status']=='OBSERVED_PARTIAL_NOT_NUMERICAL_PASS'and row['sample_count']==1 for row in rows));self.assertTrue(all(row['observed_cycles_per_outer_second']is not None for row in rows))
  self.assertTrue(self.tail_poststage(0)['numerical_pass'])
 def test_actual_cloud_and_tail_reject_rebound_downgrade(self):
  self.summary_fixture()
  def mutate(r):r['execution_admission']['budget_version']=1;r['profiles'][0].pop('log_capture')
  self.rebind_report(0,mutate);self.assertEqual(self.project_summary()['status'],'UNAVAILABLE');self.assertEqual(self.evidence_calls,0)
  with self.assertRaisesRegex(ValueError,'expected full V2'):self.tail_poststage(0)
 def test_actual_cloud_and_tail_reject_missing_capture_without_downgrade(self):
  self.summary_fixture();self.rebind_report(0,lambda r:r['profiles'][0].pop('log_capture'));self.assertEqual(self.project_summary()['status'],'UNAVAILABLE');self.assertEqual(self.evidence_calls,1)
  with self.assertRaises(ValueError):self.tail_poststage(0)
 def test_actual_summary_reserve_must_fit_original_job(self):
  self.summary_fixture();b=json.loads(self.sbp.read_text());b['job_budget_seconds']=1;self.sbp.write_text(json.dumps(b));self.assertEqual(self.project_summary()['status'],'UNAVAILABLE');self.assertEqual(self.evidence_calls,0)

class RealCloudCandidateV2Admission(unittest.TestCase):
 def setUp(self):
  import test_cloud_budget as cloud_fixture
  self.f=FullPrefill();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.c=cloud_fixture.Budget();self.c.setUp();self.addCleanup(self.c.tearDown)
  f=self.f;c=self.c
  f.b['full_block_budget']=f.f.fixture.write('full-v2-real-chain.json',f.doc)
  identity=dict(c.identity,source_commit=f.b['identity']['source_commit']);f.b['identity']=identity
  doc=copy.deepcopy(c.doc);doc.update(source_commit=identity['source_commit'],artifact_manifest_sha256=f.b['artifact_manifest']['sha256'],model_candidate_review=f.b['model_candidate_review'],execution_mode=mode.FULL,resource_scope='FULL_BLOCK_MEASURED_RESOURCE_PLAN',full_block_budget=f.b['full_block_budget'],job_budget_seconds=2000000,dut_rss_bytes=2<<30,dut_address_space_bytes=2684354560)
  f.b['cloud_budget']=c.put('real-chain-budget',doc)
  approved=dict(c.ap,purpose=mode.FULL,source_commit=identity['source_commit'],artifact_manifest_sha256=f.b['artifact_manifest']['sha256'],model_candidate_review_sha256=f.b['model_candidate_review']['sha256'],budget_sha256=f.b['cloud_budget']['sha256'])
  f.b['execution_approval']=c.put('real-chain-approval',approved)
 def test_no_mock_full_cloud_candidate_and_v2_join(self):
  result=mode.admit(self.f.b);self.assertEqual(result['budget_version'],2);self.assertEqual(result['profile_seconds']['4'],5*86400)
 def test_repin_full_doc_without_operator_approval_rejected(self):
  d=copy.deepcopy(self.f.doc);d['profiles']['0']['wall_seconds']+=1;self.f.b['full_block_budget']=self.f.f.fixture.write('unapproved-full.json',d)
  with self.assertRaises(ValueError):mode.admit(self.f.b)
 def test_repin_executor_catalog_without_budget_review_rejected(self):
  self.f.b['source_pins']=self.f.f.fixture.write('unapproved-catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=[{}]))
  with self.assertRaises(ValueError):mode.admit(self.f.b)

if __name__=='__main__':unittest.main()
