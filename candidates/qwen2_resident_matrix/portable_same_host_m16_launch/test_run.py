"""Cold parent controls. Real subprocess tests execute only stdlib fixtures."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('combined_parent_tested',HERE/'run.py')
R=importlib.util.module_from_spec(spec);exec(compile((HERE/'run.py').read_bytes(),str(HERE/'run.py'),'exec'),R.__dict__)
L=R.load_launcher(ROOT)

class Inputs(unittest.TestCase):
    def test_cold_modules_only(self):
        self.assertFalse(set(('torch','numpy','ctypes','transformers','safetensors')) & sys.modules.keys())
    def test_actual_isolated_cli_source_boundary(self):
        result=subprocess.run([sys.executable,'-I','-B',str(HERE/'run.py'),'--root',str(ROOT),'--cold-source-check'],
            capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);self.assertEqual(value['status'],'PASS_COLD_SOURCE_ONLY')
        self.assertFalse(value['actual_chain_executed']);self.assertEqual(value['production_interpreter_required'],[3,12,15])
    def test_fresh_verifier_boundary_without_ambient_imports(self):
        script="""import sys,json
from pathlib import Path
root=Path(sys.argv[1]);p=root/'candidates/qwen2_resident_matrix/portable_official_producer_launch/verify_producer.py'
ns={'__name__':'cold_verifier_boundary','__file__':str(p)}
exec(compile(p.read_bytes(),str(p),'exec'),ns)
L=ns['load']('original_verifier_launcher',p.with_name('launch.py'));L.load_contract(root)
if any(n in sys.modules for n in ('unittest','torch','numpy','ctypes','transformers','safetensors')):raise ValueError('ambient dependency')
print('PASS_FRESH_VERIFIER_SOURCE_BOUNDARY')
"""
        result=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'PASS_FRESH_VERIFIER_SOURCE_BOUNDARY')
    def test_fresh_worker_boundary_without_ambient_imports(self):
        script="""import sys
from pathlib import Path
root=Path(sys.argv[1]);p=root/'candidates/qwen2_resident_matrix/portable_same_host_m16_launch/worker.py'
ns={'__name__':'cold_worker_boundary','__file__':str(p)}
exec(compile(p.read_bytes(),str(p),'exec'),ns)
api=ns['load_parent'](root);pins=api.load_pins(root);L=api.load_launcher(root,pins);L.load_contract(root)
if any(n in sys.modules for n in ('unittest','torch','numpy','ctypes','transformers','safetensors')):raise ValueError('ambient dependency')
print('PASS_FRESH_WORKER_SOURCE_BOUNDARY')
"""
        result=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'PASS_FRESH_WORKER_SOURCE_BOUNDARY')
    def test_complete_input_contract(self):
        pins=R.load_pins(ROOT)
        self.assertGreaterEqual(len(pins['inputs']),375)
        self.assertEqual(len(pins['composed_sources']),358)
        self.assertNotIn(R.SOURCE_CONTRACT,pins['composed_sources'])
    def test_frozen_setup_identity(self):
        pins=R.load_pins(ROOT)
        self.assertEqual(pins['inputs'][R.LAUNCH+'launch.py'],R.LAUNCH_SHA)
        self.assertEqual(pins['inputs'][R.LAUNCH+'launch-contract.json'],R.CONTRACT_SHA)
        self.assertEqual(L.load_contract(ROOT)['schema'],1)
    def test_contract_deadlines(self):
        pins=R.load_pins(ROOT)
        self.assertEqual(pins['budgets'],dict(total=1950,outer_term=1940,setup=900,prepare=120,full_work=924,full_cleanup=929,full_outer=930,numeric=900))
    def test_resource_reserve_types_and_floors(self):
        good=dict(cpu_affinity=4,available_memory_bytes=8*1024**3,available_disk_bytes=8*1024**3)
        self.assertEqual(R.resource_reserves(SimpleNamespace(resource_observation=lambda _:good),Path('/tmp')),good)
        for key in good:
            for bad in (True,float(good[key]),good[key]-1):
                value=dict(good);value[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):
                    R.resource_reserves(SimpleNamespace(resource_observation=lambda _:value),Path('/tmp'))
    def test_digest_strict(self):
        for value in (None,True,0,'A'*64,'a'*63,'a'*65,'g'*64):self.assertFalse(R.digest(value))
        self.assertTrue(R.digest('a'*64))
    def test_typed_canonical_comparison(self):
        self.assertNotEqual(R.encoded({'x':True}),R.encoded({'x':1}))
        self.assertNotEqual(R.encoded({'x':1.0}),R.encoded({'x':1}))
        with self.assertRaises(ValueError):R.encoded(float('nan'))
    def test_cold_loader_checks_before_exec(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'module.py';path.write_text("raise RuntimeError('executed')")
            with self.assertRaisesRegex(ValueError,'digest'):R.cold_load('fixture',path,'0'*64)
    def test_cold_loader_ignores_pyc(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'module.py';raw=b'VALUE=17\n';path.write_bytes(raw)
            path.with_suffix('.pyc').write_bytes(b'broken cached bytecode')
            self.assertEqual(R.cold_load('fixture',path,R.sha(raw)).VALUE,17)
    def test_cold_loader_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'module.py';path.write_bytes(b'VALUE=1\n');sha=R.sha(path.read_bytes())
            link=Path(td)/'link.py';link.symlink_to(path)
            with self.assertRaises(ValueError):R.cold_load('fixture',link,sha)
            link.unlink();os.link(path,link)
            with self.assertRaises(ValueError):R.cold_load('fixture',path,sha)

class Composition(unittest.TestCase):
    def fixture(self,root,commit='a'*40):
        name=R.ENTRY+'test.py';path=root/name;path.parent.mkdir(parents=True);path.write_bytes(b'VALUE=1\n')
        pins={'composed_sources':{name:R.sha(path.read_bytes())}}
        value=dict(schema=1,profile=R.ENTRY_PROFILE,git_head=commit,sources=pins['composed_sources'],scope='FRESH_M16_ASSIGNED27_ONLY')
        (root/R.SOURCE_CONTRACT).write_bytes(R.encoded(value))
        return pins,value
    def test_current_commit_regenerated(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins,value=self.fixture(root)
            first=R.validate_composition(L,pins,root,'a'*40)
            value['git_head']='b'*40;(root/R.SOURCE_CONTRACT).write_bytes(R.encoded(value))
            second=R.validate_composition(L,pins,root,'b'*40)
            self.assertNotEqual(first[R.SOURCE_CONTRACT],second[R.SOURCE_CONTRACT])
            self.assertEqual({k:v for k,v in first.items() if k!=R.SOURCE_CONTRACT},pins['composed_sources'])
    def test_historical_commit_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins,_=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'actual-commit'):R.validate_composition(L,pins,root,'b'*40)
    def test_composition_drift_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins,_=self.fixture(root);(root/next(iter(pins['composed_sources']))).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'drift'):R.validate_composition(L,pins,root,'a'*40)
    def test_extra_contract_field_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins,value=self.fixture(root);value['old_pass']=True;(root/R.SOURCE_CONTRACT).write_bytes(R.encoded(value))
            with self.assertRaises(ValueError):R.validate_composition(L,pins,root,'a'*40)
    def test_unpinned_initializer_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins,_=self.fixture(root);(root/'candidates/__init__.py').write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'initializer'):R.validate_composition(L,pins,root,'a'*40)

class Contexts(unittest.TestCase):
    def fixture(self,full=False):
        now=time.monotonic()
        value=dict(schema=1,profile='same-host-m16-prepare-v1',parent_pid=max(2,os.getpid()),origin='/origin',out='/out',
            ci=dict(commit='a'*40,run_id='1',run_attempt='1'),host=L.host(),attempt_nonce='b'*64,producer_receipt_sha256='c'*64,deadline_ns=time.monotonic_ns()+10**9)
        if full:
            value.pop('deadline_ns');value.update(profile='same-host-m16-run-v1',source_manifest_sha256='d'*64,entry_manifest_sha256='e'*64,
                started=now,work_deadline=now+924,outer_deadline=now+930)
        return value
    def read(self,value):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'context.json';raw=R.encoded(value);path.write_bytes(raw)
            return R.read_context(L,path,R.sha(raw))
    def test_exact_contexts(self):
        for full in (False,True):
            value=self.fixture(full);self.assertEqual(self.read(value),value)
    def test_wrong_context_digest(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'context.json';path.write_bytes(R.encoded(self.fixture()))
            with self.assertRaisesRegex(ValueError,'bytes'):R.read_context(L,path,'0'*64)
    def test_extra_context_keys(self):
        value=self.fixture();value['receipt_is_authority']=True
        with self.assertRaisesRegex(ValueError,'fields'):self.read(value)
    def test_boolean_pid_schema_and_deadline(self):
        for key in ('schema','parent_pid','deadline_ns'):
            value=self.fixture();value[key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):self.read(value)
    def test_parent_pid_one(self):
        value=self.fixture();value['parent_pid']=1
        with self.assertRaises(ValueError):self.read(value)
    def test_wrong_ci_or_repeat(self):
        for key,bad in (('commit','z'*40),('run_id','١'),('run_id','0'),('run_attempt','2'),('run_attempt',1)):
            value=self.fixture();value['ci'][key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.read(value)
    def test_host_nonce_paths(self):
        for key,bad in (('host',{}),('attempt_nonce','x'),('origin','relative'),('out','/a/../b')):
            value=self.fixture();value[key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):self.read(value)
    def test_expired_prepare(self):
        value=self.fixture();value['deadline_ns']=time.monotonic_ns()-1
        with self.assertRaises(ValueError):self.read(value)
    def test_full_budget_cannot_extend(self):
        for key,extra in (('work_deadline',1),('outer_deadline',1),('started',1)):
            value=self.fixture(True);value[key]+=extra
            with self.subTest(key=key),self.assertRaises(ValueError):self.read(value)
    def test_full_nonfinite_or_boolean(self):
        for bad in (True,float('inf'),float('nan')):
            value=self.fixture(True);value['started']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.read(value)

class OwnedProcesses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.control=L.helper(ROOT,L.load_contract(ROOT))
    def tearDown(self):self.control.protect_cleanup()
    def run_child(self,script,limit=2):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);journal=[];start=time.monotonic()
            try:
                event=R.owned_phase(L,self.control,[sys.executable,'-I','-B','-c',script],cwd=root,
                    env={'PATH':'/usr/bin:/bin'},log=root/'child.log',work_deadline=start+limit,cleanup_deadline=start+limit+1,
                    journal=journal,phase='stdlib_fixture')
                return event,journal
            except BaseException as error:return error,journal
    def test_owned_zero_observed_before_cleanup(self):
        event,journal=self.run_child('pass')
        self.assertIsInstance(event,dict);self.assertEqual(event['observed_exit_code'],0);self.assertEqual(event['final_exit_code'],0)
        self.assertTrue(event['owned_group_cleanup_complete']);self.assertEqual(event['status'],'PASS');self.assertGreater(event['pid'],1)
        self.assertEqual(event['timing_diagnostic']['status'],'AVAILABLE');self.assertIs(event['timing_diagnostic']['acceptance'],False)
    def test_owned_nonzero_preserved(self):
        error,journal=self.run_child('raise SystemExit(7)');self.assertIsInstance(error,ValueError)
        self.assertEqual(journal[0]['observed_exit_code'],7);self.assertEqual(journal[0]['final_exit_code'],7)
        self.assertTrue(journal[0]['owned_group_cleanup_complete']);self.assertEqual(journal[0]['status'],'FAILED')
        self.assertEqual(journal[0]['timing_diagnostic']['status'],'AVAILABLE')
    def test_owned_timeout_cleanup(self):
        error,journal=self.run_child('import time; time.sleep(10)',.15)
        self.assertIsInstance(error,TimeoutError);self.assertIsNone(journal[0]['observed_exit_code'])
        self.assertTrue(journal[0]['owned_group_cleanup_complete']);self.assertEqual(journal[0]['status'],'TIMEOUT')
        self.assertEqual(journal[0]['timing_diagnostic']['reason'],'EXIT_UNOBSERVED')
    def test_cleanup_failure_never_pass(self):
        control=SimpleNamespace()
        process=SimpleNamespace(pid=123,returncode=None)
        def spawn(owner,*args,**kwargs):owner.update(process=process,identity={'pid':123})
        control.spawn_owned=spawn;control.observe_exit=lambda *a:0
        with tempfile.TemporaryDirectory() as td,mock.patch.object(L,'arm'),mock.patch.object(L,'finish_owned',side_effect=RuntimeError('fixture cleanup failure')):
            journal=[]
            with self.assertRaisesRegex(RuntimeError,'cleanup failure'):
                R.owned_phase(L,control,['unused'],cwd=td,env={},log=Path(td)/'log',work_deadline=time.monotonic()+1,cleanup_deadline=time.monotonic()+2,journal=journal,phase='fixture')
            self.assertEqual(journal[0]['status'],'CLEANUP_FAILED');self.assertFalse(journal[0]['owned_group_cleanup_complete'])
    def test_real_parent_sigterm_cleans_retained_child(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ready=root/'ready';receipt=root/'receipt.json'
            script = """import importlib.util,json,sys,time,os,signal
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_DFL)
path=Path(sys.argv[1]); root=path.parents[3]
spec=importlib.util.spec_from_file_location('cold_parent',path);R=importlib.util.module_from_spec(spec)
exec(compile(path.read_bytes(),str(path),'exec'),R.__dict__)
L=R.load_launcher(root);c=L.helper(root,L.load_contract(root));out=Path(sys.argv[2]);journal=[]
child='from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text(str(__import__(\"os\").getpid()));time.sleep(30)'
error=None
try:
 R.owned_phase(L,c,[sys.executable,'-I','-B','-c',child,out/'ready'],cwd=out,env={'PATH':'/usr/bin:/bin'},log=out/'log',work_deadline=time.monotonic()+10,cleanup_deadline=time.monotonic()+11,journal=journal,phase='signal_fixture')
except BaseException as e:error=type(e).__name__
finally:
 c.protect_cleanup();(out/'receipt.json').write_text(json.dumps({'error':error,'stages':journal}))
"""
            parent=subprocess.Popen([sys.executable,'-I','-B','-c',script,str(HERE/'run.py'),str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                stop=time.monotonic()+5
                while not ready.exists() and parent.poll() is None and time.monotonic()<stop:time.sleep(.02)
                self.assertTrue(ready.exists(), 'fixture did not start')
                pid=int(ready.read_text());parent.send_signal(signal.SIGTERM)
                stdout,stderr=parent.communicate(timeout=5)
                self.assertEqual(parent.returncode,0,(stdout,stderr));value=json.loads(receipt.read_text())
                self.assertEqual(value['error'],'TimeoutError');self.assertTrue(value['stages'][0]['owned_group_cleanup_complete'])
                self.assertEqual(value['stages'][0]['status'],'TIMEOUT')
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finally:
                if parent.poll() is None:parent.kill()
                parent.communicate(timeout=5)
    def test_unrelated_process_untouched(self):
        unrelated=subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(20)'])
        try:
            event,_=self.run_child('pass');self.assertEqual(event['status'],'PASS');self.assertIsNone(unrelated.poll())
        finally:unrelated.kill();unrelated.wait(timeout=3)

class TerminalPostflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator=L.load_checked('terminal_validator',ROOT/R.ENTRY/'terminal_validator.py',R.sha(L.safe(ROOT/R.ENTRY/'terminal_validator.py')))
        with mock.patch.dict(sys.modules,{'terminal_validator':cls.validator}):
            cls.fixture_module=L.load_checked('cold_terminal_fixture',ROOT/R.ENTRY/'test_terminal_validator.py',R.sha(L.safe(ROOT/R.ENTRY/'test_terminal_validator.py')))
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)
        work=out/'full_m16';(work/'actual').mkdir(parents=True);(work/'snapshot').mkdir()
        snapshot=work/'snapshot/SNAPSHOT.json';summary=work/'actual/summary.json'
        receipt,snap,sources=type(self).fixture_module.fixture(snapshot)
        snapshot.write_bytes(self.validator.encoded(snap,pretty=True));summary.write_bytes(self.validator.encoded(receipt,pretty=True))
        vp=out/'source'/R.ENTRY/'terminal_validator.py';vp.parent.mkdir(parents=True);vp.write_bytes(L.safe(ROOT/R.ENTRY/'terminal_validator.py'))
        pins={'composed_sources':{R.ENTRY+'terminal_validator.py':R.sha(vp.read_bytes())}}
        qualified=dict(attempt_nonce='a'*64,ci=dict(commit='b'*40,run_id='1',run_attempt='1'))
        (out/'setup').mkdir();qualified_sha=L.write_new(out/'setup/QUALIFICATION.json',qualified)
        validation=self.validator.validate_terminal(summary,R.sha(summary.read_bytes()),sources,snapshot,R.sha(snapshot.read_bytes()))
        child_result=dict(schema=1,profile=R.ENTRY_PROFILE,status='VALIDATED_FRESH_M16_CHILD_RESULT',attempt_nonce=qualified['attempt_nonce'],
            producer_receipt_sha256=qualified_sha,source_manifest_sha256=R.sha(R.encoded(sources)),summary_sha256=R.sha(summary.read_bytes()),
            snapshot_sha256=R.sha(snapshot.read_bytes()),validation=validation,parent_must_authenticate_exit_and_cleanup=True,
            full_29_node_acceptance=False,rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False)
        L.write_new(work/'CHILD_RESULT.json',child_result)
        context={'started':time.monotonic()};child=dict(pid=123,observed_exit_code=0,final_exit_code=0,owned_group_cleanup_complete=True)
        return out,pins,sources,qualified,qualified_sha,context,child
    def check(self,args):
        with mock.patch.object(R,'validate_composition',return_value=args[2]):
            return R.terminal_postflight(L,args[1],args[0],*args[2:])
    def test_parent_replays_original_terminal_validator(self):
        args=self.fixture();result=self.check(args)
        self.assertEqual(result['validation']['assigned_official_gates'],27)
        self.assertFalse(result['validation']['execution_authenticated_by_this_validator'])
        self.assertEqual(result['child_exit_code'],0);self.assertTrue(result['owned_group_cleanup_complete'])
        self.assertFalse(any(result['claims'].values()))
    def test_zero_exit_and_cleanup_are_required(self):
        for key,bad in (('observed_exit_code',1),('observed_exit_code',False),('final_exit_code',1),('final_exit_code',False),('pid',True),('owned_group_cleanup_complete',False)):
            args=self.fixture();args[-1][key]=bad
            args[-1]['timing_diagnostic']=dict(schema=1,status='AVAILABLE',diagnostic_only=True,acceptance=False,
                scope='PARENT_RUSAGE_CHILDREN_DELTA',reason=None,wall_seconds=1.0,
                reaped_children_user_cpu_seconds=1.0,reaped_children_system_cpu_seconds=0.0)
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.check(args)
    def test_child_result_cannot_substitute_admission(self):
        args=self.fixture();path=args[0]/'full_m16/CHILD_RESULT.json';value=L.strict(L.safe(path));value['producer_receipt_sha256']='f'*64;path.write_bytes(R.encoded(value))
        with self.assertRaisesRegex(ValueError,'child result'):self.check(args)
    def test_producer_qualification_drift_rejected(self):
        args=self.fixture();(args[0]/'setup/QUALIFICATION.json').write_bytes(b'{}\n')
        with self.assertRaisesRegex(ValueError,'qualification drift'):self.check(args)
    def test_original_gate_failure_recomputed_before_child_claim(self):
        args=self.fixture();path=args[0]/'full_m16/actual/summary.json';value=L.strict(L.safe(path))
        value['comparison']['methods']['official_self_cache']['stages']['y']['metrics']['max_abs']=1.0
        path.write_bytes(R.encoded(value))
        with self.assertRaises(ValueError):self.check(args)

class SyntheticOrchestration(unittest.TestCase):
    def simulate(self,fail=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);base=Path(tmp.name);root=base/'origin';root.mkdir();out=base/'out'
        ci=dict(commit='a'*40,run_id='12',run_attempt='1');calls=[];sources={'fixture.py':'f'*64}
        control=SimpleNamespace(c=SimpleNamespace(admit=lambda *a:ci['commit'],loader=lambda *a:{},validate=lambda *a:{}),
            clean_environment=lambda *a:{},protect_cleanup=lambda:None,arm_receipt_deadline=lambda *a:None)
        fake=SimpleNamespace(**{name:getattr(L,name) for name in ('safe','strict','write_new','host','encoded','sha','PROFILE','CONSUMER')})
        fake.load_contract=lambda *a:{};fake.helper=lambda *a:control;fake.arm=lambda *a:None;fake.remaining=lambda *a:1
        resource_checks=[]
        def resources(*a):
            resource_checks.append(1)
            return dict(cpu_affinity=4,available_memory_bytes=8*1024**3,available_disk_bytes=8*1024**3-(1 if fail=='resources' and len(resource_checks)>1 else 0))
        fake.resource_observation=resources
        def producer(args):
            calls.append('producer');setup=out/'setup';(setup/'evidence').mkdir(parents=True)
            event=dict(phase='producer',pid=101,observed_exit_code=0,final_exit_code=0,owned_group_cleanup_complete=True,status='PASS')
            L.write_new(setup/'evidence/summary.json',dict(observed_complete=fail!='producer',owned_groups_cleanup_complete=True,stages=[event]))
            if fail=='producer':raise RuntimeError('producer fixture')
            L.write_new(setup/'QUALIFICATION.json',dict(profile=L.PROFILE,status='PASS_FRESH_M16_PRODUCER',ci=ci,
                owned_group_cleanup_complete=True,child_exit_code=0,attempt_nonce='b'*64))
            return 0
        fake.main=producer
        def owned(*a,**kw):
            phase=kw['phase'];calls.append(phase);event=dict(phase=phase,pid=102,observed_exit_code=0,final_exit_code=0,owned_group_cleanup_complete=True,status='PASS')
            kw['journal'].append(event)
            if fail==phase:
                event.update(observed_exit_code=3,final_exit_code=3,status='FAILED');raise ValueError('phase fixture')
            if phase=='fresh_git_worktree':(out/'source').mkdir()
            if phase=='seal':
                L.write_new(out/'ENTRY_MANIFEST.json',{})
                raw=L.safe(out/'setup/QUALIFICATION.json');q=L.strict(raw)
                L.write_new(out/'SEALED.json',dict(schema=1,profile=R.ENTRY_PROFILE,entry_manifest_sha256=R.sha(L.safe(out/'ENTRY_MANIFEST.json')),
                    producer_receipt_sha256=R.sha(raw),source_manifest_sha256=R.sha(R.encoded(sources)),attempt_nonce=q['attempt_nonce'],ci=ci))
            return event
        def postflight(*a):
            calls.append('postflight')
            if fail=='postflight':raise ValueError('terminal fixture')
            return {'status':'SYNTHETIC_COLD_ONLY'}
        flags=SimpleNamespace(isolated=1,optimize=0)
        patches=(mock.patch.object(R.sys,'version_info',(3,12,15)),mock.patch.object(R.sys,'flags',flags),
            mock.patch.object(R,'load_pins',return_value={'inputs':{},'composed_sources':sources}),mock.patch.object(R,'load_launcher',return_value=fake),
            mock.patch.object(R,'owned_phase',side_effect=owned),mock.patch.object(R,'validate_composition',return_value=sources),
            mock.patch.object(R,'terminal_postflight',side_effect=postflight),mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'12','GITHUB_RUN_ATTEMPT':'1'}))
        from contextlib import ExitStack
        error=None
        with ExitStack() as stack:
            for patch in patches:stack.enter_context(patch)
            try:R.main(['--root',str(root),'--out',str(out)])
            except BaseException as value:error=value
        summary=L.strict(L.safe(out/'evidence/summary.json'))
        stages=L.strict(L.safe(out/'evidence/stage_exits.json'))['stages']
        return out,calls,summary,stages,error
    def test_all_phases_in_one_parent(self):
        out,calls,summary,stages,error=self.simulate()
        self.assertIsNone(error);self.assertEqual(calls,['producer','fresh_git_worktree','compose','seal','full_m16','postflight'])
        self.assertEqual(summary['status'],'PASS_FRESH_SAME_HOST_M16_ASSIGNED27');self.assertTrue(summary['full_m16_assigned27_pass'])
        self.assertTrue(summary['owned_groups_cleanup_complete']);self.assertFalse(any(summary['claims'].values()))
        context=L.strict(L.safe(out/'RUN_CONTEXT.json'));self.assertEqual(context['parent_pid'],os.getpid())
        self.assertEqual(context['work_deadline']-context['started'],924);self.assertEqual(context['outer_deadline']-context['started'],930)
    def test_resource_floor_rechecked_after_provisioning(self):
        _,calls,summary,_,error=self.simulate('resources')
        self.assertIsNotNone(error);self.assertEqual(calls,['producer']);self.assertTrue(summary['producer_qualified'])
        self.assertFalse(summary['full_m16_assigned27_pass']);self.assertEqual(summary['phase'],'source_and_admission')
    def test_producer_failure_stops_all_later_phases(self):
        _,calls,summary,stages,error=self.simulate('producer');self.assertIsNotNone(error);self.assertEqual(calls,['producer'])
        self.assertFalse(summary['producer_qualified']);self.assertFalse(summary['full_m16_assigned27_pass']);self.assertEqual(len(stages),1)
    def test_each_phase_failure_stops_later_work(self):
        order=['producer','fresh_git_worktree','compose','seal','full_m16','postflight']
        for phase in order[1:]:
            with self.subTest(phase=phase):
                out,calls,summary,stages,error=self.simulate(phase)
                self.assertIsNotNone(error);self.assertEqual(calls,order[:order.index(phase)+1]);self.assertFalse(summary['full_m16_assigned27_pass'])
                self.assertFalse((out/'evidence/full_m16_summary.json').exists());self.assertEqual(summary['status'],'FAILED_SAME_HOST_M16_ATTEMPT')
    def test_safe_public_receipt_inventory(self):
        out,_,_,_,error=self.simulate();self.assertIsNone(error)
        self.assertEqual({p.name for p in (out/'evidence').iterdir()},{'summary.json','source_hashes.json','producer_summary.json','full_m16_summary.json','stage_exits.json'})
    def test_no_receipt_can_broaden_claims(self):
        _,_,summary,_,_=self.simulate()
        self.assertEqual(summary['claims'],dict(full_29_node_acceptance=False,full_m128_acceptance=False,rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False))

if __name__=='__main__':unittest.main()
