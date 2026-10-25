"""Focused order/aggregate-supervision mocks; no real numeric/native run."""
from pathlib import Path
import ast,copy,hashlib,importlib.util,json,os,sys,tempfile,time,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;HERE=ROOT/'overlay/candidates/qwen2_attention_selective_compare';sys.path.insert(0,str(HERE))
import stability as s
import launch as launch
FIELDS=('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
def make_fields(d,prefix):
 out={}
 for name in FIELDS:
  file=prefix+'_'+name+'.u32le';presence=prefix+'_PRESENCE_'+name+'.binmeta';(d/file).write_bytes(b'\x01\0\0\0');(d/presence).write_bytes(b'\x01')
  out[name]=dict(file=file,bytes=4,sha256=s.digest(d/file),presence_file=presence,presence_sha256=s.digest(d/presence),shape=[1],frequency=[1])
 (d/(prefix+'_FIELDS.json')).write_text(json.dumps(out))
def fixture(root):
 directories=[]
 for order_index,order in enumerate(s.ORDERS):
  d=root/('SYNTHETIC_NO_NATIVE_'+str(order_index));d.mkdir();directories.append(d);arms=[];links=[]
  (d/'REFERENCE_OUTPUT.u32le').write_bytes(b'\x01\0\0\0');(d/'REFERENCE_SCORES.u32le').write_bytes(b'\x01\0\0\0');make_fields(d,'REFERENCE')
  for i,v in enumerate(order):
   link=dict(variant=v,execution_index=i,output='OUTPUT_'+str(i)+'.u32le',scores='SCORES_'+str(i)+'.u32le',writes='WRITES_'+str(i)+'.json',service_events='SERVICE_EVENTS_'+str(i)+'.json',capture_fields=None if v=='off' else 'CAPTURE_'+str(i)+'_FIELDS.json');links.append(link)
   (d/link['output']).write_bytes(b'\x01\0\0\0');(d/link['scores']).write_bytes(b'\x01\0\0\0');(d/link['writes']).write_text('[[1,2,[3]]]')
   ticket=100+order_index*10+i;events=[['acquire',0,['normal',10]],['accept_group',1,[0x23,1,10,255,2]],['accept_step',2,[0,0,True,True,True,True,'packet']],['retire_result',3,[0,True,False,ticket,0,'result']],['retire_done',4,[10,False,ticket,0]],['retire_owner_response',5,[]],['release',6,[]]];(d/link['service_events']).write_text(json.dumps(events))
   if v!='off':make_fields(d,'CAPTURE_'+str(i))
   arm={k:{} for k in ('counts','service_counts','scalar_calls','work_events','lane_calls','owner_counts')};arm.update(native_fmas=1,edges=1,owner_clock=1,held_checks=1,observer_variant=v,terminal_acked=True,resources_released=True,service_trace_error=None,capture_error=None,capture_report=None if v=='off' else {'synthetic':True},stages=[dict(stage='actual_owner_job_through_terminal_ack_and_monitor_exit',cpu_ns={'off':100,'original':200,'selective_identity_r1':150}[v]+order_index,wall_ns=250+order_index)]);arms.append(arm)
  result=dict(status='PASS_REAL_ATTENTION_M2_ROTATED_IDENTITY_TRIO_DIAGNOSTIC_ONLY',m=2,order_index=order_index,execution_order=list(order),canonical_reporting_order=list(s.CANONICAL),reference_after_all_three_terminals=True,identity=dict(boot_id='SYNTHETIC',pid=order_index+10,start_ticks=order_index+100),arms=arms,arm_artifacts=links)
  (d/'RESULT.json').write_text(json.dumps(result))
 return directories
class Ordering(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.root=Path(self.temp.name);self.dirs=fixture(self.root)
 def tearDown(self):self.temp.cleanup()
 def change_result(self,index,callback):
  p=self.dirs[index]/'RESULT.json';r=json.loads(p.read_text());callback(r);p.write_text(json.dumps(r))
 def test_three_rotations_preserve_raw_order_and_tickets(self):
  before={p:p.read_bytes() for d in self.dirs for p in d.iterdir()};report=s.summarize_experiment(self.dirs)
  self.assertTrue(report['identity_cpu_lower_in_all_three']);self.assertFalse(report['performance_adopted']);self.assertEqual([r['execution_order'] for r in report['rounds']],[list(x) for x in s.ORDERS]);self.assertEqual(before,{p:p.read_bytes() for p in before})
 def test_canonical_comparison_retains_actual_arm_objects(self):
  for order in s.ORDERS:
   arms=[dict(observer_variant=v,terminal_acked=True,resources_released=True) for v in order];before=arms[:];canonical=s.canonical_arms(arms,order)
   self.assertEqual([x['observer_variant'] for x in canonical],list(s.CANONICAL));self.assertEqual(arms,before)
   for arm in canonical:self.assertTrue(any(arm is original for original in arms))
 def test_unacked_physical_arm_rejected(self):
  self.change_result(1,lambda r:r['arms'][0].update(terminal_acked=False))
  with self.assertRaisesRegex(ValueError,'physical terminals'):s.summarize_experiment(self.dirs)
 def test_wrong_artifact_variant_link_rejected(self):
  self.change_result(1,lambda r:r['arm_artifacts'][0].update(variant='off'))
  with self.assertRaisesRegex(ValueError,'artifact index'):s.summarize_experiment(self.dirs)
 def test_wrong_order_receipt_rejected(self):
  self.change_result(1,lambda r:r.update(execution_order=list(s.CANONICAL)))
  with self.assertRaisesRegex(ValueError,'order mismatch'):s.summarize_experiment(self.dirs)
 def test_duplicate_process_birth_rejected(self):
  first=json.loads((self.dirs[0]/'RESULT.json').read_text())['identity'];self.change_result(1,lambda r:r.update(identity=first))
  with self.assertRaisesRegex(ValueError,'fresh worker'):s.summarize_experiment(self.dirs)
 def test_raw_output_change_rejected(self):
  (self.dirs[2]/'OUTPUT_1.u32le').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'own reference'):s.summarize_experiment(self.dirs)
 def test_uniformly_corrupt_outputs_rejected_against_own_reference(self):
  for directory in self.dirs:
   for path in directory.glob('OUTPUT_*.u32le'):path.write_bytes(b'all-corrupt')
  with self.assertRaisesRegex(ValueError,'own reference'):s.summarize_experiment(self.dirs)
 def test_uniformly_corrupt_captures_rejected_against_own_reference(self):
  for directory in self.dirs:
   for path in directory.glob('CAPTURE_*_FIELDS.json'):
    fields=json.loads(path.read_text());row=fields['dot_parts'];raw=directory/row['file'];raw.write_bytes(b'\x02\0\0\0');row['sha256']=s.digest(raw);path.write_text(json.dumps(fields))
  with self.assertRaisesRegex(ValueError,'fields differ from own reference'):s.summarize_experiment(self.dirs)
 def test_raw_event_lifecycle_change_rejected(self):
  p=self.dirs[1]/'SERVICE_EVENTS_0.json';events=json.loads(p.read_text());events[3][2][1]=False;p.write_text(json.dumps(events))
  with self.assertRaisesRegex(ValueError,'metadata'):s.summarize_experiment(self.dirs)
 def test_capture_frequency_change_rejected(self):
  p=self.dirs[1]/'CAPTURE_0_FIELDS.json';fields=json.loads(p.read_text());fields['dot_parts']['frequency']=[2];p.write_text(json.dumps(fields))
  with self.assertRaisesRegex(ValueError,'capture/frequency'):s.summarize_experiment(self.dirs)
 def test_reference_payload_change_rejected(self):
  (self.dirs[1]/'REFERENCE_OUTPUT.u32le').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'reference changed'):s.summarize_experiment(self.dirs)
 def test_worker_uses_canonical_only_for_comparison(self):
  source=(HERE/'worker.py').read_text()
  self.assertIn('for index,variant in enumerate(execution_order)',source);self.assertIn('control_arms=canonical_arms(arms,execution_order)',source);self.assertIn('comparison=compare_original(config,a.m,inputs,control_arms,reference_out=out)',source);self.assertIn('for arm in arms:',source)
  self.assertLess(source.index('control=compare_three(control_arms'),source.index('guard.terminal=True'))
 def test_harness_and_capture_runtime_are_byte_identical_to_actual(self):
  old=ROOT.parent/'identity_real_compare_20261025T0723/overlay/candidates/qwen2_attention_selective_compare'
  for name in ('harness.py','runtime_observer.py','reference_capture.py','selective_binding.py','artifacts.py','stage_clock.py'):
   self.assertEqual((HERE/name).read_bytes(),(old/name).read_bytes(),name)
class Supervision(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def budget(self,wall=.1):
  class FakeBudget:
   def allowance(self):return 1,wall
   def snapshot(self,*a):return dict(cpu_seconds=0,wall_seconds=0,rss_bytes=0)
   def require_work_budget(self,*a):return self.snapshot()
  return FakeBudget()
 def test_successful_stdlib_child_is_reaped_and_group_empty(self):
  record=launch.supervise([sys.executable,'-I','-S','-B','-c','print("STDLIB_MOCK_ONLY")'],os.environ.copy(),self.root/'ok',self.budget(2))
  self.assertEqual(record['status'],'EXITED');self.assertFalse(record['group_remaining'])
 def test_timed_out_owned_child_group_cleaned_no_output_deleted(self):
  record=launch.supervise([sys.executable,'-I','-S','-B','-c','import time; print("partial",flush=True); time.sleep(10)'],os.environ.copy(),self.root/'timeout',self.budget(.05))
  self.assertEqual(record['status'],'FAILED_RETAINED');self.assertFalse(record['group_remaining']);self.assertEqual(record['cleanup_signal'],'SIGKILL_OWN_VERIFIED_GROUP');self.assertIn('partial',(self.root/'timeout/worker.log').read_text())
 def test_exited_leader_descendant_is_killed_before_group_identity_reuse(self):
  child="import subprocess,sys; p=subprocess.Popen([sys.executable,'-I','-S','-B','-c','import time; time.sleep(10)']); print(p.pid,flush=True)"
  record=launch.supervise([sys.executable,'-I','-S','-B','-c',child],os.environ.copy(),self.root/'linger',self.budget(2))
  self.assertEqual(record['status'],'FAILED_RETAINED');self.assertTrue(record['unexpected_descendants_after_leader_exit']);self.assertEqual(record['cleanup_signal'],'SIGKILL_OWN_VERIFIED_GROUP')
  pid=int((self.root/'linger/worker.log').read_text().strip())
  path=Path('/proc')/str(pid)/'stat'
  if path.exists():self.assertEqual(path.read_text().split(') ',1)[1].split()[0],'Z')
 def test_nonzero_child_is_not_success(self):
  record=launch.supervise([sys.executable,'-I','-S','-B','-c','raise SystemExit(7)'],os.environ.copy(),self.root/'failed',self.budget(2))
  self.assertEqual(record['status'],'FAILED_RETAINED');self.assertEqual(record['returncode'],7)
 def test_aggregate_cpu_and_wall_reserves_prevent_launch(self):
  for value in (dict(cpu_seconds=58,wall_seconds=0,rss_bytes=0),dict(cpu_seconds=0,wall_seconds=87,rss_bytes=0),dict(cpu_seconds=0,wall_seconds=0,rss_bytes=1<<30)):
   b=launch.Budget()
   with patch.object(b,'snapshot',return_value=value):
    with self.assertRaises(TimeoutError):b.allowance()
 def test_remaining_budget_is_passed_to_child(self):
  b=launch.Budget()
  with patch.object(b,'snapshot',return_value=dict(cpu_seconds=57,wall_seconds=86,rss_bytes=0)):
   self.assertEqual(b.allowance(),(1,1))
 def test_oneuse_claim_covers_all_three_once(self):
  config=self.root/'config.json';config.write_text('{}');a=launch.claim(config,2,'fixture',self.root/'out')
  self.assertEqual(json.loads(a.read_text())['orders'],[list(x) for x in s.ORDERS])
  with self.assertRaises(FileExistsError):launch.claim(config,2,'fixture',self.root/'different')
 def test_claim_rejects_M128_and_failure_stops_outer_loop(self):
  config=self.root/'config.json';config.write_text('{}')
  with self.assertRaises(ValueError):launch.claim(config,128,'fixture',self.root/'out')
  source=(HERE/'launch.py').read_text();self.assertIn("if child['status']!='EXITED':raise ValueError",source);self.assertIn("approval.get('orders')==values['arm_orders']",source)
 def test_parent_work_guard_kills_before_hard_cleanup_cap(self):
  calls=[]
  with patch.object(launch,'kill_active_if_owned',side_effect=lambda:calls.append('kill')),patch.object(launch.resource,'setrlimit',side_effect=lambda *a:calls.append('hardcap')),patch.object(launch.signal,'setitimer'),patch.object(launch.signal,'signal'):
   with self.assertRaises(TimeoutError):launch.parent_work_budget_signal(0,None)
  self.assertEqual(calls,['kill','hardcap'])
 def test_parent_fallback_guard_survives_ownership_read_failure(self):
  calls=[]
  with patch.object(launch,'kill_active_if_owned',side_effect=OSError('identity unreadable')),patch.object(launch.resource,'setrlimit',side_effect=lambda *a:calls.append('hardcap')),patch.object(launch.signal,'setitimer') as timer,patch.object(launch.signal,'signal'):
   with self.assertRaisesRegex(OSError,'identity unreadable'):launch.parent_work_budget_signal(0,None)
   timer.assert_any_call(launch.signal.ITIMER_REAL,3)
  self.assertEqual(calls,['hardcap'])
 def test_foreign_active_identity_is_never_signalled(self):
  prior=launch.ACTIVE;launch.ACTIVE=(type('Proc',(),{'pid':123,'returncode':None})(),{'fixture':'original'})
  try:
   with patch.object(launch,'identity',return_value={'fixture':'foreign'}),patch.object(launch.os,'killpg') as kill:
    launch.kill_active_if_owned();kill.assert_not_called()
  finally:launch.ACTIVE=prior
 def test_limits_are_aggregate_with_lower_per_child_maxima(self):
  self.assertEqual(s.LIMITS['cpu_seconds'],60);self.assertEqual(s.LIMITS['wall_seconds'],90)
  self.assertEqual(s.LIMITS['child_cpu_seconds']*3,54);self.assertEqual(s.LIMITS['child_wall_seconds']*3,81)
if __name__=='__main__':unittest.main(verbosity=2)
