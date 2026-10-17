"""Stdlib-only cold contracts. No packages, weights, compilation or model runs."""
import ast
import copy
import importlib.util
import inspect
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    exec(compile(Path(path).read_bytes(),str(path),'exec'),m.__dict__);return m

D=load('cold_m128_driver',HERE/'driver.py')
V=load('cold_m128_verifier',HERE/'verify.py')
B=D.baseline()


def context_fixture(job,start=1000):
    ci=dict(commit='a'*40,run_id='123',run_attempt='1')
    value=dict(schema=1,profile=D.CONTEXT_PROFILE,parent_pid=1234,root=str(ROOT),workspace=str(job/'producer128'),
        upstream_workspace=str(job/'m16/setup/producer'),created_ns=start,producer_deadline_ns=start+260*10**9,
        deadline_ns=start+290*10**9,cleanup_deadline_ns=start+299*10**9,receipt_deadline_ns=start+300*10**9,
        attempt_nonce='b'*64,ci=ci,host=dict(host_sha256='c'*64,boot_sha256='d'*64,machine='x86_64',system='Linux'),
        driver_sha256=D.IMPORTED_DRIVER_SHA,source_lock_sha256=D.IMPORTED_LOCK_SHA,
        python=str(job/'m16/setup/venv/bin/python'),upstream={k:{} for k in D.UPSTREAM_KEYS})
    return value


def check_context(value):
    job=Path(value['workspace']).parent
    return D.validate_context(value,ROOT,job/'producer128',1000+290*10**9,'b'*64,
        dict(commit='a'*40,run_id='123',run_attempt='1'),parent_pid=1234,now_ns=1001,
        host=dict(host_sha256='c'*64,boot_sha256='d'*64,machine='x86_64',system='Linux'),python=job/'m16/setup/venv/bin/python')


class ColdDriver(unittest.TestCase):
    def test_import_does_not_load_numerical_packages(self):
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)
        self.assertNotIn('transformers',sys.modules)

    def test_exact_source_closure(self):
        sources,lock=D.verify_sources(ROOT)
        self.assertEqual(len(sources),76)
        self.assertEqual(sources[D.BASE_REL+'driver.py'],D.BASE_SHA)
        self.assertEqual(sources[D.BASE_REL+'owned_commands.py'],'c89ea10cf44f92a54c4386907d7c51d3f01e22af750a2d2b1d50df93418f0a4a')
        self.assertEqual(lock,D.IMPORTED_LOCK_SHA)
        self.assertTrue(all(D.PREREQUISITE_REL+n in sources for n in D.PREREQUISITE_FILES))

    def test_source_drift_rejected_before_numerical_import(self):
        p=ROOT/'spec/numerical_contract.md';raw=p.read_bytes()
        try:
            p.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'source drift'):D.verify_sources(ROOT)
        finally:p.write_bytes(raw)
        D.verify_sources(ROOT)

    def test_source_cache_rejected(self):
        target=ROOT/'scripts/qwen2_layer0_model_gate.pyc'
        self.assertFalse(target.exists())
        try:
            target.write_bytes(b'not bytecode')
            with self.assertRaisesRegex(ValueError,'source cache'):D.verify_sources(ROOT)
        finally:target.unlink()

    def test_fresh_context_exact_deadlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=context_fixture(Path(tmp));self.assertEqual(check_context(value),value)
            for key,bad in (('parent_pid',1235),('attempt_nonce','0'*64),('producer_deadline_ns',1000+261*10**9),
                            ('deadline_ns',True),('cleanup_deadline_ns',1000+300*10**9),('receipt_deadline_ns',1000+301*10**9),
                            ('driver_sha256','0'*64),('source_lock_sha256','0'*64),('python','/usr/bin/python')):
                candidate=copy.deepcopy(value);candidate[key]=bad
                with self.subTest(key=key),self.assertRaises(ValueError):check_context(candidate)
            for key,bad in (('ci',dict(value['ci'],run_attempt='2')),('host',dict(value['host'],boot_sha256='0'*64))):
                candidate=copy.deepcopy(value);candidate[key]=bad
                with self.subTest(key=key),self.assertRaises(ValueError):check_context(candidate)
            candidate=copy.deepcopy(value);candidate['rows']=16
            with self.assertRaises(ValueError):check_context(candidate)

    def test_private_fresh_directories_and_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw_stages';D.fresh_directory(p)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700)
            with self.assertRaises(FileExistsError):D.fresh_directory(p)
            (p/'existing').write_text('preserve')
            with self.assertRaises(FileExistsError):D.fresh_directory(p)
            self.assertEqual((p/'existing').read_text(),'preserve')
            alias=Path(tmp)/'alias';alias.symlink_to(p)
            with self.assertRaises(ValueError):D.fresh_directory(alias)

    def test_output_namespace_and_rooted_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp);workspace=job/'producer128';workspace.mkdir()
            up=job/'m16/setup/producer';up.mkdir(parents=True)
            p=up/'payload.bin';p.write_bytes(b'payload')
            value=dict(roots=dict(current=str(workspace),upstream=str(up)))
            item=D.rooted(B.record(up,p),'upstream')
            self.assertEqual(D.resolve_artifact(workspace,value,item),p)
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,dict(item,path='../payload.bin'))
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,dict(item,root='history'))
            q=up/'alias';os.link(p,q)
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,item)
            q.unlink()
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,item)

    def test_no_isa_assignment_or_unowned_spawn(self):
        tree=ast.parse((HERE/'driver.py').read_bytes())
        forbidden={'subprocess.run','subprocess.Popen','subprocess.check_output','os.system','rms.generate_tables'}
        calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertFalse(set(calls)&forbidden)
        self.assertTrue(any(c.endswith("['owner'].run") for c in calls))
        for n in ast.walk(tree):
            if isinstance(n,(ast.Assign,ast.AugAssign)):
                self.assertNotIn('os.environ[',ast.unparse(n))

    def test_true128_native_scalar_and_arena_calls(self):
        tree=ast.parse((HERE/'driver.py').read_bytes());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        native=[n for n in calls if ast.unparse(n.func)=='native.run_gate'];self.assertEqual(len(native),1)
        keywords={k.arg:ast.unparse(k.value) for k in native[0].keywords}
        self.assertEqual(keywords['tokens'],'128');self.assertEqual(keywords['carried'],'False')
        self.assertEqual(keywords['threads'],'4');self.assertIn('native16/RESULT.json',keywords['small_gate'])
        arena=next(n for n in calls if ast.unparse(n.func)=='rms.write_arena')
        self.assertEqual(ast.literal_eval(arena.args[2]),128);self.assertEqual(ast.literal_eval(arena.args[3]),0)
        self.assertEqual(D.CAPS,dict(compile=10,arena_and_table=30,native128=120,scalar=45,independent_postflight=30))
        self.assertIn("'128',str(raw),'0'",(HERE/'driver.py').read_text())

    def test_full128_output_geometry(self):
        W=load('cold_original_workload',ROOT/'candidates/qwen2_resident_matrix/dense_block_reduce/reference/workload.py')
        inventory=W.output_inventory(128)
        self.assertEqual(len(inventory),22)
        self.assertEqual(inventory['scores.f32le'],12*128*128*4)
        self.assertEqual(inventory['cache_k.f32le'],128*2*128*4)
        self.assertEqual(inventory['phase_10_gate_recipe.f32le'],128*8960*4)
        sealed={n:dict(bytes=size) for n,size in inventory.items()};W.validate_sealed_inventory(128,sealed)
        for mutation in (dict(sealed,extra=dict(bytes=4)),{n:r for n,r in sealed.items() if n!='scores.f32le'}):
            with self.assertRaises(ValueError):W.validate_sealed_inventory(128,mutation)
        sealed['scores.f32le']['bytes']=16*16*12*4
        with self.assertRaises(ValueError):W.validate_sealed_inventory(128,sealed)
        for rows in (True,16.0,127,129):
            with self.assertRaises(ValueError):W.output_inventory(rows)

    def test_m128_dispatch_roles_use_original_parser(self):
        diag=load('cold_original_dispatch',ROOT/'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/dispatch_diagnostic.py')
        self.assertEqual(diag._role('matmul','12x128x128:12x128x128'),'ATTENTION_SQUARE')
        empty=diag.parse_verbose(b'');m=dict(gate=types.SimpleNamespace(diagnostic=diag))
        self.assertEqual(D.check_dispatch(m,dict(bf16=empty,fp32=empty)),dict(bf16=empty,fp32=empty))
        with self.assertRaises(ValueError):D.check_dispatch(m,dict(bf16=empty))
        tree=ast.parse((HERE/'driver.py').read_bytes());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='check_dispatch')
        self.assertIn('ATTENTION_SQUARE=2',ast.unparse(node));self.assertNotIn('QK=1',ast.unparse(node))

    def test_plain_isolated_entry_probes(self):
        for filename in ('driver.py','verify.py'):
            done=subprocess.run([sys.executable,'-I','-B',str(HERE/filename),'--help'],capture_output=True,text=True,timeout=10)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertIn('--context-sha256',done.stdout)


# Test-only identity-aware observation. Production cleanup code is not replaced.
class ObservationError(RuntimeError):
    pass


PROC_STATES=frozenset('RSDZTtXxKWPI')
DEAD_STATES=frozenset(('Z','X','x'))
IDENTITY_KEYS={'pid','starttime','pgid','session','ppid','state'}


def parse_proc_stat(raw):
    if type(raw) is not bytes or not raw or len(raw)>4096:
        raise ObservationError('bounded nonempty proc stat required')
    try:
        opening=raw.index(b' (');closing=raw.rindex(b')')
        pid_text=raw[:opening].decode('ascii');fields=raw[closing+1:].decode('ascii').split()
        if not pid_text.isdecimal() or closing<=opening+1 or len(fields)<50:
            raise ValueError('proc stat structure')
        if len(fields[0])!=1 or fields[0] not in PROC_STATES:
            raise ValueError('unknown process state')
        if any(not value.lstrip('-').isdecimal() or value.count('-')>1 or
               ('-' in value and not value.startswith('-')) for value in fields[1:]):
            raise ValueError('proc stat numeric field')
        result=dict(pid=int(pid_text),state=fields[0],ppid=int(fields[1]),pgid=int(fields[2]),
            session=int(fields[3]),starttime=int(fields[19]))
        if result['pid']<=0 or result['starttime']<=0 or any(result[k]<0 for k in ('ppid','pgid','session')):
            raise ValueError('proc stat numeric range')
        return result
    except (UnicodeError,ValueError) as error:
        raise ObservationError('invalid proc stat: '+str(error)) from error


def read_proc_identity(pid):
    try:
        with (Path('/proc')/str(pid)/'stat').open('rb') as stream:raw=stream.read(4097)
    except FileNotFoundError:
        return None
    result=parse_proc_stat(raw)
    if result['pid']!=pid:raise ObservationError('proc pathname PID mismatch')
    return result


def read_boot_id():
    value=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if len(value)!=36 or tuple(i for i,c in enumerate(value) if c=='-')!=(8,13,18,23) or any(
            c not in '0123456789abcdef-' for c in value):
        raise ObservationError('invalid boot identity')
    return value


def require_work_timeout(error):
    # The adapter's SIGALRM handler raises this exact work-timeout error.
    # A cleanup ValueError/ownership failure must never satisfy this predicate.
    if type(error) is not InterruptedError or str(error)!='owned command interrupted':
        raise ObservationError('expected exact owned-command work timeout')


def validate_identity(value):
    if type(value) is not dict or set(value)!=IDENTITY_KEYS:
        raise ObservationError('complete process identity required')
    if any(type(value[k]) is not int or value[k]<=0 for k in ('pid','starttime','pgid','session')) or (
            type(value['ppid']) is not int or value['ppid']<0) or (
            type(value['state']) is not str or value['state'] not in PROC_STATES):
        raise ObservationError('invalid captured process identity')


def validate_ready_manifest(value,nonce,boot,parent_pid,started_ns,end_ns):
    expected={'schema','nonce','boot_id','ready','created_ns','leader','descendants'}
    if type(value) is not dict or set(value)!=expected or type(value['schema']) is not int or value['schema']!=1:
        raise ObservationError('complete fixture manifest required')
    if value['nonce']!=nonce or value['boot_id']!=boot or value['ready'] is not True or (
            type(value['created_ns']) is not int or not started_ns<=value['created_ns']<end_ns-6*10**9):
        raise ObservationError('fixture readiness/nonce/boot/time mismatch')
    leader=value['leader'];validate_identity(leader)
    if leader['pid']!=leader['pgid'] or leader['pid']!=leader['session'] or leader['ppid']!=parent_pid or (
            leader['state'] in DEAD_STATES):
        raise ObservationError('fixture leader/session provenance')
    descendants=value['descendants']
    if type(descendants) is not list or len(descendants)!=1:
        raise ObservationError('complete ready descendant inventory required')
    seen={leader['pid']}
    for item in descendants:
        validate_identity(item)
        if item['pid'] in seen or item['ppid']!=leader['pid'] or item['pgid']!=leader['pgid'] or (
                item['session']!=leader['session'] or item['starttime']<leader['starttime'] or item['state'] in DEAD_STATES):
            raise ObservationError('fixture descendant provenance/readiness')
        seen.add(item['pid'])
    return value


def classify_identity(original,current):
    validate_identity(original)
    if current is None:return 'identity_disappeared'
    validate_identity(current)
    if current['pid']!=original['pid']:raise ObservationError('captured PID mismatch')
    if current['starttime']!=original['starttime']:return 'identity_reused_unrelated'
    if current['pgid']!=original['pgid'] or current['session']!=original['session']:
        raise ObservationError('captured original escaped owned group/session')
    if current['state']=='Z':return 'defunct_awaiting_reaper'
    if current['state'] in ('X','x'):return 'dead_transient_present'
    return 'live_or_not_proven_dead'


def scan_proc_group(manifest,tracked,end_ns,*,now=time.monotonic_ns):
    """Read-only, non-atomic scan; preserve races and fail incomplete scans."""
    scan=dict(started_ns=now(),finished_ns=None,complete=False,captured={},entries=[],
        vanished_during_read=[],raw_pid_exists={},raw_exists_observed_ns={},boot_id=None)
    def within():
        if now()>=end_ns:raise ObservationError('original deadline reached during scan')
    def read(pid):
        within();value=read_proc_identity(pid);within()
        if value is None:scan['vanished_during_read'].append(pid)
        return value
    try:
        within();scan['boot_id']=read_boot_id();within()
        if scan['boot_id']!=manifest['boot_id']:raise ObservationError('boot identity changed')
        for pid in sorted(tracked):
            within()
            try:(Path('/proc')/str(pid)).stat();exists=True
            except FileNotFoundError:exists=False
            scan['raw_pid_exists'][str(pid)]=exists;scan['raw_exists_observed_ns'][str(pid)]=now()
            scan['captured'][str(pid)]=read(pid)
        within();names=os.listdir('/proc');within()
        if len(names)>100000:raise ObservationError('proc enumeration bound exceeded')
        for name in sorted(n for n in names if n.isascii() and n.isdecimal()):
            value=read(int(name))
            if value is not None and (value['pgid']==manifest['leader']['pgid'] or value['pid'] in tracked):
                scan['entries'].append(value)
        within();scan['complete']=True
    except (ObservationError,OSError,ValueError) as error:
        scan['error']=type(error).__name__+': '+str(error)
    scan['finished_ns']=now()
    if scan['finished_ns']>=end_ns:
        scan['complete']=False;scan['error']='original deadline reached during scan'
    return scan


def observe_cleanup(manifest,end_ns,scanner,*,now=time.monotonic_ns,sleep=time.sleep):
    """No fresh timeout, signals, wait/reap claim, or unbound-PGID cleanup."""
    tracked={item['pid']:dict(item) for item in [manifest['leader'],*manifest['descendants']]}
    leader=manifest['leader'];group=leader['pgid'];session=leader['session']
    report=dict(status='FAIL_BOUNDED_IDENTITY_DISAPPEARANCE',original_end_ns=end_ns,observations=[],
        initial_raw_pid_exists=None,original_immediate_absence_predicate=None,
        executable_residue_observed=False,first_live_observed_ns=None,last_live_observed_ns=None,
        original_identity_disappearance_observed=False,group_disappearance_observed=False,
        reviewing_parent_reaped_descendants=False)
    try:
        if manifest.get('ready') is not True or not tracked or len(tracked)!=2:
            raise ObservationError('complete ready captured identities required')
        for identity in tracked.values():validate_identity(identity)
        while True:
            if now()>=end_ns:raise ObservationError('original observation budget exhausted')
            scan=scanner(manifest,tracked,end_ns);report['observations'].append(scan)
            if report['initial_raw_pid_exists'] is None:
                report['initial_raw_pid_exists']=dict(scan.get('raw_pid_exists',{}))
                descendant_pid=str(manifest['descendants'][0]['pid'])
                if descendant_pid not in scan.get('raw_pid_exists',{}):
                    raise ObservationError('missing original descendant existence observation')
                report['original_immediate_absence_predicate']=scan['raw_pid_exists'][descendant_pid] is False
            if scan.get('complete') is not True or scan.get('boot_id')!=manifest['boot_id'] or (
                    type(scan.get('started_ns')) is not int or type(scan.get('finished_ns')) is not int or
                    not scan['started_ns']<=scan['finished_ns']<end_ns or now()>=end_ns):
                raise ObservationError('incomplete, mismatched, or over-deadline group scan: '+str(scan.get('error')))
            if set(scan['captured'])!={str(pid) for pid in tracked}:
                raise ObservationError('incomplete independent captured-PID reads')
            rows=[row for row in scan['captured'].values() if row is not None]+scan['entries']
            for row in rows:validate_identity(row)
            matches=[row for row in rows if row['pid'] in tracked and
                row['starttime']==tracked[row['pid']]['starttime']]
            # Validate escapes independently of PGID enumeration, including a
            # retained unexpected group member observed in an earlier scan.
            for row in matches:classify_identity(tracked[row['pid']],row)
            if any(row['pid']==leader['pid'] for row in matches):
                raise ObservationError('direct leader still observable after helper return')
            anchored=bool(matches)
            for row in scan['entries']:
                if row['pgid']!=group:continue
                same=row['pid'] in tracked and row['starttime']==tracked[row['pid']]['starttime']
                if not same:
                    if not anchored or row['session']!=session or row['starttime']<leader['starttime'] or row['pid'] in tracked:
                        raise ObservationError('ambiguous same-number process group ownership')
                    tracked[row['pid']]=dict(row)
            states=[];present=False
            for pid,original in sorted(tracked.items()):
                found=[row for row in rows if row['pid']==pid]
                if not found:found=[None]
                for current in found:
                    state=classify_identity(original,current)
                    states.append(dict(original=original,observed=current,classification=state))
                    if state not in ('identity_disappeared','identity_reused_unrelated'):present=True
                    if state=='live_or_not_proven_dead':
                        report['executable_residue_observed']=True
                        if report['first_live_observed_ns'] is None:report['first_live_observed_ns']=scan['started_ns']
                        report['last_live_observed_ns']=scan['finished_ns']
            scan['classifications']=states
            if not present and not any(row['pgid']==group for row in scan['entries']):
                report.update(status='PASS_BOUNDED_IDENTITY_DISAPPEARANCE',
                    original_identity_disappearance_observed=True,group_disappearance_observed=True,
                    completed_scan_ns=scan['finished_ns'])
                return report
            remaining=end_ns-now()
            if remaining<=0:raise ObservationError('original observation budget exhausted')
            sleep(min(0.02,remaining/10**9))
    except (ObservationError,OSError,ValueError) as error:
        report['error']=type(error).__name__+': '+str(error)
        return report


def cleanup_fixture_source():
    # One deliberate fork, both identities ready before the atomic manifest.
    # Neither branch forks or changes its group/session after readiness.
    prefix='import json,os,sys,time,subprocess\nfrom pathlib import Path\n'
    helpers='\n'.join(inspect.getsource(value) for value in
        (ObservationError,parse_proc_stat,read_proc_identity,read_boot_id))
    return prefix+'\nPROC_STATES='+repr(PROC_STATES)+'\n'+helpers+r'''
role,out,nonce,boot=sys.argv[1:];out=Path(out)
if read_boot_id()!=boot:raise RuntimeError('fixture boot mismatch')
def atomic(path,value):
    pending=path.with_suffix('.pending');pending.write_text(json.dumps(value,sort_keys=True));pending.replace(path)
if role=='descendant':
    atomic(out/'descendant-ready.json',dict(nonce=nonce,boot_id=boot,ready=True,
        identity=read_proc_identity(os.getpid())))
    time.sleep(60)
elif role=='leader':
    child=subprocess.Popen([sys.executable,'-I','-B',__file__,'descendant',str(out),nonce,boot])
    ready=out/'descendant-ready.json'
    while not ready.exists():time.sleep(0.001)
    value=json.loads(ready.read_text())
    if value['nonce']!=nonce or value['boot_id']!=boot or value['ready'] is not True or value['identity']['pid']!=child.pid:
        raise RuntimeError('descendant readiness mismatch')
    atomic(out/'ready.json',dict(schema=1,nonce=nonce,boot_id=boot,ready=True,
        created_ns=time.monotonic_ns(),leader=read_proc_identity(os.getpid()),descendants=[value['identity']]))
    time.sleep(60)
else:raise RuntimeError('fixture role')
'''


class CleanupObservationTests(unittest.TestCase):
    def setUp(self):
        self.leader=dict(pid=100,starttime=1000,pgid=100,session=100,ppid=50,state='S')
        self.child=dict(pid=101,starttime=1001,pgid=100,session=100,ppid=100,state='S')
        self.manifest=dict(schema=1,nonce='fixture',boot_id='test-boot',ready=True,created_ns=1,
            leader=self.leader,descendants=[self.child])

    def run_sequence(self,sequence,*,end_ns=100,step_ns=10):
        clock=[0];remaining=list(sequence)
        def now():return clock[0]
        def sleep(seconds):clock[0]+=step_ns
        def scan(manifest,tracked,end):
            row=remaining.pop(0) if len(remaining)>1 else remaining[0]
            snapshot=dict(started_ns=clock[0],finished_ns=clock[0]+1,complete=True,
                boot_id=manifest['boot_id'],captured={str(pid):None for pid in tracked},entries=[],
                raw_pid_exists={str(pid):False for pid in tracked},vanished_during_read=[])
            snapshot.update(copy.deepcopy(row))
            for pid in tracked:
                if str(pid) not in snapshot['captured']:snapshot['captured'][str(pid)]=None
            clock[0]+=1
            return snapshot
        return observe_cleanup(self.manifest,end_ns,scan,now=now,sleep=sleep)

    def child_scan(self,**changes):
        row=dict(self.child,**changes)
        return dict(captured={'100':None,'101':row},entries=[row],raw_pid_exists={'100':False,'101':True})

    def test_stat_parser_command_names_and_all_numeric_fields(self):
        fields=['S','50','100','100']+['0']*46;fields[19]='1001'
        raw=('101 (name with ) and spaces) '+' '.join(fields)+'\n').encode()
        self.assertEqual(parse_proc_stat(raw),dict(self.child,ppid=50))
        self.assertEqual(parse_proc_stat(raw.replace(b'name with',b'name \xff with')),dict(self.child,ppid=50))
        for bad in (raw[:20],raw.replace(b'1001',b'-1'),raw.replace(b') S ',b') ? '),raw+b' x',b'x'*4097):
            with self.subTest(raw=bad[:40]),self.assertRaises(ObservationError):parse_proc_stat(bad)

    def test_exact_work_timeout_only(self):
        require_work_timeout(InterruptedError('owned command interrupted'))
        for error in (None,ValueError('owned command interrupted'),TimeoutError('unrelated'),InterruptedError('wrong')):
            with self.subTest(error=error),self.assertRaises(ObservationError):require_work_timeout(error)

    def test_missing_or_incomplete_readiness_manifest_rejected(self):
        value=copy.deepcopy(self.manifest);value['created_ns']=100
        validate_ready_manifest(value,'fixture','test-boot',50,1,7*10**9)
        for change in ({'ready':False},{'nonce':'other'},{'boot_id':'other'},{'descendants':[]},
                       {'descendants':[dict(self.child,starttime=0)]},{'descendants':[dict(self.child,pgid=99)]},
                       {'descendants':[dict(self.child,session=99)]},{'created_ns':7*10**9}):
            with self.subTest(change=change),self.assertRaises(ObservationError):
                validate_ready_manifest(dict(value,**change),'fixture','test-boot',50,1,7*10**9)
        for key in value:
            incomplete=dict(value);del incomplete[key]
            with self.subTest(missing=key),self.assertRaises(ObservationError):
                validate_ready_manifest(incomplete,'fixture','test-boot',50,1,7*10**9)

    def test_live_sleeping_blocked_stopped_and_traced_transients_recorded(self):
        for state in ('R','S','D','T','t','I'):
            with self.subTest(state=state):
                result=self.run_sequence([self.child_scan(state=state),{}])
                self.assertEqual(result['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE')
                self.assertTrue(result['executable_residue_observed'])
                self.assertIsNotNone(result['first_live_observed_ns'])
                self.assertFalse(result['original_immediate_absence_predicate'])

    def test_persistent_live_and_defunct_states_fail_original_bound(self):
        for state in ('S','D','T','t','Z','X','x'):
            with self.subTest(state=state):
                result=self.run_sequence([self.child_scan(state=state)])
                self.assertEqual(result['status'],'FAIL_BOUNDED_IDENTITY_DISAPPEARANCE')
                self.assertEqual(result['executable_residue_observed'],state not in DEAD_STATES)
                self.assertRegex(result['error'],'budget exhausted|over-deadline group scan')

    def test_defunct_and_dead_transient_then_disappearance_are_distinct(self):
        for state,classification in (('Z','defunct_awaiting_reaper'),('X','dead_transient_present'),('x','dead_transient_present')):
            with self.subTest(state=state):
                result=self.run_sequence([self.child_scan(state=state),{}])
                self.assertEqual(result['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE')
                self.assertFalse(result['executable_residue_observed'])
                self.assertFalse(result['reviewing_parent_reaped_descendants'])
                self.assertIn(classification,[row['classification'] for row in result['observations'][0]['classifications']])

    def test_captured_identity_group_or_session_escape_fails_immediately(self):
        for changes in ({'pgid':999},{'session':999}):
            result=self.run_sequence([self.child_scan(**changes),{}])
            self.assertEqual(result['status'],'FAIL_BOUNDED_IDENTITY_DISAPPEARANCE')
            self.assertIn('escaped',result['error']);self.assertEqual(len(result['observations']),1)

    def test_pid_reuse_unrelated_is_not_original_survival(self):
        reused=dict(self.child,starttime=2000,pgid=999,session=999)
        self.assertEqual(classify_identity(self.child,reused),'identity_reused_unrelated')
        result=self.run_sequence([dict(captured={'100':None,'101':reused},entries=[reused],
            raw_pid_exists={'100':False,'101':True})])
        self.assertEqual(result['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE')
        self.assertFalse(result['original_immediate_absence_predicate'])
        self.assertFalse(result['executable_residue_observed'])

    def test_ambiguous_same_number_group_is_inconclusive(self):
        for row in (dict(self.child,starttime=2000),dict(self.child,pid=102),dict(self.child,pid=102,session=999)):
            result=self.run_sequence([dict(entries=[row])])
            self.assertEqual(result['status'],'FAIL_BOUNDED_IDENTITY_DISAPPEARANCE')
            self.assertIn('ambiguous',result['error'])

    def test_unrecorded_bound_member_is_retained_until_it_disappears(self):
        extra=dict(self.child,pid=102,starttime=1002)
        first=self.child_scan(state='Z');first['entries'].append(extra)
        second=dict(captured={'100':None,'101':None,'102':extra},entries=[extra])
        result=self.run_sequence([first,second,{}])
        self.assertEqual(result['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE')
        self.assertTrue(result['executable_residue_observed'])
        self.assertEqual(len(result['observations']),3)
        escaped=dict(extra,pgid=999)
        result=self.run_sequence([first,dict(captured={'100':None,'101':None,'102':escaped},entries=[escaped])])
        self.assertIn('escaped',result['error'])

    def test_unrelated_other_group_excluded(self):
        result=self.run_sequence([dict(entries=[dict(self.child,pid=999,starttime=4000,pgid=800,session=800)])])
        self.assertEqual(result['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE')
        self.assertFalse(result['executable_residue_observed'])

    def test_direct_leader_defunct_is_a_separate_helper_anomaly(self):
        result=self.run_sequence([dict(captured={'100':dict(self.leader,state='Z'),'101':None},
            raw_pid_exists={'100':True,'101':False})])
        self.assertTrue(result['original_immediate_absence_predicate'])
        self.assertTrue(result['initial_raw_pid_exists']['100'])
        self.assertEqual(result['status'],'FAIL_BOUNDED_IDENTITY_DISAPPEARANCE')
        self.assertIn('direct leader',result['error'])

    def test_unknown_state_read_errors_and_incomplete_scan_fail_closed(self):
        for row in (self.child_scan(state='?'),dict(complete=False,error='permission denied'),
                    dict(complete=False,error='truncated enumeration'),dict(boot_id='other')):
            result=self.run_sequence([row])
            self.assertEqual(result['status'],'FAIL_BOUNDED_IDENTITY_DISAPPEARANCE')
        # ENOENT remains explicitly visible as a non-atomic observation race.
        result=self.run_sequence([dict(vanished_during_read=[101])])
        self.assertEqual(result['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE')
        self.assertEqual(result['observations'][0]['vanished_during_read'],[101])

    def test_no_new_budget_when_observation_starts_or_scan_ends_late(self):
        self.assertEqual(self.run_sequence([{}],end_ns=0)['observations'],[])
        result=self.run_sequence([dict(finished_ns=100)],end_ns=100)
        self.assertEqual(result['status'],'FAIL_BOUNDED_IDENTITY_DISAPPEARANCE')
        self.assertEqual(result['original_end_ns'],100)


class OwnedBoundaries(unittest.TestCase):
    def test_exact_owned_zero_and_nonzero(self):
        owner=load('cold_owned_commands',ROOT/D.BASE_REL/'owned_commands.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            result=owner.run(ROOT,[sys.executable,'-I','-B','-c','print("source-only child")'],cwd=out,
                log=out/'zero.log',end_ns=time.monotonic_ns()+8*10**9)
            self.assertEqual(result['observed_exit_code'],0);self.assertEqual(result['reaped_exit_code'],0)
            self.assertIs(result['cleanup_complete'],True)
            with self.assertRaises(ValueError):owner.run(ROOT,[sys.executable,'-I','-B','-c','raise SystemExit(7)'],cwd=out,
                log=out/'nonzero.log',end_ns=time.monotonic_ns()+8*10**9)

    def test_owned_timeout_identity_bounded_disappearance(self):
        """New bounded predicate; it does not retroactively pass the old failure."""
        owner=load('cold_owned_timeout',ROOT/D.BASE_REL/'owned_commands.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);manifest_path=out/'ready.json';nonce=os.urandom(16).hex()
            boot=read_boot_id();fixture=out/'fixture.py'
            fixture.write_text(cleanup_fixture_source())
            started_ns=time.monotonic_ns();end_ns=started_ns+7*10**9
            caught=None
            try:
                owner.run(ROOT,[sys.executable,'-I','-B',str(fixture),'leader',str(out),nonce,boot],
                    cwd=out,log=out/'timeout.log',end_ns=end_ns)
            except Exception as error:
                caught=error
            returned_ns=time.monotonic_ns()
            report=dict(status='FAIL_SETUP_OR_TIMEOUT',original_end_ns=end_ns,returned_ns=returned_ns,
                exception=None if caught is None else dict(type=type(caught).__name__,message=str(caught)),
                historical_first_failure='UNKNOWN_IDENTITY_AND_STATE_UNCHANGED',
                semantic_refinement='BOUND_ORIGINAL_IDENTITIES_DISAPPEAR_BY_ORIGINAL_DEADLINE',
                reviewing_parent_reaped_descendants=False)
            try:
                try:require_work_timeout(caught);timeout_ok=True
                except ObservationError as error:
                    timeout_ok=False;report['timeout_error']=str(error)
                if returned_ns>=end_ns:raise ObservationError('original observation budget exhausted')
                with manifest_path.open('rb') as stream:raw=stream.read(16385)
                if len(raw)>16384:raise ObservationError('bounded fixture manifest')
                manifest=json.loads(raw);report['manifest']=manifest
                validate_ready_manifest(manifest,nonce,boot,os.getpid(),started_ns,end_ns)
                observed=observe_cleanup(manifest,end_ns,scan_proc_group)
                report.update(observed)
                if not timeout_ok:
                    report['bounded_observation_status']=observed['status']
                    report['status']='FAIL_UNEXPECTED_OWNER_EXCEPTION'
            except (ObservationError,OSError,ValueError) as error:
                report['error']=type(error).__name__+': '+str(error)
            print('CLEANUP_EVIDENCE_JSON='+json.dumps(report,sort_keys=True),flush=True)
            self.assertEqual(report['status'],'PASS_BOUNDED_IDENTITY_DISAPPEARANCE',report)


if __name__=='__main__':unittest.main()
