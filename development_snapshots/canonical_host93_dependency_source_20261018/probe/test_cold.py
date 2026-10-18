"""Fixed same-buffer sources, synthetic files and existing WNOWAIT mocks only."""
import argparse,ast,contextlib,hashlib,io,json,os,signal,socket,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise ValueError('use -I -S -B')
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False)
for n in ('repo','staging-gate','worker-source'):parser.add_argument('--'+n,type=Path,required=True)
a,extra=parser.parse_known_args();raw=(HERE/'run_probe.py').read_bytes()
if len(raw)!=14750 or hashlib.sha256(raw).hexdigest()!='3c160adc2b51b27ffe151c524929ebbbcb7b6ec49f923afdfd8afd6d88613a26':raise ValueError('cold wrapper samebuffer size/SHA')
g=types.ModuleType('fixed_probe_gate');g.__file__=str(HERE/'run_probe.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
# Cold-only front-door substitution: restored before any test runs. Production is unchanged.
with contextlib.ExitStack() as source_only:
    original_gate_load = g.load
    def cold_gate_load(raw, path, expected):
        gate = original_gate_load(raw, path, expected)
        original_worker_load = gate.load
        def cold_worker_load(raw, path):
            worker = original_worker_load(raw, path)
            source_only.enter_context(mock.patch.object(worker, 'require_actual_review', return_value=None))
            return worker
        source_only.enter_context(mock.patch.object(gate, 'load', side_effect=cold_worker_load))
        return gate
    source_only.enter_context(mock.patch.object(g, 'load', side_effect=cold_gate_load))
    p,modes,stagegate,worker,pins,projected,worker_raw=g.configure(a.repo,a.staging_gate,a.worker_source)
source_configuration=(p,modes,stagegate,worker,pins,projected,worker_raw)
ns={'__builtins__':__builtins__,'os':g.os,'resource':g.resource,'signal':g.signal,'subprocess':g.subprocess,'time':g.time,'json':json,'AS_LIMIT':536870912,'CHILD_ENV':{'PATH':'fixed','LC_ALL':'C'}};exec(compile(projected,'fixed_projected_supervisor','exec',dont_inherit=True),ns);r=types.SimpleNamespace(**ns)
raw=(a.repo/'development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py').read_bytes()
if len(raw)!=18004 or hashlib.sha256(raw).hexdigest()!='fc88db7e72d64fca1603de193940e7b95e9030f90dc3eb0e574cec9d5b40ff46':raise ValueError('published mock source pin')
classes=[n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='FakeOS']
if len(classes)!=1:raise ValueError('one fixed mock class')
ns={'contextlib':contextlib,'types':types,'runner':r,'signal':signal,'mock':mock};exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),'fixed_FakeOS','exec',dont_inherit=True),ns);FakeOS=ns['FakeOS']

class Cold(unittest.TestCase):
    def setUp(self):self.net=mock.patch.object(socket,'socket',side_effect=AssertionError('network'));self.net.start()
    def tearDown(self):self.net.stop()
    def test_source_mock_restored_and_production_configure_rejects(self):
        with self.assertRaisesRegex(ValueError,'ACTUAL_IDENTITY_REVIEW_PENDING'):
            worker.require_actual_review(pins)
        with mock.patch.object(g.subprocess,'Popen') as spawn, mock.patch.object(Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'ACTUAL_IDENTITY_REVIEW_PENDING'):
                g.configure(a.repo,a.staging_gate,a.worker_source)
            spawn.assert_not_called();mkdir.assert_not_called()

    def test_production_execute_rejects_unbound_identity_before_output(self):
        with tempfile.TemporaryDirectory() as t:
            arg=types.SimpleNamespace(repo=a.repo,staging_gate=a.staging_gate,worker_source=a.worker_source,mode='m4-version',output=Path(t)/'never',stage_outer=Path(t),stage_review=Path(t))
            with mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.subprocess,'Popen') as spawn, mock.patch.object(Path,'mkdir') as mkdir:
                with self.assertRaisesRegex(ValueError,'ACTUAL_IDENTITY_REVIEW_PENDING'):g.execute(arg,g.time.monotonic())
                spawn.assert_not_called();mkdir.assert_not_called();self.assertFalse(arg.output.exists())

    def test_fixed_ten_modes_and_pending(self):
        self.assertIsNone(p['actual_staging']);self.assertEqual(len(modes),10);self.assertEqual(p['budget']['total_seconds'],20);self.assertEqual(p['budget']['work_seconds'],10)
    def test_exact_supervisor_projection(self):
        self.assertIn('os.WNOWAIT',projected.decode());self.assertIn('env=CHILD_ENV)',projected.decode());self.assertNotIn('env=None',projected.decode());self.assertIn('signal.setitimer(signal.ITIMER_REAL, 0)',projected.decode())
    def test_original_lifecycle_modes(self):
        for mode,error in [('pass',None),('timeout',r.subprocess.TimeoutExpired),('interrupt',KeyboardInterrupt),('other_exception',RuntimeError),('reap_unknown',r.subprocess.TimeoutExpired),('spawn_fail',OSError),('compiler_fail',ValueError)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                root=Path(t);fake=FakeOS(mode)
                with fake.patches(),mock.patch.object(r.signal,'setitimer'):
                    if error:
                        with self.assertRaises(error):r.bounded('probe',['mock'],root,root,10,10)
                    else:r.bounded('probe',['mock'],root,root,10,10)
                receipt=json.loads((root/'probe.json').read_bytes());self.assertEqual(receipt['status'],'FAIL' if error else 'PASS')
                if mode!='spawn_fail':self.assertEqual(fake.calls.count((424242,signal.SIGKILL)),1)
    def test_exact_child_limits_and_env(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fake=FakeOS('pass');seen=[]
            def spawn(command,**kw):
                self.assertEqual(kw['env'],r.CHILD_ENV)
                with mock.patch.object(r.resource,'setrlimit') as limits,mock.patch.object(r.os,'sched_getaffinity',return_value={5,9}),mock.patch.object(r.os,'sched_setaffinity') as aff:kw['preexec_fn']();seen.extend(limits.call_args_list);aff.assert_called_once_with(0,{5})
                return fake.spawn(command,**kw)
            with fake.patches(),mock.patch.object(r.subprocess,'Popen',side_effect=spawn),mock.patch.object(r.signal,'setitimer'):r.bounded('probe',['mock'],root,root,10,10)
            for k,v in [(r.resource.RLIMIT_CPU,10),(r.resource.RLIMIT_AS,536870912),(r.resource.RLIMIT_FSIZE,4194304)]:self.assertIn(mock.call(k,(v,v)),seen)
    def test_environment_is_allowlist(self):
        env=g.environment(Path('/fresh'),Path('/stage'));self.assertEqual(len(env),11);self.assertEqual(env['M4'],'/fresh/tools/usr/bin/m4');self.assertEqual(env['HOME'],'/fresh/home');self.assertEqual(env['AUTOM4TE_CFG'],'/stage/relocation/autom4te.cfg')
        for n in ['LD_PRELOAD','PERL5OPT','PYTHONPATH','BASH_ENV','M4PATH']:self.assertNotIn(n,env)
    def test_bad_source_before_compile(self):
        with mock.patch('builtins.compile') as compiler:
            for raw in [b'bad',b'x'*g.GATE_PIN['bytes']]:
                with self.assertRaises(ValueError):g.load(raw,HERE/'bad.py',g.GATE_PIN)
            compiler.assert_not_called()
    def test_source_default_no_spawn_or_stage(self):
        argv=['g','--repo',str(a.repo),'--staging-gate',str(a.staging_gate),'--worker-source',str(a.worker_source)]
        with mock.patch.object(sys,'argv',argv),mock.patch.object(g,'stage_identity',side_effect=AssertionError('actual')),mock.patch.object(g.subprocess,'Popen',side_effect=AssertionError('spawn')),mock.patch.object(g.signal,'setitimer',side_effect=AssertionError('timer')),mock.patch.object(Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'ACTUAL_IDENTITY_REVIEW_PENDING'):g.main()
            mkdir.assert_not_called()
    def test_pending_before_output(self):
        with tempfile.TemporaryDirectory() as t:
            arg=types.SimpleNamespace(repo=a.repo,staging_gate=a.staging_gate,worker_source=a.worker_source,mode='m4-version',output=Path(t)/'never',stage_outer=Path(t),stage_review=Path(t))
            with mock.patch.object(g,'configure',return_value=source_configuration),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'ACTUAL_STAGING_REVIEW_PENDING'):g.execute(arg,g.time.monotonic())
                spawn.assert_not_called();self.assertFalse(arg.output.exists())
    def fixture68(self,root):
        expected={};stage=root/'stage';stage.mkdir()
        names=['usr/bin/'+x for x in g.TOOLS]+['usr/share/resource%02d'%i for i in range(62)]+['relocation/autom4te.cfg']
        for name in names:
            path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);raw=name.encode();path.write_bytes(raw);path.chmod(0o600);expected[name]=g.pin(raw)
        return stage,expected
    def test_exact68_copy_and_five_execute(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);stage,expected=self.fixture68(root);dest=root/'tools';g.copy_tools(dest,stage,expected);g.verify_copies(dest,expected)
            self.assertEqual(sum((dest/n).stat().st_mode&0o111!=0 for n in expected),5);self.assertTrue(all((stage/n).stat().st_mode&0o777==0o600 for n in expected))
    def test_copy_change_wrong_mode_or_extra_refused(self):
        for bad in ['hash','mode','extra']:
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as t:
                root=Path(t);stage,expected=self.fixture68(root);dest=root/'tools';g.copy_tools(dest,stage,expected)
                if bad=='hash':(dest/'usr/bin/m4').write_bytes(b'wrong')
                elif bad=='mode':(dest/'usr/share/resource00').chmod(0o700)
                else:(dest/'extra').write_bytes(b'x')
                with self.assertRaises(ValueError):g.verify_copies(dest,expected)
    def test_ten_fixture_expected_outputs(self):
        for name,d in modes.items():
            with self.subTest(mode=name),tempfile.TemporaryDirectory() as t:
                work=Path(t)
                for n,spec in d['generated_files'].items():(work/n).write_bytes('\n'.join(spec['contains']).encode())
                log=d['expected_log_exact'].encode() if d['expected_log_exact'] is not None else '\n'.join(d['expected_log_contains']).encode();g.check_probe(name,d,work,log)
    def test_wrong_log_missing_generated_marker_refused(self):
        with tempfile.TemporaryDirectory() as t:
            work=Path(t)
            with self.assertRaises(ValueError):g.check_probe('m4-version',modes['m4-version'],work,b'wrong')
            with self.assertRaises(ValueError):g.check_probe('m4-micro',modes['m4-micro'],work,b'HOST93_M4_RESOURCE_OK\nextra')
            (work/'tiny.tab.c').write_bytes(b'empty')
            with self.assertRaises(ValueError):g.check_probe('bison-micro',modes['bison-micro'],work,b'')
    def test_inventory_rejects_link(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'bad').symlink_to('/dev/null')
            with self.assertRaises(ValueError):g.inventory(root)
    def test_usage_peak_not_difference(self):
        fake=types.SimpleNamespace(ru_utime=1.25,ru_stime=.5,ru_maxrss=99,ru_majflt=0,ru_minflt=2,ru_nvcsw=3,ru_nivcsw=4)
        with mock.patch.object(g.resource,'getrusage',return_value=fake):self.assertEqual(g.usage()['maxrss_kib'],99)

    def outer(self,kind='pass'):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);stage=root/'stage';stage.mkdir();out=root/'fresh'
            cfg=dict(p,actual_staging={'mock':True});m=types.SimpleNamespace(OUTPUT_ROOT=str(stage));now=[1.]
            stub=("def bounded(*args):\n    raise TimeoutError('mock child timeout')\n" if kind=='child_failure' else "def bounded(*args):\n    return {'cleanup_confirmed':True,'exit_code':0},b'm4 (GNU M4) 1.4.19'\n").encode()
            configuration=(cfg,modes,stagegate,m,pins,stub,worker_raw)
            arg=types.SimpleNamespace(repo=a.repo,staging_gate=a.staging_gate,worker_source=a.worker_source,mode='m4-version',output=out,stage_outer=root/'outer',stage_review=root/'review')
            real_save=g.save
            def save(path,value):
                result=real_save(path,value)
                if kind=='late_save' and path.name=='OUTPUT_INVENTORY.json':now[0]=21.
                return result
            u0={'user_cpu_seconds':0.,'system_cpu_seconds':0.,'maxrss_kib':0};u1={'user_cpu_seconds':1.,'system_cpu_seconds':.2,'maxrss_kib':42}
            with mock.patch.object(g,'configure',return_value=configuration),mock.patch.object(g,'stage_identity'),mock.patch.object(g,'copy_tools',side_effect=lambda root,*a:root.mkdir()),mock.patch.object(g,'verify_copies'),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g,'usage',side_effect=[u0,u1]),mock.patch.object(g,'save',side_effect=save),contextlib.redirect_stdout(io.StringIO()):
                if kind=='child_failure':
                    with self.assertRaisesRegex(TimeoutError,'mock child timeout'):g.execute(arg,0.)
                elif kind=='late_save':
                    with self.assertRaisesRegex(ValueError,'post-save same20'):g.execute(arg,0.)
                else:g.execute(arg,0.)
            usage=json.loads((out/'CHILD_USAGE.json').read_bytes());self.assertEqual(usage['after']['maxrss_kib'],42)
            if kind=='child_failure':self.assertFalse((out/'RESULT.json').exists());self.assertEqual(usage['failure_type'],'TimeoutError');self.assertTrue((out/'FAILURE.json').is_file())
            else:
                result=json.loads((out/'RESULT.json').read_bytes());self.assertFalse(result['terminal_success']);self.assertFalse(result['production_source_compiled']);inv=json.loads((out/'OUTPUT_INVENTORY.json').read_bytes());self.assertIn('RESULT.json',inv['files']);self.assertEqual(inv['inventory_excludes_only_its_own_file'],'OUTPUT_INVENTORY.json')
    def test_outer_nonterminal_result_and_usage(self):self.outer()
    def test_outer_failure_still_records_usage(self):self.outer('child_failure')
    def test_late_final_inventory_never_terminal(self):self.outer('late_save')

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+extra,verbosity=2)
