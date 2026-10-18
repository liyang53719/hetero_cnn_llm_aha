"""Tiny local buffers and mocks only; never parses the real 42MB FIR."""
import argparse,contextlib,hashlib,io,json,signal,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(add_help=False);p.add_argument('--checker',type=Path,required=True);args,remaining=p.parse_known_args()
raw=(HERE/'run_structure_gate.py').read_bytes()
if len(raw)!=7972 or hashlib.sha256(raw).hexdigest()!='0484d8824ddc9c45aab727ea0a54f6248450c70c28eb9adb3a845af47832b510':raise ValueError('gate source drift')
g=types.ModuleType('fixed_structure_gate');g.__file__=str(HERE/'run_structure_gate.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)

class StructureCold(unittest.TestCase):
    def test_01_original_checker_raw_source_only(self):
        m=g.load_checker(args.checker);self.assertTrue(callable(m.check_bytes));self.assertEqual(m.MAX_BYTES,48*1024*1024)
        self.assertEqual(m.MAX_DEFINITIONS,768);self.assertEqual(m.MAX_PATHS,20000)

    def test_02_fixed_buffer_read_and_post_hash(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'fixture';f.write_bytes(b'fixture')
            with mock.patch.object(g,'FIR_BYTES',7),mock.patch.object(g,'FIR_SHA',g.sha(b'fixture')):
                raw,identity=g.read_fir(f,True);self.assertEqual(raw,b'fixture');self.assertEqual(g.read_fir(f,False),(None,identity))
                f.write_bytes(b'changed')
                with self.assertRaises(ValueError):g.read_fir(f,True)

    def test_03_symlink_fir_refused(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'fixture';f.write_bytes(b'fixture');link=Path(t)/'link';link.symlink_to('fixture')
            with self.assertRaises(ValueError):g.read_fir(link,True)

    def test_04_pending_review_before_read(self):
        with mock.patch.object(g,'GENERATION_REVIEW_SHA','PENDING'),mock.patch.object(g,'read_fir') as read:
            with self.assertRaises(ValueError):g.execute(types.SimpleNamespace(),0)
            read.assert_not_called()

    def test_05_source_preflight_no_fir_or_resource_changes(self):
        with mock.patch.object(sys,'argv',['g','--checker',str(args.checker)]),mock.patch.object(g,'read_fir',side_effect=AssertionError('actual read')),mock.patch.object(g,'limits',side_effect=AssertionError('limit')),contextlib.redirect_stdout(io.StringIO()) as out:
            g.main();self.assertFalse(json.loads(out.getvalue())['actual_fir_read'])

    def test_06_resource_budget_mocked(self):
        with mock.patch.object(g.os,'sched_getaffinity',return_value={3,5}),mock.patch.object(g.os,'sched_setaffinity') as affinity,mock.patch.object(g.resource,'setrlimit') as setlimit:
            g.limits();affinity.assert_called_once_with(0,{3})
            self.assertIn(mock.call(g.resource.RLIMIT_AS,(1073741824,1073741824)),setlimit.call_args_list)
            self.assertIn(mock.call(g.resource.RLIMIT_CPU,(80,80)),setlimit.call_args_list)
            self.assertIn(mock.call(g.resource.RLIMIT_FSIZE,(2097152,2097152)),setlimit.call_args_list)

    def fixture(self,mode='ok'):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fir=root/'actual/fixture.fir';fir.parent.mkdir();fir.write_bytes(b'fixture');output=root/'report';now=[0.0];seen=[]
            original_save=g.save
            def check(raw):
                seen.append(raw)
                if mode=='syntax':raise ValueError('unsupported observed syntax')
                if mode=='timeout':raise TimeoutError('structure check70s deadline')
                if mode=='changed':fir.write_bytes(b'changed')
                return {'status':'PASS','bytes':7,'sha256':g.sha(b'fixture'),'definition_count':2,'host_instance_count':3,'collection_instance_count':4}
            def save(path,value):
                original_save(path,value)
                if path.name=='STRUCTURE_EVIDENCE.json' and mode in ('late','interrupt'):
                    now[0]=91
                    if mode=='interrupt':raise TimeoutError('after final evidence save')
            a=types.SimpleNamespace(checker=args.checker,fir=fir,output=output)
            with mock.patch.object(g,'GENERATION_REVIEW_SHA','a'*64),mock.patch.object(g,'FIR_BYTES',7),mock.patch.object(g,'FIR_SHA',g.sha(b'fixture')),mock.patch.object(g,'load_checker',return_value=types.SimpleNamespace(check_bytes=check)),mock.patch.object(g,'limits'),mock.patch.object(g,'save',side_effect=save),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer') as timer,mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]):
                if mode!='ok':
                    with self.assertRaises((ValueError,TimeoutError)):g.execute(a,0)
                    if mode in ('late','interrupt'):
                        evidence=json.loads((output/'STRUCTURE_EVIDENCE.json').read_bytes());self.assertFalse(evidence['terminal_success'])
                    else:
                        evidence=json.loads((output/'FAILURE.json').read_bytes());self.assertEqual(evidence['status'],'INCOMPLETE_STATIC_STRUCTURE');self.assertFalse(evidence['terminal_success'])
                        self.assertEqual(evidence['fir_unchanged_rechecked'],mode!='changed')
                    self.assertEqual(fir.read_bytes(),b'changed' if mode=='changed' else b'fixture')
                else:
                    r=g.execute(a,0);self.assertEqual(seen,[b'fixture']);self.assertFalse(r['terminal_success']);self.assertTrue(r['fir_unchanged'])
                    self.assertEqual(r['structure']['host_instance_count'],3);self.assertEqual(r['structure']['collection_instance_count'],4)
                    self.assertEqual(r['structure']['definition_count'],2)
                    values=[c.args[1] for c in timer.call_args_list];self.assertIn(10,values);self.assertIn(70,values);self.assertIn(90,values)

    def test_07_same_buffer_check_and_distinct_count_scopes(self):self.fixture()
    def test_08_unknown_syntax_is_incomplete_and_retained(self):self.fixture('syntax')
    def test_09_timeout_is_incomplete_and_retained(self):self.fixture('timeout')
    def test_10_post_read_changes_rejected(self):self.fixture('changed')
    def test_11_late_final_record_is_non_success(self):self.fixture('late')
    def test_12_interrupted_final_record_is_non_success(self):self.fixture('interrupt')

    def test_13_report_bound(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):g.save(Path(t)/'report',{'data':'x'*(2*1024*1024)})
            self.assertFalse((Path(t)/'report').exists())

    def test_14_existing_timer_refused(self):
        with mock.patch.object(g,'GENERATION_REVIEW_SHA','a'*64),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(1.0,0.0)),mock.patch.object(g,'limits') as limits:
            with self.assertRaises(ValueError):g.execute(types.SimpleNamespace(),0)
            limits.assert_not_called()

if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use python -I -S -B')
    unittest.main(argv=[sys.argv[0]]+remaining,verbosity=2)
