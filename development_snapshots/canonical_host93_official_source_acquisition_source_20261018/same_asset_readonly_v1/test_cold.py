"""Tiny readonly mode exception, unchanged-input and final-evidence regressions."""
import argparse,ast,contextlib,hashlib,io,json,os,signal,socket,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise ValueError('use -I -S -B')
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--gate-source',type=Path,required=True);parser.add_argument('--worker-source',type=Path,required=True);args,extra=parser.parse_known_args()
raw=(HERE/'run_readonly.py').read_bytes()
if len(raw)!=9344 or hashlib.sha256(raw).hexdigest()!='7897dbfc109754b4492543898671b4d121611dcd8844098c37798abe6a60b3cb':raise ValueError('cold source pin')
g=types.ModuleType('fixed_readonly_gate');g.__file__=str(HERE/'run_readonly.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
p,original,projection,data=g.config(args.gate_source,args.worker_source)
raw=(args.gate_source/'test_gate_cold.py').read_bytes()
if len(raw)!=13485 or hashlib.sha256(raw).hexdigest()!='61fb192cc413c68871903652b0f6cdf74f5d5100de50425431e3c96965ddc834':raise ValueError('fixed synthetic fixture source')
node=[f for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='Cold' for f in n.body if isinstance(f,ast.FunctionDef) and f.name=='fixture_artifacts'][0]
ns={'Path':Path,'json':json,'hashlib':hashlib};exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'fixed_tiny_fixture','exec',dont_inherit=True),ns);fixture=ns['fixture_artifacts']

class Cold(unittest.TestCase):
    def setUp(self):self.network=mock.patch.object(socket,'socket',side_effect=AssertionError('no network'));self.network.start()
    def tearDown(self):self.network.stop()
    def test_fixed_projection_and_budget(self):
        self.assertEqual(projection['sole_change'],'allow only the exact SOURCE.json data receipt mode0644; all archive/member modes remain0600')
        self.assertEqual(p['budget']['total_seconds'],30);self.assertEqual(p['budget']['cpu_seconds'],20)
    def post(self,root,table,policy,pins,total):
        with mock.patch.object(original,'PINNED_TOTAL',total),mock.patch.object(original,'PINNED_COUNT',2):return original.postflight(root,table,policy,pins)
    def test_exact_pinned_receipt_mode_exception(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);table,policy,pins,receipt,total=fixture(None,root);(root/'SOURCE.json').chmod(0o644)
            self.assertEqual(self.post(root,table,policy,pins,total),receipt)
    def test_receipt_other_modes_rejected(self):
        for mode in [0o600,0o666,0o700,0o755]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                root=Path(t);table,policy,pins,receipt,total=fixture(None,root);(root/'SOURCE.json').chmod(mode)
                with self.assertRaises(ValueError):self.post(root,table,policy,pins,total)
    def test_archive_and_member_still600(self):
        for name in ['source.tar.gz','verilator/README']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as t:
                root=Path(t);table,policy,pins,receipt,total=fixture(None,root);(root/'SOURCE.json').chmod(0o644);(root/name).chmod(0o644)
                with self.assertRaises(ValueError):self.post(root,table,policy,pins,total)
    def test_inventory_records_mode_bytes_and_identity(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'data').write_bytes(b'abc');before=g.inventory(root);self.assertEqual(before,g.inventory(root));(root/'data').chmod(0o600);self.assertNotEqual(before,g.inventory(root))
    def test_inventory_link_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'link').symlink_to('/dev/null')
            with self.assertRaises(ValueError):g.inventory(root)
    def test_bad_source_rejected_before_compile(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'source';path.write_bytes(b'bad')
            with mock.patch('builtins.compile') as compiler:
                with self.assertRaises(ValueError):g.checked(path,{'bytes':3,'sha256':'0'*64})
                compiler.assert_not_called()
    def test_source_default_does_not_read_actual(self):
        with mock.patch.object(sys,'argv',['g','--gate-source',str(args.gate_source),'--worker-source',str(args.worker_source)]),mock.patch.object(g,'inventory',side_effect=AssertionError('actual')),mock.patch.object(g.signal,'setitimer',side_effect=AssertionError('timer')),contextlib.redirect_stdout(io.StringIO()) as out:g.main()
        self.assertEqual(json.loads(out.getvalue())['status'],'SOURCE_ONLY_NO_ASSET_READ')
    def test_limits_exact(self):
        with mock.patch.object(g.os,'sched_getaffinity',return_value={4,6}),mock.patch.object(g.os,'sched_setaffinity') as affinity,mock.patch.object(g.resource,'setrlimit') as limits:g.limits()
        affinity.assert_called_once_with(0,{4})
        for kind,value in [(g.resource.RLIMIT_CPU,20),(g.resource.RLIMIT_AS,536870912),(g.resource.RLIMIT_FSIZE,524288),(g.resource.RLIMIT_CORE,0)]:self.assertIn(mock.call(kind,(value,value)),limits.call_args_list)
    def outer(self,late=False):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'original';source.mkdir();worker=root/'worker';worker.mkdir();gate=root/'gate';gate.mkdir();review=root/'review';review.mkdir();out=root/'fresh'
            (source/'FAILURE.json').write_text(json.dumps({'status':'FAIL_PRESERVED_NO_RETRY','terminal_success':False}));(source/'acquire.json').write_text(json.dumps({'exit_code':0,'cleanup_confirmed':True}))
            (worker/'SOURCE_PLAN.json').write_text('{}');(worker/'FIXED_CORE_MEMBERS.json').write_text('{}');(gate/'run_gate.py').write_bytes(b'fixed')
            for name in ['MANIFEST.json','SUMMARY.json']:(review/name).write_text('{}')
            cfg={'gate_source':g.pin(b'fixed'),'worker_inputs':{n:g.pin((worker/n).read_bytes()) for n in ['SOURCE_PLAN.json','FIXED_CORE_MEMBERS.json']},'failed_actual_review':{'manifest':g.pin(b'{}'),'summary':g.pin(b'{}')},'original_evidence':{n:g.pin((source/n).read_bytes()) for n in ['FAILURE.json','acquire.json']},'archive':{'bytes':1,'sha256':'a'*64}}
            data={n:(worker/n).read_bytes() for n in cfg['worker_inputs']};now=[1.];original_save=g.save
            def save(path,value):
                result=original_save(path,value)
                if late and path.name=='RESULT.json':now[0]=31.
                return result
            argv=types.SimpleNamespace(gate_source=gate,worker_source=worker,failed_actual_review=review,original_attempt=source,output=out)
            fake=types.SimpleNamespace(postflight=lambda *a:{'received_bytes':1,'archive_sha256_observed':'a'*64,'selected_bytes':11747893})
            before=g.inventory(source)
            with mock.patch.object(g,'config',return_value=(cfg,fake,{},data)),mock.patch.object(g,'limits'),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g,'save',side_effect=save),contextlib.redirect_stdout(io.StringIO()):
                if late:
                    with self.assertRaisesRegex(ValueError,'final save'):g.execute(argv,0.)
                else:g.execute(argv,0.)
            self.assertEqual(before,g.inventory(source));result=json.loads((out/'RESULT.json').read_bytes());self.assertFalse(result['terminal_success']);self.assertEqual(result['original_acquisition_verdict'],'FAIL_PRESERVED_NO_RETRY')
    def test_new_evidence_preserves_original_failure(self):self.outer()
    def test_late_final_save_never_terminal(self):self.outer(late=True)

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+extra,verbosity=2)
