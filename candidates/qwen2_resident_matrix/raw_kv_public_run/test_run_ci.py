"""Cold launch tests: mocked originals and tiny cleanup children, no native math."""
from contextlib import ExitStack,redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
from . import run_ci as run

COMMIT='a'*40
SOURCES={'original.py':'1'*64}
FROZEN=dict(contract_sha256='2'*64,sources=SOURCES,original_sources=SOURCES,generated={},git_blobs={})


def actual():
    stages={name:dict(metrics={'finite':True},observed_elements=1,verdict=
        dict(passed=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE') if name=='softmax_fp32' else dict(passed=True))
        for name in run.assets.shapes() if name!='mask'}
    host=dict(accepted=dict(completion_fire=21,request_fire=17,owner_result_fire=17,result_fire=1,raw_kv_parent_edges=7),
        launch_result=dict(status=None,completed=21,jobs=17),reset_required=False,
        completions=[dict(pc=i,status=None) for i in range(21)])
    return dict(status='PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES',native_acceptance='PASS_OBSERVED_ONLY',
        actual_dataflow_pass=True,full_29_node_acceptance=False,rows=16,enable_raw_kv=True,fresh_profile=True,
        old_pass_inherited=False,rtl_executed=False,scala_executed=False,source_sha256=SOURCES,source_sha256_after=SOURCES,
        comparison=dict(fixed_arithmetic_pass=True,full_29_node_acceptance=False,
            acceptance_requires_all_assigned_official_observed_node_gates=True,official_target='official_self_cache',
            methods={'official_self_cache':dict(failed_stages=[],numerical_status='PASS_OBSERVED_ONLY',stages=stages)}),
        execution=dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED',full_block_software_model_executed=True,
            same_owner_and_banks=True,same_physical_memory_and_services=True,host=host,
            reports=[dict(kind='Attention',pcs=[10,11,12],report=dict(accepted=dict(requests=10,responses=10),
                final_ack_fence=dict(terminal_strictly_after_final_ack=True,final_ack_tick=5,terminal_tick=6)))]))


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(run.assets.encoded(value))


def context(private,evidence):
    start=time.monotonic_ns()
    return dict(schema=1,private=str(private),evidence=str(evidence),checkout_commit=COMMIT,started_ns=start,
        deadline_ns=start+run.TOTAL*10**9,contract_sha256=FROZEN['contract_sha256'],source_sha256=SOURCES,
        generated_sha256={},git_blobs={'original.py':'b'*40,run.CONTRACT:'c'*40})


def complete(private,ctx,value=None):
    value=actual() if value is None else value
    write_json(private/'actual/summary.json',value)
    write_json(private/'snapshot/SNAPSHOT.json',{'source_sha256':SOURCES})
    write_json(private/'assets/SETUP.json',{'status':run.setup.SETUP_STATUS})
    result=run.validate_actual(actual(),SOURCES)
    result.update(schema=1,status=run.PASS,rows=16,enable_raw_kv=True,fresh_profile=True,
        launch_contract_sha256=ctx['contract_sha256'],setup_receipt_sha256=run.assets.file_sha(private/'assets/SETUP.json'),
        actual_receipt_sha256=run.assets.file_sha(private/'actual/summary.json'),snapshot_sha256=run.assets.file_sha(private/'snapshot/SNAPSHOT.json'),
        source_manifest_sha256=run.assets.sha(run.assets.encoded(SOURCES)),actual_source_manifest_sha256=run.assets.sha(run.assets.encoded(SOURCES)))
    write_json(private/'numeric.complete.json',result)
    return result


class LaunchTests(unittest.TestCase):
    def exercise(self,root,*,child=None,setup_result=None,check=None):
        private=root/'private';evidence=root/'safe';private.mkdir();evidence.mkdir();(private/'logs').mkdir();(private/'tmp').mkdir()
        ctx=context(private,evidence);write_json(private/'context.json',ctx);calls=[]
        def command(budget,argv,**kw):
            calls.append((argv,kw))
            if kw.get('end_ns') is not None:budget.arm(kw['end_ns']-int(run.RECEIPT*10**9))
            if child:return child(private,ctx,kw)
            complete(private,ctx);return 0
        with patch.object(run,'expected_entry_sources',return_value=SOURCES),patch.object(run,'check_context',return_value=FROZEN,side_effect=check),patch.object(run.setup,'run',return_value=setup_result or (0,{'status':run.setup.SETUP_STATUS})),patch.object(run.Budget,'command',command):
            result=run.resume(ctx,private,evidence)
        return (*result,calls,ctx,private,evidence)

    def test_one_setup_one_numeric_child_and_exact_deadlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp))
            self.assertEqual((code,summary['status']),(0,run.PASS));self.assertEqual(len(calls),1)
            argv,kw=calls[0];self.assertEqual(kw['cap'],930)
            self.assertEqual(argv[0],str(private/'assets/venv/bin/python'))
            self.assertIn('--internal-numeric',argv)
            deadline=int(kw['extra_env']['QWEN2_PUBLIC_NUMERIC_DEADLINE_NS'])
            self.assertLessEqual(deadline,ctx['deadline_ns'])
            self.assertEqual(summary['assigned_official_gates'],27)
            self.assertFalse(summary['full_29_node_acceptance'])
            self.assertNotEqual(json.loads((evidence/'progress.json').read_text())['status'],run.PASS)

    def test_setup_has_no_inherited_alarm_and_deadline_only_shortens(self):
        def setup(*args,**kw):
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
            self.assertLessEqual(kw['deadline_ns']-time.monotonic_ns(),600*10**9)
            return 1,{'status':'SETUP_TIMEOUT'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(run.setup,'run',side_effect=setup) as called:
            root=Path(tmp);private=root/'private';private.mkdir();evidence=root/'safe';evidence.mkdir();ctx=context(private,evidence)
            with patch.object(run,'check_context',return_value=FROZEN),patch.object(run.Budget,'command') as child:
                code,summary=run.resume(ctx,private,evidence)
            self.assertNotEqual(code,0);called.assert_called_once();child.assert_not_called()
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_failed_setup_never_runs_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,*_=self.exercise(Path(tmp),setup_result=(1,{'status':'SETUP_FAILED'}))
            self.assertNotEqual(code,0);self.assertFalse(calls)

    def test_child_zero_without_actual_terminal_is_not_pass(self):
        def child(private,ctx,kw):
            complete(private,ctx,{'status':run.setup.SETUP_STATUS});return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),child=child)
            self.assertNotEqual(code,0);self.assertNotEqual(summary['status'],run.PASS)

    def test_nonzero_or_timeout_child_cannot_use_complete_receipt(self):
        for error in (RuntimeError('raw=[1,2] /private https://signed'),subprocess.TimeoutExpired(['SECRET'],1)):
            def child(private,ctx,kw):complete(private,ctx);raise error
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as tmp:
                code,summary,*_=self.exercise(Path(tmp),child=child)
                self.assertNotEqual(code,0)
                for forbidden in ('SECRET','raw=','/private','https://'):self.assertNotIn(forbidden,json.dumps(summary))

    def test_public_projection_never_copies_private_actual_fields(self):
        private_text='/private/token raw_tensor=[1,2,3] https://cdn/?signature=SECRET'
        def child(private,ctx,kw):
            value=actual();value['error']=private_text;value['snapshot']=private_text;complete(private,ctx,value);return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls,ctx,private,evidence=self.exercise(Path(tmp),child=child)
            self.assertEqual(code,0)
            public=json.dumps(summary)+''.join(p.read_text() for p in evidence.iterdir())
            for forbidden in ('SECRET','raw_tensor','/private/token','https://',tmp):self.assertNotIn(forbidden,public)

    def test_source_drift_after_child_prevents_pass(self):
        calls=0
        def check(*args,**kwargs):
            nonlocal calls
            calls+=1
            return FROZEN if calls<3 else dict(FROZEN,sources={'changed.py':'f'*64})
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),check=check)
            self.assertNotEqual(code,0);self.assertNotEqual(summary['status'],run.PASS)

    def test_strict_original_receipt_negative_fields_and_host_retirement(self):
        variants=[]
        for field,bad in (('rows',True),('enable_raw_kv',1),('fresh_profile',False),('full_29_node_acceptance',True),
                          ('old_pass_inherited',True),('actual_dataflow_pass',False),('status','PASS')):
            value=actual();value[field]=bad;variants.append(value)
        value=actual();value['comparison']['methods']['official_self_cache']['stages']['q']['verdict']['passed']=False;variants.append(value)
        value=actual();value['execution']['host']['accepted']['raw_kv_parent_edges']=0;variants.append(value)
        value=actual();value['execution']['host']['accepted']['completion_fire']=20;variants.append(value)
        value=actual();value['execution']['reports'][0]['report']['final_ack_fence']['terminal_tick']=5;variants.append(value)
        value=actual();value['comparison']['fixed_arithmetic_pass']=1;variants.append(value)
        value=actual();value['execution']['host']['completions'][0]['pc']=False;variants.append(value)
        value=actual();value['execution']['reports'][0]['report']['accepted']=dict(requests=1,responses=True);variants.append(value)
        for index,value in enumerate(variants):
            with self.subTest(index=index),self.assertRaises((ValueError,KeyError)):run.validate_actual(value,SOURCES)

    def test_context_preserves_original_origin_and_rejects_future_expired_or_changed_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';evidence=root/'safe';private.mkdir();evidence.mkdir();ctx=context(private,evidence)
            path=private/'context.json';write_json(path,ctx)
            restored,_,_=run.context_read(path,run.assets.file_sha(path))
            self.assertEqual((restored['started_ns'],restored['deadline_ns']),(ctx['started_ns'],ctx['deadline_ns']))
            for kind in ('future','expired','extra_budget','bool','missing_git'):
                bad=copy.deepcopy(ctx)
                if kind=='future':bad['started_ns']=time.monotonic_ns()+10**9;bad['deadline_ns']=bad['started_ns']+run.TOTAL*10**9
                if kind=='expired':bad['deadline_ns']=time.monotonic_ns()-1;bad['started_ns']=bad['deadline_ns']-run.TOTAL*10**9
                if kind=='extra_budget':bad['deadline_ns']+=1
                if kind=='bool':bad['started_ns']=True
                if kind=='missing_git':bad['git_blobs']={}
                write_json(path,bad)
                with self.subTest(kind=kind),self.assertRaises(ValueError):run.context_read(path,run.assets.file_sha(path))

    def test_run_attempt_two_and_missing_opt_in_fail_before_bootstrap(self):
        for args,attempt in (([], '1'),(['--execute','--private','p','--evidence','s','--checkout-commit',COMMIT],'2')):
            with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':attempt}),patch.object(run,'bootstrap') as call,redirect_stdout(io.StringIO()):
                self.assertNotEqual(run.main(args),0);call.assert_not_called()

    def test_resume_checks_identity_before_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);private=root/'private';evidence=root/'safe';private.mkdir();evidence.mkdir();ctx=context(private,evidence)
            with patch.object(run,'check_context',side_effect=ValueError('different commit')),patch.object(run.setup,'run') as setup:
                code,summary=run.resume(ctx,private,evidence)
            self.assertNotEqual(code,0);setup.assert_not_called()

    def test_admission_consuming_child_deadline_prevents_original_import(self):
        from . import admission
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ctx={'deadline_ns':time.monotonic_ns()+10**9,'checkout_commit':COMMIT}
            deadline=time.monotonic_ns()+30_000_000
            def admit(*args,**kwargs):time.sleep(.05);return object()
            with patch.object(run,'check_context',return_value=FROZEN),patch.object(admission,'verify_setup',side_effect=admit),patch.object(run.importlib,'import_module') as imported:
                with self.assertRaises(TimeoutError):run.numeric(ctx,root,deadline_ns=deadline)
                imported.assert_not_called()

    def test_numeric_calls_original_prepare_run_once_with_revalidation(self):
        from . import admission
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);ctx={'deadline_ns':time.monotonic_ns()+10**9,'checkout_commit':COMMIT,'contract_sha256':FROZEN['contract_sha256']}
            identity=types.SimpleNamespace(library_receipt=private/'library.json',manifest=private/'ASSETS.json',manifest_sha256='3'*64,receipt_sha256='4'*64)
            calls=[];value=actual();snapshot={'source_sha256':SOURCES}
            def prepare(*args,**kwargs):
                calls.append(('prepare',args,kwargs));write_json(private/'snapshot/SNAPSHOT.json',snapshot);return private/'snapshot/SNAPSHOT.json',snapshot
            def execute(*args,**kwargs):
                calls.append(('run',args,kwargs));write_json(private/'actual/summary.json',value);return value
            entry=types.SimpleNamespace(prepare=prepare,run=execute,source_hashes=lambda **kw:SOURCES)
            with patch.object(run,'expected_entry_sources',return_value=SOURCES),patch.object(run,'check_context',return_value=FROZEN),patch.object(admission,'verify_setup',return_value=identity),patch.object(admission,'revalidate',side_effect=lambda x:calls.append(('revalidate',None,None))),patch.object(run.importlib,'import_module',return_value=entry):
                result=run.numeric(ctx,private,deadline_ns=ctx['deadline_ns'])
            self.assertEqual([x[0] for x in calls],['prepare','revalidate','run','revalidate'])
            self.assertEqual(calls[2][2],dict(wall_budget=900,enable_raw_kv=True,fresh_profile=True))
            self.assertEqual(calls[0][2]['rows'],16);self.assertIsNone(calls[0][1][2]);self.assertIsNone(calls[0][1][3])
            self.assertEqual(result['status'],run.PASS)

    def test_real_term_resistant_child_is_reaped_inside_same_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp);(private/'logs').mkdir();(private/'tmp').mkdir();pidfile=private/'pid'
            script='import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('+repr(str(pidfile))+').write_text(str(os.getpid()));time.sleep(30)'
            with patch.object(run,'TOTAL',1),patch.object(run,'GRACE',.1),patch.object(run,'RECEIPT',.05):
                start=time.monotonic_ns();budget=run.Budget(start,start+10**9)
                try:
                    with self.assertRaises(subprocess.TimeoutExpired):budget.command([sys.executable,'-c',script],private=private,cwd=private,phase='numeric',cap=.3)
                finally:budget.close()
            pid=int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):os.killpg(pid,0)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_numeric_postflight_cannot_escape_same_numeric_deadline(self):
        original=run.safe_numeric_receipt
        for kind in ('receipt','source'):
            checks=0
            def check(*args,**kwargs):
                nonlocal checks
                checks+=1
                if kind=='source' and checks==3:time.sleep(.5)
                return FROZEN
            def slow(*args,**kwargs):
                if kind=='receipt':time.sleep(.5)
                return original(*args,**kwargs)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp,patch.object(run,'NUMERIC_BUDGET',.18),patch.object(run,'GRACE',.03),patch.object(run,'RECEIPT',.02),patch.object(run,'safe_numeric_receipt',side_effect=slow):
                start=time.monotonic();code,summary,*_=self.exercise(Path(tmp),check=check)
                self.assertEqual((code,summary['status']),(1,'TIMEOUT'))
                self.assertLess(time.monotonic()-start,.45)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_setup_diagnostic_projection_keeps_cause_without_private_extra_fields(self):
        value=dict(status='SETUP_FAILED',phase='acquisition',reason='phase_failed',
            diagnostic=dict(phase='acquisition',exception='ValueError',frames=[dict(source='original.py',line=7)]),
            error='/private/path https://signed raw_tensor=[1,2]')
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),setup_result=(1,value))
            self.assertEqual(code,1);self.assertEqual(summary['setup_phase'],'acquisition')
            self.assertEqual(summary['diagnostic']['exception'],'ValueError')
            self.assertNotIn('/private/path',json.dumps(summary))
        bad=copy.deepcopy(value);bad['diagnostic']['payload']='SECRET'
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),setup_result=(1,bad))
            self.assertEqual(code,1);self.assertNotIn('SECRET',json.dumps(summary))

    def test_numeric_failure_diagnostic_is_bounded_and_allowlisted(self):
        for malicious in (False,True):
            def child(private,ctx,kw):
                value=dict(phase='numeric',exception='ValueError',frames=[dict(source='original.py',line=8)])
                if malicious:value.update(error='/private SECRET',payload=[1,2])
                write_json(private/'numeric.failure.json',value)
                error=RuntimeError('PRIVATE RAW');error.exit_code=1;raise error
            with self.subTest(malicious=malicious),tempfile.TemporaryDirectory() as tmp:
                code,summary,*_=self.exercise(Path(tmp),child=child)
                self.assertEqual(code,1);self.assertEqual(summary['diagnostic']['exit_code'],1)
                self.assertEqual(summary['diagnostic']['exception'],'RuntimeError' if malicious else 'ValueError')
                for text in ('PRIVATE','SECRET','/private','payload'):self.assertNotIn(text,json.dumps(summary))

    def test_mutually_forged_empty_actual_source_maps_are_rejected(self):
        def child(private,ctx,kw):
            result=complete(private,ctx)
            value=actual();value['source_sha256']={};value['source_sha256_after']={}
            write_json(private/'actual/summary.json',value);write_json(private/'snapshot/SNAPSHOT.json',{'source_sha256':{}})
            result.update(actual_receipt_sha256=run.assets.file_sha(private/'actual/summary.json'),
                snapshot_sha256=run.assets.file_sha(private/'snapshot/SNAPSHOT.json'),
                actual_source_manifest_sha256=run.assets.sha(run.assets.encoded({})))
            write_json(private/'numeric.complete.json',result);return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,*_=self.exercise(Path(tmp),child=child)
            self.assertNotEqual(code,0);self.assertNotEqual(summary['status'],run.PASS)

    def test_contract_and_git_blob_bind_exact_same_parsed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=['base%d.py'%i for i in range(8)];names=base+list(run.OWN);sources={}
            for name in names:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
                sources[name]=run.assets.file_sha(path)
            generated={name:'f'*64 for name in base}
            pins=dict(source_paths=base,generated_sha256={'enabled':generated})
            value=dict(schema=1,profile=run.PROFILE,base_setup_commit=run.BASE_SETUP_COMMIT,rows=16,past_tokens=0,
                enable_raw_kv=True,setup_budget=600,numeric_budget=930,numeric_wall_budget=900,total_budget=1680,
                source_sha256=sources,generated_sha256=generated)
            path=root/run.CONTRACT;write_json(path,value);raw=path.read_bytes();parse=run.assets.json_bytes
            def mutate(data,**kwargs):
                result=parse(data,**kwargs);path.write_bytes(b'{}');return result
            with patch.object(run,'ROOT',root),patch.object(run,'BASE_SETUP_SHA256',{}),patch.object(run.setup,'BASE_VERIFIER_SHA256',{}),patch.object(run,'IMPORTED_SHA256',sources[run.OWN[0]]),patch.object(run.assets,'read_json',return_value=pins),patch.object(run.assets,'json_bytes',side_effect=mutate):
                result=run.contract_snapshot()
            self.assertEqual(result['contract_sha256'],run.assets.sha(raw))
            self.assertEqual(result['git_blobs'][run.CONTRACT],run.hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())
            self.assertNotEqual(result['contract_sha256'],run.assets.file_sha(path))

    def test_bootstrap_clone_and_reexec_preserve_origin_without_global_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);commands=[]
            def command(budget,argv,**kw):commands.append((argv,kw));return 0
            with patch.object(run,'contract_snapshot',return_value=FROZEN),patch.object(run,'git_identity'),patch.object(run.Budget,'command',command),patch.object(run.os,'chdir') as chdir,patch.object(run.os,'execve',side_effect=RuntimeError('test intercepted exec')) as execve:
                code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
            self.assertEqual(code,1)
            self.assertEqual(commands[0][0][:4],['git','clone','--no-local','--no-checkout'])
            self.assertEqual(commands[1][0][-2:],['--detach',COMMIT])
            self.assertIn('--internal-compose',commands[2][0])
            ctx=json.loads((root/'private/context.json').read_text())
            self.assertEqual(ctx['deadline_ns']-ctx['started_ns'],1680*10**9)
            self.assertIn('--resume',execve.call_args.args[1])
            self.assertEqual(execve.call_args.args[1][-1],run.assets.file_sha(root/'private/context.json'))
            chdir.assert_called_once_with(root/'private/checkout')
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_missing_launch_contract_fails_before_clone_or_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(run,'ROOT',root),patch.object(run,'git_identity') as git,patch.object(run.Budget,'command') as child:
                code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
            self.assertNotEqual(code,0);git.assert_not_called();child.assert_not_called()
            self.assertFalse((root/'private').exists());self.assertFalse((root/'safe').exists())

    def test_git_environment_disallows_lazy_network_and_inherited_config(self):
        with patch.dict(os.environ,{'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'url.bad.insteadOf','GIT_CONFIG_VALUE_0':'file:'}):
            env=run.environment(Path('/unused'))
        self.assertNotIn('GIT_CONFIG_COUNT',env);self.assertEqual(env['GIT_ALLOW_PROTOCOL'],'file')
        self.assertEqual(env['GIT_NO_LAZY_FETCH'],'1');self.assertEqual(env['GIT_TERMINAL_PROMPT'],'0')

    def test_workflow_is_single_attempt_and_exact_safe_artifacts(self):
        raw=(run.ROOT/run.WORKFLOW).read_text()
        self.assertIn('timeout-minutes: 30',raw);self.assertIn('timeout-minutes: 29',raw)
        self.assertIn('github.run_attempt == 1',raw);self.assertIn("paths: ['.github/workflows/raw-kv-public-m16.yml']",raw)
        paths=[line.strip() for line in raw.splitlines() if line.strip().startswith('work/raw-kv-public-m16-')]
        self.assertEqual(paths,['work/raw-kv-public-m16-safe/'+name for name in ('summary.json','progress.json','source_hashes.json')])
        self.assertNotIn('pip install',raw);self.assertNotIn('work/raw-kv-public-m16-private/',raw)


if __name__=='__main__':unittest.main()
