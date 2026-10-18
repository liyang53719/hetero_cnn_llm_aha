"""Tiny synthetic files and published supervisor mocks. No network or child."""
import argparse,ast,contextlib,hashlib,io,json,os,signal,socket,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use -I -S -B')
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--worker-source',type=Path,required=True);a,extra=parser.parse_known_args()
raw=(HERE/'run_gate.py').read_bytes()
if len(raw)!=15002 or hashlib.sha256(raw).hexdigest()!='d1dbf8cee2f6ae0428c265bc1fda1c7c93a2c8ba5e5b5ae3f5727b9934de412e':raise ValueError('cold gate source pin')
g=types.ModuleType('fixed_official_source_gate');g.__file__=str(HERE/'run_gate.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
p,frozen,projected,identities=g.preflight(a.repo,a.worker_source)
r=types.SimpleNamespace(**g.supervisor(projected))
raw=(a.repo/'development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py').read_bytes()
if len(raw)!=18004 or hashlib.sha256(raw).hexdigest()!='fc88db7e72d64fca1603de193940e7b95e9030f90dc3eb0e574cec9d5b40ff46':raise ValueError('published mock source pin')
classes=[n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='FakeOS']
if len(classes)!=1:raise ValueError('mock class selection')
ns={'contextlib':contextlib,'types':types,'runner':r,'signal':signal,'mock':mock};exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),'fixed_published_FakeOS','exec',dont_inherit=True),ns);FakeOS=ns['FakeOS']

class Cold(unittest.TestCase):
    def setUp(self):self.net=mock.patch.object(socket,'socket',side_effect=AssertionError('network forbidden'));self.net.start()
    def tearDown(self):self.net.stop()
    def test_fixed_source_and_budget(self):
        self.assertEqual(set(frozen),{'acquire_official_source.py','SOURCE_PLAN.json','acquire_base.py','FIXED_CORE_MEMBERS.json'})
        self.assertEqual(p['budget']['total_seconds'],420);self.assertEqual(p['budget']['work_max_seconds'],400)
        self.assertEqual(tuple(identities),g.FUNCTIONS)
        self.assertIn('os.WNOWAIT',projected.decode());self.assertIn('env=None)',projected.decode())
        self.assertIn('signal.setitimer(signal.ITIMER_REAL, 0)',projected.decode())
    def test_source_default_no_timer_no_spawn(self):
        with mock.patch.object(sys,'argv',['g','--repo',str(a.repo),'--worker-source',str(a.worker_source)]),mock.patch.object(g.subprocess,'Popen',side_effect=AssertionError('spawn')),mock.patch.object(g.signal,'setitimer',side_effect=AssertionError('timer')),contextlib.redirect_stdout(io.StringIO()) as out:g.main()
        self.assertFalse(json.loads(out.getvalue())['child_started'])
    def test_original_lifecycle_modes(self):
        for mode,error in [('pass',None),('timeout',r.subprocess.TimeoutExpired),('interrupt',KeyboardInterrupt),('other_exception',RuntimeError),('reap_unknown',r.subprocess.TimeoutExpired),('spawn_fail',OSError),('compiler_fail',ValueError)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                root=Path(t);fake=FakeOS(mode)
                with fake.patches(),mock.patch.object(r.signal,'setitimer'):
                    if error:
                        with self.assertRaises(error):r.bounded('acquire',['mock'],root,root,10,10)
                    else:r.bounded('acquire',['mock'],root,root,10,10)
                receipt=json.loads((root/'acquire.json').read_bytes());self.assertEqual(receipt['status'],'FAIL' if error else 'PASS')
                if mode!='spawn_fail':self.assertEqual(fake.calls.count((424242,signal.SIGKILL)),1)
    def test_resource_limits_and_default_environment(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fake=FakeOS('pass');seen=[]
            def spawn(command,**kw):
                self.assertIsNone(kw['env'])
                with mock.patch.object(r.resource,'setrlimit') as limits,mock.patch.object(r.os,'sched_getaffinity',return_value={4,7}),mock.patch.object(r.os,'sched_setaffinity') as aff:
                    kw['preexec_fn']();seen.extend(limits.call_args_list);aff.assert_called_once_with(0,{4})
                return fake.spawn(command,**kw)
            with fake.patches(),mock.patch.object(r.subprocess,'Popen',side_effect=spawn),mock.patch.object(r.signal,'setitimer'):r.bounded('acquire',['mock'],root,root,400,400)
            for kind,value in [(r.resource.RLIMIT_CPU,400),(r.resource.RLIMIT_AS,536870912),(r.resource.RLIMIT_FSIZE,67108864)]:self.assertIn(mock.call(kind,(value,value)),seen)
    def test_inherited_alarm_refused(self):
        for blocked,timer in [({signal.SIGALRM},(0.,0.)),(set(),(3.,0.))]:
            with mock.patch.object(g.signal,'pthread_sigmask',return_value=blocked),mock.patch.object(g.signal,'getitimer',return_value=timer),mock.patch.object(g.signal,'setitimer') as setter:
                with self.assertRaises(ValueError):g.alarm_available()
                setter.assert_not_called()
    def fixture_artifacts(self,root):
        (root/'verilator'/'src').mkdir(parents=True)
        members=[];rows=[];total=0
        for i,name in enumerate(['README','src/code.cpp']):
            data=('member'+str(i)).encode();path=root/'verilator'/name;path.write_bytes(data);path.chmod(0o600);total+=len(data)
            blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();mode='100644' if i==0 else '100755'
            members.append({'path':name,'bytes':len(data),'mode':mode,'git_blob_sha':blob})
            rows.append({'path':name,'bytes':len(data),'git_blob_sha1':blob,'sha256_observed':hashlib.sha256(data).hexdigest(),'original_git_mode':mode,'materialized_mode':'0600'})
        archive=b'tiny opaque archive';f=root/'source.tar.gz';f.write_bytes(archive);f.chmod(0o600)
        table={'members':members,'revision':'a'*40,'tree_sha':'b'*40}
        policy={'archive_api_url':'https://example.invalid/archive','exact_prefix':'fixed-root'}
        pins={'SOURCE_PLAN.json':{'sha256':'c'*64},'FIXED_CORE_MEMBERS.json':{'sha256':'d'*64}}
        receipt={'status':'SELECTED_SOURCE_PREPARED_PENDING_OUTER_EXIT0_AND_REVIEW','terminal_success':False,'commit':table['revision'],'tree':table['tree_sha'],'fixed_members_sha256':pins['FIXED_CORE_MEMBERS.json']['sha256'],'fixed_plan_sha256':pins['SOURCE_PLAN.json']['sha256'],'archive_api_url':policy['archive_api_url'],'exact_archive_prefix':policy['exact_prefix'],'transport':'default-platform-HTTPS-one-exact-official-302-no-retry','archive_complete':True,'cleanup_errors':[],'installed':False,'source_executed':False,'native_executed':False,'host_compilation_or_rtl_evidence':False,'archive_sha256_is_independent_provenance':False,'expanded_bytes':1024,'tar_entries':4,'received_bytes':len(archive),'retained_archive_bytes':len(archive),'archive_sha256_observed':hashlib.sha256(archive).hexdigest(),'verified_members':rows,'selected_bytes':total}
        f=root/'SOURCE.json';f.write_text(json.dumps(receipt));f.chmod(0o600)
        return table,policy,pins,receipt,total
    def post(self,root,table,policy,pins,total):
        with mock.patch.object(g,'PINNED_TOTAL',total),mock.patch.object(g,'PINNED_COUNT',2):return g.postflight(root,table,policy,pins)
    def test_tiny_postflight_complete(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);table,policy,pins,receipt,total=self.fixture_artifacts(root)
            self.assertEqual(self.post(root,table,policy,pins,total),receipt)
    def test_tiny_actual_git_hash_independent_from_receipt_sha(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);table,policy,pins,receipt,total=self.fixture_artifacts(root);changed=b'evilxxx';(root/'verilator'/'README').write_bytes(changed)
            receipt['verified_members'][0]['sha256_observed']=hashlib.sha256(changed).hexdigest();(root/'SOURCE.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'independent fixed Git blob'):self.post(root,table,policy,pins,total)
    def test_tiny_postflight_scope_or_conflicting_inventory(self):
        for mode in ['scope','failed','partial','mode','symlink','empty_extra_dir']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                root=Path(t);table,policy,pins,receipt,total=self.fixture_artifacts(root)
                if mode=='scope':receipt['source_executed']=True;(root/'SOURCE.json').write_text(json.dumps(receipt))
                elif mode=='failed':(root/'FAILED.json').write_text('{}')
                elif mode=='partial':(root/'source.tar.gz.part').write_bytes(b'x')
                elif mode=='mode':(root/'verilator'/'README').chmod(0o700)
                elif mode=='empty_extra_dir':(root/'extra').mkdir()
                else:(root/'verilator'/'README').unlink();(root/'verilator'/'README').symlink_to(root/'source.tar.gz')
                with self.assertRaises(ValueError):self.post(root,table,policy,pins,total)
    def test_duplicate_receipt_member_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);table,policy,pins,receipt,total=self.fixture_artifacts(root);receipt['verified_members'][1]=receipt['verified_members'][0];(root/'SOURCE.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'exact unique'):self.post(root,table,policy,pins,total)
    def test_wrong_original_mode_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);table,policy,pins,receipt,total=self.fixture_artifacts(root);receipt['verified_members'][1]['original_git_mode']='100644';(root/'SOURCE.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'identity metadata'):self.post(root,table,policy,pins,total)
    def test_archive_observed_sha_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);table,policy,pins,receipt,total=self.fixture_artifacts(root);path=root/'source.tar.gz';path.write_bytes(b'x'*path.stat().st_size)
            with self.assertRaisesRegex(ValueError,'observed quarantine SHA'):self.post(root,table,policy,pins,total)
    def outer(self,mode='ok'):
        now=[5.];seen=[]
        def bounded(label,command,directory,output,wall,cpu):
            seen.append((wall,cpu,command))
            if mode=='child_failure':now[0]=421.;raise TimeoutError('late child')
            return {'cleanup_confirmed':True,'exit_code':0},b''
        def save(path,value):
            r.save(path,value)
            if path.name=='RESULT.json' and mode in ('late','interrupt'):
                now[0]=421.
                if mode=='interrupt':raise TimeoutError('after save')
        with tempfile.TemporaryDirectory() as t,mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer') as timer,mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g,'supervisor',return_value={'bounded':bounded,'save':save}),mock.patch.object(g,'postflight',return_value={'received_bytes':2466616,'selected_bytes':11747893,'archive_sha256_observed':'a'*64}):
            root=Path(t)/'attempt'
            if mode!='ok':
                with self.assertRaises((ValueError,TimeoutError)):g.execute(a.repo,a.worker_source,root,0.)
                if mode in ('late','interrupt'):
                    saved=json.loads((root/'RESULT.json').read_bytes());self.assertFalse(saved['terminal_success']);self.assertEqual(saved['status'],'EVIDENCE_PENDING_OUTER_EXIT0')
                else:self.assertFalse((root/'RESULT.json').exists())
            else:
                result=g.execute(a.repo,a.worker_source,root,0.);self.assertFalse(result['terminal_success']);self.assertEqual(seen[0][:2],(400.,400))
                self.assertIn('--shared-start-monotonic',seen[0][2]);self.assertEqual(float(seen[0][2][seen[0][2].index('--work-deadline-monotonic')+1]),405.)
                self.assertEqual(timer.call_args_list,[mock.call(signal.ITIMER_REAL,5.),mock.call(signal.ITIMER_REAL,400.),mock.call(signal.ITIMER_REAL,415.),mock.call(signal.ITIMER_REAL,0)])
    def test_shared_deadline_no_new_budget(self):self.outer()
    def test_late_child_has_no_success(self):self.outer('child_failure')
    def test_late_final_save_remains_nonterminal(self):self.outer('late')
    def test_interrupted_final_save_remains_nonterminal(self):self.outer('interrupt')
    def test_source_mutation_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'src';p.write_bytes(b'a');pin=g.digest(b'a');self.assertEqual(g.checked(p,pin),b'a');p.write_bytes(b'b')
            with self.assertRaises(ValueError):g.checked(p,pin)
            q=Path(t)/'link';q.symlink_to(p)
            with self.assertRaises(ValueError):g.checked(q,pin)
    def test_freeze_nonexecutable_exclusive(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'src';g.freeze(p,b'code');self.assertEqual(p.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):g.freeze(p,b'other')

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+extra,verbosity=2)
