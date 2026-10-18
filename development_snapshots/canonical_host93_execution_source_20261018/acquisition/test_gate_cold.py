"""Fixed-source projection and pure mocks; no real child, signal, network or limits."""
import argparse
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--acquisition-source',type=Path,required=True)
args,remaining=parser.parse_known_args()
raw=(HERE/'run_acquisition_gate.py').read_bytes()
if len(raw)!=11419 or hashlib.sha256(raw).hexdigest()!='875719997b99a88d9aeea82588f62ceef3424c7301f3eaaa4fcb2f5b239b0120':
    raise ValueError('gate source changed before execution')
gate=types.ModuleType('gate_source_candidate');gate.__file__=str(HERE/'run_acquisition_gate.py')
exec(compile(raw,gate.__file__,'exec',dont_inherit=True),gate.__dict__)
plan,frozen,projected,identities=gate.preflight(args.repo,args.acquisition_source)
runner=types.SimpleNamespace(**gate.supervisor(projected))
test_raw=(args.repo/'development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py').read_bytes()
if len(test_raw)!=18004 or hashlib.sha256(test_raw).hexdigest()!='fc88db7e72d64fca1603de193940e7b95e9030f90dc3eb0e574cec9d5b40ff46':
    raise ValueError('published mock source changed')
tree=ast.parse(test_raw)
classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='FakeOS']
if len(classes)!=1:raise ValueError('fixed FakeOS projection')
namespace={'contextlib':contextlib,'types':types,'runner':runner,'signal':signal,'mock':mock}
exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),
             'published_FakeOS_only','exec',dont_inherit=True),namespace)
FakeOS=namespace['FakeOS']


class GateCold(unittest.TestCase):
    def test_01_exact_source_and_budget_projection(self):
        self.assertEqual(tuple(identities),gate.FUNCTIONS)
        self.assertEqual(set(frozen),{'acquire.py','plans/jar87.json','plans/hardfloat20.json'})
        for group,total,work in [('jar87',1200,1190),('hardfloat20',300,290)]:
            b=plan['groups'][group]
            self.assertEqual((b['total_wall_seconds'],b['work_deadline_offset_seconds']),(total,work))
            self.assertEqual(work+b['cleanup_seconds']+b['postflight_reserve_seconds'],total)
        text=projected.decode()
        self.assertIn('env=None)',text)
        self.assertIn('os.WNOWAIT',text)
        self.assertIn('signal.setitimer(signal.ITIMER_REAL, 0)',text)
        self.assertIn('os.sched_setaffinity(0, {min(allowed)})',text)
        self.assertEqual(runner.AS_LIMIT if hasattr(runner,'AS_LIMIT') else 0,512*1024*1024)

    def scenario(self,mode,exception):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);fake=FakeOS(mode)
            with fake.patches(),mock.patch.object(runner.signal,'setitimer'):
                if exception:
                    with self.assertRaises(exception):runner.bounded('acquire',['mock-python'],out,out,10,10)
                else:runner.bounded('acquire',['mock-python'],out,out,10,10)
            record=json.loads((out/'acquire.json').read_text())
            self.assertEqual(record['status'],'FAIL' if exception else 'PASS')
            if mode=='spawn_fail':
                self.assertFalse(record['spawn_handle_acquired']);self.assertEqual(fake.calls,[])
            else:
                self.assertTrue(record['anchor_confirmed'])
                self.assertEqual(fake.calls.count((424242,signal.SIGKILL)),1)
                self.assertEqual(record['cleanup_confirmed'],mode!='reap_unknown')
            return record

    def test_02_original_success_kills_before_reap(self):
        record=self.scenario('pass',None)
        self.assertEqual(record['exit_code'],0)
        self.assertEqual(record['group_state'],'absent')

    def test_03_original_finite_failure_cleanup_cases(self):
        for mode,error in [('timeout',runner.subprocess.TimeoutExpired),('interrupt',KeyboardInterrupt),
                           ('other_exception',RuntimeError),('reap_unknown',runner.subprocess.TimeoutExpired),
                           ('spawn_fail',OSError),('compiler_fail',ValueError)]:
            with self.subTest(mode=mode):self.scenario(mode,error)

    def test_04_child_policy_defaults_and_limits_are_mocked(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);fake=FakeOS('pass');seen=[]
            def spawn(command,**kwargs):
                self.assertIsNone(kwargs['env'])
                self.assertTrue(kwargs['start_new_session'])
                with mock.patch.object(runner.resource,'setrlimit') as limits, \
                     mock.patch.object(runner.os,'sched_getaffinity',return_value={7,9}), \
                     mock.patch.object(runner.os,'sched_setaffinity') as affinity:
                    kwargs['preexec_fn']()
                    seen.extend(limits.call_args_list)
                    affinity.assert_called_once_with(0,{7})
                return fake.spawn(command,**kwargs)
            with fake.patches(),mock.patch.object(runner.subprocess,'Popen',side_effect=spawn), \
                 mock.patch.object(runner.signal,'setitimer'):
                runner.bounded('acquire',['mock-python'],out,out,10,10)
            self.assertIn(mock.call(runner.resource.RLIMIT_AS,(536870912,536870912)),seen)
            self.assertIn(mock.call(runner.resource.RLIMIT_FSIZE,(67108864,67108864)),seen)

    def test_05_blocked_or_existing_alarm_refused_unchanged(self):
        for blocked,timer in [({signal.SIGALRM},(0.0,0.0)),(set(),(4.0,0.0))]:
            with mock.patch.object(gate.signal,'pthread_sigmask',return_value=blocked) as mask, \
                 mock.patch.object(gate.signal,'getitimer',return_value=timer), \
                 mock.patch.object(gate.signal,'setitimer') as setter:
                with self.assertRaises(ValueError):gate.alarm_available()
                mask.assert_called_once_with(signal.SIG_BLOCK,[]);setter.assert_not_called()

    def test_06_shared_deadline_never_restarts_total(self):
        with mock.patch.object(gate.time,'monotonic',return_value=1197),mock.patch.object(gate.signal,'setitimer') as setter:
            gate.arm(1200);setter.assert_called_once_with(signal.ITIMER_REAL,3)
        with mock.patch.object(gate.time,'monotonic',return_value=1200),mock.patch.object(gate.signal,'setitimer') as setter:
            with self.assertRaises(ValueError):gate.arm(1200)
            setter.assert_not_called()

    def test_07_acquisition_receipt_exact_identity_and_scope(self):
        selected=json.loads(frozen['plans/hardfloat20.json'])
        rows=[{'relative_destination':p['relative_destination'],'sha256':p['sha256'],
               'origin_url':p['url'],'transport':selected['transport'],'size_bytes':p['known_size_bytes']}
              for p in selected['artifacts']]
        receipt={'status':'VERIFIED_OPAQUE_BYTES_ONLY','group':'hardfloat20','artifacts':rows,
                 'received_bytes':149157,'extracted':False,'installed':False,'executed':False,
                 'host_compilation_or_rtl_evidence':False}
        gate.receipt_matches(receipt,selected)
        for key in ('extracted','installed','executed','host_compilation_or_rtl_evidence'):
            with self.assertRaises(ValueError):gate.receipt_matches(dict(receipt,**{key:True}),selected)
        with self.assertRaises(ValueError):gate.receipt_matches(dict(receipt,received_bytes=0),selected)
        changed=json.loads(json.dumps(receipt));changed['artifacts'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):gate.receipt_matches(changed,selected)

    def test_08_default_main_never_arms_timer_or_spawns(self):
        argv=['gate','--repo',str(args.repo),'--acquisition-source',str(args.acquisition_source),'--group','jar87']
        with mock.patch.object(sys,'argv',argv),mock.patch.object(gate.subprocess,'Popen',side_effect=AssertionError('spawn')), \
             mock.patch.object(gate.signal,'setitimer',side_effect=AssertionError('timer')),contextlib.redirect_stdout(io.StringIO()) as out:
            gate.main()
        self.assertFalse(json.loads(out.getvalue())['child_started'])

    def test_09_nonreviewed_supervisor_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'source.py';path.write_bytes(b'not approved')
            with self.assertRaises(ValueError):gate.checked(path,{'bytes':12,'sha256':'0'*64})

    def test_10_outer_gate_uses_remaining_shared_budget_with_mock_child(self):
        selected=json.loads(frozen['plans/hardfloat20.json'])
        rows=[{'relative_destination':p['relative_destination'],'sha256':p['sha256'],
               'origin_url':p['url'],'transport':selected['transport'],'size_bytes':p['known_size_bytes']}
              for p in selected['artifacts']]
        receipt={'status':'VERIFIED_OPAQUE_BYTES_ONLY','group':'hardfloat20','artifacts':rows,
                 'received_bytes':149157,'extracted':False,'installed':False,'executed':False,
                 'host_compilation_or_rtl_evidence':False}
        seen=[]
        def fake_bounded(label,command,directory,output,wall,cpu):
            seen.append((wall,cpu,command))
            (output/'artifacts').mkdir()
            (output/'artifacts'/'ACQUISITION.json').write_text(json.dumps(receipt))
            return {'cleanup_confirmed':True},b''
        with tempfile.TemporaryDirectory() as t, \
             mock.patch.object(gate.signal,'pthread_sigmask',return_value=set()), \
             mock.patch.object(gate.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(gate.signal,'signal'),mock.patch.object(gate.signal,'setitimer') as timer, \
             mock.patch.object(gate.time,'monotonic',return_value=5), \
             mock.patch.object(gate,'supervisor',return_value={'bounded':fake_bounded,'save':runner.save}):
            result=gate.execute('hardfloat20',args.repo,args.acquisition_source,Path(t)/'attempt',0)
        self.assertEqual(seen[0][:2],(285,290))
        self.assertEqual(timer.call_args_list,[mock.call(signal.ITIMER_REAL,285),
                                              mock.call(signal.ITIMER_REAL,295),mock.call(signal.ITIMER_REAL,0)])
        self.assertEqual(result['status'],'EVIDENCE_PENDING_OUTER_EXIT0')
        self.assertFalse(result['terminal_success'])
        self.assertFalse(result['packages_executed'])

    def test_11_expired_total_budget_cannot_publish_pass(self):
        now=[5]
        def failed_child(*_args):
            now[0]=301
            raise TimeoutError('synthetic late cleanup')
        with tempfile.TemporaryDirectory() as t, \
             mock.patch.object(gate.signal,'pthread_sigmask',return_value=set()), \
             mock.patch.object(gate.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(gate.signal,'signal'),mock.patch.object(gate.signal,'setitimer'), \
             mock.patch.object(gate.time,'monotonic',side_effect=lambda:now[0]), \
             mock.patch.object(gate,'supervisor',return_value={'bounded':failed_child,'save':runner.save}):
            output=Path(t)/'attempt'
            with self.assertRaisesRegex(ValueError,'deadline exhausted'):
                gate.execute('hardfloat20',args.repo,args.acquisition_source,output,0)
            self.assertFalse((output/'RESULT.json').exists())



    def final_commit_case(self,throw_after_commit):
        # The independent review's two exact save-after-replace counterexamples.
        selected=json.loads(frozen['plans/hardfloat20.json'])
        receipt={'status':'VERIFIED_OPAQUE_BYTES_ONLY','group':'hardfloat20',
            'artifacts':[{'relative_destination':x['relative_destination'],'sha256':x['sha256'],
                          'origin_url':x['url'],'transport':selected['transport'],
                          'size_bytes':x['known_size_bytes']} for x in selected['artifacts']],
            'received_bytes':149157,'extracted':False,'installed':False,'executed':False,
            'host_compilation_or_rtl_evidence':False}
        now=[5.0]
        def fake_bounded(label,command,directory,output,wall,cpu):
            (output/'artifacts').mkdir()
            (output/'artifacts'/'ACQUISITION.json').write_text(json.dumps(receipt))
            return {'cleanup_confirmed':True},b''
        def fake_save(path,value):
            runner.save(path,value)
            if path.name=='RESULT.json' and value['status']=='EVIDENCE_PENDING_OUTER_EXIT0':
                now[0]=301.0
                if throw_after_commit:
                    raise TimeoutError('synthetic deadline delivered after atomic replace')
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(gate.signal,'pthread_sigmask',return_value=set()), \
             mock.patch.object(gate.signal,'getitimer',return_value=(0.0,0.0)), \
             mock.patch.object(gate.signal,'signal'),mock.patch.object(gate.signal,'setitimer'), \
             mock.patch.object(gate.time,'monotonic',side_effect=lambda:now[0]), \
             mock.patch.object(gate,'supervisor',return_value={'bounded':fake_bounded,'save':fake_save}):
            output=Path(tmp)/'attempt'
            with self.assertRaises(TimeoutError if throw_after_commit else ValueError):
                gate.execute('hardfloat20',args.repo,args.acquisition_source,output,0)
            saved=json.loads((output/'RESULT.json').read_bytes())
            self.assertEqual(saved['status'],'EVIDENCE_PENDING_OUTER_EXIT0')
            self.assertFalse(saved['terminal_success'])
            self.assertIn('independent outer exit0',saved['acceptance_requires'])
            self.assertEqual(now[0],301.0)

    def test_12_late_final_save_cannot_return_success(self):
        self.final_commit_case(False)

    def test_13_post_commit_interrupt_cannot_leave_success(self):
        self.final_commit_case(True)


if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use -I -S -B')
    unittest.main(argv=[sys.argv[0]]+remaining,verbosity=2)
