"""Fixed-source pure mocks and synthetic files; never runs Java or real source assembly."""
import argparse,ast,contextlib,hashlib,io,json,signal,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--repo',type=Path,required=True);args,remaining=parser.parse_known_args()
raw=(HERE/'run_class_gate.py').read_bytes()
if len(raw)!=17327 or hashlib.sha256(raw).hexdigest()!='ade8c397292fb92226e8e83d5e461112b2b4021d60e793493ad54e830c61448a':raise ValueError('gate source drift')
g=types.ModuleType('fixed_class_gate');g.__file__=str(HERE/'run_class_gate.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
plan,sources,jars,deps,projected=g.configuration(args.repo)
runner=types.SimpleNamespace(**g.supervisor(projected))
test_raw=(args.repo/'development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py').read_bytes()
if len(test_raw)!=18004 or hashlib.sha256(test_raw).hexdigest()!='fc88db7e72d64fca1603de193940e7b95e9030f90dc3eb0e574cec9d5b40ff46':raise ValueError('published mock drift')
classes=[n for n in ast.parse(test_raw).body if isinstance(n,ast.ClassDef) and n.name=='FakeOS']
if len(classes)!=1:raise ValueError('FakeOS projection drift')
ns={'contextlib':contextlib,'types':types,'runner':runner,'signal':signal,'mock':mock}
exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),'published_FakeOS_only','exec',dont_inherit=True),ns)
FakeOS=ns['FakeOS']

class ClassCold(unittest.TestCase):
    def test_01_fixed_projection_resource_claims(self):
        text=projected.decode();self.assertIn('48 * 1024 * 1024',text);self.assertIn("if record['log_bytes'] > 2 * 1024 * 1024",text)
        self.assertIn('os.WNOWAIT',text);self.assertIn("env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}",text)
        self.assertEqual(runner.AS_LIMIT,4294967296);self.assertEqual(plan['entry_total_seconds'],330);self.assertEqual(plan['compile_max_seconds'],300)

    def scenario(self,mode,error):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);fake=FakeOS(mode)
            with fake.patches(),mock.patch.object(runner.signal,'setitimer'),mock.patch.object(g,'sample_leader'):
                if error:
                    with self.assertRaises(error):runner.bounded('compile',['fake-java'],out,out,300,300)
                else:runner.bounded('compile',['fake-java'],out,out,300,300)
            record=json.loads((out/'compile.json').read_bytes())
            self.assertEqual(record['status'],'FAIL' if error else 'PASS')
            if mode!='spawn_fail':self.assertEqual(fake.calls.count((424242,signal.SIGKILL)),1)
            return record

    def test_02_original_wnowait_success(self):self.assertTrue(self.scenario('pass',None)['cleanup_confirmed'])
    def test_03_original_wnowait_finite_failures(self):
        for mode,error in [('timeout',runner.subprocess.TimeoutExpired),('interrupt',KeyboardInterrupt),('other_exception',RuntimeError),('reap_unknown',runner.subprocess.TimeoutExpired),('spawn_fail',OSError),('compiler_fail',ValueError)]:
            with self.subTest(mode=mode):self.scenario(mode,error)

    def test_04_exact_arg_order_uses93_and87_only(self):
        argv=g.command(Path('/java'),Path('/cache'),Path('/fresh/classes'),Path('/fresh/scala'),sources['expected93'],jars)
        self.assertEqual(argv[1:3],['-Xmx1024m','-XX:ActiveProcessorCount=1'])
        self.assertEqual(len(argv[4].split(':')),87);self.assertEqual(argv[4],argv[7]);self.assertIn('scala.tools.nsc.Main',argv)
        self.assertEqual(argv[-93:],[str(Path('/fresh/scala')/name) for name in sorted(sources['expected93'])]);self.assertFalse(any('Bench.scala' in x or 'Spec.scala' in x for x in argv[-93:]))

    def test_05_snapshot_is_same_bytes_and_failed_SHA_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);source=p/'input';source.write_bytes(b'fixture')
            self.assertEqual(g.verified_file(source,g.sha(b'fixture'),7,p/'snapshot'),7);self.assertEqual((p/'snapshot').read_bytes(),b'fixture')
            with self.assertRaises(ValueError):g.verified_file(source,'0'*64,7)
            with self.assertRaises(ValueError):g.verified_file(source,g.sha(b'fixture'),6)

    def test_06_source_inventory_rejects_extra(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'x.scala').write_bytes(b'x')
            with self.assertRaises(ValueError):g.exact_sources(p,{})

    def test_07_default_source_preflight_never_reads_actual_or_spawns(self):
        with mock.patch.object(sys,'argv',['g','--repo',str(args.repo)]),mock.patch.object(g,'verified_file',side_effect=AssertionError('actual read')),mock.patch.object(g.subprocess,'Popen',side_effect=AssertionError('spawn')),mock.patch.object(g.signal,'setitimer',side_effect=AssertionError('timer')),contextlib.redirect_stdout(io.StringIO()) as captured:
            g.main();self.assertEqual(json.loads(captured.getvalue())['status'],'CLASS_SOURCE_PREFLIGHT_ONLY')

    def test_08_blocked_alarm_refuses_before_output(self):
        with mock.patch.object(g.signal,'pthread_sigmask',return_value={signal.SIGALRM}),mock.patch.object(g,'configuration') as conf:
            with self.assertRaises(ValueError):g.execute(types.SimpleNamespace(),0)
            conf.assert_not_called()

    def full_synthetic(self,late_commit=False,interrupt_commit=False,absent=False,child_error=False):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);assembled=root/'assembled';scala=assembled/'scala';scala.mkdir(parents=True)
            expected={str(n)+'.scala':g.sha(b'synthetic') for n in range(93)}
            for name in expected:(scala/name).write_bytes(b'synthetic')
            fake_sources={'expected93':expected}
            receipt={'status':'PASS_NEW_DERIVED_HOST93_SOURCE_ONLY','source_count':93,'source_sha256':expected,'recipe_sha256':plan['project_files']['source_plan']['sha256'],**{k:False for k in ('historical95_identity_inherited','compiler_started','elaboration_started','rtl_generated','hardware_executed')}}
            if not absent:(assembled/'SOURCE_RECEIPT.json').write_text(json.dumps(receipt))
            cache=root/'cache';cache.mkdir();arts=[]
            for n in range(87):
                name=str(n)+'.jar';(cache/name).write_bytes(b'jar');arts.append({'relative_destination':name,'sha256':g.sha(b'jar'),'max_transfer_bytes':4,'known_size_bytes':3})
            java=root/'jdk/bin/java';java.parent.mkdir(parents=True);java.write_bytes(b'fake-java');(java.parent.parent/'release').write_bytes(b'fake-release')
            fake_deps={'java_sha256':g.sha(b'fake-java'),'java_release_sha256':g.sha(b'fake-release')}
            output=root/'attempt';now=[0.0];seen=[]
            a=types.SimpleNamespace(repo=args.repo,assembled_source=assembled,jar_artifacts=cache,java=java,output=output)
            def bounded(label,argv,directory,out,wall,cpu):
                seen.append((wall,cpu))
                if child_error:raise TimeoutError('mock compile_work300s deadline after cleanup')
                target=out/'classes/heteronpu/continuous/EmitCanonicalHost93$.class';target.parent.mkdir(parents=True);target.write_bytes(b'synthetic-not-a-real-class');return {'cleanup_confirmed':True},b''
            def save(path,value):
                runner.save(path,value)
                if path.name=='RESULT.json' and (late_commit or interrupt_commit):
                    now[0]=331.0
                    if interrupt_commit:raise TimeoutError('after final evidence replace')
            with mock.patch.object(g,'usage',side_effect=[{'user_cpu_seconds':0,'system_cpu_seconds':0,'maxrss_kib':0},{'user_cpu_seconds':1.2,'system_cpu_seconds':.1,'maxrss_kib':123456}]),mock.patch.object(g,'configuration',return_value=(plan,fake_sources,{'artifacts':arts},fake_deps,projected)),mock.patch.object(g,'supervisor',return_value={'bounded':bounded,'save':save}),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]):
                if absent:
                    with self.assertRaises(ValueError):g.execute(a,0)
                    self.assertFalse(output.exists());self.assertEqual(seen,[])
                elif child_error:
                    with self.assertRaises(TimeoutError):g.execute(a,0)
                    usage=json.loads((output/'CHILD_USAGE.json').read_bytes());self.assertEqual(usage['after']['maxrss_kib'],123456);self.assertEqual(usage['failure_type'],'TimeoutError');self.assertFalse((output/'RESULT.json').exists());self.assertTrue((output/'FAILURE.json').exists())
                elif late_commit or interrupt_commit:
                    with self.assertRaises(TimeoutError if interrupt_commit else ValueError):g.execute(a,0)
                    r=json.loads((output/'RESULT.json').read_bytes());self.assertFalse(r['terminal_success']);self.assertEqual(r['status'],'CLASS_EVIDENCE_PENDING_OUTER_EXIT0')
                else:
                    result=g.execute(a,0);self.assertEqual(seen,[(300,300)]);self.assertEqual(result['status'],'CLASS_EVIDENCE_PENDING_OUTER_EXIT0');self.assertFalse(result['terminal_success']);self.assertEqual(result['class_count'],1)

    def test_09_full_synthetic_snapshot_and_non_success_receipt(self):self.full_synthetic()
    def test_10_absent_real_source_contract_refuses_before_output(self):self.full_synthetic(absent=True)
    def test_11_late_final_commit_cannot_return_success(self):self.full_synthetic(late_commit=True)
    def test_12_interrupted_final_commit_leaves_no_success(self):self.full_synthetic(interrupt_commit=True)

    def test_13_child_limits_and_environment_are_only_mocked(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);fake=FakeOS('pass');seen=[]
            def spawn(argv,**kw):
                self.assertEqual(kw['env'],{'PATH':'/usr/bin:/bin','LC_ALL':'C'})
                with mock.patch.object(runner.resource,'setrlimit') as limits,mock.patch.object(runner.os,'sched_getaffinity',return_value={2,9}),mock.patch.object(runner.os,'sched_setaffinity') as affinity:
                    kw['preexec_fn']();seen.extend(limits.call_args_list);affinity.assert_called_once_with(0,{2})
                return fake.spawn(argv,**kw)
            with fake.patches(),mock.patch.object(runner.subprocess,'Popen',side_effect=spawn),mock.patch.object(runner.signal,'setitimer'),mock.patch.object(g,'sample_leader'):
                runner.bounded('compile',['fake-java'],out,out,300,300)
            self.assertIn(mock.call(runner.resource.RLIMIT_AS,(4294967296,4294967296)),seen)
            self.assertIn(mock.call(runner.resource.RLIMIT_CPU,(300,300)),seen)
            self.assertIn(mock.call(runner.resource.RLIMIT_FSIZE,(50331648,50331648)),seen)

    @staticmethod
    def stat(pid=7,start=99,user=100,system=50):
        fields=['S']+['0']*49
        for index,value in ((11,user),(12,system),(19,start),(21,256)):fields[index]=str(value)
        return (str(pid)+' (java ) fixture) '+' '.join(fields)+'\n').encode()

    def test_14_proc_stat_field_positions_and_parentheses(self):
        s=g.proc_stat(self.stat(),7);self.assertEqual((s['pid'],s['starttime_ticks'],s['user_ticks'],s['system_ticks'],s['rss_pages']),(7,99,100,50,256))
        with self.assertRaises(ValueError):g.proc_stat(self.stat(pid=8),7)

    def test_15_samples_visible_each_row_and_rate_limited(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'samples';state={'path':path,'identity':None,'count':0,'next':None,'start':None};now=[0.0]
            def read(pid,leaf):return self.stat() if leaf=='stat' else b'VmRSS: 1024 kB\nVmHWM: 2048 kB\n'
            with mock.patch.object(g,'proc_bytes',side_effect=read) as reader,mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g.os,'sysconf',return_value=100):
                g.sample_leader(types.SimpleNamespace(pid=7),state)
                first=json.loads(path.read_bytes());self.assertEqual((first['vmrss_kib'],first['vmhwm_kib'],first['user_cpu_seconds']),(1024,2048,1.0));self.assertEqual(reader.call_count,3)
                now[0]=.99;g.sample_leader(types.SimpleNamespace(pid=7),state);self.assertEqual(reader.call_count,3)
                now[0]=1;g.sample_leader(types.SimpleNamespace(pid=7),state);self.assertEqual(len(path.read_text().splitlines()),2);self.assertEqual(reader.call_count,6)

    def test_16_identity_change_refused_before_row(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'samples';state={'path':path,'identity':(7,99),'count':0,'next':None,'start':0}
            with mock.patch.object(g,'proc_bytes',return_value=self.stat(start=100)):
                with self.assertRaises(ValueError):g.sample_leader(types.SimpleNamespace(pid=7),state)
            self.assertFalse(path.exists())

    def test_17_identity_change_across_status_refused(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'samples';state={'path':path,'identity':None,'count':0,'next':None,'start':None}
            with mock.patch.object(g,'proc_bytes',side_effect=[self.stat(),b'VmRSS: 1 kB\n',self.stat(start=100)]):
                with self.assertRaises(ValueError):g.sample_leader(types.SimpleNamespace(pid=7),state)
            self.assertFalse(path.exists())

    def test_18_row_cap_no_additional_proc_read(self):
        state={'path':Path('/never'),'identity':(7,99),'count':340,'next':None,'start':0}
        with mock.patch.object(g,'proc_bytes',side_effect=AssertionError('over-cap read')):
            with self.assertRaises(ValueError):g.sample_leader(types.SimpleNamespace(pid=7),state)

    def test_19_missing_memory_metrics_are_null_not_zero(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'samples';state={'path':path,'identity':None,'count':0,'next':None,'start':None}
            with mock.patch.object(g,'proc_bytes',side_effect=[self.stat(),b'Name: java\n',self.stat()]):g.sample_leader(types.SimpleNamespace(pid=7),state)
            r=json.loads(path.read_bytes());self.assertIsNone(r['vmrss_kib']);self.assertIsNone(r['vmhwm_kib'])

    def test_20_timeout_error_classification_and_original_cleanup(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);fake=FakeOS('pass');calls=[0];original=fake.waitid
            def observe(*a):
                calls[0]+=1
                if calls[0]==1:raise TimeoutError('work300s signal')
                return original(*a)
            with fake.patches(),mock.patch.object(runner.os,'waitid',side_effect=observe),mock.patch.object(runner.signal,'setitimer'),mock.patch.object(g,'sample_leader'):
                with self.assertRaises(TimeoutError):runner.bounded('compile',['fake-java'],out,out,300,300)
            r=json.loads((out/'compile.json').read_bytes());self.assertTrue(r['timed_out']);self.assertTrue(r['cleanup_confirmed']);self.assertEqual(fake.calls.count((424242,signal.SIGKILL)),1)

    def test_21_failed_child_retains_absolute_usage(self):self.full_synthetic(child_error=True)

    def test_22_observation_anchor_checked_before_sample(self):
        namespace=runner.observe_exit.__globals__
        with mock.patch.object(runner.os,'waitid',return_value=types.SimpleNamespace(si_pid=8)),mock.patch.dict(namespace,{'sample_leader':mock.Mock(side_effect=AssertionError('wrong identity sampled'))}):
            with self.assertRaises(ValueError):runner.observe_exit(types.SimpleNamespace(pid=7),['fake'],1)

    def test_23_verbose_is_the_only_new_compiler_option(self):
        a=g.command(Path('/java'),Path('/cache'),Path('/classes'),Path('/scala'),sources['expected93'],jars)
        self.assertEqual(a.count('-verbose'),1);self.assertFalse(any('debug' in x or 'profile' in x or 'statistics' in x for x in a[:13]))

if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use python -I -S -B')
    unittest.main(argv=[sys.argv[0]]+remaining,verbosity=2)
