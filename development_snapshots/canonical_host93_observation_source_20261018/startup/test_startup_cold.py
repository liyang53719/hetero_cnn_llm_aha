"""Only mocked child/resource/signal operations and synthetic temporary receipts."""
from pathlib import Path
import contextlib,hashlib,io,json,sys,tempfile,types,unittest
from unittest import mock
HERE=Path(__file__).resolve().parent;raw=(HERE/'run_startup_probe.py').read_bytes()
if len(raw)!=6281 or hashlib.sha256(raw).hexdigest()!='7f7bdac94d7970c55a9fb81e29d372f8b3421931bd980e633f69c9e52d93603a':raise ValueError('wrapper drift')
p=types.ModuleType('fixed_startup_source');p.__file__=str(HERE/'run_startup_probe.py');exec(compile(raw,p.__file__,'exec',dont_inherit=True),p.__dict__)

class StartupCold(unittest.TestCase):
    def test_01_exact_version_commands_no_sources_or_plugin(self):
        jars={'artifacts':[{'relative_destination':str(i)+'.jar'} for i in range(87)]}
        self.assertEqual(p.probe_argv('java-version',Path('/java'),Path('/cache'),jars),['/java','-Xmx1024m','-XX:ActiveProcessorCount=1','-version'])
        argv=p.probe_argv('scala-version',Path('/java'),Path('/cache'),jars)
        self.assertEqual(argv[-2:],['scala.tools.nsc.Main','-version']);self.assertEqual(len(argv[4].split(':')),87)
        self.assertFalse(any(x.endswith('.scala') or x.startswith('-Xplugin') for x in argv))

    def test_02_usage_reports_absolute_maxrss(self):
        r=types.SimpleNamespace(ru_utime=1.2,ru_stime=.3,ru_maxrss=7000,ru_majflt=1,ru_minflt=2,ru_nvcsw=3,ru_nivcsw=4)
        with mock.patch.object(p.resource,'getrusage',return_value=r):
            self.assertEqual(p.usage()['maxrss_kib'],7000);self.assertEqual(p.usage()['user_cpu_seconds'],1.2)

    def test_03_changed_class_gate_source_refused(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t);(path/'run_class_gate.py').write_text('marker=True')
            with self.assertRaises(ValueError):p.load_gate(path)

    def test_04_expiration_is_timeout(self):
        with self.assertRaises(TimeoutError):p.expired(None,None)

    def synthetic(self,mode='scala-version',late=False,prior=False,child_error=False):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);output=root/'output';now=[0.0];seen=[];reads=[]
            projected=b'fixed mock projection'
            class Fake:
                clean=staticmethod(lambda path:Path(path).absolute())
                verified_file=staticmethod(lambda *a,**k:reads.append((a,k)))
                configuration=staticmethod(lambda repo:({}, {}, {'artifacts':[{'relative_destination':'one.jar','sha256':'fake','max_transfer_bytes':2,'known_size_bytes':1}]}, {'java_sha256':'fake','java_release_sha256':'fake'},projected))
                def arm(self,stop):
                    p.require(stop>now[0],'mock deadline')
                def supervisor(self,raw):
                    def save(path,value):
                        path.write_text(json.dumps(value))
                        if late and path.name=='RESULT.json':now[0]=21
                    def bounded(label,argv,cwd,out,wall,cpu):
                        seen.append((argv,wall,cpu));(out/'startup.json').write_text(json.dumps({'cleanup_confirmed':True}))
                        if child_error:raise TimeoutError('synthetic child timeout after cleanup')
                        return {'cleanup_confirmed':True}, b'openjdk version 21.0.12.1' if mode=='java-version' else b'Scala compiler version 2.13.16'
                    return {'save':save,'bounded':bounded}
            before={'user_cpu_seconds':1 if prior else 0,'system_cpu_seconds':0,'maxrss_kib':0}
            after={'user_cpu_seconds':.4,'system_cpu_seconds':.1,'maxrss_kib':43000}
            argv=['p','--class-gate',str(root/'gate'),'--repo',str(root/'repo'),'--mode',mode,'--jar-artifacts',str(root/'cache'),'--java',str(root/'jdk/bin/java'),'--output',str(output),'--execute-reviewed-startup']
            with mock.patch.object(sys,'argv',argv),mock.patch.object(p,'load_gate',return_value=Fake()),mock.patch.object(p,'PROJECTION_SHA',hashlib.sha256(projected).hexdigest()),mock.patch.object(p,'usage',side_effect=[before,after]),mock.patch.object(p.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(p.signal,'pthread_sigmask',return_value=set()),mock.patch.object(p.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(p.signal,'signal'),mock.patch.object(p.signal,'setitimer'),contextlib.redirect_stdout(io.StringIO()) as captured:
                if late or prior or child_error:
                    with self.assertRaises(TimeoutError if child_error else ValueError):p.main()
                else:p.main()
            if prior:self.assertFalse(output.exists());self.assertEqual(seen,[]);return
            r=json.loads((output/'RESULT.json').read_bytes());self.assertFalse(r['terminal_success']);self.assertEqual(r['rusage_children_after']['maxrss_kib'],43000)
            self.assertEqual(seen[0][1:],(10,10));self.assertEqual(len(reads),2 if mode=='java-version' else 3)
            if child_error:self.assertEqual(r['failure_type'],'TimeoutError');self.assertIsNone(r['child_cleanup_confirmed'])
            if late or child_error:self.assertEqual(captured.getvalue(),'')

    def test_05_java_only_synthetic(self):self.synthetic('java-version')
    def test_06_scala_only_synthetic(self):self.synthetic()
    def test_07_prior_child_usage_refuses_before_output(self):self.synthetic(prior=True)
    def test_08_late_saved_evidence_not_success(self):self.synthetic(late=True)
    def test_09_failed_child_still_records_usage(self):self.synthetic(child_error=True)

if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use python -I -S -B')
    unittest.main(verbosity=2)
