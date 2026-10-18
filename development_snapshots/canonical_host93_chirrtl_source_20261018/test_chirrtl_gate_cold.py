"""Pure tiny/mocked CHIRRTL gate tests. No Java, downloaded code or real FIR execution."""
import argparse,contextlib,copy,hashlib,io,json,signal,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--repo',type=Path,required=True);args,remaining=parser.parse_known_args()
raw=(HERE/'run_chirrtl_gate.py').read_bytes()
if len(raw)!=12335 or hashlib.sha256(raw).hexdigest()!='2d07c07fa03595dceeaf024df31650ff9e22547b9f5e5c6ad829549256dc8ff5':raise ValueError('gate source drift')
g=types.ModuleType('fixed_chirrtl_gate');g.__file__=str(HERE/'run_chirrtl_gate.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
plan=g.load_plan();cal=g.load_gate(args.repo);_,sources,jars,deps,projected=cal.configuration(args.repo)

class ChirrtlCold(unittest.TestCase):
    def test_01_fixed_actual_class_and_supervisor(self):
        g.validate_binding(plan);self.assertEqual(g.digest(projected),g.PROJECTION_SHA)
        self.assertEqual(plan['class_actual_review_manifest_sha256'],'95fba4715ea61110a00ea660a5fb2df1d2538555e34db0980dcb898ba8f263b7')
        self.assertEqual(len(jars['artifacts']),87)

    def test_02_pending_binding_fails(self):
        p=copy.deepcopy(plan);p['class_actual_review_manifest_sha256']='PENDING'
        with self.assertRaises(ValueError):g.validate_binding(p)

    def test_03_exact_single_emitter_command(self):
        argv=g.command(Path('/java'),Path('/fresh/classes'),Path('/fresh/jars'),jars,Path('/fresh/structure'))
        self.assertEqual(argv[:4],['/java','-Xmx1024m','-XX:ActiveProcessorCount=1','-cp'])
        self.assertEqual(len(argv[4].split(':')),88);self.assertEqual(argv[-2:],['heteronpu.continuous.EmitCanonicalHost93','/fresh/structure'])
        self.assertEqual(len(argv),7);self.assertNotIn('scala.tools.nsc.Main',argv)

    def test_04_inventory_rejects_extra_empty_directory(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'file').write_bytes(b'x');g.inventory(root,{'file'});(root/'extra').mkdir()
            with self.assertRaises(ValueError):g.inventory(root,{'file'})

    def test_05_inventory_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'file').write_bytes(b'x');(root/'link').symlink_to('file')
            with self.assertRaises(ValueError):g.inventory(root,{'file','link'})

    def test_06_fixed_raw_buffer_hash_rejects_drift(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source';p.write_bytes(b'fixture');self.assertEqual(g.fixed(p,7,g.digest(b'fixture')),b'fixture')
            with self.assertRaises(ValueError):g.fixed(p,7,'0'*64)

    def test_07_same_buffer_copy_original_helper(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'source').write_bytes(b'fixture')
            self.assertEqual(cal.verified_file(p/'source',g.digest(b'fixture'),7,p/'copy',7),7);self.assertEqual((p/'copy').read_bytes(),b'fixture')
            with self.assertRaises(ValueError):cal.verified_file(p/'source','0'*64,7)

    def test_08_source_preflight_never_reads_actual_or_spawns(self):
        with mock.patch.object(sys,'argv',['g','--repo',str(args.repo)]),mock.patch.object(cal.subprocess,'Popen',side_effect=AssertionError('spawn')),mock.patch.object(g,'fixed',wraps=g.fixed) as fixed,contextlib.redirect_stdout(io.StringIO()) as captured:
            g.main();self.assertEqual(json.loads(captured.getvalue())['status'],'CHIRRTL_SOURCE_PREFLIGHT_ONLY')
            self.assertTrue(all('run_class_gate.py' in str(c.args[0]) for c in fixed.call_args_list))

    def test_09_blocked_alarm_refuses_before_output(self):
        with mock.patch.object(g.signal,'pthread_sigmask',return_value={signal.SIGALRM}),mock.patch.object(g,'load_plan') as load:
            with self.assertRaises(ValueError):g.execute(types.SimpleNamespace(),0)
            load.assert_not_called()

    def full_mock(self,mode='ok'):
        # Identity verification is separately exercised above. Here each fixed object is
        # represented by one byte and the original verifier is mocked: orchestration only.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);origin=root/'class_attempt';origin.mkdir();p=copy.deepcopy(plan)
            p['classes']={n:{'bytes':1,'sha256':g.digest(b'c')} for n in p['classes']}
            p['classes_map_sha256']=g.digest(json.dumps({n:v['sha256'] for n,v in p['classes'].items()},sort_keys=True,separators=(',',':')).encode())
            fake_jars=copy.deepcopy(jars)
            for item in fake_jars['artifacts']:item['sha256']=g.digest(b'j')
            for name in p['classes']:
                file=origin/'classes'/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'c')
            for item in jars['artifacts']:
                file=origin/'dependencies'/item['relative_destination'];file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'j')
            receipts={'RESULT.json':{'classes_sha256':{n:v['sha256'] for n,v in p['classes'].items()},'source_count':93,'jar_count':87},'INPUTS.json':{'source_sha256':sources['expected93']}}
            for name,value in receipts.items():
                raw=json.dumps(value).encode();(origin/name).write_bytes(raw);p['class_receipts'][name]={'bytes':len(raw),'sha256':g.digest(raw)}
            java=root/'jdk/bin/java';java.parent.mkdir(parents=True);java.write_bytes(b'j');(java.parent.parent/'release').write_bytes(b'r')
            output=root/'attempt';now=[0.0];seen=[];failure_mode=mode in ('timeout','extra','missing_marker','late_commit','interrupt_commit')
            def verified(path,sha,cap,target=None,known_size=None):
                if target is not None:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(path).read_bytes())
                if '/dependencies/' in str(path):return 61870159-86 if str(path).endswith('/'+jars['artifacts'][0]['relative_destination']) else 1
                return known_size if known_size is not None else Path(path).stat().st_size
            def save(path,value):
                path.write_text(json.dumps(value,sort_keys=True)+'\n')
                if path.name=='RESULT.json' and mode in ('late_commit','interrupt_commit'):
                    now[0]=91
                    if mode=='interrupt_commit':raise TimeoutError('after final evidence save')
            def bounded(label,argv,cwd,out,wall,cpu):
                seen.append((label,wall,cpu));record={'cleanup_confirmed':True,'timed_out':mode=='timeout'}
                save(out/'emit.json',record);(out/'leader_samples.jsonl').write_bytes(b'{}\n')
                log=b'CANONICAL_HOST93_CHIRRTL_BEGIN fixture\nCANONICAL_HOST93_CHIRRTL_WRITTEN fixture\n'
                if mode=='missing_marker':log=b''
                (out/'emit.log').write_bytes(log)
                if mode=='timeout':raise TimeoutError('CHIRRTL emit_work60s deadline')
                (out/'structure').mkdir();(out/'structure/HostBlockCollection.fir').write_bytes(b'synthetic FIR without semantic qualification')
                if mode=='extra':(out/'structure/unknown').write_bytes(b'x')
                return record,log
            before={'user_cpu_seconds':0,'system_cpu_seconds':0,'maxrss_kib':0};after={'user_cpu_seconds':1,'system_cpu_seconds':.1,'maxrss_kib':1234}
            a=types.SimpleNamespace(repo=args.repo,class_attempt=origin,java=java,output=output)
            with mock.patch.object(g,'load_plan',return_value=p),mock.patch.object(g,'validate_binding'),mock.patch.object(g,'load_gate',return_value=cal),mock.patch.object(cal,'configuration',return_value=(None,sources,fake_jars,deps,projected)),mock.patch.object(cal,'verified_file',side_effect=verified),mock.patch.object(cal,'usage',side_effect=[before,after]),mock.patch.object(cal,'supervisor',return_value={'save':save,'bounded':bounded}),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]):
                if failure_mode:
                    with self.assertRaises((TimeoutError,ValueError)):g.execute(a,0)
                    if mode in ('late_commit','interrupt_commit'):
                        r=json.loads((output/'RESULT.json').read_bytes());self.assertFalse(r['terminal_success']);self.assertEqual(r['status'],'CHIRRTL_EVIDENCE_PENDING_OUTER_EXIT0')
                    else:self.assertFalse((output/'RESULT.json').exists());self.assertTrue((output/'FAILURE.json').exists())
                    if mode=='timeout':
                        usage=json.loads((output/'CHILD_USAGE.json').read_bytes());self.assertEqual(usage['failure_type'],'TimeoutError');self.assertEqual(usage['after']['maxrss_kib'],1234)
                    elif mode not in ('late_commit','interrupt_commit'):self.assertTrue((output/'structure/HostBlockCollection.fir').exists())
                else:
                    r=g.execute(a,0);self.assertEqual(seen,[('emit',60,60)]);self.assertFalse(r['terminal_success'])
                    self.assertEqual(r['structure_qualification'],'INCOMPLETE_REQUIRES_SAME_FIR_READ_ONLY_REVIEW')
                    inventory=json.loads((output/'OUTPUT_INVENTORY.json').read_bytes());self.assertEqual(len(inventory),655)
                    self.assertEqual(r['fir'],inventory['structure/HostBlockCollection.fir']);self.assertEqual(r['output_inventory_sha256'],g.digest((output/'OUTPUT_INVENTORY.json').read_bytes()))
                    self.assertFalse(r['rtl_generated']);self.assertFalse(r['host_executed'])

    def test_10_mock_complete_inventory_no_structure_pass(self):self.full_mock()
    def test_11_mock_timeout_retains_usage(self):self.full_mock('timeout')
    def test_12_mock_unknown_output_retains_fir(self):self.full_mock('extra')
    def test_13_mock_missing_marker_fails(self):self.full_mock('missing_marker')
    def test_14_late_final_commit_is_non_success(self):self.full_mock('late_commit')
    def test_15_interrupted_final_commit_is_non_success(self):self.full_mock('interrupt_commit')

    def test_16_no_checker_import_or_structural_claim(self):
        self.assertNotIn(b'load_checker',raw);self.assertNotIn(b'checker.check',raw);self.assertNotIn('checker',plan)

    def test_17_exact_deadlines_and_original_supervisor_limits(self):
        self.assertEqual(plan['budgets']['entry_total_seconds'],90);self.assertEqual(plan['budgets']['work_max_seconds'],60)
        self.assertEqual(plan['budgets']['preflight_seconds'],20);self.assertEqual(plan['budgets']['work_latest_offset_seconds'],80)
        self.assertIn(b'os.WNOWAIT',projected);self.assertIn(b'48 * 1024 * 1024',projected);self.assertIn(b'2 * 1024 * 1024',projected)

if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use python -I -S -B')
    unittest.main(argv=[sys.argv[0]]+remaining,verbosity=2)
