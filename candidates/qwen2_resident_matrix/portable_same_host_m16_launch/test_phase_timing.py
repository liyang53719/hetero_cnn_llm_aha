"""Stdlib-only diagnostic boundaries; no packages, native code, or model work."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('timing_parent_tested',HERE/'run.py')
R=importlib.util.module_from_spec(spec)
exec(compile((HERE/'run.py').read_bytes(),str(HERE/'run.py'),'exec'),R.__dict__)
KEYS={'schema','diagnostic_only','acceptance','scope','status','reason','wall_seconds',
      'reaped_children_user_cpu_seconds','reaped_children_system_cpu_seconds'}
MEASURES=('wall_seconds','reaped_children_user_cpu_seconds','reaped_children_system_cpu_seconds')


class Snapshots(unittest.TestCase):
    def event(self): return dict(observed_exit_code=0,owned_group_cleanup_complete=True)
    def test_no_numerical_imports(self):
        self.assertFalse(set(('torch','numpy','ctypes','transformers','safetensors')) & sys.modules.keys())
    def test_strict_finite_nonnegative_bounded_scalars(self):
        for value in (None,True,False,'1',-1,float('nan'),float('inf'),-float('inf'),2**53+1,10**400):
            with self.subTest(value=str(value)): self.assertFalse(R.timing_seconds(value))
        for value in (0,0.0,.125,2**53): self.assertTrue(R.timing_seconds(value))
    def test_rusage_children_seconds_without_conversion(self):
        usage=SimpleNamespace(ru_utime=2.25,ru_stime=.125)
        with mock.patch.object(R.time,'monotonic',return_value=100.5),mock.patch.object(R.resource,'getrusage',return_value=usage) as get:
            self.assertEqual(R.phase_snapshot(),(100.5,2.25,.125))
        get.assert_called_once_with(R.resource.RUSAGE_CHILDREN)
    def test_unavailable_and_invalid_snapshot(self):
        for error in (OSError('no resource'),ValueError('invalid'),AttributeError('missing')):
            with mock.patch.object(R.resource,'getrusage',side_effect=error):self.assertIsNone(R.phase_snapshot())
        for bad in (True,-1,float('nan'),float('inf'),2**53+1):
            for key in ('ru_utime','ru_stime'):
                usage=SimpleNamespace(ru_utime=1.0,ru_stime=1.0);setattr(usage,key,bad)
                with self.subTest(key=key,bad=bad),mock.patch.object(R.resource,'getrusage',return_value=usage):
                    self.assertIsNone(R.phase_snapshot())
            with mock.patch.object(R.time,'monotonic',return_value=bad):self.assertIsNone(R.phase_snapshot())
    def test_snapshot_does_not_swallow_timeout(self):
        timeout=TimeoutError('global deadline')
        with mock.patch.object(R.resource,'getrusage',side_effect=timeout),self.assertRaises(TimeoutError) as caught:
            R.phase_snapshot()
        self.assertIs(caught.exception,timeout)
    def test_exact_diagnostic_schema_and_units(self):
        with mock.patch.object(R,'phase_snapshot',return_value=(15.75,7.25,3.5)):
            value=R.phase_timing((10.0,3.0,1.0),self.event())
        self.assertEqual(set(value),KEYS);self.assertIs(value['diagnostic_only'],True);self.assertIs(value['acceptance'],False)
        self.assertEqual(value['schema'],1);self.assertEqual(value['scope'],'PARENT_RUSAGE_CHILDREN_DELTA')
        self.assertEqual(value['status'],'AVAILABLE');self.assertIsNone(value['reason'])
        self.assertEqual(tuple(value[k] for k in MEASURES),(5.75,4.25,2.5))
        self.assertEqual(json.loads(R.encoded(value)),value)
    def test_observed_exit_and_cleanup_fences(self):
        for key,bad,reason in (('observed_exit_code',None,'EXIT_UNOBSERVED'),('observed_exit_code',False,'EXIT_UNOBSERVED'),
            ('owned_group_cleanup_complete',False,'CLEANUP_INCOMPLETE'),('owned_group_cleanup_complete',1,'CLEANUP_INCOMPLETE')):
            event=self.event();event[key]=bad
            with self.subTest(key=key,bad=bad),mock.patch.object(R,'phase_snapshot') as get:
                value=R.phase_timing((1.0,1.0,1.0),event)
            get.assert_not_called();self.assertEqual(value['reason'],reason)
            self.assertEqual(set(value),KEYS);self.assertTrue(all(value[k] is None for k in MEASURES))
    def test_invalid_snapshot_shapes_and_types(self):
        for bad in (None,(),(1,2),(1,2,3,4),[1,2,3],(True,1,1),(1,float('inf'),1),(1,1,-1)):
            with self.subTest(bad=bad),mock.patch.object(R,'phase_snapshot',return_value=bad):
                self.assertEqual(R.phase_timing((1,1,1),self.event())['status'],'UNAVAILABLE')
                self.assertEqual(R.phase_timing(bad,self.event())['status'],'UNAVAILABLE')
    def test_negative_delta_unavailable_without_clamping(self):
        for after in ((.5,1,1),(1,.5,1),(1,1,.5)):
            with mock.patch.object(R,'phase_snapshot',return_value=after):value=R.phase_timing((1,1,1),self.event())
            self.assertEqual(value['reason'],'INVALID_DELTA');self.assertTrue(all(value[k] is None for k in MEASURES))
    def test_zero_delta_available(self):
        with mock.patch.object(R,'phase_snapshot',return_value=(1.0,1.0,1.0)):
            value=R.phase_timing((1.0,1.0,1.0),self.event())
        self.assertEqual(value['status'],'AVAILABLE');self.assertEqual(tuple(value[k] for k in MEASURES),(0,0,0))


class OwnedBoundaries(unittest.TestCase):
    def run_phase(self,code=0,observe_error=None,cleanup_error=None,cleaned=True,snapshot_error=None,at_start=False,expired=False):
        calls=[];process=SimpleNamespace(pid=123,returncode=None)
        def spawn(owner,*args,**kwargs):calls.append('spawn');owner.update(process=process,identity={'pid':123})
        def observe(*args):
            calls.append('observe')
            if observe_error is not None:raise observe_error
            return code
        def cleanup(control,owner,deadline,*,cancel):
            calls.append(('cleanup',cancel))
            if cleanup_error is not None:raise cleanup_error
            if owner['process'] is not None:process.returncode=code if observe_error is None else -9
            return cleaned if owner['process'] is not None else False
        count=0
        def usage(which):
            nonlocal count
            self.assertEqual(which,R.resource.RUSAGE_CHILDREN)
            count+=1;calls.append('snapshot')
            if snapshot_error is not None and (at_start or count==2):raise snapshot_error
            return SimpleNamespace(ru_utime=float(count),ru_stime=float(count)/2)
        launcher=SimpleNamespace(EXEC='unused',arm=lambda stop:calls.append(('arm',stop)),finish_owned=cleanup,
            remaining=lambda stop:calls.append(('remaining',stop)))
        control=SimpleNamespace(spawn_owned=spawn,observe_exit=observe,
            arm_receipt_deadline=lambda stop:calls.append(('receipt_arm',stop)))
        journal=[];error=None
        with tempfile.TemporaryDirectory() as td,mock.patch.object(R.resource,'getrusage',side_effect=usage),\
            mock.patch.object(R.time,'monotonic',return_value=200 if expired else 0):
            try:
                R.owned_phase(launcher,control,['unused'],cwd=td,env={},log=Path(td)/'log',work_deadline=100,
                    cleanup_deadline=110,journal=journal,phase='stdlib_fixture')
            except BaseException as value:error=value
        return journal[0],error,calls
    def test_only_two_boundary_snapshots_after_reap(self):
        event,error,calls=self.run_phase()
        self.assertIsNone(error);self.assertEqual(calls,[('arm',100),'snapshot','spawn','observe',('cleanup',False),
            ('receipt_arm',110),('remaining',110),'snapshot',('remaining',110)])
        self.assertEqual(event['timing_diagnostic']['status'],'AVAILABLE');self.assertEqual(event['status'],'PASS')
        self.assertEqual(event['observed_exit_code'],0);self.assertEqual(event['final_exit_code'],0)
        self.assertIs(event['owned_group_cleanup_complete'],True)
    def test_nonzero_preserved_with_diagnostic(self):
        event,error,_=self.run_phase(code=7)
        self.assertIsInstance(error,ValueError);self.assertIn('nonzero exit',str(error))
        self.assertEqual(event['observed_exit_code'],7);self.assertEqual(event['final_exit_code'],7)
        self.assertEqual(event['status'],'FAILED');self.assertEqual(event['timing_diagnostic']['status'],'AVAILABLE')
    def test_timeout_unavailable_retains_cleanup(self):
        timeout=TimeoutError('original work deadline');event,error,calls=self.run_phase(observe_error=timeout)
        self.assertIs(error,timeout);self.assertEqual(event['status'],'TIMEOUT')
        self.assertIsNone(event['observed_exit_code']);self.assertEqual(event['final_exit_code'],137)
        self.assertIs(event['owned_group_cleanup_complete'],True);self.assertEqual(calls.count('snapshot'),1)
        self.assertEqual(event['timing_diagnostic']['reason'],'EXIT_UNOBSERVED')
    def test_cleanup_failure_preserved(self):
        original=RuntimeError('original cleanup failure');event,error,calls=self.run_phase(cleanup_error=original)
        self.assertIs(error,original);self.assertEqual(event['status'],'CLEANUP_FAILED')
        self.assertIs(event['owned_group_cleanup_complete'],False);self.assertEqual(calls.count('snapshot'),1)
        self.assertEqual(event['timing_diagnostic']['reason'],'CLEANUP_INCOMPLETE')
    def test_original_failure_survives_cleanup_failure(self):
        original=TimeoutError('original deadline')
        event,error,_=self.run_phase(observe_error=original,cleanup_error=RuntimeError('cleanup failure'))
        self.assertIs(error,original);self.assertEqual(event['status'],'CLEANUP_FAILED')
        self.assertIs(event['owned_group_cleanup_complete'],False);self.assertIs(event['observed_exit_code'],None)
    def test_false_cleanup_never_returns_success(self):
        event,error,calls=self.run_phase(cleaned=False)
        self.assertIsInstance(error,ValueError);self.assertIn('owned phase cleanup',str(error))
        self.assertIs(event['owned_group_cleanup_complete'],False);self.assertEqual(calls.count('snapshot'),1)
        self.assertEqual(event['timing_diagnostic']['reason'],'CLEANUP_INCOMPLETE')
    def test_unavailable_measurement_cannot_fail_successful_phase(self):
        for at_start in (False,True):
            event,error,_=self.run_phase(snapshot_error=OSError('measurement unavailable'),at_start=at_start)
            self.assertIsNone(error);self.assertEqual(event['status'],'PASS')
            self.assertEqual(event['timing_diagnostic']['reason'],'SNAPSHOT_UNAVAILABLE')
    def test_unavailable_measurement_cannot_replace_nonzero_failure(self):
        event,error,_=self.run_phase(code=7,snapshot_error=OSError('measurement unavailable'))
        self.assertIsInstance(error,ValueError);self.assertIn('nonzero exit',str(error))
        self.assertEqual(event['status'],'FAILED');self.assertIs(event['owned_group_cleanup_complete'],True)
        self.assertEqual(event['timing_diagnostic']['reason'],'SNAPSHOT_UNAVAILABLE')
    def test_end_snapshot_timeout_is_not_swallowed(self):
        timeout=TimeoutError('global deadline');event,error,_=self.run_phase(snapshot_error=timeout)
        self.assertIs(error,timeout);self.assertEqual(event['status'],'TIMEOUT')
        self.assertIs(event['owned_group_cleanup_complete'],True);self.assertEqual(event['timing_diagnostic']['reason'],'INTERRUPTED')
    def test_unexpected_timing_error_preserves_success(self):
        with mock.patch.object(R,'phase_timing',side_effect=ValueError('private measurement error')):
            event,error,_=self.run_phase()
        self.assertIsNone(error);self.assertEqual(event['status'],'PASS')
        self.assertEqual(event['observed_exit_code'],0);self.assertEqual(event['final_exit_code'],0)
        self.assertIs(event['owned_group_cleanup_complete'],True)
        self.assertEqual(event['timing_diagnostic']['reason'],'MEASUREMENT_UNAVAILABLE')
        self.assertIs(event['timing_diagnostic']['acceptance'],False)
        self.assertNotIn('private measurement error',R.encoded(event).decode())
    def test_unexpected_timing_error_preserves_original_failure(self):
        with mock.patch.object(R,'phase_timing',side_effect=ValueError('private measurement error')):
            event,error,_=self.run_phase(code=7)
        self.assertIsInstance(error,ValueError);self.assertIn('nonzero exit',str(error))
        self.assertEqual(event['status'],'FAILED');self.assertEqual(event['observed_exit_code'],7)
        self.assertEqual(event['final_exit_code'],7);self.assertIs(event['owned_group_cleanup_complete'],True)
        self.assertEqual(event['timing_diagnostic']['reason'],'MEASUREMENT_UNAVAILABLE')
        self.assertIs(event['timing_diagnostic']['acceptance'],False)
        self.assertNotIn('private measurement error',R.encoded(event).decode())
    def test_end_snapshot_timeout_keeps_original_failure(self):
        event,error,_=self.run_phase(code=7,snapshot_error=TimeoutError('late deadline'))
        self.assertIsInstance(error,ValueError);self.assertIn('nonzero exit',str(error))
        self.assertEqual(event['status'],'FAILED');self.assertEqual(event['observed_exit_code'],7)
        self.assertEqual(event['timing_diagnostic']['reason'],'INTERRUPTED')
    def test_start_snapshot_timeout_stops_work(self):
        timeout=TimeoutError('global deadline');event,error,calls=self.run_phase(snapshot_error=timeout,at_start=True)
        self.assertIs(error,timeout);self.assertNotIn('spawn',calls);self.assertEqual(event['status'],'TIMEOUT')
        self.assertIs(event['owned_group_cleanup_complete'],False)
    def test_expired_cleanup_deadline_skips_read_and_cannot_pass(self):
        event,error,calls=self.run_phase(expired=True)
        self.assertIsInstance(error,TimeoutError);self.assertEqual(event['status'],'TIMEOUT')
        self.assertEqual(calls.count('snapshot'),1);self.assertNotIn(('receipt_arm',110),calls)
        self.assertEqual(event['timing_diagnostic']['reason'],'DEADLINE_EXPIRED')
        self.assertIs(event['owned_group_cleanup_complete'],True)
    def test_expired_cleanup_deadline_preserves_original_failure(self):
        event,error,calls=self.run_phase(code=7,expired=True)
        self.assertIsInstance(error,ValueError);self.assertIn('nonzero exit',str(error))
        self.assertEqual(event['status'],'FAILED');self.assertEqual(calls.count('snapshot'),1)
        self.assertEqual(event['timing_diagnostic']['reason'],'DEADLINE_EXPIRED')


class AlarmLifecycle(unittest.TestCase):
    def test_actual_cleanup_then_receipt_alarm_bounds_measurement(self):
        script='''import importlib.util,json,signal,sys,time
from pathlib import Path
p=Path(sys.argv[1]);root=p.parents[3];out=Path(sys.argv[2]);code=int(sys.argv[3])
spec=importlib.util.spec_from_file_location('timed_parent',p);R=importlib.util.module_from_spec(spec)
exec(compile(p.read_bytes(),str(p),'exec'),R.__dict__)
L=R.load_launcher(root);control=L.helper(root,L.load_contract(root))
original_snapshot=R.phase_snapshot;original_finish=L.finish_owned;state={'snapshots':0};journal=[]
def finish(*args,**kwargs):
 result=original_finish(*args,**kwargs)
 state['alarm_after_cleanup']=signal.getitimer(signal.ITIMER_REAL)[0]
 return result
def snapshot():
 state['snapshots']+=1
 if state['snapshots']==2:
  state['alarm_at_measurement']=signal.getitimer(signal.ITIMER_REAL)[0]
  time.sleep(5)
 return original_snapshot()
L.finish_owned=finish;R.phase_snapshot=snapshot;started=time.monotonic();error=None
try:
 R.owned_phase(L,control,[sys.executable,'-I','-B','-c','raise SystemExit('+str(code)+')'],cwd=out,
  env={'PATH':'/usr/bin:/bin'},log=out/'log',work_deadline=started+.4,cleanup_deadline=started+.65,
  journal=journal,phase='alarm_fixture')
except BaseException as e:error={'kind':type(e).__name__,'text':str(e)}
finally:control.protect_cleanup()
state.update(error=error,event=journal[0],elapsed=time.monotonic()-started,
 alarm_after_teardown=signal.getitimer(signal.ITIMER_REAL)[0],
 alarm_handler_ignored=signal.getsignal(signal.SIGALRM)==signal.SIG_IGN)
print(json.dumps(state))
'''
        for code in (0,7):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as td:
                result=subprocess.run([sys.executable,'-I','-B',*(['-O'] if sys.flags.optimize else []),
                    '-c',script,str(HERE/'run.py'),td,str(code)],
                    capture_output=True,text=True,timeout=4)
            self.assertEqual(result.returncode,0,result.stderr);value=json.loads(result.stdout)
            self.assertEqual(value['alarm_after_cleanup'],0);self.assertGreater(value['alarm_at_measurement'],0)
            self.assertEqual(value['alarm_after_teardown'],0);self.assertIs(value['alarm_handler_ignored'],True)
            self.assertEqual(value['snapshots'],2);self.assertLess(value['elapsed'],2)
            self.assertEqual(value['error']['kind'],'TimeoutError' if code==0 else 'ValueError')
            if code:self.assertIn('nonzero exit',value['error']['text'])
            self.assertEqual(value['event']['observed_exit_code'],code)
            self.assertEqual(value['event']['final_exit_code'],code)
            self.assertIs(value['event']['owned_group_cleanup_complete'],True)
            self.assertEqual(value['event']['status'],'TIMEOUT' if code==0 else 'FAILED')
            self.assertEqual(value['event']['timing_diagnostic']['reason'],'INTERRUPTED')


if __name__=='__main__':unittest.main()
