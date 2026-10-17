"""Cold launcher controls only: no install, build, native math or model run."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('fresh_launch',HERE/'launch.py')
L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)


class Controls(unittest.TestCase):
    def test_json_duplicate(self):
        with self.assertRaises(ValueError): L.strict(b'{"x":1,"x":2}')

    def test_json_nonfinite(self):
        for raw in (b'NaN',b'Infinity',b'1e999'):
            with self.subTest(raw=raw),self.assertRaises(ValueError): L.strict(raw)

    def test_json_oversize(self):
        with self.assertRaises(ValueError): L.strict(b' '*17,16)

    def test_json_types_remain_distinct(self):
        self.assertNotEqual(L.encoded({'x':True}),L.encoded({'x':1}))
        self.assertNotEqual(L.encoded({'x':1}),L.encoded({'x':1.0}))

    def test_exclusive_replay_preserves_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'QUALIFICATION.json';L.write_new(path,{'status':'FIRST'})
            before=path.read_bytes()
            with self.assertRaises(FileExistsError): L.write_new(path,{'status':'SECOND'})
            self.assertEqual(path.read_bytes(),before)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').write_bytes(b'a');(root/'link').symlink_to(root/'data')
            with self.assertRaises(ValueError): L.safe(root/'link')

    def test_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').write_bytes(b'a');os.link(root/'data',root/'link')
            with self.assertRaises(ValueError): L.safe(root/'data')

    def test_record_path_and_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').write_bytes(b'a')
            good=dict(path='data',bytes=1,sha256=L.sha(b'a'))
            self.assertEqual(L.record(root,good),root/'data')
            for bad in (dict(good,path='../data'),dict(good,path='/data'),dict(good,path='x\\data'),
                        dict(good,bytes=True),dict(good,sha256='0'*64),dict(good,extra=1)):
                with self.subTest(bad=bad),self.assertRaises(ValueError): L.record(root,bad)

    def test_resource_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=L.resource_observation(Path(tmp)/'new')
            self.assertEqual(set(value),{'cpu_affinity','available_memory_bytes','available_disk_bytes'})
            self.assertTrue(all(type(v) is int and v>0 for v in value.values()))

    def test_host_schema(self):
        value=L.host()
        self.assertEqual(set(value),{'host_sha256','boot_sha256','machine','system'})
        self.assertTrue(L.digest(value['host_sha256']) and L.digest(value['boot_sha256']))

    def test_production_main_rejects_replay_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'existing';out.mkdir();receipt=out/'QUALIFICATION.json';receipt.write_bytes(b'original')
            fake_flags=type('Flags',(),dict(optimize=0,isolated=1))()
            with mock.patch.object(L.sys,'version_info',(3,12,15)),mock.patch.object(L.sys,'flags',fake_flags):
                with self.assertRaisesRegex(ValueError,'fresh owned output'):
                    L.main(['--root',str(root),'--out',str(out)])
            self.assertEqual(receipt.read_bytes(),b'original')
            self.assertEqual([p.name for p in out.iterdir()],['QUALIFICATION.json'])

    def test_deadline_constants(self):
        self.assertEqual((L.WORK_SECONDS,L.CLEANUP_SECONDS,L.TOTAL_SECONDS),(890,899,900))

    def test_isolated_import_is_cold(self):
        code=('import importlib.util,sys;'
              's=importlib.util.spec_from_file_location("x",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
              'bad=set(sys.modules)&{"torch","numpy","ctypes"};'
              'sys.exit(1 if bad else 0)')
        completed=subprocess.run([sys.executable,'-I','-B','-c',code,str(HERE/'launch.py')],timeout=5)
        self.assertEqual(completed.returncode,0)

    def _helper(self):
        hashes={L.CONSUMER+n:L.sha(L.safe(ROOT/L.CONSUMER/n)) for n in ('run_ci.py','contract.py')}
        return L.helper(ROOT,{'sources':hashes})

    def test_owned_actual_exec_preserves_pid_and_unmasks(self):
        control=self._helper()
        old={s:signal.getsignal(s) for s in L.SIGNALS};old_mask=signal.pthread_sigmask(signal.SIG_BLOCK,L.SIGNALS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);log=out/'actual.log';start=time.monotonic()
                code='import os,signal;print(os.getpid());print(len(signal.pthread_sigmask(signal.SIG_BLOCK,set()) & {signal.SIGALRM,signal.SIGTERM,signal.SIGINT}))'
                result=L.stage(control,[sys.executable,'-I','-B','-c',code],cwd=out,env={'PATH':'/usr/bin:/bin'},
                    log=log,cap=2,work_stop=start+3,cleanup_stop=start+4)
                self.assertEqual(log.read_text().splitlines(),[str(result['pid']),'0'])
                self.assertEqual(result['exit_code'],0);self.assertIs(result['owned_group_cleanup_complete'],True)
                with self.assertRaises(ChildProcessError): os.waitid(os.P_PID,result['pid'],os.WEXITED|os.WNOHANG|os.WNOWAIT)
        finally:
            control.protect_cleanup()
            for s,h in old.items(): signal.signal(s,h)
            signal.pthread_sigmask(signal.SIG_SETMASK,old_mask)

    def test_owned_actual_timeout_cleans(self):
        control=self._helper();old={s:signal.getsignal(s) for s in L.SIGNALS}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);start=time.monotonic();log=out/'sleep.log'
                with self.assertRaises(TimeoutError):
                    L.stage(control,[sys.executable,'-I','-B','-c','import time;time.sleep(60)'],cwd=out,
                        env={'PATH':'/usr/bin:/bin'},log=log,cap=.08,work_stop=start+1,cleanup_stop=start+2)
                self.assertLess(time.monotonic()-start,2)
        finally:
            control.protect_cleanup()
            for s,h in old.items(): signal.signal(s,h)


    def test_output_inside_source_rejected_before_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'new'
            flags=SimpleNamespace(optimize=0,isolated=1)
            with mock.patch.object(L.sys,'version_info',(3,12,15)),mock.patch.object(L.sys,'flags',flags),mock.patch.object(L,'load_contract') as contract:
                with self.assertRaisesRegex(ValueError,'disjoint'): L.main(['--root',str(root),'--out',str(out)])
                contract.assert_not_called()
            self.assertFalse(out.exists())

    def test_output_dotdot_rejected_before_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source').mkdir();(root/'existing').mkdir()
            flags=SimpleNamespace(optimize=0,isolated=1)
            with mock.patch.object(L.sys,'version_info',(3,12,15)),mock.patch.object(L.sys,'flags',flags),mock.patch.object(L,'load_contract') as contract:
                with self.assertRaisesRegex(ValueError,'fresh owned output'):
                    L.main(['--root',str(root/'source'),'--out',str(root/'existing/../new')])
                contract.assert_not_called()

    def test_owned_nonzero_retains_exit_and_cleanup(self):
        control=self._helper();old={s:signal.getsignal(s) for s in L.SIGNALS};events=[]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);start=time.monotonic()
                with self.assertRaisesRegex(ValueError,'nonzero'):
                    L.stage(control,[sys.executable,'-I','-B','-c','raise SystemExit(7)'],cwd=out,
                        env={'PATH':'/usr/bin:/bin'},log=out/'fail.log',cap=2,work_stop=start+3,cleanup_stop=start+4,journal=events,name='nonzero')
                self.assertEqual(events[0]['observed_exit_code'],7)
                self.assertEqual(events[0]['final_exit_code'],7)
                self.assertEqual(events[0]['status'],'FAILED')
                self.assertIs(events[0]['owned_group_cleanup_complete'],True)
                with self.assertRaises(ChildProcessError): os.waitid(os.P_PID,events[0]['pid'],os.WEXITED|os.WNOHANG|os.WNOWAIT)
        finally:
            control.protect_cleanup()
            for signum,handler in old.items(): signal.signal(signum,handler)

    def test_spawn_failure_keeps_no_false_cleanup(self):
        control=self._helper();old={s:signal.getsignal(s) for s in L.SIGNALS};events=[]
        try:
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(control,'spawn_owned',side_effect=OSError('cold spawn failure')):
                start=time.monotonic()
                with self.assertRaises(OSError):
                    L.stage(control,['/no-program'],cwd=tmp,env={},log=Path(tmp)/'spawn.log',cap=1,work_stop=start+2,cleanup_stop=start+3,journal=events)
                self.assertIsNone(events[0]['pid']);self.assertIsNone(events[0]['final_exit_code'])
                self.assertFalse(events[0]['owned_group_cleanup_complete'])
        finally:
            control.protect_cleanup()
            for signum,handler in old.items(): signal.signal(signum,handler)

    def test_cleanup_failure_retained_even_with_zero_exit(self):
        control=self._helper();old={s:signal.getsignal(s) for s in L.SIGNALS};events=[]
        original=control.cleanup_owned
        def cleanup(owner,stop):
            original(owner,stop)
            raise RuntimeError('cold post-cleanup verification failure')
        try:
            with tempfile.TemporaryDirectory() as tmp,mock.patch.object(control,'cleanup_owned',side_effect=cleanup):
                start=time.monotonic()
                with self.assertRaises(RuntimeError):
                    L.stage(control,[sys.executable,'-I','-B','-c','pass'],cwd=tmp,env={'PATH':'/usr/bin:/bin'},
                        log=Path(tmp)/'cleanup.log',cap=2,work_stop=start+3,cleanup_stop=start+4,journal=events)
                self.assertEqual(events[0]['observed_exit_code'],0)
                self.assertEqual(events[0]['status'],'CLEANUP_FAILED')
                self.assertFalse(events[0]['owned_group_cleanup_complete'])
        finally:
            control.protect_cleanup()
            for signum,handler in old.items(): signal.signal(signum,handler)

    def test_parent_failure_summary_and_no_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);root=parent/'source';root.mkdir();out=parent/'private'
            flags=SimpleNamespace(optimize=0,isolated=1)
            control=SimpleNamespace(c=SimpleNamespace(admit=lambda env,out:'a'*40,loader=lambda env,exe:{},validate=lambda root,here:{}),
                clean_environment=lambda out,loader:{},protect_cleanup=lambda:None,arm_receipt_deadline=lambda deadline:None)
            contract={'minimum_resources':{'cpu_affinity':1,'available_memory_bytes':1,'available_disk_bytes':1}}
            def fail(control,argv,**kw):
                kw['journal'].append(dict(phase=kw['name'],pid=123,observed_exit_code=5,final_exit_code=5,
                    owned_group_cleanup_complete=True,status='FAILED'))
                raise ValueError('cold deliberate control failure')
            with mock.patch.object(L.sys,'version_info',(3,12,15)),mock.patch.object(L.sys,'flags',flags), \
                 mock.patch.object(L,'load_contract',return_value=contract),mock.patch.object(L,'helper',return_value=control), \
                 mock.patch.object(L,'packages',return_value=(None,None)),mock.patch.object(L,'arm'),mock.patch.object(L,'stage',side_effect=fail), \
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'},clear=True):
                with self.assertRaisesRegex(ValueError,'deliberate'): L.main(['--root',str(root),'--out',str(out)])
            receipt=L.strict((out/'evidence/summary.json').read_bytes())
            self.assertEqual(receipt['status'],'FAILED_PREPARATION')
            self.assertEqual(receipt['stages'][0]['final_exit_code'],5)
            self.assertTrue(receipt['owned_groups_cleanup_complete'])
            self.assertFalse(receipt['producer_started']);self.assertFalse(receipt['observed_complete'])
            self.assertFalse((out/'QUALIFICATION.json').exists())
            self.assertIsNone(receipt['producer_failure_diagnostic'])

    def test_owned_verifier_exact_binding(self):
        producer=dict(source_manifest_sha256='a'*64,runtime_identity={'r':1},host={'h':1})
        ci=dict(commit='c'*40,run_id='1',run_attempt='1')
        receipt=dict(schema=1,profile='qwen2-fresh-parent-native-verification-v1',status='PASS_ORIGINAL_M16_NATIVE_GATES',
            attempt_nonce='d'*64,ci=ci,producer_manifest_sha256='b'*64,parent_context_sha256='e'*64,
            source_manifest_sha256='a'*64,runtime_identity_sha256=L.sha(L.encoded(producer['runtime_identity'])),
            host_sha256=L.sha(L.encoded(producer['host'])),native_exports=116,original_array_gate_revalidated=True,
            new_forward_executed=False,claims=L.CLAIMS)
        self.assertEqual(L.validate_verifier(receipt,producer,'b'*64,'e'*64,'d'*64,ci),receipt)
        for changed in (dict(receipt,native_exports=115),dict(receipt,original_array_gate_revalidated=1),
                        dict(receipt,new_forward_executed=True),dict(receipt,parent_context_sha256='0'*64),dict(receipt,extra=0)):
            with self.subTest(changed=changed),self.assertRaises(ValueError): L.validate_verifier(changed,producer,'b'*64,'e'*64,'d'*64,ci)

    def test_all_imports_are_cold(self):
        code=('import importlib.util,sys;'
              's=importlib.util.spec_from_file_location("x",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
              'bad=set(sys.modules)&{"torch","numpy","ctypes"};sys.exit(1 if bad else 0)')
        for name in ('launch.py','package_validation.py','installed_inventory.py','verify_producer.py'):
            with self.subTest(name=name):
                completed=subprocess.run([sys.executable,'-I','-B','-c',code,str(HERE/name)],timeout=5)
                self.assertEqual(completed.returncode,0)


    def test_complete_source_and_package_contract(self):
        contract=L.load_contract(ROOT)
        self.assertGreaterEqual(len(contract['sources']),180)
        validator,lock=L.packages(ROOT,contract)
        self.assertEqual(len(lock['packages']),26)
        helper=L.helper(ROOT,contract)
        tiny=helper.c.validate(ROOT,ROOT/L.CONSUMER)
        self.assertEqual(len(tiny['source_sha256']),114)

    def test_source_drift_rejected(self):
        original=L.safe
        target=ROOT/L.PRODUCER/'driver.py'
        def read(path,*args):
            raw=original(path,*args)
            return raw+b'\n# mutated\n' if Path(path)==target else raw
        with mock.patch.object(L,'safe',side_effect=read),self.assertRaisesRegex(ValueError,'source drift'):
            L.load_contract(ROOT)

    def test_tiny_and_producer_omissions_rejected(self):
        original=L.safe
        for name in (L.CONSUMER+'worker.py',L.PRODUCER+'gate.py',L.CONSUMER+'input-contract.json'):
            def read(path,*args):
                raw=original(path,*args)
                if Path(path)==HERE/'launch-contract.json':
                    value=L.strict(raw);value['sources'].pop(name);return L.encoded(value)
                return raw
            with self.subTest(name=name),mock.patch.object(L,'safe',side_effect=read),self.assertRaises(ValueError):
                L.load_contract(ROOT)


    def _mock_pipeline(self,fail_phase=None):
        """Exercise orchestration with byte-only fixtures, never real commands."""
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);root=parent/'source';root.mkdir();out=parent/'private'
            flags=SimpleNamespace(optimize=0,isolated=1)
            tiny_contract=dict(source_sha256={'x':'1'*64},generated_sha256={'y':'2'*64})
            control=SimpleNamespace(c=SimpleNamespace(admit=lambda env,out:'a'*40,loader=lambda env,exe:{},
                validate=lambda root,here:tiny_contract,result=lambda value,commit,contract:value),
                clean_environment=lambda out,loader:{},protect_cleanup=lambda:None,arm_receipt_deadline=lambda deadline:None)
            package_validator=SimpleNamespace(validate_report=lambda value,lock,role:None,validate_inventory=lambda value,lock:None)
            contract=dict(minimum_resources=dict(cpu_affinity=1,available_memory_bytes=1,available_disk_bytes=1),
                packages=dict(bootstrap='bootstrap.lock',runtime='runtime.lock'),
                sources={L.PRODUCER+'driver.py':'3'*64,L.PRODUCER+'source-lock.json':'4'*64})
            producer=dict(source_manifest_sha256='5'*64,runtime_identity={'runtime':'fixture'},host={'host':'fixture'})
            phases=[]
            def fake_stage(control,argv,**kw):
                name=kw['name'];phases.append(name)
                event=dict(phase=name,pid=1000+len(phases),observed_exit_code=0,final_exit_code=0,
                    owned_group_cleanup_complete=True,status='PASS')
                kw['journal'].append(event)
                if name==fail_phase:
                    event.update(observed_exit_code=17,final_exit_code=17,status='FAILED')
                    raise ValueError('fixture phase failure')
                if name=='checkout_identity': (out/'head.log').write_text('a'*40+'\n')
                if name.startswith('pip_'): L.write_new(out/('pip-'+name[4:]+'-report.json'),{})
                if name=='installed_inventory': L.write_new(out/'installed.json',{})
                if name=='fresh_fixed_cases': L.write_new(out/'tiny/result.json',{'fixture':True})
                if name=='original_native_verification':
                    context=L.strict((out/'PRODUCER_CONTEXT.json').read_bytes())
                    receipt=dict(schema=1,profile='qwen2-fresh-parent-native-verification-v1',status='PASS_ORIGINAL_M16_NATIVE_GATES',
                        attempt_nonce=context['attempt_nonce'],ci=context['ci'],producer_manifest_sha256='6'*64,
                        parent_context_sha256=L.sha((out/'PRODUCER_CONTEXT.json').read_bytes()),source_manifest_sha256='5'*64,
                        runtime_identity_sha256=L.sha(L.encoded(producer['runtime_identity'])),host_sha256=L.sha(L.encoded(producer['host'])),
                        native_exports=116,original_array_gate_revalidated=True,new_forward_executed=False,claims=L.CLAIMS)
                    L.write_new(out/'VERIFIED_PRODUCER.json',receipt)
                return dict(pid=event['pid'],exit_code=0,owned_group_cleanup_complete=True)
            with mock.patch.object(L.sys,'version_info',(3,12,15)),mock.patch.object(L.sys,'flags',flags), \
                 mock.patch.object(L,'load_contract',return_value=contract),mock.patch.object(L,'helper',return_value=control), \
                 mock.patch.object(L,'packages',return_value=(package_validator,{})),mock.patch.object(L,'arm'),mock.patch.object(L,'stage',side_effect=fake_stage), \
                 mock.patch.object(L,'manifest_postflight',return_value=(producer,'6'*64)), \
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'},clear=True):
                if fail_phase:
                    with self.assertRaisesRegex(ValueError,'fixture phase failure'): L.main(['--root',str(root),'--out',str(out)])
                else: self.assertEqual(L.main(['--root',str(root),'--out',str(out)]),0)
            summary=L.strict((out/'evidence/summary.json').read_bytes())
            if fail_phase:
                self.assertFalse((out/'QUALIFICATION.json').exists());self.assertFalse(summary['observed_complete'])
                self.assertEqual(phases[-1],fail_phase)
            else:
                qualification=L.strict((out/'QUALIFICATION.json').read_bytes())
                self.assertEqual(qualification['child_pid'],1000+phases.index('fresh_producer')+1)
                self.assertNotEqual(qualification['child_pid'],summary['stages'][-1]['pid'])
                self.assertTrue(qualification['producer_native_gate_validated'])
                self.assertTrue(all(v is False for v in qualification['claims'].values()))
                self.assertTrue(summary['observed_complete'])
            return phases,summary

    def test_mocked_full_orchestration_requires_separate_verifier(self):
        phases,summary=self._mock_pipeline()
        self.assertEqual(phases,['checkout_identity','private_venv','pip_bootstrap','pip_runtime','installed_inventory',
            'fresh_fixed_cases','fresh_producer','original_native_verification'])

    def test_mocked_producer_failure_cannot_qualify(self): self._mock_pipeline('fresh_producer')

    def test_mocked_verifier_failure_cannot_qualify(self): self._mock_pipeline('original_native_verification')

    def test_mocked_provision_failure_never_starts_producer(self):
        phases,summary=self._mock_pipeline('pip_runtime')
        self.assertNotIn('fresh_producer',phases);self.assertFalse(summary['producer_started'])


    def test_checked_loader_never_uses_bytecode_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'module.py';path.write_text('value = "checked source"\n')
            with mock.patch('importlib.machinery.SourceFileLoader.exec_module',side_effect=AssertionError('cached loader used')):
                module=L.load_checked('fixture_checked',path,L.sha(path.read_bytes()))
            self.assertEqual(module.value,'checked source')
            with self.assertRaisesRegex(ValueError,'imported source identity'): L.load_checked('fixture_checked',path,'0'*64)


    def test_import_guard_rejects_cache_and_unpinned_initializers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'pkg';directory.mkdir();path=directory/'module.py';path.write_text('pass\n')
            sources={'pkg/module.py':L.sha(path.read_bytes())}
            L.import_path_guard(root,sources)
            for name in ('module.pyc','__init__.py','__init__.pyc','module'+L.importlib.machinery.EXTENSION_SUFFIXES[0]):
                extra=directory/name;extra.write_bytes(b'fixture')
                try:
                    with self.subTest(name=name),self.assertRaises(ValueError): L.import_path_guard(root,sources)
                finally: extra.unlink()
            cache=directory/'__pycache__';cache.mkdir();(cache/'module.cpython-312.pyc').write_bytes(b'fixture')
            with self.assertRaisesRegex(ValueError,'bytecode cache'): L.import_path_guard(root,sources)


    def test_actual_parent_term_cleans_owned_child(self):
        control=self._helper();old={s:signal.getsignal(s) for s in L.SIGNALS};events=[]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                start=time.monotonic()
                code='import os,signal,time;os.kill(os.getppid(),signal.SIGTERM);time.sleep(60)'
                with self.assertRaises(TimeoutError):
                    L.stage(control,[sys.executable,'-I','-B','-c',code],cwd=tmp,env={'PATH':'/usr/bin:/bin'},
                        log=Path(tmp)/'term.log',cap=2,work_stop=start+3,cleanup_stop=start+4,journal=events)
                self.assertEqual(events[0]['status'],'TIMEOUT')
                self.assertTrue(events[0]['owned_group_cleanup_complete'])
                self.assertIsInstance(events[0]['final_exit_code'],int)
                with self.assertRaises(ChildProcessError): os.waitid(os.P_PID,events[0]['pid'],os.WEXITED|os.WNOHANG|os.WNOWAIT)
        finally:
            control.protect_cleanup()
            for signum,handler in old.items(): signal.signal(signum,handler)

    def test_cleanup_does_not_signal_unrelated_child(self):
        control=self._helper();old={s:signal.getsignal(s) for s in L.SIGNALS}
        unrelated=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(60)'],start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                start=time.monotonic()
                L.stage(control,[sys.executable,'-I','-B','-c','pass'],cwd=tmp,env={'PATH':'/usr/bin:/bin'},
                    log=Path(tmp)/'pass.log',cap=2,work_stop=start+3,cleanup_stop=start+4)
                self.assertIsNone(unrelated.poll())
        finally:
            unrelated.kill();unrelated.wait(timeout=5)
            control.protect_cleanup()
            for signum,handler in old.items(): signal.signal(signum,handler)


class FailureDiagnostics(unittest.TestCase):
    def event(self,**changes):
        return dict(dict(phase='fresh_producer',pid=123,observed_exit_code=1,final_exit_code=1,
            owned_group_cleanup_complete=True,status='FAILED'),**changes)

    def source_fixture(self,base):
        root=base/'source';root.mkdir();out=base/'private';out.mkdir()
        source=root/'failing.py';source.write_text('raise ValueError("PRIVATE_MESSAGE_SENTINEL")\n')
        parser=root/L.OWN/'failure_diagnostic.py';parser.parent.mkdir(parents=True)
        parser.write_bytes((HERE/'failure_diagnostic.py').read_bytes())
        sources={p.relative_to(root).as_posix():L.sha(p.read_bytes()) for p in (source,parser)}
        return root,out,source,{'sources':sources}

    def test_real_failed_child_retains_only_safe_locations(self):
        control=Controls()._helper();old={s:signal.getsignal(s) for s in L.SIGNALS}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root,out,source,contract=self.source_fixture(Path(tmp));start=time.monotonic();journal=[]
                with self.assertRaisesRegex(ValueError,'nonzero'):
                    L.stage(control,[sys.executable,'-I','-B',source],cwd=root,env={'PATH':'/usr/bin:/bin'},
                        log=out/'producer.log',cap=2,work_stop=start+3,cleanup_stop=start+4,
                        journal=journal,name='fresh_producer')
                observed=L.producer_failure_diagnostic(root,out,contract,journal)
                self.assertEqual(observed['status'],'OBSERVED')
                self.assertEqual(observed['child_pid'],journal[0]['pid'])
                self.assertEqual(observed['observed_exit_code'],1)
                self.assertTrue(observed['diagnostic_only']);self.assertFalse(observed['origin_authenticated'])
                self.assertEqual(observed['observation']['exception_class'],'ValueError')
                self.assertEqual(observed['observation']['frames'],[dict(path='failing.py',sha256=contract['sources']['failing.py'],line=1)])
                self.assertNotIn('PRIVATE_MESSAGE_SENTINEL',L.encoded(observed).decode())
                self.assertNotIn(str(root),L.encoded(observed).decode())
                self.assertFalse((out/'QUALIFICATION.json').exists())
                self.assertTrue(journal[0]['owned_group_cleanup_complete'])
        finally:
            control.protect_cleanup()
            for signum,handler in old.items():signal.signal(signum,handler)

    def test_no_log_reads_without_one_retained_clean_failed_child(self):
        events=[[],[self.event(),self.event()], [self.event(pid=None)], [self.event(pid=True)],
            [self.event(observed_exit_code=0,final_exit_code=0)], [self.event(observed_exit_code=True)],
            [self.event(final_exit_code=2)], [self.event(owned_group_cleanup_complete=False)],
            [self.event(status='TIMEOUT')], [self.event(phase='original_native_verification')]]
        with mock.patch.object(L,'diagnostic_log') as read:
            for journal in events:
                result=L.producer_failure_diagnostic('/unread/source','/unread/private',{},journal)
                self.assertEqual(result['reason'],'OWNERSHIP_NOT_ESTABLISHED')
                self.assertIsNone(result['observation'])
            read.assert_not_called()

    def test_missing_oversize_alias_log_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,source,contract=self.source_fixture(Path(tmp));log=out/'producer.log'
            for kind in ('missing','oversize','symlink','hardlink'):
                with self.subTest(kind=kind):
                    if log.exists() or log.is_symlink():log.unlink()
                    if kind=='oversize':log.write_bytes(b'x'*65537)
                    if kind=='symlink':log.symlink_to(source)
                    if kind=='hardlink':os.link(source,log)
                    result=L.producer_failure_diagnostic(root,out,contract,[self.event()])
                    self.assertEqual(result['reason'],'LOG_UNAVAILABLE')
                    self.assertIsNone(result['observation'])

    def test_source_drift_and_parser_error_cannot_replace_original_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,source,contract=self.source_fixture(Path(tmp));(out/'producer.log').write_bytes(b'not a traceback\n')
            source.write_bytes(b'# changed\n')
            result=L.producer_failure_diagnostic(root,out,contract,[self.event()])
            self.assertEqual(result['reason'],'SOURCE_OR_PARSER_UNAVAILABLE')
            contract['sources']['failing.py']=L.sha(source.read_bytes())
            parser=SimpleNamespace(extract=mock.Mock(side_effect=ValueError('PRIVATE_EXCEPTION_SENTINEL')))
            with mock.patch.object(L,'load_checked',return_value=parser):
                result=L.producer_failure_diagnostic(root,out,contract,[self.event()])
            self.assertEqual(result['reason'],'SOURCE_OR_PARSER_UNAVAILABLE')
            self.assertNotIn('PRIVATE_EXCEPTION_SENTINEL',L.encoded(result).decode())
            self.assertEqual(result['observed_exit_code'],1)

    def test_diagnostic_work_is_bounded_and_errors_do_not_replace_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,out,source,contract=self.source_fixture(Path(tmp));(out/'producer.log').write_bytes(b'no traceback\n')
            with mock.patch.object(L.time,'monotonic',side_effect=[1.0,3.0]):
                result=L.producer_failure_diagnostic(root,out,contract,[self.event()])
            self.assertEqual(result['reason'],'DIAGNOSTIC_BUDGET')
            with mock.patch.object(L,'diagnostic_log',side_effect=TimeoutError('local read timeout')):
                result=L.producer_failure_diagnostic(root,out,contract,[self.event()])
            self.assertEqual(result['reason'],'LOG_UNAVAILABLE')
            with mock.patch.object(L,'diagnostic_log') as read:
                result=L.producer_failure_diagnostic(root,out,contract,[self.event()],deadline=0.0)
            self.assertEqual(result['reason'],'DIAGNOSTIC_BUDGET');read.assert_not_called()


    def test_diagnostic_failure_or_late_budget_preserves_original_summary(self):
        for mode in ('parser_error','near_deadline'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root,out,source,diag_contract=self.source_fixture(Path(tmp));out.rmdir()
                clock=[0.0];flags=SimpleNamespace(optimize=0,isolated=1)
                contract=dict(minimum_resources={'cpu_affinity':1,'available_memory_bytes':1,'available_disk_bytes':1},
                    sources={L.PRODUCER+'driver.py':'a'*64,L.PRODUCER+'source-lock.json':'b'*64},
                    packages={'bootstrap':'bootstrap.lock','runtime':'runtime.lock'})
                c=SimpleNamespace(admit=lambda env,out:'a'*40,loader=lambda env,exe:{},
                    validate=lambda root,here:{},result=lambda *a:{})
                control=SimpleNamespace(c=c,clean_environment=lambda out,loader:{},
                    protect_cleanup=lambda:None,arm_receipt_deadline=lambda deadline:None)
                validator=SimpleNamespace(validate_report=lambda *a:None,validate_inventory=lambda *a:None)
                def stage(control,argv,**kw):
                    name=kw['name'];entry=dict(phase=name,pid=123,observed_exit_code=0,final_exit_code=0,
                        owned_group_cleanup_complete=True,status='PASS');kw['journal'].append(entry)
                    if name=='checkout_identity':Path(kw['log']).write_text('a'*40+'\n')
                    if name in ('pip_bootstrap','pip_runtime'):
                        (out/('pip-'+name.removeprefix('pip_')+'-report.json')).write_bytes(b'{}\n')
                    if name=='installed_inventory':(out/'installed.json').write_bytes(b'{}\n')
                    if name=='fresh_fixed_cases':(out/'tiny/result.json').write_bytes(b'{}\n')
                    if name=='fresh_producer':
                        (out/'producer.log').write_bytes(b'private original log\n')
                        entry.update(observed_exit_code=1,final_exit_code=1,status='FAILED')
                        if mode=='near_deadline':clock[0]=899.0
                        raise ValueError('ORIGINAL_PRODUCER_EXIT_FAILURE')
                    return dict(pid=123,exit_code=0,owned_group_cleanup_complete=True)
                original=L.producer_failure_diagnostic
                def diagnose(root,out,unused,journal,**kw):
                    return original(root,out,diag_contract,journal,**kw)
                bad_parser=SimpleNamespace(extract=mock.Mock(side_effect=ValueError('PRIVATE_PARSER_MESSAGE')))
                with mock.patch.object(L.sys,'version_info',(3,12,15)),mock.patch.object(L.sys,'flags',flags), \
                     mock.patch.object(L,'load_contract',return_value=contract),mock.patch.object(L,'helper',return_value=control), \
                     mock.patch.object(L,'packages',return_value=(validator,None)),mock.patch.object(L,'arm'), \
                     mock.patch.object(L,'stage',side_effect=stage),mock.patch.object(L,'load_checked',return_value=bad_parser), \
                     mock.patch.object(L,'producer_failure_diagnostic',side_effect=diagnose), \
                     mock.patch.object(L.time,'monotonic',side_effect=lambda:clock[0]), \
                     mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'},clear=True):
                    with self.assertRaisesRegex(ValueError,'ORIGINAL_PRODUCER_EXIT_FAILURE'):
                        L.main(['--root',str(root),'--out',str(out)])
                summary=L.strict((out/'evidence/summary.json').read_bytes())
                self.assertEqual(summary['status'],'FAILED_PREPARATION');self.assertEqual(summary['failure_kind'],'ValueError')
                self.assertEqual(summary['phase'],'producer');self.assertFalse(summary['observed_complete'])
                expected='DIAGNOSTIC_BUDGET' if mode=='near_deadline' else 'SOURCE_OR_PARSER_UNAVAILABLE'
                self.assertEqual(summary['producer_failure_diagnostic']['reason'],expected)
                self.assertNotIn('PRIVATE_PARSER_MESSAGE',L.encoded(summary).decode())
                self.assertFalse((out/'QUALIFICATION.json').exists())
                if mode=='near_deadline':bad_parser.extract.assert_not_called()


    def test_diagnostic_reader_never_reads_beyond_64k_on_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'producer.log';path.write_bytes(b'x'*65536)
            original=Path.open;reads=[]
            class Reader:
                def __init__(self,stream):self.stream=stream
                def __enter__(self):self.stream.__enter__();return self
                def __exit__(self,*a):return self.stream.__exit__(*a)
                def fileno(self):return self.stream.fileno()
                def read(self,n):
                    reads.append(n)
                    with original(path,'ab') as growing:growing.write(b'y')
                    return self.stream.read(n)
            def opened(target,*a,**kw):return Reader(original(target,*a,**kw))
            with mock.patch.object(Path,'open',opened),self.assertRaisesRegex(ValueError,'drift'):
                L.diagnostic_log(path)
            self.assertEqual(reads,[65536])


if __name__=='__main__': unittest.main()
