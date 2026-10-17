"""Stdlib-only parent controls, adversarial metadata, and synthetic orchestration.

Real subprocesses execute only isolated stdlib signal/source-loader fixtures.
No producer, model, package installation, native library, numerical work or CI.
The final suite requires the fully assembled source root and input contract.
"""
import copy
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), module.__dict__)
    return module


R = load('cold_m128_parent_tested', HERE/'run.py')
D = load('cold_parent_m128_driver', HERE.parent/'portable_official_producer_m128/driver.py')
V = load('cold_parent_m128_verifier', HERE.parent/'portable_official_producer_m128/verify.py')
I = load('cold_parent_m128_identity', HERE.parent/'attention_packed_m128_same_host/identity.py')
HOST = dict(host_sha256='a'*64, boot_sha256='b'*64, system='Linux', machine='x86_64')
CI = dict(commit='c'*40, run_id='123', run_attempt='1')


def safe(path, limit=2*1024*1024):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('fixture symlink')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('fixture file type/alias/size')
    return path.read_bytes()


def strict(raw, limit=2*1024*1024):
    if not isinstance(raw, bytes) or len(raw)>limit: raise ValueError('fixture JSON size')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('fixture duplicate key')
            value[key] = item
        return value
    def constant(value): raise ValueError('fixture nonfinite')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def write(path, value, *, replace=False):
    raw = R.encoded(value)
    with Path(path).open('wb' if replace else 'xb') as stream: stream.write(raw)
    return R.sha(raw)


def launcher():
    return SimpleNamespace(safe=safe, strict=strict, write_new=write, host=lambda:copy.deepcopy(HOST),
        sha=R.sha, encoded=R.encoded, import_path_guard=mock.Mock())


def event(phase='fixture', pid=123):
    return dict(phase=phase, pid=pid, observed_exit_code=0, final_exit_code=0,
        owned_group_cleanup_complete=True, status='PASS')


class SourceBoundary(unittest.TestCase):
    def test_no_numerical_imports(self):
        self.assertFalse(set(('numpy','torch','ctypes','transformers','safetensors')) & sys.modules.keys())

    def test_exact_source_preflight_without_unittest_ambient(self):
        script = """import sys
from pathlib import Path
p=Path(sys.argv[1]);ns={'__name__':'isolated_parent','__file__':str(p)}
exec(compile(p.read_bytes(),str(p),'exec'),ns)
pins,L,c,R=ns['source_preflight'](p.parents[3])
if any(n in sys.modules for n in ('unittest','numpy','torch','ctypes','transformers','safetensors')):raise ValueError('ambient import')
if R.sha((p.parents[3]/ns['M16']/'run.py').read_bytes())!=ns['M16_RUN_SHA']:raise ValueError('M16 identity')
print('PASS_STDLIB_PARENT_PREFLIGHT')
"""
        result = subprocess.run([sys.executable,'-I','-B','-c',script,str(HERE/'run.py')], capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'PASS_STDLIB_PARENT_PREFLIGHT')

    def test_actual_isolated_cold_cli(self):
        result = subprocess.run([sys.executable,'-I','-B',str(HERE/'run.py'),'--root',str(ROOT),'--cold-source-check'],
            capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['status'],'PASS_COLD_SOURCE_ONLY')
        self.assertIs(value['actual_chain_executed'],False)
        self.assertEqual(value['production_interpreter_required'],[3,12,15])

    def test_complete_input_contract_and_immutable_m16(self):
        pins=R.load_pins(ROOT);old=R.load_m16(ROOT,pins);old_pins=old.load_pins(ROOT)
        self.assertEqual(R.M16_RUN_SHA,'9b997dcdfd1bca66af6451f0be0dbd6d9c2bf0712426200b00645f07ac3bd8fd')
        self.assertTrue(all(pins['inputs'].get(k)==v for k,v in old_pins['inputs'].items()))
        self.assertEqual(pins['inputs'][R.M16+'run.py'],R.M16_RUN_SHA)
        self.assertNotIn(R.SOURCE_CONTRACT,pins['composed_sources'])
        self.assertEqual(pins['workflow'],'.github/workflows/portable-same-host-m128-launch-r1.yml')
        self.assertGreater(len(pins['inputs']),len(old_pins['inputs']))

    def test_exact_budget_contract(self):
        expected=dict(total=4920,outer_term=4910,m16_routine=1950,m16_transition=30,
            producer=260,reference_work=290,reference_cleanup=299,reference_outer=300,
            prepare=120,full_work=2424,full_cleanup=2429,full_outer=2430,numeric=2400)
        self.assertEqual(R.BUDGETS,expected)
        self.assertEqual(R.load_pins(ROOT)['budgets'],expected)

    def test_input_contract_closed_types_paths_and_budgets(self):
        L=R.load_launcher(ROOT);original=L.safe
        initial=L.strict(original(HERE/'input-contract.json'))
        mutations=[]
        for key,bad in (('schema',True),('profile','old-profile'),('workflow','.github/workflows/other.yml')):
            v=copy.deepcopy(initial);v[key]=bad;mutations.append(v)
        v=copy.deepcopy(initial);v['extra']=True;mutations.append(v)
        for key in R.BUDGETS:
            v=copy.deepcopy(initial);v['budgets'][key]+=1;mutations.append(v)
        v=copy.deepcopy(initial);v['budgets']['total']=4920.0;mutations.append(v)
        for name in ('../escape','/absolute','a//b','a/./b','a\\b',''):
            v=copy.deepcopy(initial);v['inputs'][name]='0'*64;mutations.append(v)
        v=copy.deepcopy(initial);v['composed_sources'][R.SOURCE_CONTRACT]='0'*64;mutations.append(v)
        v=copy.deepcopy(initial);v['inputs'][R.M16+'run.py']='0'*64;mutations.append(v)
        v=copy.deepcopy(initial);v['inputs'][R.OWN+'run.py']='0'*64;mutations.append(v)
        v=copy.deepcopy(initial);v['inputs']={};mutations.append(v)
        v=copy.deepcopy(initial);v['composed_sources']={str(i):'0'*64 for i in range(513)};mutations.append(v)
        for index,value in enumerate(mutations):
            raw=R.encoded(value)
            def chosen(path,limit=2*1024*1024):
                return raw if Path(path)==HERE/'input-contract.json' else original(path,limit)
            with self.subTest(index=index),mock.patch.object(R,'load_launcher',return_value=L),mock.patch.object(L,'safe',side_effect=chosen),self.assertRaises(ValueError):
                R.load_pins(ROOT)

    def test_frozen_resource_floors_and_strict_types(self):
        old=R.load_m16(ROOT);good=dict(cpu_affinity=4,available_memory_bytes=8*1024**3,available_disk_bytes=8*1024**3)
        self.assertEqual(R.resource_reserves(old,SimpleNamespace(resource_observation=lambda _:good),Path('/tmp')),good)
        for key in good:
            for bad in (True,float(good[key]),good[key]-1):
                value=dict(good);value[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):
                    R.resource_reserves(old,SimpleNamespace(resource_observation=lambda _:value),Path('/tmp'))

    def test_wrong_frozen_source_pins_rejected_before_load(self):
        for method,name in ((R.load_m16,R.M16+'run.py'),(R.load_launcher,R.LAUNCH+'launch.py')):
            with self.subTest(name=name),mock.patch.object(R,'cold_load') as call,self.assertRaises(ValueError):
                method(ROOT,{'inputs':{name:'0'*64}})
            call.assert_not_called()

    def test_cold_loader_digest_precedes_execution_and_ignores_cache(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'fixture.py';path.write_bytes(b"raise RuntimeError('executed')\n")
            with self.assertRaisesRegex(ValueError,'digest'):R.cold_load('fixture',path,'0'*64)
            raw=b'VALUE=17\n';path.write_bytes(raw);path.with_suffix('.pyc').write_bytes(b'bad pyc')
            self.assertEqual(R.cold_load('fixture',path,R.sha(raw)).VALUE,17)

    def test_cold_loader_rejects_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'fixture.py';path.write_bytes(b'VALUE=1\n');digest=R.sha(path.read_bytes())
            link=Path(td)/'link.py';link.symlink_to(path)
            with self.assertRaises(ValueError):R.cold_load('fixture',link,digest)
            link.unlink();os.link(path,link)
            with self.assertRaises(ValueError):R.cold_load('fixture',path,digest)

    def test_digest_and_canonical_types(self):
        for bad in (None,True,0,'A'*64,'a'*63,'a'*65,'g'*64):self.assertFalse(R.digest(bad))
        self.assertTrue(R.digest('a'*64));self.assertTrue(R.digest('b'*40,40))
        self.assertNotEqual(R.encoded({'x':True}),R.encoded({'x':1}))
        self.assertNotEqual(R.encoded({'x':1.0}),R.encoded({'x':1}))
        with self.assertRaises(ValueError):R.encoded(float('nan'))


class Composition(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        name=R.ENTRY+'test.py';path=root/name;path.parent.mkdir(parents=True);path.write_bytes(b'VALUE=1\n')
        pins={'composed_sources':{name:R.sha(path.read_bytes())}}
        value=dict(schema=1,profile=R.ENTRY_PROFILE,git_head=CI['commit'],sources=pins['composed_sources'],scope='FRESH_M128_ASSIGNED27_ONLY')
        write(root/R.SOURCE_CONTRACT,value)
        return root,pins,value

    def test_actual_commit_changes_contract_only(self):
        root,pins,value=self.fixture();L=launcher()
        first=R.validate_composition(L,pins,root,CI['commit'])
        value['git_head']='d'*40;write(root/R.SOURCE_CONTRACT,value,replace=True)
        second=R.validate_composition(L,pins,root,value['git_head'])
        self.assertNotEqual(first[R.SOURCE_CONTRACT],second[R.SOURCE_CONTRACT])
        self.assertEqual({k:v for k,v in first.items() if k!=R.SOURCE_CONTRACT},pins['composed_sources'])
        L.import_path_guard.assert_called_with(root,second)

    def test_historical_or_untyped_commit_rejected(self):
        for bad in ('d'*40,'D'*40,'d'*39,True):
            root,pins,_=self.fixture()
            with self.subTest(commit=bad),self.assertRaises(ValueError):R.validate_composition(launcher(),pins,root,bad)

    def test_source_and_exact_contract_bytes_bound(self):
        for kind in ('source','extra','pretty','scope','source_map'):
            root,pins,value=self.fixture()
            if kind=='source':(root/next(iter(pins['composed_sources']))).write_bytes(b'changed')
            elif kind=='pretty':(root/R.SOURCE_CONTRACT).write_text(json.dumps(value,indent=2))
            else:
                if kind=='extra':value['old_pass']=True
                elif kind=='scope':value['scope']='FRESH_M16_ASSIGNED27_ONLY'
                else:value['sources']={}
                write(root/R.SOURCE_CONTRACT,value,replace=True)
            with self.subTest(kind=kind),self.assertRaises(ValueError):R.validate_composition(launcher(),pins,root,CI['commit'])

    def test_real_import_guard_rejects_unpinned_initializer(self):
        root,pins,_=self.fixture();(root/'candidates/__init__.py').write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'initializer'):
            R.validate_composition(R.load_launcher(ROOT),pins,root,CI['commit'])


class Contexts(unittest.TestCase):
    def fixture(self,full=False):
        now=time.monotonic()
        value=dict(schema=1,profile='same-host-m128-prepare-v1',parent_pid=max(2,os.getpid()),origin='/origin',out='/out',
            ci=copy.deepcopy(CI),host=copy.deepcopy(HOST),attempt_nonce='d'*64,producer_receipt_sha256='e'*64,
            m16_prerequisite_sha256='f'*64,producer_context_sha256='1'*64,deadline_ns=time.monotonic_ns()+10**9)
        if full:
            value.pop('deadline_ns');value.update(profile='same-host-m128-run-v1',source_manifest_sha256='2'*64,
                entry_manifest_sha256='3'*64,started=now,work_deadline=now+2424,outer_deadline=now+2430)
        return value

    def read(self,value):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'context.json';digest=write(path,value)
            return R.read_context(launcher(),path,digest)

    def test_exact_prepare_and_full(self):
        for full in (False,True):
            value=self.fixture(full);self.assertEqual(self.read(value),value)

    def test_wrong_byte_digest(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'context.json';write(path,self.fixture())
            for digest in ('0'*64,'not-a-digest',True):
                with self.subTest(digest=digest),self.assertRaises(ValueError):R.read_context(launcher(),path,digest)

    def test_closed_context_fields(self):
        for full in (False,True):
            for change in ('extra','missing','profile'):
                value=self.fixture(full)
                if change=='extra':value['receipt_is_authority']=True
                elif change=='missing':value.pop('m16_prerequisite_sha256')
                else:value['profile']='same-host-m16-run-v1'
                with self.subTest(full=full,change=change),self.assertRaises(ValueError):self.read(value)

    def test_strict_schema_pid_and_prepare_time(self):
        for key,bad in (('schema',True),('schema',1.0),('parent_pid',True),('parent_pid',1),('parent_pid',2.0),
                        ('deadline_ns',True),('deadline_ns',float(time.monotonic_ns()+10**9)),('deadline_ns',time.monotonic_ns()-1)):
            value=self.fixture();value[key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.read(value)

    def test_first_ci_identity_and_closed_fields(self):
        for key,bad in (('commit','g'*40),('commit','c'*39),('run_id',True),('run_id',123),('run_id','١'),
                        ('run_id','0'),('run_id','-1'),('run_id','1.0'),('run_attempt',1),('run_attempt','2')):
            value=self.fixture();value['ci'][key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.read(value)
        value=self.fixture();value['ci']['branch']='main'
        with self.assertRaises(ValueError):self.read(value)

    def test_host_nonce_prerequisite_and_source_binding(self):
        for key in ('attempt_nonce','producer_receipt_sha256','m16_prerequisite_sha256','producer_context_sha256',
                    'source_manifest_sha256','entry_manifest_sha256'):
            for bad in (True,'a'*63,'A'*64):
                value=self.fixture(True);value[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.read(value)
        for key,bad in (('host',{}),('origin','relative'),('out','/a/../b'),('origin',1)):
            value=self.fixture();value[key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):self.read(value)

    def test_full_deadlines_are_finite_current_exact_envelope(self):
        for key in ('started','work_deadline','outer_deadline'):
            for bad in (True,float('inf'),float('nan'),0):
                value=self.fixture(True);value[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.read(value)
            value=self.fixture(True);value[key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):self.read(value)
        for started in (time.monotonic()+60,time.monotonic()-2500):
            value=self.fixture(True);value.update(started=started,work_deadline=started+2424,outer_deadline=started+2430)
            with self.subTest(started=started),self.assertRaises(ValueError):self.read(value)


class DeadlinesAndSignals(unittest.TestCase):
    def test_restore_m16_bounds_transition_and_arms_before_return(self):
        L=launcher();L.arm=mock.Mock()
        with mock.patch.object(R.time,'monotonic',return_value=100):
            self.assertEqual(R.restore_after_m16(L,1000),130);L.arm.assert_called_once_with(130)
            L.arm.reset_mock();self.assertEqual(R.restore_after_m16(L,110),110);L.arm.assert_called_once_with(110)

    def test_prepare_bounded120_keeps_complete2430_and_arms_work(self):
        for total,expected in ((5000,(220,210,219)),(2600,(170,160,169)),(2570,(140,130,139))):
            L=launcher();L.arm=mock.Mock()
            with self.subTest(total=total),mock.patch.object(R.time,'monotonic',return_value=100):
                result=R.begin_prepare(L,total)
                self.assertEqual(result,expected);self.assertLessEqual(result[0]-100,120)
                self.assertGreaterEqual(total-result[0],2430);L.arm.assert_called_once_with(expected[1])

    def test_prepare_refuses_to_borrow_full_reserve(self):
        L=launcher();L.arm=mock.Mock()
        with mock.patch.object(R.time,'monotonic',return_value=100),self.assertRaises(ValueError):R.begin_prepare(L,2569.99)
        L.arm.assert_not_called()

    def signal_fixture(self,boundary,signum):
        script="""import json,os,signal,sys,time
from pathlib import Path
p=Path(sys.argv[1]);out=Path(sys.argv[2]);boundary=sys.argv[3]
ns={'__name__':'signal_parent','__file__':str(p)};exec(compile(p.read_bytes(),str(p),'exec'),ns)
L=ns['load_launcher'](p.parents[3]);control=L.helper(p.parents[3],L.load_contract(p.parents[3]))
control.protect_cleanup()
if not all(signal.getsignal(s)==signal.SIG_IGN for s in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM)):raise ValueError('fixture not ignored')
if boundary=='receipt':
 control.arm_receipt_deadline(time.monotonic()+0.05)
 ns['begin_prepare'](L,time.monotonic()+3000)
 time.sleep(.08)
else:ns['restore_after_m16'](L,time.monotonic()+30)
if not all(callable(signal.getsignal(s)) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM)):raise ValueError('cancellation not restored')
(out/'ready').write_text('ready')
try:time.sleep(10)
except BaseException as error:
 control.protect_cleanup();(out/'receipt').write_text(json.dumps({'error':type(error).__name__,'signal':int(sys.argv[4])}))
else:raise ValueError('signal ignored')
if any(n in sys.modules for n in ('unittest','numpy','torch','ctypes','transformers','safetensors')):raise ValueError('ambient import')
"""
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)
            process=subprocess.Popen([sys.executable,'-I','-B','-c',script,str(HERE/'run.py'),str(out),boundary,str(signum)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                stop=time.monotonic()+10
                while not (out/'ready').exists() and process.poll() is None and time.monotonic()<stop:time.sleep(.01)
                if not (out/'ready').exists():
                    stdout,stderr=process.communicate(timeout=3);self.fail('isolated fixture not ready: '+stdout+stderr)
                process.send_signal(signum);stdout,stderr=process.communicate(timeout=3)
                self.assertEqual(process.returncode,0,(stdout,stderr))
                self.assertEqual(json.loads((out/'receipt').read_text()),{'error':'TimeoutError','signal':signum})
            finally:
                if process.poll() is None:process.kill()
                process.communicate(timeout=3)

    def test_real_term_int_alarm_after_m16_cleanup(self):
        for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM):
            with self.subTest(signal=signum):self.signal_fixture('m16',signum)

    def test_real_term_int_alarm_after_receipt_to_prepare(self):
        for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM):
            with self.subTest(signal=signum):self.signal_fixture('receipt',signum)

    def test_real_m16_restore_alarm_expires(self):
        script="""import sys,time
from pathlib import Path
p=Path(sys.argv[1]);ns={'__name__':'alarm_fixture','__file__':str(p)};exec(compile(p.read_bytes(),str(p),'exec'),ns)
L=ns['load_launcher'](p.parents[3]);c=L.helper(p.parents[3],L.load_contract(p.parents[3]));c.protect_cleanup()
try:
 ns['restore_after_m16'](L,time.monotonic()+.05);time.sleep(2)
except TimeoutError:c.protect_cleanup();print('PASS_REAL_ALARM')
else:raise ValueError('timer not restored')
"""
        result=subprocess.run([sys.executable,'-I','-B','-c',script,str(HERE/'run.py')],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'PASS_REAL_ALARM')


class M16AndProducerContext(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)
        paths=('m16/setup/producer/PRODUCER_M16.json','m16/setup/QUALIFICATION.json',
               'm16/setup/producer/native16/RESULT.json','m16/evidence/stage_exits.json')
        for name in paths:
            path=out/name;path.parent.mkdir(parents=True,exist_ok=True);write(path,{'fixture':name})
        lib=dict(origin_root=str(out/'m16/setup/tiny/source'),
            receipt=dict(path=str(out/'m16/setup/tiny/build/compile.json'),sha256='2'*64),
            binary=dict(path=str(out/'m16/setup/tiny/build/library.so'),sha256='3'*64,bytes=256))
        m16=dict(library=lib,attempt_nonce='4'*64,host_sha256=R.sha(R.encoded(HOST)),
            runtime_identity_sha256='5'*64,source_sha256={'fixture.py':'6'*64})
        pins={'inputs':{R.PRODUCER+'driver.py':'7'*64,R.PRODUCER+'source-lock.json':'8'*64}}
        return out,m16,pins

    def test_m16_pass_zero_and_cleanup_required(self):
        out,_,_=self.fixture();path=out/'m16/evidence/stage_exits.json';good=event('full_m16')
        write(path,dict(stages=[event('other'),good]),replace=True)
        observed=R.m16_observation(launcher(),out)
        self.assertEqual(observed,{k:good[k] for k in ('pid','observed_exit_code','final_exit_code','owned_group_cleanup_complete')})
        for key,bad in (('status','FAILED'),('pid',True),('pid',1),('observed_exit_code',False),('observed_exit_code',1),
                        ('final_exit_code',False),('final_exit_code',1),('owned_group_cleanup_complete',False),('owned_group_cleanup_complete',1)):
            candidate=dict(good);candidate[key]=bad;write(path,dict(stages=[candidate]),replace=True)
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):R.m16_observation(launcher(),out)

    def test_exactly_one_m16_child_no_report_substitute(self):
        out,_,_=self.fixture();path=out/'m16/evidence/stage_exits.json'
        for stages in ([],[event('unrelated')],[event('full_m16'),event('full_m16',124)]):
            write(path,dict(status='PASS',full_m16_assigned27_pass=True,stages=stages),replace=True)
            with self.subTest(stages=len(stages)),self.assertRaises(ValueError):R.m16_observation(launcher(),out)

    def test_producer_context_same_venv_nonce_library_and_260_290_299_300(self):
        out,m16,pins=self.fixture();start=123456789012345
        context=R.make_producer_context(launcher(),pins,ROOT,out,CI,m16,'9'*64,start)
        self.assertEqual(context['profile'],'qwen2-fresh-same-host-m128-context-v1')
        self.assertEqual(context['parent_pid'],os.getpid());self.assertEqual(context['python'],str(out/'m16/setup/venv/bin/python'))
        self.assertEqual(context['attempt_nonce'],m16['attempt_nonce']);self.assertEqual(context['ci'],CI);self.assertEqual(context['host'],HOST)
        self.assertEqual(context['workspace'],str(out/'producer128'));self.assertEqual(context['upstream_workspace'],str(out/'m16/setup/producer'))
        for key,seconds in (('producer_deadline_ns',260),('deadline_ns',290),('cleanup_deadline_ns',299),('receipt_deadline_ns',300)):
            self.assertIs(type(context[key]),int);self.assertEqual(context[key],start+seconds*10**9)
        for key,path in (('producer_manifest','m16/setup/producer/PRODUCER_M16.json'),('qualification','m16/setup/QUALIFICATION.json'),
                         ('native16_result','m16/setup/producer/native16/RESULT.json')):
            self.assertEqual(context['upstream'][key],dict(path=str(out/path),sha256=R.sha(safe(out/path))))
        self.assertEqual(context['upstream']['m16_prerequisite'],dict(path=str(out/'M16_PREREQUISITE.json'),sha256='9'*64))
        self.assertEqual(context['upstream']['combined_library'],dict(receipt=m16['library']['receipt'],binary={k:m16['library']['binary'][k] for k in ('path','sha256')}))
        self.assertEqual(context['driver_sha256'],pins['inputs'][R.PRODUCER+'driver.py'])
        self.assertEqual(context['source_lock_sha256'],pins['inputs'][R.PRODUCER+'source-lock.json'])

    def test_producer_context_strict_shared_clock_type(self):
        out,m16,pins=self.fixture()
        for bad in (True,0,-1,1.0,'1'):
            with self.subTest(start=bad),self.assertRaises(ValueError):R.make_producer_context(launcher(),pins,ROOT,out,CI,m16,'9'*64,bad)

    def test_seal_m16_reverifies_complete_sources_and_current_identity(self):
        out,m16,pins=self.fixture();write(out/'m16/evidence/stage_exits.json',dict(stages=[event('full_m16')]),replace=True)
        old=SimpleNamespace(load_pins=mock.Mock(return_value={'fixture':'old'}),validate_composition=mock.Mock(return_value=m16['source_sha256']))
        P=SimpleNamespace(seal=mock.Mock(return_value=(out/'M16_PREREQUISITE.json','a'*64,m16)),verify=mock.Mock())
        with mock.patch.object(R,'prerequisite_module',return_value=P):
            self.assertEqual(R.seal_m16_prerequisite(launcher(),old,pins,ROOT,out,CI),(m16,'a'*64))
        old.validate_composition.assert_called_once_with(mock.ANY,{'fixture':'old'},out/'m16/source',CI['commit'])
        P.verify.assert_called_once_with(out/'M16_PREREQUISITE.json','a'*64,m16_root=out/'m16',parent_pid=os.getpid(),ci=CI,
            attempt_nonce=m16['attempt_nonce'],host_sha256=m16['host_sha256'],runtime_identity_sha256=m16['runtime_identity_sha256'])

    def test_seal_m16_rejects_source_host_or_verify_failure(self):
        for kind in ('source','host','path','verify'):
            out,m16,pins=self.fixture();write(out/'m16/evidence/stage_exits.json',dict(stages=[event('full_m16')]),replace=True)
            old=SimpleNamespace(load_pins=lambda _: {},validate_composition=lambda *args:dict(m16['source_sha256']))
            if kind=='source':old.validate_composition=lambda *args:{}
            if kind=='host':m16['host_sha256']='0'*64
            P=SimpleNamespace(seal=lambda *args,**kw:(out/('WRONG.json' if kind=='path' else 'M16_PREREQUISITE.json'),'a'*64,m16),
                verify=mock.Mock(side_effect=ValueError('fixture independent verification') if kind=='verify' else None))
            with self.subTest(kind=kind),mock.patch.object(R,'prerequisite_module',return_value=P),self.assertRaises(ValueError):
                R.seal_m16_prerequisite(launcher(),old,pins,ROOT,out,CI)


class ProducerQualification(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name)
        (self.out/'producer128').mkdir();(self.out/'m16/setup/producer').mkdir(parents=True)
        self.L=launcher();self.sources={'fixture/producer.py':'1'*64,'fixture/replay.py':'2'*64};self.lock='3'*64
        self.context=dict(driver_sha256='4'*64,attempt_nonce='5'*64,ci=copy.deepcopy(CI),host=copy.deepcopy(HOST),
            upstream=dict(m16_prerequisite=dict(path=str(self.out/'M16_PREREQUISITE.json'),sha256='6'*64),
                combined_library=dict(receipt=dict(path='/same/compile.json',sha256='7'*64),binary=dict(path='/same/library.so',sha256='8'*64))))
        self.context_sha=write(self.out/'M128_CONTEXT.json',self.context)
        self.runtime=dict(python='3.12.15',torch='fixture-measured');self.observation=dict(host=copy.deepcopy(HOST),threads=4)
        write(self.out/'m16/setup/producer/PRODUCER_M16.json',dict(runtime_identity=self.runtime,runtime_observation=self.observation))
        self.value=dict(schema=1,profile=D.PROFILE,status=D.STATUS,rows=128,past_tokens=0,attempt_nonce=self.context['attempt_nonce'],ci=copy.deepcopy(CI),
            host=copy.deepcopy(HOST),roots=dict(current=str(self.out/'producer128'),upstream=str(self.out/'m16/setup/producer')),
            upstream=copy.deepcopy(self.context['upstream']),parent_context_sha256=self.context_sha,runtime_identity=copy.deepcopy(self.runtime),
            runtime_observation=copy.deepcopy(self.observation),source_sha256=copy.deepcopy(self.sources),source_manifest_sha256=R.sha(R.encoded(self.sources)),
            driver_sha256=self.context['driver_sha256'],source_lock_sha256=self.lock,payload={},readonly={},
            sequential=dict(outputs={str(i):{} for i in range(22)}),reduced=dict(outputs={str(i):{} for i in range(22)}),
            native=dict(producer='generated-paired-qkv-qk.run_gate',result=dict(sha256='9'*64),
                outputs={mode:{method:{str(i):{} for i in range(29)} for method in D.METHODS} for mode in D.MODES}),
            dispatch={},libraries={},claims=copy.deepcopy(D.CLAIMS),original_small_gate_revalidated=True)
        self.pins={'inputs':{R.PRODUCER+'driver.py':'a'*64,R.PRODUCER+'verify.py':'b'*64}}
        self.child=event('fresh_producer',234);self.verified=event('independent_m128_verifier',235)
        self.rebind()

    def rebind(self):
        self.manifest_sha=write(self.out/'producer128/PRODUCER_M128.json',self.value,replace=True)
        self.verification=V.verification_receipt(D,self.value,self.manifest_sha,self.context_sha)
        write(self.out/'VERIFIED_M128_PRODUCER.json',self.verification,replace=True)

    def qualify(self):
        def module(name,path,digest):
            self.assertEqual(digest,self.pins['inputs'][R.PRODUCER+Path(path).name])
            return D if Path(path).name=='driver.py' else V
        with mock.patch.object(R,'cold_load',side_effect=module),mock.patch.object(D,'verify_sources',return_value=(self.sources,self.lock)):
            return R.qualify_m128(self.L,self.pins,ROOT,self.out,self.context,self.context_sha,self.child,self.verified)

    def test_real_manifest_and_verification_receipt_checks(self):
        q,value=self.qualify()
        self.assertEqual(value,self.value);self.assertEqual(q['status'],'PASS_FRESH_M128_PRODUCER')
        self.assertEqual(q['producer_manifest_sha256'],self.manifest_sha);self.assertEqual(q['parent_context_sha256'],self.context_sha)
        self.assertEqual(q['verifier_receipt_sha256'],R.sha(safe(self.out/'VERIFIED_M128_PRODUCER.json')))
        self.assertEqual(q['child_pid'],234);self.assertEqual(q['child_exit_code'],0)
        self.assertIs(q['owned_group_cleanup_complete'],True);self.assertIs(q['original_array_gate_revalidated'],True)
        self.assertFalse(any(q['claims'].values()))

    def test_both_owned_processes_require_typed_zero_and_cleanup(self):
        for which in ('child','verified'):
            for key,bad in (('pid',True),('pid',1),('observed_exit_code',False),('observed_exit_code',1),
                            ('final_exit_code',False),('final_exit_code',1),('owned_group_cleanup_complete',False),('owned_group_cleanup_complete',1)):
                original=copy.deepcopy(getattr(self,which));getattr(self,which)[key]=bad
                with self.subTest(which=which,key=key,bad=bad),self.assertRaises(ValueError):self.qualify()
                setattr(self,which,original)

    def test_exact_complete_source_closure_lock_and_driver(self):
        for key,bad in (('source_sha256',dict(self.sources,extra='0'*64)),('source_manifest_sha256','0'*64),
                        ('source_lock_sha256','0'*64),('driver_sha256','0'*64)):
            original=copy.deepcopy(self.value);self.value[key]=bad
            if key=='source_sha256':self.value['source_manifest_sha256']=R.sha(R.encoded(bad))
            self.rebind()
            with self.subTest(key=key),self.assertRaises(ValueError):self.qualify()
            self.value=original

    def test_parent_nonce_ci_host_upstream_and_shared_elf_binding(self):
        mutations=[('parent_context_sha256','0'*64),('attempt_nonce','0'*64),('ci',dict(CI,run_id='124')),
            ('host',dict(HOST,boot_sha256='0'*64)),('upstream',{})]
        for part in ('receipt','binary'):
            upstream=copy.deepcopy(self.context['upstream']);upstream['combined_library'][part]['sha256']='0'*64
            mutations.append(('upstream',upstream))
        upstream=copy.deepcopy(self.context['upstream']);upstream['m16_prerequisite']['sha256']='0'*64;mutations.append(('upstream',upstream))
        for key,bad in mutations:
            original=copy.deepcopy(self.value);self.value[key]=bad;self.rebind()
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.qualify()
            self.value=original

    def test_same_current_m16_m128_runtime_identity_and_observation(self):
        for key in ('runtime_identity','runtime_observation'):
            original=copy.deepcopy(self.value);self.value[key]={'different':True};self.rebind()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'runtime'):self.qualify()
            self.value=original

    def test_original_full_array_receipt_cannot_be_json_pass_shortcut(self):
        for value in ({'status':'PASS'},dict(self.verification,original_array_gate_revalidated=False),
                      dict(self.verification,native_exports=115),dict(self.verification,producer_manifest_sha256='0'*64),
                      dict(self.verification,parent_context_sha256='0'*64),dict(self.verification,extra=True)):
            write(self.out/'VERIFIED_M128_PRODUCER.json',value,replace=True)
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'replay receipt'):self.qualify()

    def test_context_and_manifest_bytes_stable_at_qualification(self):
        write(self.out/'M128_CONTEXT.json',dict(self.context,extra=True),replace=True)
        with self.assertRaisesRegex(ValueError,'byte stability'):self.qualify()
        write(self.out/'M128_CONTEXT.json',self.context,replace=True)
        original=self.L.safe;reads=[0]
        def changed(path,limit=2*1024*1024):
            raw=original(path,limit)
            if Path(path)==self.out/'producer128/PRODUCER_M128.json':
                reads[0]+=1
                if reads[0]>1:return raw+b' '
            return raw
        self.L.safe=changed
        with self.assertRaisesRegex(ValueError,'byte stability'):self.qualify()

    def test_true128_typed_shape_closed_manifest_and_false_claims(self):
        for key,bad in (('rows',16),('rows',128.0),('past_tokens',False),('original_small_gate_revalidated',False),
                        ('claims',dict(D.CLAIMS,full_29_node_acceptance=True)),('status','PASS')):
            original=copy.deepcopy(self.value);self.value[key]=bad;self.rebind()
            with self.subTest(key=key),self.assertRaises(ValueError):self.qualify()
            self.value=original


class IndependentIdentity(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name)
        root=out/'origin';target=root/R.ENTRY/'identity.py';target.parent.mkdir(parents=True)
        target.write_bytes((HERE.parent/'attention_packed_m128_same_host/identity.py').read_bytes())
        pins={'inputs':{R.ENTRY+'identity.py':R.sha(target.read_bytes())}}
        for name in ('M128_QUALIFICATION.json','M128_CONTEXT.json','M16_PREREQUISITE.json'):write(out/name,{'fixture':name})
        library=dict(origin_root='/same/source',receipt=dict(path='/same/compile',sha256='1'*64),binary=dict(path='/same/elf',sha256='2'*64,bytes=256))
        q=dict(producer_manifest_sha256='3'*64,attempt_nonce='4'*64)
        m16=dict(library=library,attempt_nonce='4'*64,ci=CI,host_sha256='5'*64,runtime_identity_sha256='6'*64,
            source_manifest_sha256='7'*64,records={'actual':{'sha256':'8'*64}})
        producer=dict(native=dict(result=dict(sha256='9'*64)))
        manifest=dict(producer_workspace=str(out/'producer128'),producer_manifest=dict(path=str(out/'producer128/PRODUCER_M128.json'),sha256='3'*64),
            producer_receipt=R.pointer(launcher(),out/'M128_QUALIFICATION.json'),producer_context=R.pointer(launcher(),out/'M128_CONTEXT.json'),
            m16_prerequisite=R.pointer(launcher(),out/'M16_PREREQUISITE.json'),library=copy.deepcopy(library))
        digest=write(out/'M128_ENTRY_MANIFEST.json',manifest)
        return root,out,pins,q,producer,m16,manifest,digest

    def test_exact_independent_identity_projection(self):
        root,out,pins,q,producer,m16,manifest,digest=self.fixture()
        value=R.independent_identity(launcher(),pins,root,out,q,producer,m16,digest)
        self.assertEqual(value,I.terminal_identity(manifest,producer,q,m16,digest))
        self.assertEqual(value['library'],m16['library']);self.assertEqual(value['native_result_sha256'],'9'*64)
        self.assertIs(value['m16_prerequisite']['m128_verdict_inherited'],False)

    def test_each_manifest_pointer_elf_and_bytes_are_bound(self):
        for key in ('producer_manifest','producer_receipt','producer_context','m16_prerequisite','library','digest'):
            root,out,pins,q,producer,m16,manifest,digest=self.fixture()
            if key=='digest':digest='0'*64
            elif key=='library':
                manifest[key]['binary']['sha256']='0'*64;digest=write(out/'M128_ENTRY_MANIFEST.json',manifest,replace=True)
            else:
                manifest[key]['sha256']='0'*64;digest=write(out/'M128_ENTRY_MANIFEST.json',manifest,replace=True)
            with self.subTest(key=key),self.assertRaises(ValueError):R.independent_identity(launcher(),pins,root,out,q,producer,m16,digest)


class TerminalPostflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory=HERE.parent/'attention_packed_m128_same_host'
        cls.validator=load('parent_real_m128_terminal',directory/'terminal_validator.py')
        with mock.patch.dict(sys.modules,{'terminal_validator':cls.validator}):
            cls.fixtures=load('parent_terminal_stdlib_fixture',directory/'test_terminal_validator.py')

    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);out=Path(tmp.name);work=out/'full_m128'
        (work/'actual').mkdir(parents=True);(work/'snapshot').mkdir()
        snapshot=work/'snapshot/SNAPSHOT.json';summary=work/'actual/summary.json'
        receipt,snap,sources=self.fixtures.fixture(snapshot);identity=self.fixtures.fresh_identity(snap)
        snapshot.write_bytes(self.validator.encoded(snap,pretty=True));summary.write_bytes(self.validator.encoded(receipt,pretty=True))
        target=out/'source128'/R.ENTRY/'terminal_validator.py';target.parent.mkdir(parents=True)
        target.write_bytes((HERE.parent/'attention_packed_m128_same_host/terminal_validator.py').read_bytes())
        pins={'composed_sources':{R.ENTRY+'terminal_validator.py':R.sha(target.read_bytes())}}
        q=dict(attempt_nonce='a'*64,ci=copy.deepcopy(CI),host_sha256='b'*64,runtime_identity_sha256='c'*64)
        q_sha=write(out/'M128_QUALIFICATION.json',q);m16={'library':identity['library']};m_sha=write(out/'M16_PREREQUISITE.json',m16)
        validation=self.validator.validate_terminal(summary,R.sha(safe(summary)),sources,snapshot,R.sha(safe(snapshot)),fresh_identity=identity)
        child=dict(schema=1,profile=R.ENTRY_PROFILE,status='VALIDATED_FRESH_M128_CHILD_RESULT',attempt_nonce=q['attempt_nonce'],
            producer_receipt_sha256=q_sha,m16_prerequisite_sha256=m_sha,source_manifest_sha256=R.sha(R.encoded(sources)),
            summary_sha256=R.sha(safe(summary)),snapshot_sha256=R.sha(safe(snapshot)),validation=validation,
            parent_must_authenticate_exit_and_cleanup=True,full_29_node_acceptance=False,rtl_execution=False,
            hardware_recipe_acceptance=False,old_pass_inherited=False)
        write(work/'CHILD_RESULT.json',child)
        return SimpleNamespace(out=out,pins=pins,sources=sources,q=q,q_sha=q_sha,m16=m16,m_sha=m_sha,identity=identity,
            context={'started':time.monotonic()},child=event('full_m128'),L=launcher(),prerequisite=SimpleNamespace(verify=mock.Mock()))

    def check(self,a):
        with mock.patch.object(R,'prerequisite_module',return_value=a.prerequisite),mock.patch.object(R,'validate_composition',return_value=a.sources):
            return R.terminal_postflight(a.L,a.pins,ROOT,a.out,a.sources,a.q,a.q_sha,a.m16,a.m_sha,{},a.context,a.child,a.identity)

    def test_real_terminal_replayed_and_prerequisite_reverified(self):
        a=self.fixture();result=self.check(a)
        self.assertEqual(result['status'],'PASS_FRESH_SAME_HOST_M128_ASSIGNED27')
        self.assertEqual(result['validation']['assigned_official_gates'],27)
        self.assertFalse(result['validation']['execution_authenticated_by_this_validator'])
        self.assertFalse(any(result['claims'].values()));self.assertEqual(result['child_exit_code'],0)
        a.prerequisite.verify.assert_called_once_with(a.out/'M16_PREREQUISITE.json',a.m_sha,m16_root=a.out/'m16',parent_pid=os.getpid(),ci=a.q['ci'],
            attempt_nonce=a.q['attempt_nonce'],host_sha256=a.q['host_sha256'],runtime_identity_sha256=a.q['runtime_identity_sha256'],
            current_sources=a.sources,library=a.m16['library'])

    def test_exit_zero_cleanup_and_pid_are_independent_of_pass_report(self):
        for key,bad in (('pid',True),('pid',1),('observed_exit_code',False),('observed_exit_code',7),
                        ('final_exit_code',False),('final_exit_code',7),('owned_group_cleanup_complete',False)):
            a=self.fixture();a.child[key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.check(a)

    def test_child_result_exact_binding_and_scope(self):
        for key,bad in (('producer_receipt_sha256','0'*64),('m16_prerequisite_sha256','0'*64),('attempt_nonce','0'*64),
                        ('source_manifest_sha256','0'*64),('summary_sha256','0'*64),('snapshot_sha256','0'*64),
                        ('parent_must_authenticate_exit_and_cleanup',False),('full_29_node_acceptance',True),('validation',{'status':'PASS'})):
            a=self.fixture();path=a.out/'full_m128/CHILD_RESULT.json';value=strict(safe(path));value[key]=bad;write(path,value,replace=True)
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(a)

    def test_actual_metric_failure_not_overridden_by_child_pass(self):
        a=self.fixture();path=a.out/'full_m128/actual/summary.json';value=strict(safe(path))
        value['comparison']['methods']['official_self_cache']['stages']['y']['metrics']['max_abs']=1.0
        write(path,value,replace=True)
        with self.assertRaises(ValueError):self.check(a)

    def test_current_identity_rejects_historical_elf_and_native_result(self):
        for key in ('native','library','manifest'):
            a=self.fixture()
            if key=='native':a.identity['native_result_sha256']='0'*64
            elif key=='library':a.identity['library']['binary']['sha256']='0'*64
            else:a.identity['entry_manifest_sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(a)

    def test_receipt_drift_and_independent_m16_reverify_failure(self):
        for name in ('M128_QUALIFICATION.json','M16_PREREQUISITE.json'):
            a=self.fixture();write(a.out/name,{},replace=True)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'drift'):self.check(a)
        a=self.fixture();a.prerequisite.verify.side_effect=ValueError('fixture M16 replay failed')
        with self.assertRaisesRegex(ValueError,'M16 replay'):self.check(a)

    def test_composed_source_and_terminal_metadata_rechecked_after_validation(self):
        a=self.fixture()
        with mock.patch.object(R,'prerequisite_module',return_value=a.prerequisite),mock.patch.object(R,'validate_composition',return_value={}):
            with self.assertRaisesRegex(ValueError,'terminal source drift'):
                R.terminal_postflight(a.L,a.pins,ROOT,a.out,a.sources,a.q,a.q_sha,a.m16,a.m_sha,{},a.context,a.child,a.identity)
        for relative in ('full_m128/actual/summary.json','full_m128/snapshot/SNAPSHOT.json'):
            a=self.fixture();original=a.L.safe;reads=[0]
            def changed(path,limit=2*1024*1024):
                raw=original(path,limit)
                if Path(path)==a.out/relative:
                    reads[0]+=1
                    if reads[0]>1:return raw+b' '
                return raw
            a.L.safe=changed
            with self.subTest(relative=relative),self.assertRaisesRegex(ValueError,'metadata drift'):self.check(a)


class SyntheticOrchestration(unittest.TestCase):
    """All execution hooks are stdlib fixtures; real parent main is exercised."""
    def simulate(self,fail=None,*,forged_report=False,m16_code=0):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);base=Path(tmp.name)
        root=base/'origin';root.mkdir();out=base/'out';calls=[];owned_calls=[];arms=[];resources=[]
        L=launcher();clock=SimpleNamespace(monotonic=lambda:1000.0,monotonic_ns=lambda:1000*10**9)
        source_map={'fixture.py':'a'*64};pins={'inputs':{R.PRODUCER+'driver.py':'b'*64,R.PRODUCER+'source-lock.json':'c'*64},'composed_sources':source_map}
        state={'armed':False};identity={'independently_projected':'identity'}
        def arm(stop):state['armed']=True;arms.append(stop)
        def cleanup():state['armed']=False;calls.append('protect_cleanup')
        def receipt_arm(stop):state['armed']='receipt';calls.append('receipt_deadline')
        L.arm=arm;L.remaining=lambda stop:stop-1000
        L.producer_failure_diagnostic=mock.Mock(return_value=dict(status='DIAGNOSTIC_ONLY',diagnostic_only=True,acceptance=False))
        control=SimpleNamespace(c=SimpleNamespace(admit=lambda *args:CI['commit'],loader=lambda *args:{}),
            clean_environment=lambda *args:{},protect_cleanup=cleanup,arm_receipt_deadline=receipt_arm)
        def checkpoint(name):
            calls.append(name)
            if fail==name:raise ValueError('fixture failure: '+name)
        def reserve(*args):
            resources.append(state['armed'])
            if len(resources)>1:self.assertIs(state['armed'],True,'resources read before work cancellation restored')
            checkpoint('resources_'+str(len(resources)))
            return dict(cpu_affinity=4,available_memory_bytes=8*1024**3,available_disk_bytes=8*1024**3)
        def m16_main(argv):
            calls.append('m16_main');self.assertEqual(argv,['--root',str(root),'--out',str(out/'m16')])
            directory=out/'m16/evidence';directory.mkdir(parents=True)
            write(directory/'summary.json',dict(status='PASS' if forged_report or fail!='m16_main' else 'FAILED',fixture=True))
            write(directory/'stage_exits.json',dict(stages=[event('full_m16',201)]))
            write(directory/'full_m16_summary.json',dict(status='SYNTHETIC_M16_ONLY'))
            setup=out/'m16/setup/producer/native16';setup.mkdir(parents=True)
            for name in ('m16/setup/producer/PRODUCER_M16.json','m16/setup/QUALIFICATION.json','m16/setup/producer/native16/RESULT.json'):
                write(out/name,{'fixture':name})
            cleanup()
            if fail=='m16_main':raise ValueError('fixture failure: m16_main')
            return m16_code
        m16=dict(attempt_nonce='d'*64,library=dict(receipt={'path':'/shared/compile','sha256':'e'*64},
            binary={'path':'/shared/elf','sha256':'f'*64,'bytes':256}))
        def seal(*args):
            self.assertIs(state['armed'],True,'M16 receipt read before cancellation restoration');checkpoint('seal_m16')
            return m16,write(out/'M16_PREREQUISITE.json',m16)
        def owned(_L,_control,argv,**kw):
            phase=kw['phase'];owned_calls.append((phase,list(map(str,argv)),kw));calls.append(phase)
            e=event(phase,300+len(owned_calls));kw['journal'].append(e)
            if fail==phase:
                e.update(status='FAILED',observed_exit_code=7,final_exit_code=7)
                if forged_report:
                    path=out/'full_m128';path.mkdir(exist_ok=True)
                    write(path/'CHILD_RESULT.json',dict(status='VALIDATED_FRESH_M128_CHILD_RESULT',validation={'status':'PASS'}))
                cleanup();raise ValueError('fixture failure: '+phase)
            if phase=='fresh_producer':
                (out/'producer128').mkdir();write(out/'producer128/PRODUCER_M128.json',{'fixture':'producer'})
            elif phase=='independent_m128_verifier':write(out/'VERIFIED_M128_PRODUCER.json',{'fixture':'verifier'})
            elif phase=='m128_git_worktree':(out/'source128').mkdir()
            elif phase=='m128_seal':
                entry_sha=write(out/'M128_ENTRY_MANIFEST.json',{'fixture':'entry'})
                c=strict(safe(out/'M128_PREPARE_CONTEXT.json'))
                write(out/'M128_SEALED.json',dict(schema=1,profile=R.ENTRY_PROFILE,entry_manifest_sha256=entry_sha,
                    producer_receipt_sha256=c['producer_receipt_sha256'],source_manifest_sha256=R.sha(R.encoded(source_map)),
                    attempt_nonce=c['attempt_nonce'],ci=c['ci'],m16_prerequisite_sha256=c['m16_prerequisite_sha256'],
                    producer_context_sha256=c['producer_context_sha256'],terminal_identity=identity,terminal_identity_sha256=R.sha(R.encoded(identity))))
            cleanup();return e
        old=SimpleNamespace(main=m16_main,owned_phase=owned)
        def qualify(*args):
            checkpoint('qualification')
            return dict(attempt_nonce=m16['attempt_nonce'],ci=copy.deepcopy(CI),producer_manifest_sha256='1'*64,verifier_receipt_sha256='2'*64),{'fixture':'producer'}
        def composed(*args):checkpoint('composition');return source_map
        def independent(*args):checkpoint('identity');return identity
        def terminal(*args):checkpoint('terminal_postflight');return {'status':'SYNTHETIC_COLD_ONLY','claims':R.CLAIMS}
        fake_sys=SimpleNamespace(version_info=(3,12,15),flags=SimpleNamespace(isolated=1,optimize=0),dont_write_bytecode=True,executable=sys.executable)
        patches=(mock.patch.object(R,'sys',fake_sys),mock.patch.object(R,'time',clock),
            mock.patch.object(R,'source_preflight',return_value=(pins,L,control,old)),mock.patch.object(R,'resource_reserves',side_effect=reserve),
            mock.patch.object(R,'seal_m16_prerequisite',side_effect=seal),mock.patch.object(R,'qualify_m128',side_effect=qualify),
            mock.patch.object(R,'validate_composition',side_effect=composed),mock.patch.object(R,'independent_identity',side_effect=independent),
            mock.patch.object(R,'load_pins',side_effect=lambda *args:checkpoint('reload_pins') or pins),
            mock.patch.object(R,'terminal_postflight',side_effect=terminal),mock.patch.dict(os.environ,GITHUB_RUN_ID=CI['run_id'],GITHUB_RUN_ATTEMPT='1'))
        error=None;code=None
        with ExitStack() as stack:
            for patch in patches:stack.enter_context(patch)
            try:code=R.main(['--root',str(root),'--out',str(out)])
            except BaseException as exc:error=exc
        return SimpleNamespace(out=out,root=root,calls=calls,owned=owned_calls,arms=arms,resources=resources,error=error,code=code,L=L,
            summary=strict(safe(out/'evidence/summary.json')),stages=strict(safe(out/'evidence/stage_exits.json')))

    def test_one_same_process_m16_then_producer_verify_compose_seal_full(self):
        a=self.simulate();self.assertIsNone(a.error,repr(a.error));self.assertEqual(a.code,0)
        expected=['m16_main','seal_m16','fresh_producer','independent_m128_verifier','qualification','m128_git_worktree',
            'm128_compose','m128_seal','composition','identity','reload_pins','full_m128','terminal_postflight']
        self.assertEqual([n for n in a.calls if n in expected],expected)
        self.assertEqual([item[0] for item in a.owned],['fresh_producer','independent_m128_verifier','m128_git_worktree','m128_compose','m128_seal','full_m128'])
        self.assertEqual(a.summary['status'],'PASS_FRESH_SAME_HOST_M128_ASSIGNED27')
        self.assertIs(a.summary['full_m16_prerequisite_pass'],True);self.assertIs(a.summary['producer128_qualified'],True)
        self.assertIs(a.summary['full_m128_assigned27_pass'],True);self.assertFalse(any(a.summary['claims'].values()))
        self.assertEqual(a.resources,[False,True,True]);self.assertEqual(a.calls.count('m16_main'),1)
        self.assertTrue((a.out/'evidence/m16_attempt_summary.json').is_file());self.assertTrue((a.out/'evidence/producer_summary.json').is_file())
        self.assertEqual(a.stages['m16_stage_exits_sha256'],R.sha(safe(a.out/'m16/evidence/stage_exits.json')))

    def test_one_same_venv_and_exact_absolute_phase_deadlines(self):
        a=self.simulate();self.assertIsNone(a.error,repr(a.error));by={n:(argv,kw) for n,argv,kw in a.owned}
        python=str(a.out/'m16/setup/venv/bin/python')
        for name in ('fresh_producer','independent_m128_verifier','m128_compose','m128_seal','full_m128'):
            self.assertEqual(by[name][0][0],python);self.assertEqual(by[name][0][1:3],['-I','-B'])
        self.assertEqual(by['fresh_producer'][1]['work_deadline'],1260)
        self.assertEqual(by['independent_m128_verifier'][1]['work_deadline'],1290)
        for name in ('fresh_producer','independent_m128_verifier'):self.assertEqual(by[name][1]['cleanup_deadline'],1299)
        for name in ('m128_git_worktree','m128_compose','m128_seal'):
            self.assertEqual(by[name][1]['work_deadline'],1110);self.assertEqual(by[name][1]['cleanup_deadline'],1119)
        self.assertEqual(by['full_m128'][1]['work_deadline'],3424);self.assertEqual(by['full_m128'][1]['cleanup_deadline'],3429)
        self.assertEqual(by['full_m128'][1]['cwd'],a.out/'source128')
        self.assertEqual(by['m128_git_worktree'][0],['/usr/bin/git','worktree','add','--detach',str(a.out/'source128'),CI['commit']])
        context=strict(safe(a.out/'M128_RUN_CONTEXT.json'))
        self.assertEqual(context['outer_deadline']-context['started'],2430)
        self.assertEqual(context['work_deadline']-context['started'],2424)
        self.assertNotIn('cold-source-check',' '.join(v for _,argv,_ in a.owned for v in argv))

    def test_each_failure_stops_without_retry_and_preserves_receipts(self):
        order=['m16_main','seal_m16','fresh_producer','independent_m128_verifier','qualification','m128_git_worktree',
            'm128_compose','m128_seal','composition','identity','reload_pins','full_m128','terminal_postflight']
        for failing in order:
            with self.subTest(failing=failing):
                a=self.simulate(failing)
                self.assertIsInstance(a.error,ValueError);self.assertIn(failing,str(a.error))
                self.assertEqual([n for n in a.calls if n in order],order[:order.index(failing)+1])
                self.assertEqual(a.summary['status'],'FAILED_SAME_HOST_M128_ATTEMPT');self.assertFalse(a.summary['full_m128_assigned27_pass'])
                self.assertEqual(a.calls.count('m16_main'),1);self.assertFalse((a.out/'evidence/full_m128_summary.json').exists())
                self.assertTrue((a.out/'m16/evidence/summary.json').exists());self.assertTrue((a.out/'evidence/m16_attempt_summary.json').exists())
                if order.index(failing)>order.index('qualification'):self.assertTrue((a.out/'evidence/producer_summary.json').exists())
                if failing=='fresh_producer':
                    a.L.producer_failure_diagnostic.assert_called_once();self.assertFalse(a.summary['producer_failure_observation']['acceptance'])
                else:a.L.producer_failure_diagnostic.assert_not_called()

    def test_m16_return_code_typed_zero_cannot_be_forged_by_json(self):
        for bad in (False,1,None):
            with self.subTest(code=bad):
                a=self.simulate(forged_report=True,m16_code=bad)
                self.assertIsInstance(a.error,ValueError);self.assertNotIn('seal_m16',a.calls);self.assertFalse(a.owned)
                self.assertFalse(a.summary['full_m16_prerequisite_pass']);self.assertFalse(a.summary['full_m128_assigned27_pass'])

    def test_forged_full_report_cannot_replace_owned_exit_or_postflight(self):
        for phase in ('full_m128','terminal_postflight'):
            with self.subTest(phase=phase):
                a=self.simulate(phase,forged_report=True)
                self.assertIsInstance(a.error,ValueError);self.assertFalse(a.summary['full_m128_assigned27_pass'])
                self.assertFalse((a.out/'evidence/full_m128_summary.json').exists())

    def test_unavailable_full_failure_diagnostic_preserves_primary_failure(self):
        a=self.simulate('full_m128')
        self.assertIsInstance(a.error,ValueError);self.assertIn('fixture failure: full_m128',str(a.error))
        self.assertEqual(a.summary['failure_kind'],'ValueError');self.assertEqual(a.summary['phase'],'full_m128')
        self.assertEqual(a.summary['status'],'FAILED_SAME_HOST_M128_ATTEMPT')
        diagnostic=a.summary['full_m128_failure_diagnostic']
        self.assertEqual(diagnostic['reason'],'DIAGNOSTIC_UNAVAILABLE')
        self.assertIs(diagnostic['acceptance'],False);self.assertIs(diagnostic['origin_authenticated'],False)
        self.assertTrue((a.out/'evidence/producer_summary.json').is_file())
        self.assertTrue((a.out/'evidence/m16_attempt_summary.json').is_file())
        a=self.simulate('fresh_producer');self.assertIsNone(a.summary['full_m128_failure_diagnostic'])

    def test_producer_and_prepare_resources_checked_under_restored_cancellation(self):
        for name in ('resources_2','resources_3'):
            with self.subTest(name=name):
                a=self.simulate(name);self.assertIsInstance(a.error,ValueError)
                self.assertEqual(a.resources[-1],True);self.assertFalse(a.summary['full_m128_assigned27_pass'])
                self.assertNotIn('m128_git_worktree',a.calls)
                if name=='resources_2':self.assertNotIn('fresh_producer',a.calls)
                else:self.assertTrue((a.out/'evidence/producer_summary.json').is_file())


if __name__=='__main__':unittest.main()
