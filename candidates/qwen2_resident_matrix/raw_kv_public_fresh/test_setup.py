"""Cold supervisor tests. No package installation, weights or native arithmetic."""
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

from . import setup

COMMIT='a'*40
SOURCES={name:'0'*64 for name in (*setup.SETUP_SOURCES,setup.PROFILE_PATH)}
SOURCES['original.py']='1'*64


def gone_or_zombie(pid):
    try:
        return Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1].split()[0]=='Z'
    except (FileNotFoundError,ProcessLookupError):
        return True


class SupervisorTests(unittest.TestCase):
    def exercise(self,root,*,child=None,snapshot=None,deadline_ns=None):
        calls=[]
        def fake(command,**kw):
            calls.append((command,kw))
            phase=command[command.index('--internal-phase')+1]
            workspace=root/'private'
            if child:
                result=child(phase,workspace,kw)
                if result is not None:return result
            receipt=dict(schema=1,phase=phase,status='COMPLETE_SETUP_PHASE',
                source_manifest_sha256=setup.assets.sha(setup.assets.encoded(SOURCES)))
            if phase=='seal':
                (workspace/'ASSETS.json').write_text('{}')
                receipt['manifest_sha256']=setup.digest(workspace/'ASSETS.json')
            (workspace/(phase+'.complete.json')).write_text(json.dumps(receipt))
            return 0
        with ExitStack() as stack:
            stack.enter_context(patch.object(setup,'source_snapshot',return_value=SOURCES,side_effect=snapshot))
            stack.enter_context(patch.object(setup,'run_group',side_effect=fake))
            result=setup.run(root/'private',root/'evidence',checkout_commit=COMMIT,deadline_ns=deadline_ns)
        return (*result,calls)

    def test_success_is_setup_only_and_fixed_phases_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code,summary,calls=self.exercise(root)
            self.assertEqual((code,summary['status']),(0,setup.SETUP_STATUS))
            self.assertEqual(summary['completed_phases'],list(setup.PHASES))
            self.assertEqual(len(calls),len(setup.PHASES))
            self.assertFalse(summary['actual_chain_executed']);self.assertFalse(summary['numerical_acceptance'])
            self.assertEqual({p.name for p in (root/'evidence').iterdir()},set(setup.OUTPUTS))
            for command,kw in calls:
                phase=command[command.index('--internal-phase')+1]
                self.assertLessEqual(kw['timeout'],setup.PHASE_LIMITS[phase])
                self.assertLessEqual(kw['timeout'],594)
                self.assertEqual(kw['grace'],5)
                self.assertTrue(kw['log'].closed)
            public=''.join(p.read_text() for p in (root/'evidence').iterdir())
            self.assertNotIn(tmp,public)
            self.assertLess((root/'evidence/progress.json').stat().st_size,1024)
            receipt=json.loads((root/'private/SETUP.json').read_text())
            context=json.loads((root/'private/context.json').read_text())
            self.assertEqual(receipt['status'],setup.SETUP_STATUS)
            self.assertEqual(receipt['source_sha256'],SOURCES)
            self.assertEqual(context['asset_source_sha256'],{'original.py':'1'*64})
            self.assertEqual(receipt['asset_manifest_sha256'],summary['manifest_sha256'])
            self.assertEqual(receipt['source_recheck'],'UNCHANGED')

    def test_missing_new_source_pin_fails_before_files_or_child(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(setup.assets,'source_snapshot',return_value={}),patch.object(setup,'run_group') as child:
            root=Path(tmp)
            # Publication may install the real profile; this fixture explicitly lacks it.
            with patch.object(setup,'ROOT',root):
                code,summary=setup.run(root/'private',root/'evidence',checkout_commit=COMMIT)
            self.assertNotEqual(code,0);self.assertEqual(summary['reason'],'source_pin_not_installed')
            self.assertFalse((root/'private').exists());self.assertFalse((root/'evidence').exists());child.assert_not_called()

    def test_expired_and_short_deadline_have_no_side_effects(self):
        for delta in (-1,1,5):
            with self.subTest(delta=delta),tempfile.TemporaryDirectory() as tmp,patch.object(setup,'source_snapshot') as snap,patch.object(setup,'run_group') as child:
                root=Path(tmp);deadline=time.monotonic_ns()+int(delta*1e9)
                code,summary=setup.run(root/'private',root/'evidence',checkout_commit=COMMIT,deadline_ns=deadline)
                self.assertEqual((code,summary['status']),(2,'NOT_RUN'))
                self.assertFalse(list(root.iterdir()));snap.assert_not_called();child.assert_not_called()

    def test_external_deadline_can_only_shorten(self):
        for seconds in (30,6000):
            with self.subTest(seconds=seconds),tempfile.TemporaryDirectory() as tmp:
                code,summary,calls=self.exercise(Path(tmp),deadline_ns=time.monotonic_ns()+int(seconds*1e9))
                self.assertEqual(code,0)
                for _,kw in calls:self.assertLessEqual(kw['timeout'],min(seconds,600)-6)

    def test_invalid_canonical_arguments(self):
        cases=({'checkout_commit':'HEAD'},{'checkout_commit':COMMIT,'enable_raw_kv':1},
               {'checkout_commit':COMMIT,'deadline_ns':True},{'checkout_commit':COMMIT,'deadline_ns':float('inf')})
        with tempfile.TemporaryDirectory() as tmp,patch.object(setup,'source_snapshot') as snap:
            for case in cases:
                code,summary=setup.run(Path(tmp)/'private',Path(tmp)/'evidence',**case)
                self.assertEqual(code,2)
            snap.assert_not_called();self.assertFalse(list(Path(tmp).iterdir()))

    def test_existing_alias_and_symlink_directories_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);existing=root/'existing';existing.mkdir()
            link=root/'link';link.symlink_to(existing,target_is_directory=True)
            cases=((existing,root/'new'),(root/'same',root/'same'),(root/'outer',root/'outer/evidence'),
                   (root/'outer/evidence',root/'outer'),(root/'private',link/'evidence'))
            for workspace,evidence in cases:
                with self.subTest(workspace=workspace),self.assertRaises(setup.SetupError):setup.fresh_directories(workspace,evidence)

    def test_nonzero_stops_without_retry_or_ready(self):
        def child(phase,workspace,kw):
            if phase=='acquisition':kw['log'].write(b'private raw_tensor=[1,2,3]');return 9
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls=self.exercise(Path(tmp),child=child)
            self.assertEqual(code,1);self.assertEqual(summary['status'],'SETUP_FAILED')
            self.assertEqual(summary['completed_phases'],['preflight','environment'])
            self.assertEqual(len(calls),3);self.assertEqual(summary['diagnostic']['exit_code'],9)
            self.assertNotIn('manifest_sha256',summary)

    def test_invalid_phase_receipt_cannot_advance(self):
        def child(phase,workspace,kw):
            (workspace/(phase+'.complete.json')).write_text('{"status":"COMPLETE_SETUP_PHASE"}')
            return 0
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls=self.exercise(Path(tmp),child=child)
            self.assertEqual(code,1);self.assertEqual(summary['completed_phases'],[]);self.assertEqual(len(calls),1)

    def test_source_drift_cannot_succeed(self):
        count=0
        def source(_):
            nonlocal count
            count+=1
            return SOURCES if count<4 else {name:'1'*64 for name in SOURCES}
        with tempfile.TemporaryDirectory() as tmp:
            code,summary,calls=self.exercise(Path(tmp),snapshot=source)
            self.assertEqual((code,summary['reason']),(1,'source_drift'))
            self.assertLess(len(calls),len(setup.PHASES))

    def test_child_output_exception_and_diagnostic_cannot_leak(self):
        private='/private/token SECRET raw_tensor=[1,2,3] https://cdn.test/?signature=SECRET'
        for variant in ('exception','diagnostic'):
            def child(phase,workspace,kw):
                kw['log'].write(private.encode())
                if variant=='exception':raise ValueError(private)
                (workspace/(phase+'.failure.json')).write_text(json.dumps(dict(phase=phase,exception=private,frames=[private])))
                return 4
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                code,summary,_=self.exercise(Path(tmp),child=child)
                raw=json.dumps(summary)+''.join(p.read_text() for p in (Path(tmp)/'evidence').iterdir())
                self.assertNotEqual(code,0)
                for text in ('SECRET','/private/token','raw_tensor','https://',tmp):self.assertNotIn(text,raw)

    def test_repository_frames_are_allowlisted_only(self):
        try:raise ValueError('/secret raw_tensor')
        except ValueError as error:result=setup.safe_diagnostic(error,phase='preflight',sources=SOURCES)
        self.assertTrue(result['frames'])
        self.assertTrue(all(f['source'] in SOURCES for f in result['frames']))
        self.assertNotIn('/secret',json.dumps(result))
        bad=copy.deepcopy(result);bad['frames'][0]['source']='../../secret'
        with self.assertRaises(setup.SetupError):setup.validate_diagnostic(bad,'preflight',SOURCES)

    def test_signal_or_timeout_restores_handlers(self):
        old=(signal.getsignal(signal.SIGALRM),signal.getsignal(signal.SIGTERM))
        for kind in ('timeout','term'):
            def child(phase,workspace,kw):
                if kind=='term':os.kill(os.getpid(),signal.SIGTERM)
                raise subprocess.TimeoutExpired(['PRIVATE'],1)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                code,summary,_=self.exercise(Path(tmp),child=child)
                self.assertEqual(code,1)
                self.assertEqual(summary['status'],'SETUP_TIMEOUT' if kind=='timeout' else 'SETUP_INTERRUPTED')
                self.assertEqual((signal.getsignal(signal.SIGALRM),signal.getsignal(signal.SIGTERM)),old)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_real_resistant_group_timeout_uses_uninterrupted_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pidfile=root/'pid'
            script='import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path('+repr(str(pidfile))+').write_text(str(os.getpid())); time.sleep(30)'
            def source(_):time.sleep(.015);return SOURCES
            with patch.object(setup,'TOTAL_SECONDS',.55),patch.object(setup,'CLEANUP_SECONDS',.1),patch.object(setup,'RECEIPT_SECONDS',.05),patch.object(setup,'source_snapshot',side_effect=source),patch.object(setup,'phase_command',return_value=[sys.executable,'-c',script]):
                started=time.monotonic();code,summary=setup.run(root/'private',root/'evidence',checkout_commit=COMMIT)
            self.assertEqual((code,summary['status']),(1,'SETUP_TIMEOUT'));self.assertLess(time.monotonic()-started,1.5)
            pid=int(pidfile.read_text());self.assertTrue(gone_or_zombie(pid))
            with self.assertRaises(ProcessLookupError):os.killpg(pid,0)

    def test_successful_leader_cannot_leave_background_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pidfile=root/'descendant'
            grandchild='import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path('+repr(str(pidfile))+').write_text(str(os.getpid())); time.sleep(30)'
            script='import subprocess,sys,time; from pathlib import Path; subprocess.Popen([sys.executable,"-c",'+repr(grandchild)+']);\nwhile not Path('+repr(str(pidfile))+').exists():time.sleep(.005)'
            with (root/'private.log').open('wb') as log,self.assertRaises(setup.SetupError):
                setup.run_group([sys.executable,'-c',script],cwd=root,env=dict(os.environ),log=log,timeout=2,grace=.1)
            pid=int(pidfile.read_text());end=time.monotonic()+1
            while not gone_or_zombie(pid) and time.monotonic()<end:time.sleep(.01)
            self.assertTrue(gone_or_zombie(pid))

    def test_atomic_progress_and_staging_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'progress.json';value={'status':'PROGRESS'}
            setup.atomic_json(path,value,1024)
            self.assertEqual(json.loads(path.read_text()),value);self.assertFalse((root/'progress.json.pending').exists())
            (root/'progress.json.pending').symlink_to(root/'unrelated')
            with self.assertRaises(setup.SetupError):setup.atomic_json(path,value,1024)
            self.assertFalse((root/'unrelated').exists())

    def test_environment_removes_import_and_package_override(self):
        with patch.dict(os.environ,{'PYTHONPATH':'/private','PYTHONHOME':'/private','PYTHONOPTIMIZE':'2','PIP_INDEX_URL':'https://private','PIP_EXTRA_INDEX_URL':'https://private'}):
            env=setup.child_environment(Path('/unused'))
        for key in ('PYTHONPATH','PYTHONHOME','PYTHONOPTIMIZE','PIP_INDEX_URL','PIP_EXTRA_INDEX_URL'):self.assertNotIn(key,env)
        self.assertEqual(env['PIP_CONFIG_FILE'],'/dev/null');self.assertEqual(env['OMP_NUM_THREADS'],'4')

    def test_cli_requires_explicit_opt_in_and_no_budget_override(self):
        with patch.object(setup,'run') as run:
            self.assertEqual(setup.main([]),2);run.assert_not_called()
        output=io.StringIO()
        with patch.object(setup,'run',return_value=(2,{'status':'NOT_RUN'})) as run,redirect_stdout(output):
            self.assertEqual(setup.main(['--execute-setup','--workspace','/private','--evidence','/evidence','--checkout-commit',COMMIT]),2)
            self.assertNotIn('deadline_ns',run.call_args.kwargs)

    def test_post_cleanup_source_drift_preserves_producer_diagnostic(self):
        failed=False
        def child(phase,workspace,kw):
            nonlocal failed
            failed=True
            return 23
        def snapshot(_):
            return {name:'f'*64 for name in SOURCES} if failed else SOURCES
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code,summary,_=self.exercise(root,child=child,snapshot=snapshot)
            self.assertEqual((code,summary['reason']),(1,'phase_failed'))
            self.assertEqual(summary['diagnostic']['exit_code'],23)
            self.assertEqual(summary['source_recheck'],'FAILED')
            self.assertEqual(summary['postflight_reason'],'source_drift')
            self.assertFalse((root/'private/SETUP.json').exists())

    def test_final_evidence_has_absolute_timer_and_no_commit_after_timeout(self):
        original=setup.atomic_json
        def slow_final(path,value,limit):
            if path.name=='summary.json' and value['status']==setup.SETUP_STATUS:time.sleep(2)
            original(path,value,limit)
        with tempfile.TemporaryDirectory() as tmp,patch.object(setup,'TOTAL_SECONDS',.20),patch.object(setup,'CLEANUP_SECONDS',.03),patch.object(setup,'RECEIPT_SECONDS',.02),patch.object(setup,'atomic_json',side_effect=slow_final):
            root=Path(tmp);start=time.monotonic();code,summary,_=self.exercise(root)
            self.assertEqual((code,summary['status']),(1,'SETUP_TIMEOUT'))
            self.assertLess(time.monotonic()-start,.7)
            self.assertFalse((root/'private/SETUP.json').exists())
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))

    def test_interrupted_private_commit_never_leaves_successful_public_summary(self):
        original=setup.atomic_json
        for point in ('before','after'):
            def interrupted(path,value,limit):
                if path.name=='SETUP.json':
                    if point=='after':original(path,value,limit)
                    raise OSError('/private/path raw_tensor=[1,2,3]')
                return original(path,value,limit)
            with self.subTest(point=point),tempfile.TemporaryDirectory() as tmp,patch.object(setup,'atomic_json',side_effect=interrupted):
                root=Path(tmp);code,summary,_=self.exercise(root)
                self.assertEqual(code,1);self.assertNotEqual(summary['status'],setup.SETUP_STATUS)
                public=json.loads((root/'evidence/summary.json').read_text())
                self.assertNotEqual(public['status'],setup.SETUP_STATUS)
                self.assertNotIn('setup_receipt_sha256',public)
                self.assertFalse((root/'private/SETUP.json').exists())
                self.assertNotIn('/private/path',json.dumps(public))

    def test_interrupted_final_summary_revokes_both_completion_credentials(self):
        original=setup.atomic_json
        def interrupted(path,value,limit):
            original(path,value,limit)
            if path.name=='summary.json' and value['status']==setup.SETUP_STATUS:
                raise OSError('private compiler diagnostic')
        with tempfile.TemporaryDirectory() as tmp,patch.object(setup,'atomic_json',side_effect=interrupted):
            root=Path(tmp);code,summary,_=self.exercise(root)
            self.assertEqual(code,1)
            self.assertFalse((root/'private/SETUP.json').exists())
            public=json.loads((root/'evidence/summary.json').read_text())
            self.assertNotEqual(public['status'],setup.SETUP_STATUS)
            self.assertNotIn('setup_receipt_sha256',public)

    def test_final_source_check_timeout_is_incomplete_and_preserves_failure(self):
        failed=False
        def child(phase,workspace,kw):
            nonlocal failed
            failed=True
            return 7
        def snapshot(_):
            if failed:time.sleep(2)
            return SOURCES
        with tempfile.TemporaryDirectory() as tmp,patch.object(setup,'TOTAL_SECONDS',.22),patch.object(setup,'CLEANUP_SECONDS',.04),patch.object(setup,'RECEIPT_SECONDS',.03):
            root=Path(tmp);code,summary,_=self.exercise(root,child=child,snapshot=snapshot)
            self.assertEqual((code,summary['reason']),(1,'phase_failed'))
            self.assertEqual(summary['diagnostic']['exit_code'],7)
            self.assertEqual(summary['source_recheck'],'NOT_COMPLETED_DEADLINE')
            self.assertFalse((root/'private/SETUP.json').exists())

    def test_separate_source_profile_exact_schema_and_loaded_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source={}
            for name in setup.SETUP_SOURCES:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
                source[name]=setup.digest(p)
            base=dict(setup.BASE_VERIFIER_SHA256)
            base.update({'original_%d.py'%i:'0'*64 for i in range(183-len(base))})
            profile=dict(schema=1,profile=setup.PROFILE,base_commit=setup.BASE_COMMIT,
                base_profile=setup.assets.PROFILE,base_verifier_sha256=setup.BASE_VERIFIER_SHA256,
                setup_source_sha256=source,rows=16,past_tokens=0,total_budget=600)
            path=root/setup.PROFILE_PATH
            with patch.object(setup,'ROOT',root),patch.object(setup.assets,'source_snapshot',return_value=base),patch.object(setup,'IMPORTED_SETUP_SHA256',source[setup.SETUP_SOURCES[0]]):
                path.write_text(json.dumps(profile))
                result=setup.source_snapshot(False)
                self.assertEqual(len(result),187)
                self.assertEqual(setup.asset_sources(result),base)
                for field,value in (('schema',True),('rows',True),('past_tokens',False),('total_budget',True),('base_commit','a'*40),('extra',1)):
                    bad=copy.deepcopy(profile);bad[field]=value;path.write_text(json.dumps(bad))
                    with self.subTest(field=field),self.assertRaises(setup.SetupError):setup.source_snapshot(False)
                for field in ('base_verifier_sha256','setup_source_sha256'):
                    bad=copy.deepcopy(profile);bad[field][next(iter(bad[field]))]='f'*64;path.write_text(json.dumps(bad))
                    with self.subTest(field=field),self.assertRaises(setup.SetupError):setup.source_snapshot(False)
                path.write_text(json.dumps(profile))
                with patch.object(setup,'IMPORTED_SETUP_SHA256','f'*64),self.assertRaises(setup.SetupError):setup.source_snapshot(False)
                # Mutate the pathname after parsing: the frozen digest must still
                # identify the exact admitted bytes, not a second unrelated read.
                raw=path.read_bytes();parse=setup.assets.json_bytes
                def mutate(data,**kwargs):
                    value=parse(data,**kwargs)
                    path.write_bytes(b'{}')
                    return value
                with patch.object(setup.assets,'json_bytes',side_effect=mutate):
                    result=setup.source_snapshot(False)
                self.assertEqual(result[setup.PROFILE_PATH],setup.assets.sha(raw))
                self.assertNotEqual(result[setup.PROFILE_PATH],setup.digest(path))
                with self.assertRaises(setup.SetupError):setup.source_snapshot(False)

    def test_native_child_rechecks_backend_before_and_threads_after_original_gate(self):
        calls=[];torch=object()
        gate=types.ModuleType('scripts.qwen2_layer0_model_gate')
        def forward(*args,**kwargs):
            calls.append(('gate',kwargs));return {'status':'PASS_BF16_STAGE_BUDGET'}
        gate.run_gate=forward
        def identity():calls.append(('identity',None));return torch,{}
        def threads(actual):self.assertIs(actual,torch);calls.append(('threads',None))
        context={'work_deadline_ns':time.monotonic_ns()+int(2e9)}
        with patch.dict(sys.modules,{'scripts.qwen2_layer0_model_gate':gate}),patch.object(setup,'backend_identity',side_effect=identity),patch.object(setup,'backend_threads',side_effect=threads):
            setup._phase_native(context,Path('/unused'))
        self.assertEqual([x[0] for x in calls],['identity','gate','threads'])
        self.assertEqual(calls[1][1],dict(tokens=16,carried=False,threads=4))

    def test_phase_dispatch_is_fixed_original_producer_set(self):
        self.assertEqual(tuple(setup.PRODUCERS),setup.PHASES)
        self.assertEqual(setup.phase_command('native',Path('/unused'))[0],'/unused/venv/bin/python')
        self.assertEqual(setup.phase_command('preflight',Path('/unused'))[0],sys.executable)


if __name__=='__main__':unittest.main()
