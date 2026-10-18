"""Only synthetic source and mocked limits/signals; no actual assembly or Java."""
from pathlib import Path
import contextlib,hashlib,io,json,sys,tempfile,types,unittest
from unittest import mock
HERE=Path(__file__).resolve().parent
raw=(HERE/'run_source_assembly.py').read_bytes()
if len(raw)!=4504 or hashlib.sha256(raw).hexdigest()!='fe3631b570cb1f20a09e2215820a9946abfba0d726efc67846391f5b5ff00b93':raise ValueError('wrapper drift')
w=types.ModuleType('fixed_wrapper');w.__file__=str(HERE/'run_source_assembly.py')
exec(compile(raw,w.__file__,'exec',dont_inherit=True),w.__dict__)

class Cold(unittest.TestCase):
    def test_01_valid_93_source_cap_is_before_original_write(self):
        original=mock.Mock();m=types.SimpleNamespace(write_tree=original);out=Path('/synthetic/output')
        w.bound_final_source_writes(m,out);sources={str(n):b'x' for n in range(93)}
        m.write_tree(out/'scala',sources);original.assert_called_once_with(out/'scala',sources)

    def test_02_count_and_sum_fail_before_write(self):
        class Large:
            def __len__(self):return w.SOURCE_CAP+1
        for sources in ({'one':b'x'},{str(n):Large() if n==0 else b'x' for n in range(93)}):
            original=mock.Mock();m=types.SimpleNamespace(write_tree=original);out=Path('/synthetic/output')
            w.bound_final_source_writes(m,out)
            with self.assertRaises(ValueError):m.write_tree(out/'scala',sources)
            original.assert_not_called()

    def test_03_resource_policy_is_only_mocked(self):
        with mock.patch.object(w.os,'sched_getaffinity',return_value={3,7}),mock.patch.object(w.os,'sched_setaffinity') as a, mock.patch.object(w.resource,'setrlimit') as r:
            w.process_limits();a.assert_called_once_with(0,{3})
            self.assertEqual(r.call_args_list,[mock.call(w.resource.RLIMIT_AS,(536870912,536870912)),mock.call(w.resource.RLIMIT_CPU,(60,60)),mock.call(w.resource.RLIMIT_FSIZE,(33554432,33554432)),mock.call(w.resource.RLIMIT_CORE,(0,0))])

    def test_04_bad_source_refused_before_load(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'assembler.py';p.write_text('marker=True')
            with self.assertRaises(ValueError):w.load_assembler(p)

    def test_05_expiration_raises(self):
        with self.assertRaises(TimeoutError):w.expired(None,None)

    def test_06_no_execute_flag_cannot_set_limits(self):
        with mock.patch.object(sys,'argv',['w','--repo','/synthetic/repo','--hardfloat-scala','/synthetic/hf','--output','/synthetic/out']),mock.patch.object(w,'process_limits') as limits:
            with self.assertRaises(ValueError):w.main()
            limits.assert_not_called()

    def synthetic_main(self,late):
        now=[0.0]
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'output'
            def writer(root,sources):
                root.mkdir(parents=True)
                for name,raw in sources.items():(root/name).write_bytes(raw)
            m=types.SimpleNamespace(clean_path=lambda p:p.absolute(),write_tree=writer)
            def main():
                m.write_tree(out/'scala',{str(n)+'.scala':b'synthetic' for n in range(93)})
                print('assembler source result suppressed')
                if late:now[0]=61.0
            m.main=main
            with mock.patch.object(sys,'argv',['w','--repo',t,'--hardfloat-scala',t,'--output',str(out),'--execute-reviewed-source']),mock.patch.object(w,'load_assembler',return_value=m),mock.patch.object(w,'process_limits'),mock.patch.object(w.signal,'pthread_sigmask',return_value=set()),mock.patch.object(w.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(w.signal,'signal'),mock.patch.object(w.signal,'setitimer'),mock.patch.object(w.time,'monotonic',side_effect=lambda:now[0]),contextlib.redirect_stdout(io.StringIO()) as captured:
                if late:
                    with self.assertRaises(ValueError):w.main()
                    self.assertEqual(captured.getvalue(),'')
                else:
                    w.main();r=json.loads(captured.getvalue());self.assertEqual(r['status'],'SOURCE_EVIDENCE_PENDING_OUTER_EXIT0');self.assertFalse(r['terminal_success']);self.assertEqual(r['source_count'],93)

    def test_07_synthetic_only_output_requires_outer_exit0(self):self.synthetic_main(False)
    def test_08_late_synthetic_assembly_does_not_print_success(self):self.synthetic_main(True)

if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use -I -S -B')
    unittest.main(verbosity=2)
