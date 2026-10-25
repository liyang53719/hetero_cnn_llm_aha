"""Mandatory direct-helper reuse tests; do not fork/simplify the lease sandbox.

Run the unchanged original test_service_trace and test_resource_faults suites
alongside this file. Monitor below inherits the original fixture unchanged;
only the four additional local event names/bits are supplied.
"""
import argparse,ast,hashlib,importlib.util,os,resource,signal,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS,(1<<30,)*2);resource.setrlimit(resource.RLIMIT_CPU,(30,30));signal.alarm(45)
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--lease-source',type=Path,required=True);parser.add_argument('--lease-sha',required=True);parser.add_argument('--reviewed-tests-root',type=Path,required=True)
args,remaining=parser.parse_known_args()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
p=load('cost_probe',HERE/'cost_probe.py')
LEASE=p.load_reviewed_lease(dict(monitor_lease_source=str(args.lease_source),files={str(args.lease_source):dict(bytes=args.lease_source.stat().st_size,sha256=args.lease_sha)}))
original=load('_reviewed_original_lease_fixture',args.reviewed_tests_root/'test_service_trace.py')
class Monitor(original.Monitor):
 events=types.SimpleNamespace(PY_START=1,PY_RESUME=2,PY_RETURN=4,PY_YIELD=8,LINE=16)
class LeaseControls(unittest.TestCase):
 def setUp(self):
  self.mon=Monitor();self.patch=patch.object(sys,'monitoring',self.mon);self.patch.start()
  self.code=(lambda:17).__code__;self.q=p.SelectiveProbe({self.code:'mock'},lease=LEASE)
 def tearDown(self):self.patch.stop()
 def test_direct_helper_and_fixture_source_identity(self):
  self.assertEqual(hashlib.sha256(Path(LEASE.__file__).read_bytes()).hexdigest(),args.lease_sha)
  for name in ('monitoring_enter','monitoring_stop','capture_error'):
   self.assertEqual(getattr(LEASE,name).__code__,getattr(original.subject,name).__code__)
  self.assertEqual(Monitor.__mro__[1],original.Monitor)
  tree=ast.parse((HERE/'cost_probe.py').read_text())
  self.assertFalse(any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('monitoring_enter','monitoring_stop') for n in ast.walk(tree)))
 def test_foreign_busy_lease_is_untouched(self):
  self.mon.slots[2]='foreign';before=dict(self.mon.slots)
  with self.assertRaisesRegex(ValueError,'busy'):self.q.__enter__()
  self.assertEqual(self.mon.slots,before);self.assertEqual(self.mon.calls,[])
 def test_free_slot_stale_callback_is_restored(self):
  foreign=lambda *a:None;self.mon.callbacks[(2,4)]=foreign
  with self.assertRaisesRegex(ValueError,'stale'):self.q.__enter__()
  self.assertIs(self.mon.callbacks[(2,4)],foreign);self.assertEqual(self.mon.slots,{})
  self.assertIsNotNone(self.q.error)
 def test_free_slot_stale_local_masks_are_untouched(self):
  self.mon.locals[(2,self.code)]=16;before=dict(self.mon.locals)
  with self.assertRaisesRegex(ValueError,'retains'):self.q.__enter__()
  self.assertEqual(self.mon.locals,before);self.assertEqual(self.mon.calls,[])
 def test_foreign_replacement_lease_preserved(self):
  self.q.__enter__();self.mon.slots[2]='replacement';before=len(self.mon.calls)
  self.q.stop();self.assertEqual(self.mon.slots[2],'replacement');self.assertEqual(len(self.mon.calls),before)
  self.assertIn('foreign monitor lease',self.q.error)
 def test_foreign_callback_under_same_lease_preserved(self):
  self.q.__enter__();foreign=lambda *a:None;self.mon.callbacks[(2,4)]=foreign
  local=dict(self.mon.locals);self.q.stop()
  self.assertIs(self.mon.callbacks[(2,4)],foreign);self.assertEqual(local,self.mon.locals)
  self.assertIsNotNone(self.q.tool);self.assertIn('foreign monitor callback',self.q.error)
 def test_foreign_global_or_local_masks_preserved(self):
  for kind in ('global','local'):
   mon=Monitor()
   with patch.object(sys,'monitoring',mon):
    q=p.SelectiveProbe({self.code:'mock'},lease=LEASE);q.__enter__()
    if kind=='global':mon.globals[2]=16
    else:mon.locals[(2,self.code)]=16
    before=(dict(mon.globals),dict(mon.locals),dict(mon.callbacks))
    q.stop();self.assertEqual(before,(mon.globals,mon.locals,mon.callbacks))
    self.assertIn('foreign monitor masks',q.error)
 def test_partial_callback_registration_failure_sticky_once(self):
  self.mon.fail='register'
  with self.assertRaisesRegex(OSError,'registration'):self.q.__enter__()
  self.assertIn('registration',self.q.error);self.assertIsNotNone(self.q.cleanup_error)
  calls=len(self.mon.calls);self.mon.fail=None;self.q.stop();self.assertEqual(len(self.mon.calls),calls)
 def test_partial_local_install_failure_cleans_only_own_registration(self):
  self.mon.fail='local'
  with self.assertRaisesRegex(OSError,'local'):self.q.__enter__()
  self.assertTrue(self.q.closed);self.assertIsNone(self.q.tool);self.assertEqual(self.mon.slots,{})
  self.assertTrue(all(v is None for v in self.mon.callbacks.values()))
 def test_free_slot_stale_global_mask_blocks_without_mutation(self):
  self.mon.globals[2]=16
  with self.assertRaisesRegex(ValueError,'busy'):self.q.__enter__()
  self.assertEqual(self.mon.globals,{2:16});self.assertEqual(self.mon.calls,[])
 def test_uncertain_use_tool_claim_is_resolved_before_cleanup(self):
  real=self.mon.use_tool_id;error=SystemExit('after claim')
  def uncertain(slot,label):real(slot,label);raise error
  with patch.object(self.mon,'use_tool_id',side_effect=uncertain):
   try:self.q.__enter__()
   except BaseException as actual:self.assertIs(actual,error)
   else:self.fail('claim fault lost')
  self.assertEqual(self.mon.slots,{});self.assertIsNone(self.q.tool)
 def test_uncertain_registration_after_success_cleans_owned_callback(self):
  real=self.mon.register_callback;failed=[]
  def uncertain(slot,event,callback):
   old=real(slot,event,callback)
   if callback is not None and not failed:failed.append(True);raise SystemExit('after register')
   return old
  with patch.object(self.mon,'register_callback',side_effect=uncertain):
   with self.assertRaisesRegex(SystemExit,'after register'):self.q.__enter__()
  self.assertEqual(self.mon.slots,{});self.assertIsNone(self.q.tool)
  self.assertTrue(all(value is None for value in self.mon.callbacks.values()))
 def test_uncertain_local_mask_after_success_cleans_owned_mask(self):
  real=self.mon.set_local_events;failed=[]
  def uncertain(slot,code,mask):
   real(slot,code,mask)
   if mask and not failed:failed.append(True);raise SystemExit('after local')
  with patch.object(self.mon,'set_local_events',side_effect=uncertain):
   with self.assertRaisesRegex(SystemExit,'after local'):self.q.__enter__()
  self.assertEqual(self.mon.slots,{});self.assertIsNone(self.q.tool)
  self.assertTrue(all(value==0 for value in self.mon.locals.values()))
 def test_default_cleanup_clears_owned_only(self):
  self.mon.slots[3]='foreign';self.q.__enter__();self.q.stop()
  self.assertIsNone(self.q.error);self.assertEqual(self.mon.slots,{3:'foreign'})
  self.assertTrue(all(v==0 for v in self.mon.locals.values()));self.assertIsNone(self.q.tool)
 def test_uncertain_cleanup_is_not_retried(self):
  self.q.__enter__();self.mon.fail='local';self.q.stop();self.assertTrue(self.q.cleanup_error)
  before=len(self.mon.calls);self.mon.fail=None;self.q.stop();self.assertEqual(len(self.mon.calls),before)
  self.assertIsNotNone(self.q.tool)
 def test_original_task_exceptions_survive_all_cleanup_errors(self):
  for task_type in (RuntimeError,SystemExit,KeyboardInterrupt):
   for cleanup_type in (OSError,SystemExit,KeyboardInterrupt):
    q=p.SelectiveProbe({self.code:'mock'},lease=LEASE);q.__enter__();task=task_type('original');cleanup=cleanup_type('cleanup')
    with patch.object(LEASE,'monitoring_stop',side_effect=cleanup):
     try:
      try:raise task
      except BaseException:q.__exit__(*sys.exc_info());raise
     except BaseException as actual:self.assertIs(actual,task)
    self.assertIn(cleanup_type.__name__,q.cleanup_error)
    LEASE.monitoring_stop(q,tuple(getattr(self.mon.events,n) for n in q.EVENTS),q.codes)
 def test_successful_task_survives_cleanup_systemexit(self):
  self.q.__enter__()
  with patch.object(self.mon,'get_tool',side_effect=SystemExit('cleanup')):
   self.assertFalse(self.q.__exit__(None,None,None))
  self.assertIn('SystemExit',self.q.error);self.assertTrue(self.q.closed)
 def test_cleanup_keyboardinterrupt_without_original_remains_cancel(self):
  self.q.__enter__();cancel=KeyboardInterrupt('user cancel')
  with patch.object(self.mon,'get_tool',side_effect=cancel):
   try:self.q.__exit__(None,None,None)
   except BaseException as actual:self.assertIs(actual,cancel)
   else:self.fail('user cancellation lost')
 def test_setup_original_error_not_replaced_by_cleanup_cancel(self):
  original=SystemExit('setup');cleanup=KeyboardInterrupt('cleanup')
  with patch.object(LEASE,'monitoring_enter',side_effect=original),patch.object(LEASE,'monitoring_stop',side_effect=cleanup):
   try:self.q.__enter__()
   except BaseException as actual:self.assertIs(actual,original)
   else:self.fail('setup original lost')
  self.assertIn('SystemExit',self.q.error);self.assertIn('KeyboardInterrupt',self.q.cleanup_error)
 def test_callback_systemexit_is_sticky_not_task_exception(self):
  self.q.__enter__();frame=types.SimpleNamespace(f_locals={})
  with patch.object(p.time,'process_time_ns',side_effect=SystemExit('instrumentation')):
   self.assertIsNone(self.q.event(self.code,frame,'starts'))
  self.assertIn('SystemExit',self.q.error);self.assertIsNone(self.q.tool)
 def test_callback_user_keyboardinterrupt_keeps_identity(self):
  self.q.__enter__();cancel=KeyboardInterrupt('user cancel');frame=types.SimpleNamespace(f_locals={})
  with patch.object(p.time,'process_time_ns',side_effect=cancel):
   try:self.q.event(self.code,frame,'starts')
   except BaseException as actual:self.assertIs(actual,cancel)
   else:self.fail('user cancellation lost')
  self.assertIsNone(self.q.tool)
 def test_callback_error_and_cleanup_error_are_both_retained(self):
  self.q.__enter__();self.q.max_callbacks=0
  with patch.object(self.mon,'get_tool',side_effect=SystemExit('cleanup')):
   self.assertIsNone(self.q.event(self.code,types.SimpleNamespace(f_locals={}), 'starts'))
  self.assertIn('bounded',self.q.error);self.assertIn('SystemExit',self.q.cleanup_error)
  with self.assertRaisesRegex(ValueError,'incomplete'):self.q.seal({})
if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+remaining)
