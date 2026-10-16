"""Cold orchestration fixtures only; no native/package/payload execution."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from . import run_ci as run
from . import phase

COMMIT='a'*40
SOURCES={phase.kernel.ORIGINAL:phase.kernel.FIXED[phase.kernel.ORIGINAL],
    run.runtime.CONTRACT:'2'*64,'CONTROL_ONLY/source.py':'1'*64,run.SOURCE:run.IMPORTED_SHA256}
FROZEN=dict(contract_sha256='2'*64,sources=SOURCES,generated={},
    generated_module_sha256=run.runtime.GENERATED_MODULE_SHA256,
    original_setup_sources={'CONTROL_ONLY/setup.py':'3'*64},
    git_blobs={name:'a'*40 for name in SOURCES})


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(run.assets.encoded(value))


def fixture(root):
    """Explicit CONTROL_ONLY context, not real source or native admission."""
    private=root/'private';out=root/'safe';private.mkdir();out.mkdir()
    for name in ('logs','tmp','workspace'):(private/name).mkdir()
    start=time.monotonic_ns();workspace=private/'workspace'
    launch=dict(schema=1,private=str(private),evidence=str(out),checkout_commit=COMMIT,start_ns=start,
        deadline_ns=start+run.TOTAL*10**9,contract_sha256=FROZEN['contract_sha256'],sources=SOURCES,
        git_blobs=FROZEN['git_blobs'],generated={})
    context=dict(schema=1,profile=run.runtime.PROFILE,workspace=str(workspace),checkout_commit=COMMIT,
        source_sha256=SOURCES,contract_sha256=FROZEN['contract_sha256'],start_ns=start,
        deadline_ns=launch['deadline_ns'],generated_module=str(workspace/'generated'/run.runtime.GATE),
        generated_module_sha256=FROZEN['generated_module_sha256'])
    write_json(private/'launch.json',launch);write_json(workspace/'validation_context.json',context)
    return launch,context,private,out


def report(context,tokens,*,failed=False,m16_result_sha256=None,result_sha256='4'*64):
    """Safe-schema fixture using the real original scalar verdict policy."""
    helpers,stages,policy=phase.helpers();observed={}
    for name in stages:
        item=dict(max_abs=0.0,mean_abs=0.0,finite=True,bit_exact=True)
        if failed and name=='y':item.update(max_abs=1.0,mean_abs=1.0,bit_exact=False)
        verdict=helpers['stage_verdict'](name,item,'bf16',policy)
        observed[name]=dict(item,limits=verdict.get('limits'),passed=verdict['passed'])
    modes={mode:dict(status=('FAIL_BF16_STAGE_BUDGET' if failed else 'PASS_BF16_STAGE_BUDGET')
        if mode=='bf16' else 'DIAGNOSTIC_FP32',failed_stages=['y'] if failed and mode=='bf16' else [],
        semantics=dict.fromkeys(phase.SEMANTICS,True),all_semantics_exact=True) for mode in ('bf16','fp32')}
    value=dict(schema=1,carried=False,stage_count=29,assigned_bf16_checks=28,export_count=116,
        postflight_complete=True,actual_chain_executed=False,rtl_execution=False,tokens=tokens,
        status='FAIL_NATIVE_VALIDATION' if failed else 'COMPLETE_NATIVE_VALIDATION',
        native_status='FAIL_BF16_STAGE_BUDGET' if failed else 'PASS_BF16_STAGE_BUDGET',native_acceptance=not failed,
        result_sha256=result_sha256,source_manifest_sha256=phase.kernel.sha(phase.kernel.encoded(context['source_sha256'])),
        contract_sha256=context['contract_sha256'],original_module_sha256=phase.kernel.FIXED[phase.kernel.ORIGINAL],
        generated_module_sha256=context['generated_module_sha256'],library_sha256='5'*64,
        library_receipt_sha256='6'*64,recipe_pins_sha256=run.runtime.RECIPE_PINS_SHA256,
        payload_manifest_sha256='7'*64,m16_result_sha256=m16_result_sha256,
        approved_limits={k:policy[k] for k in ('operator','block')},bf16_stages=observed,modes=modes)
    return phase.validate_report(value)


def library_fixture():
    return dict(library_sha256='5'*64,receipt_sha256='6'*64,pins_sha256=run.runtime.RECIPE_PINS_SHA256)


def write_native(context,workspace,tokens,*,failed=False):
    """Tiny metadata file identities only; no native outputs exist."""
    payload=workspace/'payload/manifest.json'
    if not payload.exists():write_json(payload,{'fixture':'CONTROL_ONLY'})
    path=workspace/f'native{tokens}'/'RESULT.json'
    write_json(path,{'fixture':'CONTROL_ONLY','tokens':tokens,'failed':failed})
    value=report(context,tokens,failed=failed,result_sha256=run.assets.file_sha(path),
        m16_result_sha256=run.assets.file_sha(workspace/'native16/RESULT.json') if tokens==128 else None)
    value['payload_manifest_sha256']=run.assets.file_sha(payload)
    write_json(workspace/f'phase_native{tokens}.json',value)
    return value


class RunnerControlTests(unittest.TestCase):
    def setUp(self):
        # Any newly added orchestration path must fail closed before compilation.
        self.build_guard=patch.object(phase.kernel,'build',side_effect=AssertionError('cold test reached compiler'))
        self.build_guard.start();self.addCleanup(self.build_guard.stop)

    def exercise(self,root,*,child=None,check=None):
        launch,context,private,out=fixture(root);calls=[]
        def command(budget,argv,**kwargs):
            calls.append((argv,kwargs,budget.started,budget.end))
            if child:return child(context,private,kwargs)
            if kwargs['phase'] in ('native16','native128'):
                write_native(context,private/'workspace',int(kwargs['phase'][6:]))
            return 0
        with patch.object(run,'check_launch',side_effect=check,return_value=FROZEN), \
                patch.object(run.runtime,'read_context',return_value=(context,private/'workspace')), \
                patch.object(run.setup,'phase_receipt'),patch.object(run.Budget,'command',command), \
                patch.object(phase.kernel,'verify',return_value=library_fixture()), \
                patch.object(phase.kernel,'build',return_value=library_fixture()) as build:
            result=run.resume(launch,private,out)
        self.assertLessEqual(build.call_count,1)
        return (*result,calls,launch,context,private,out)

    def test_one_fixed_phase_sequence_shares_origin_and_capped_endpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            code,summary,calls,c,context,private,out=self.exercise(Path(temp))
            self.assertEqual((code,summary['status']),(0,run.PASS))
            self.assertEqual([kw['phase'] for _,kw,_,_ in calls],
                ['preflight','environment','acquisition','native16','native128'])
            self.assertEqual([kw['cap'] for _,kw,_,_ in calls],[20,120,420,60,120])
            for argv,kw,start,end in calls:
                self.assertEqual((start,end),(c['start_ns'],c['deadline_ns']))
                self.assertLessEqual(kw['end_ns'],end)
                self.assertEqual(int(kw['extra_env']['QWEN2_NATIVE_QKV_PHASE_END_NS']),kw['end_ns'])
                if kw['phase'] in ('native16','native128'):
                    self.assertEqual(argv[0],str(private/'workspace/venv/bin/python'))
            self.assertFalse(summary['public_executed']);self.assertFalse(summary['rtl_executed'])
            self.assertTrue(summary['postflight_complete']);self.assertTrue(summary['numerical_acceptance'])
            self.assertEqual(summary['native_results']['native128']['m16_result_sha256'],
                summary['native_results']['native16']['result_sha256'])
            self.assertEqual(json.loads((out/'summary.json').read_text()),summary)
            self.assertNotEqual(json.loads((out/'progress.json').read_text())['status'],run.PASS)

    def test_failed_native16_stops_native128_and_retains_validated_failure(self):
        for kind in ('nonzero','zero_with_failed_report','missing'):
            def child(context,private,kw):
                if kw['phase']=='native16':
                    if kind!='missing':write_native(context,private/'workspace',16,failed=True)
                    if kind=='nonzero':
                        error=RuntimeError('SECRET /private raw_tensor');error.exit_code=1;raise error
                return 0
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                code,summary,calls,*_=self.exercise(Path(temp),child=child)
                self.assertEqual((code,summary['status']),(1,'FAILED'))
                self.assertEqual(calls[-1][1]['phase'],'native16')
                self.assertNotIn('native128',[kw['phase'] for _,kw,_,_ in calls])
                self.assertFalse(summary['postflight_complete']);self.assertFalse(summary['numerical_acceptance'])
                if kind=='missing':self.assertEqual(summary['native_diagnostic_status'],'UNAVAILABLE')
                else:
                    failed=summary['native_results']['native16']
                    self.assertEqual(failed['status'],'FAIL_NATIVE_VALIDATION')
                    self.assertFalse(failed['native_acceptance']);self.assertEqual(failed['modes']['bf16']['failed_stages'],['y'])
                for text in ('SECRET','/private','raw_tensor'):self.assertNotIn(text,json.dumps(summary))

    def test_nonzero_child_and_late_postflight_cannot_inherit_valid_reports(self):
        for cause in ('child','source'):
            checks=0
            def check(*args,**kwargs):
                nonlocal checks
                checks+=1
                if cause=='source' and checks==14:raise ValueError('SECRET postflight')
                return FROZEN
            def child(context,private,kw):
                if kw['phase'] in ('native16','native128'):
                    write_native(context,private/'workspace',int(kw['phase'][6:]))
                if cause=='child' and kw['phase']=='native128':raise RuntimeError('SECRET returned nonzero')
                return 0
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as temp:
                code,summary,*_=self.exercise(Path(temp),child=child,check=check)
                self.assertEqual((code,summary['status']),(1,'FAILED'))
                self.assertFalse(summary['postflight_complete']);self.assertFalse(summary['numerical_acceptance'])

    def test_safe_report_real_schema_and_every_cross_receipt_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            _,context,private,_=fixture(Path(temp));workspace=private/'workspace'
            write_native(context,workspace,16);good=write_native(context,workspace,128)
            path=workspace/'phase_native128.json'
            with patch.object(phase.kernel,'verify',return_value=library_fixture()):
                self.assertEqual(run.safe_report(workspace,'native128',context),good)
            for key,bad in (('tokens',16),('tokens',128.0),('contract_sha256','0'*64),
                    ('source_manifest_sha256','0'*64),('generated_module_sha256','0'*64),
                    ('library_sha256','0'*64),('library_receipt_sha256','0'*64),('recipe_pins_sha256','0'*64),
                    ('result_sha256','0'*64),('payload_manifest_sha256','0'*64),('m16_result_sha256','0'*64),
                    ('native_acceptance',1),('postflight_complete',1),('private_payload','SECRET')):
                changed=dict(good,**{key:bad});write_json(path,changed)
                with self.subTest(key=key),patch.object(phase.kernel,'verify',return_value=library_fixture()), \
                        self.assertRaises(ValueError):run.safe_report(workspace,'native128',context)
            write_json(path,good)
            for target in (workspace/'native128/RESULT.json',workspace/'payload/manifest.json',workspace/'native16/RESULT.json'):
                raw=target.read_bytes();target.write_bytes(raw+b' ')
                with self.subTest(file=target.name),patch.object(phase.kernel,'verify',return_value=library_fixture()), \
                        self.assertRaises(ValueError):run.safe_report(workspace,'native128',context)
                target.write_bytes(raw)

    def test_missing_opt_in_attempt_two_or_event_commit_mismatch_reject_before_bootstrap(self):
        good=['--execute','--private','/CONTROL_ONLY/private','--evidence','/CONTROL_ONLY/safe','--checkout-commit',COMMIT]
        for args,env in (([],{}),(good,{'GITHUB_RUN_ATTEMPT':'2'}),(good,{'GITHUB_SHA':'b'*40}),
                         (['--resume','--internal-compose'],{'QWEN2_PUBLIC_RUN_CHILD':'1'}),
                         (['--resume'],{'QWEN2_PUBLIC_RUN_CHILD':'0'})):
            with self.subTest(args=args,env=env),patch.dict(os.environ,env,clear=True), \
                    patch.object(run,'bootstrap') as boot,patch.object(run,'read_launch') as read, \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run.main(args),1)
                boot.assert_not_called();read.assert_not_called()
                self.assertEqual(json.loads(output.getvalue())['status'],'NOT_RUN')

    def test_budget_preserves_origin_and_phase_cap_including_cleanup_reserve(self):
        start=time.monotonic_ns();end=start+900*10**9
        self.assertEqual(run.Budget.command,run.prior.Budget.command)
        with tempfile.TemporaryDirectory() as temp:
            private=Path(temp);(private/'logs').mkdir();(private/'tmp').mkdir()
            budget=run.Budget(start,end)
            try:
                for name,cap in run.LIMITS.items():
                    with patch.object(run.prior.setup,'run_group',return_value=0) as group:
                        budget.command(['CONTROL_ONLY'],private=private,cwd=private,phase=name,cap=cap)
                    options=group.call_args.kwargs
                    self.assertGreater(options['timeout'],0)
                    self.assertLessEqual(options['timeout'],cap-run.prior.GRACE-run.prior.RECEIPT)
                    self.assertEqual(options['grace'],5)
                    self.assertEqual((budget.started,budget.end),(start,end))
            finally:budget.close()
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        for begin,finish in ((True,end),(start,end+1),(start+10**15,end+10**15)):
            with self.subTest(origin=(begin,finish)),self.assertRaises(ValueError):run.Budget(begin,finish)

    def test_launch_same_bytes_hash_canonical_deadline_and_full_blob_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            launch,context,private,out=fixture(Path(temp));path=private/'launch.json'
            self.assertEqual(run.read_launch(path,run.assets.file_sha(path)),(launch,private,out))
            cases=[]
            for key,bad in (('schema',True),('start_ns',True),('deadline_ns',launch['deadline_ns']+1),
                    ('git_blobs',{}),('sources',{}),('contract_sha256','invalid')):
                value=deepcopy(launch);value[key]=bad;cases.append(value)
            for index,value in enumerate(cases):
                write_json(path,value)
                with self.subTest(case=index),self.assertRaises(ValueError):run.read_launch(path,run.assets.file_sha(path))
            write_json(path,launch)
            with self.assertRaises(ValueError):run.read_launch(path,'0'*64)

    def test_failure_summary_cannot_upgrade_and_does_not_leak_exception_text(self):
        for error in (RuntimeError('SECRET /private raw_tensor https://signed'),
                      subprocess.TimeoutExpired(['SECRET'],1),InterruptedError('SECRET')):
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);start=time.monotonic_ns();budget=run.Budget(start,start+900*10**9)
                summary=run.new_summary(start);summary.update(status=run.PASS,phase='native16',
                    numerical_acceptance=True,postflight_complete=True)
                code,value=run.finish(out,summary,budget,error,SOURCES)
                self.assertEqual(code,1);self.assertFalse(value['numerical_acceptance']);self.assertFalse(value['postflight_complete'])
                self.assertEqual(value['status'],'TIMEOUT' if isinstance(error,subprocess.TimeoutExpired)
                    else 'INTERRUPTED' if isinstance(error,InterruptedError) else 'FAILED')
                public=(out/'summary.json').read_text()+(out/'progress.json').read_text()
                for forbidden in ('SECRET','/private','raw_tensor','https://',run.PASS):self.assertNotIn(forbidden,public)
                self.assertEqual({p.name for p in out.iterdir()},{'summary.json','progress.json'})

    def test_publish_exact_allowlist_and_pending_success_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);summary=run.new_summary(time.monotonic_ns());summary['status']=run.PASS
            run.publish(out,summary)
            self.assertEqual(json.loads((out/'progress.json').read_text())['status'],'TERMINAL_RECEIPT_PENDING')
            (out/'private.log').write_text('SECRET')
            with self.assertRaises(ValueError):run.publish(out,summary)

    def test_real_term_resistant_sleep_only_child_is_reaped(self):
        with tempfile.TemporaryDirectory() as temp:
            private=Path(temp);(private/'logs').mkdir();(private/'tmp').mkdir();pidfile=private/'pid'
            code=("import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                  f"Path({str(pidfile)!r}).write_text(str(os.getpid()));time.sleep(30)")
            start=time.monotonic_ns();budget=run.Budget(start,start+900*10**9)
            try:
                with patch.object(run.prior,'GRACE',0.1),patch.object(run.prior,'RECEIPT',0.05):
                    with self.assertRaises(subprocess.TimeoutExpired):
                        budget.command([sys.executable,'-c',code],private=private,cwd=private,phase='kernel',cap=0.4)
            finally:budget.close()
            self.assertLess((time.monotonic_ns()-start)/1e9,2)
            with self.assertRaises(ProcessLookupError):os.killpg(int(pidfile.read_text()),0)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_direct_kernel_disarms_then_rearms_before_postflight(self):
        for cause in (None,'build','context','library'):
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as temp:
                _,context,private,_=fixture(Path(temp));workspace=private/'workspace'
                events=[];end=time.monotonic_ns()+30*10**9;failure=InterruptedError('PRIVATE')
                budget=Mock()
                budget.disarm.side_effect=lambda:events.append('disarm')
                budget.arm.side_effect=lambda value:events.append(('arm',value))
                budget.remaining.side_effect=lambda value:events.append(('remaining',value))
                def build(*args,**kwargs):
                    self.assertEqual(events,['disarm']);events.append('build')
                    if cause=='build':raise failure
                    return library_fixture()
                def context_read(*args):
                    self.assertEqual(events[-1],('arm',end-10**9));events.append('context')
                    return (dict(context,profile='foreign') if cause=='context' else context,workspace)
                def verify(*args):
                    events.append('verify')
                    return dict(library_fixture(),library_sha256='0'*64) if cause=='library' else library_fixture()
                with patch.object(phase.kernel,'build',side_effect=build) as called, \
                        patch.object(run.runtime,'read_context',side_effect=context_read), \
                        patch.object(phase.kernel,'verify',side_effect=verify):
                    if cause:
                        with self.assertRaises((ValueError,InterruptedError)) as caught:
                            run.run_kernel(workspace,context,budget,end)
                        if cause=='build':self.assertIs(caught.exception,failure)
                        self.assertFalse((workspace/'phase_kernel.json').exists())
                    else:
                        result=run.run_kernel(workspace,context,budget,end)
                        self.assertEqual(result['status'],'COMPLETE_KERNEL_BUILD')
                        self.assertFalse(result['numerical_execution'])
                        self.assertEqual(events,['disarm','build',('arm',end-10**9),'context','verify',
                            ('remaining',end-10**9)])
                called.assert_called_once_with(workspace/'recipe_library',execute=True,deadline_ns=end-6*10**9)
                budget.arm.assert_called_once_with(end-10**9)

    def test_direct_kernel_external_term_reaps_resistant_compiler_with_actual_grace(self):
        """Real owner and detached sleeper; frozen cleanup, no compiler or math."""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pidfile=root/'compiler.pid';state=root/'state.json';workspace=root/'workspace';workspace.mkdir()
            sleeper=("import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                     f"Path({str(pidfile)!r}).write_text(str(os.getpid()));time.sleep(30)")
            child='\n'.join([
                'import json,os,signal,sys,time',
                'from pathlib import Path',
                'from candidates.qwen2_resident_matrix.raw_kv_native_qkv_run import run_ci as r',
                'from candidates.qwen2_resident_matrix.raw_kv_native_qkv import kernel as k',
                "k.source_snapshot=lambda:{};k.source_bytes=lambda:b'CONTROL_ONLY'",
                "k.compiler_identity=lambda:{'path':sys.executable,'sha256':'0'*64}",
                'original=k._compile',
                f'k._compile=lambda argv,out,end:original([sys.executable,"-c",{sleeper!r}],out,end)',
                'start=time.monotonic_ns();budget=r.Budget(start,start+900*10**9);budget.arm()',
                'try:',
                f' r.run_kernel(Path({str(workspace)!r}),{{}},budget,start+30*10**9)',
                'except InterruptedError:',
                f' pid=int(Path({str(pidfile)!r}).read_text())',
                ' try:os.killpg(pid,0);gone=False',
                ' except ProcessLookupError:gone=True',
                f' Path({str(state)!r}).write_text(json.dumps(dict(gone=gone,grace=k.GRACE,rearmed=signal.getitimer(signal.ITIMER_REAL)[0]>0)))',
                ' sys.exit(3)',
                'finally:budget.close()',
                'sys.exit(0)'])
            start=time.monotonic();owner=subprocess.Popen([sys.executable,'-B','-c',child],cwd=run.ROOT,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                while not pidfile.exists() and owner.poll() is None and time.monotonic()-start<3:time.sleep(.01)
                self.assertTrue(pidfile.is_file(),'sleep-only compiler did not start')
                os.kill(owner.pid,signal.SIGTERM)
                self.assertEqual(owner.wait(timeout=8),3)
                self.assertEqual(json.loads(state.read_text()),dict(gone=True,grace=5,rearmed=True))
                with self.assertRaises(ProcessLookupError):os.killpg(int(pidfile.read_text()),0)
                self.assertFalse((workspace/'phase_kernel.json').exists())
                self.assertFalse((workspace/'recipe_library'/phase.kernel.RECEIPT).exists())
                self.assertFalse((workspace/'recipe_library'/phase.kernel.LIBRARY).exists())
                self.assertLess(time.monotonic()-start,9)
            finally:
                if pidfile.exists():
                    try:os.killpg(int(pidfile.read_text()),signal.SIGKILL)
                    except ProcessLookupError:pass
                if owner.poll() is None:os.killpg(owner.pid,signal.SIGKILL)
                owner.wait(timeout=1)

    def test_setup_child_diagnostic_is_validated_and_keeps_terminal_failure(self):
        for bad in (False,True):
            def child(context,private,kw):
                if kw['phase']=='environment':
                    value=dict(phase='environment',exception='RuntimeError',exit_code=1,
                        frames=[dict(source='CONTROL_ONLY/setup.py',line=123)])
                    if bad:value['private_text']='SECRET /private token'
                    write_json(private/'workspace/environment.failure.json',value)
                    raise RuntimeError('SECRET /private token')
                return 0
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as temp:
                code,summary,calls,*_=self.exercise(Path(temp),child=child)
                self.assertEqual((code,summary['status']),(1,'FAILED'))
                self.assertFalse(summary['postflight_complete']);self.assertFalse(summary['numerical_acceptance'])
                self.assertEqual(calls[-1][1]['phase'],'environment')
                self.assertEqual('child_diagnostic' in summary,not bad)
                if not bad:
                    self.assertEqual(summary['child_diagnostic'],dict(phase='environment',exception='RuntimeError',
                        exit_code=1,frames=[dict(source='CONTROL_ONLY/setup.py',line=123)]))
                for text in ('SECRET','/private','token'):self.assertNotIn(text,json.dumps(summary))

    def test_bootstrap_clone_and_reexec_never_reset_origin_or_modify_checkout(self):
        class Boundary(Exception):pass
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);calls=[]
            def command(budget,argv,**kwargs):
                calls.append((argv,kwargs,budget.started,budget.end))
                if kwargs['phase']=='clone':(kwargs['private']/'checkout').mkdir()
                return 0
            with patch.object(run.runtime,'snapshot',return_value=FROZEN), \
                    patch.object(run.prior,'git_identity') as git,patch.object(run.Budget,'command',command), \
                    patch.object(run.os,'chdir') as chdir,patch.object(run.os,'execve',side_effect=Boundary()) as execute:
                code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
            self.assertEqual((code,summary['status']),(1,'FAILED'))  # intercepted re-exec, no work launched
            c=run.assets.read_json(root/'private/launch.json')
            self.assertEqual(c['deadline_ns']-c['start_ns'],900*10**9)
            self.assertEqual([kw['phase'] for _,kw,_,_ in calls],['clone','checkout','compose'])
            self.assertEqual(calls[0][0][:5],['git','clone','--no-local','--no-checkout','--'])
            self.assertEqual(calls[1][0],['git','-c','core.hooksPath=/dev/null','checkout','--detach',COMMIT])
            self.assertTrue(all((start,end)==(c['start_ns'],c['deadline_ns']) for _,_,start,end in calls))
            git.assert_called_once_with(COMMIT,FROZEN['git_blobs'],root/'private')
            chdir.assert_called_once_with(root/'private/checkout')
            argv=execute.call_args.args[1];self.assertIn('--resume',argv)
            self.assertEqual(argv[-1],run.assets.file_sha(root/'private/launch.json'))
            self.assertEqual(execute.call_args.args[2]['QWEN2_PUBLIC_RUN_CHILD'],'1')
            self.assertEqual({p.name for p in (root/'safe').iterdir()},set(run.OUTPUTS))

    def test_check_launch_binds_original_git_bytes_before_and_after_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            private=Path(temp);checkout=private/'checkout';checkout.mkdir()
            old=b'# CONTROL_ONLY original\n';new=b'# CONTROL_ONLY generated\n';name='source.py'
            blob=hashlib.sha1(b'blob '+str(len(old)).encode()+b'\0'+old).hexdigest()
            runner=Path(run.__file__).read_bytes();runner_path=checkout/run.SOURCE
            runner_path.parent.mkdir(parents=True);runner_path.write_bytes(runner)
            runner_blob=hashlib.sha1(b'blob '+str(len(runner)).encode()+b'\0'+runner).hexdigest()
            c=dict(checkout_commit=COMMIT,contract_sha256='2'*64,sources={name:run.assets.sha(old),run.SOURCE:run.IMPORTED_SHA256},
                generated={name:run.assets.sha(new)},git_blobs={name:blob,run.SOURCE:runner_blob})
            for composed in (False,True):
                (checkout/name).write_bytes(new if composed else old)
                frozen=dict(FROZEN,sources={name:run.assets.sha(new if composed else old),
                    run.SOURCE:run.IMPORTED_SHA256},generated=c['generated'])
                with self.subTest(composed=composed),patch.object(run,'ROOT',checkout), \
                        patch.object(run.runtime,'snapshot',return_value=frozen),patch.object(run.prior,'git_identity'), \
                        patch.object(run.subprocess,'check_output',return_value=old) as gitshow:
                    self.assertEqual(run.check_launch(c,private,composed=composed),frozen)
                    self.assertEqual(gitshow.call_count,int(composed))
                    forged=deepcopy(c);forged['git_blobs'][name]='0'*40
                    with self.assertRaises(ValueError):run.check_launch(forged,private,composed=composed)

    def test_loaded_runner_drift_rejects_before_clone_or_git_admission(self):
        frozen=deepcopy(FROZEN);frozen['sources'][run.SOURCE]='0'*64
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(run.runtime,'snapshot',return_value=frozen), \
                    patch.object(run.prior,'git_identity') as git,patch.object(run.Budget,'command') as command:
                code,summary=run.bootstrap(root/'private',root/'safe',COMMIT)
                self.assertEqual((code,summary['status']),(1,'FAILED'))
                git.assert_not_called();command.assert_not_called()
                with self.assertRaises(ValueError):run.check_launch({},root/'private',composed=True)
                git.assert_not_called()

    def test_composition_keeps_generated_gate_separate_and_preserves_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            private=Path(temp);checkout=private/'checkout';checkout.mkdir();workspace=private/'workspace'
            names=[f'CONTROL_ONLY/overlay{i}.py' for i in range(10)]
            originals={name:b'old\n' for name in names};generated={name:b'new\n' for name in names}
            for name,raw in originals.items():
                path=checkout/name;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
            gate=checkout/run.runtime.GATE;gate.parent.mkdir();gate.write_bytes(b'original gate\n')
            start=time.monotonic_ns();c=dict(start_ns=start,deadline_ns=start+900*10**9,checkout_commit=COMMIT,
                sources={name:run.assets.sha(raw) for name,raw in originals.items()})
            frozen=dict(FROZEN,generated={name:run.assets.sha(raw) for name,raw in generated.items()})
            context=dict(CONTROL_ONLY=True)
            def prepare(out):
                out.mkdir()
                for name,raw in generated.items():
                    path=out/'overlays'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                path=out/'generated'/run.runtime.GATE;path.parent.mkdir(parents=True);path.write_bytes(b'separate gate\n')
            with patch.object(run,'ROOT',checkout),patch.object(run,'check_launch',return_value=frozen), \
                    patch.object(run.runtime,'prepare_outputs',side_effect=prepare), \
                    patch.object(run.runtime,'snapshot',return_value=frozen), \
                    patch.object(run.runtime,'make_context',return_value=context) as make, \
                    patch.object(run.runtime,'old_setup_context',return_value={'CONTROL_ONLY':True}):
                run.compose(c,private)
            make.assert_called_once_with(workspace,COMMIT,start,c['deadline_ns'],frozen)
            self.assertEqual(gate.read_bytes(),b'original gate\n')
            self.assertEqual((workspace/'generated'/run.runtime.GATE).read_bytes(),b'separate gate\n')
            for name,raw in generated.items():self.assertEqual((checkout/name).read_bytes(),raw)

    def test_workflow_single_trigger_fixed_budget_and_exact_safe_artifacts(self):
        path=run.ROOT/run.runtime.WORKFLOW;raw=path.read_text()
        self.assertIn('timeout-minutes: 20',raw);self.assertIn('timeout-minutes: 16',raw)
        self.assertIn('github.run_attempt == 1',raw);self.assertIn('cancel-in-progress: false',raw)
        self.assertIn("paths: ['.github/workflows/raw-kv-native-qkv.yml']",raw)
        self.assertIn("ref: '${{ github.sha }}'",raw);self.assertIn('persist-credentials: false',raw)
        self.assertEqual([line.strip() for line in raw.split('          path: |\n')[1].splitlines()],
            ['work/raw-kv-native-qkv-safe/'+name for name in run.OUTPUTS])
        self.assertEqual(run.TOTAL,900);self.assertEqual(run.LIMITS,run.runtime.PHASE_LIMITS)
        old=run.assets.read_json(run.ROOT/run.runtime.ORIGINAL_CONTRACT)
        original_workflow='.github/workflows/raw-kv-public-m128.yml'
        self.assertEqual(run.assets.file_sha(run.ROOT/original_workflow),old['source_sha256'][original_workflow])
        self.assertNotIn(original_workflow,raw)


if __name__=='__main__':unittest.main()
