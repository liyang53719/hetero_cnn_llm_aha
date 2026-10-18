"""Finite synthetic staging-wrapper checks; never reads or extracts real deb bodies."""
import argparse,contextlib,hashlib,io,json,os,socket,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise ValueError('use -I -S -B')
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--worker-source',type=Path,required=True);args,extra=parser.parse_known_args()
raw=(HERE/'run_stage.py').read_bytes()
if len(raw)!=8657 or hashlib.sha256(raw).hexdigest()!='e0c6e0b4e31834880fbabca809fea4e4b7de48c612bf75cb6705b1094762f07e':raise ValueError('cold wrapper raw pin')
g=types.ModuleType('fixed_staging_gate');g.__file__=str(HERE/'run_stage.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)

class Cold(unittest.TestCase):
    def setUp(self):self.net=mock.patch.object(socket,'socket',side_effect=AssertionError('no network'));self.net.start()
    def tearDown(self):self.net.stop()
    def fixture(self,base):
        root=base/'stage';root.mkdir(mode=0o700);inputs=base/'inputs';inputs.mkdir()
        selected=[];rows={};n=3598623//67
        for i in range(67):
            name='data%02d'%i;raw=b'x'*(n if i<66 else 3598623-66*n);(root/name).write_bytes(raw);(root/name).chmod(0o600);q=g.pin(raw);selected.append({'path':name,**q});rows[name]={**q,'mode':'0o600'}
        (root/'relocation').mkdir(mode=0o700);cfg=b'four exact changes';(root/'relocation/autom4te.cfg').write_bytes(cfg);(root/'relocation/autom4te.cfg').chmod(0o600);rows['relocation/autom4te.cfg']={**g.pin(cfg),'mode':'0o600'}
        (inputs/'one.deb').write_bytes(b'opaque');p={'packages':[{'selected':selected,'deb_filename':'one.deb','deb_bytes':6,'deb_sha256':g.pin(b'opaque')['sha256']}],'derived_cfg':g.pin(cfg)}
        m=types.SimpleNamespace(OUTPUT_ROOT=str(root),INPUT_ROOT=str(inputs),CFG_SHA='fixed',require_actual_review=lambda p:None)
        report={'status':'STAGING_EVIDENCE_PENDING_PARENT_ACCEPTANCE','package_tools_executed':False,'qualification':'NOT_RUN','selected_count':67,'selected_bytes':3598623,'all_original_input_stats_and_hashes_unchanged':True,'files':rows,'relocation':{'replacements':4,'source_sha256':'fixed','derived_sha256':p['derived_cfg']['sha256']}}
        encoded=(json.dumps(report)+'\n').encode();(root/'STAGING_REPORT.json').write_bytes(encoded);(root/'STAGING_REPORT.json').chmod(0o600)
        summary={'report_bytes':len(encoded),'report_sha256':g.pin(encoded)['sha256'],'output_bytes':3598623+len(cfg)+len(encoded),'output_files':69}
        return m,p,summary
    def test_pinned_worker_source_only(self):
        with self.assertRaisesRegex(ValueError,'ACTUAL_IDENTITY_REVIEW_PENDING'):g.preflight(args.worker_source)
    def test_exact69_synthetic_inventory(self):
        with tempfile.TemporaryDirectory() as t:
            m,p,s=self.fixture(Path(t));self.assertEqual(g.postflight(m,p,s)['files'],69)
    def test_missing_extra_or_mutated_data_rejected(self):
        for kind in ['missing','extra','mutated']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as t:
                m,p,s=self.fixture(Path(t));root=Path(m.OUTPUT_ROOT)
                if kind=='missing':(root/'data00').unlink()
                elif kind=='extra':(root/'extra').write_bytes(b'x')
                else:(root/'data00').write_bytes(b'wrong')
                with self.assertRaises(ValueError):g.postflight(m,p,s)
    def test_file_or_directory_mode_rejected(self):
        for relative in ['data00','relocation','.']:
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as t:
                m,p,s=self.fixture(Path(t));(Path(m.OUTPUT_ROOT)/relative).chmod(0o755)
                with self.assertRaises(ValueError):g.postflight(m,p,s)
    def test_link_and_hardlink_rejected(self):
        for kind in ['symlink','hardlink']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as t:
                m,p,s=self.fixture(Path(t));root=Path(m.OUTPUT_ROOT);(root/'data00').unlink()
                if kind=='symlink':(root/'data00').symlink_to(root/'data01')
                else:os.link(root/'data01',root/'data00')
                with self.assertRaises(ValueError):g.postflight(m,p,s)
    def test_input_hash_changed_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            m,p,s=self.fixture(Path(t));(Path(m.INPUT_ROOT)/'one.deb').write_bytes(b'changed')
            with self.assertRaises(ValueError):g.postflight(m,p,s)
    def test_worker_loader_bad_pin_before_compile(self):
        with mock.patch('builtins.compile') as c:
            for raw in [b'raise RuntimeError()',b'x'*g.WORKER['bytes']]:
                with self.assertRaises(ValueError):g.load(raw,HERE/'fixture.py')
            c.assert_not_called()
    def test_save_exclusive_and600(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'evidence';g.save(p,b'fixed');self.assertEqual(p.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):g.save(p,b'overwrite')
            self.assertEqual(p.read_bytes(),b'fixed')
    def test_source_default_has_no_actual_stage(self):
        with mock.patch.object(sys,'argv',['g','--worker-source',str(args.worker_source)]),mock.patch.object(g,'execute',side_effect=AssertionError('actual')),mock.patch.object(Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'ACTUAL_IDENTITY_REVIEW_PENDING'):g.main()
            mkdir.assert_not_called()
    def test_limits_exact(self):
        with mock.patch.object(g.os,'sched_getaffinity',return_value={3,7}),mock.patch.object(g.os,'sched_setaffinity') as aff,mock.patch.object(g.resource,'setrlimit') as limits:g.process_limits()
        aff.assert_called_once_with(0,{3})
        self.assertEqual(limits.call_args_list,[mock.call(k,(v,v)) for k,v in [(g.resource.RLIMIT_AS,512*1024*1024),(g.resource.RLIMIT_CPU,40),(g.resource.RLIMIT_FSIZE,4*1024*1024),(g.resource.RLIMIT_CORE,0)]])
    def outer(self,late=False,fail=False):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);source=base/'worker';source.mkdir();inputs=base/'input';inputs.mkdir();stage=base/'stage';out=base/'outer'
            raws={'stage_dependencies.py':b'fixed','PINS.json':b'{}'}
            for name,raw in raws.items():(source/name).write_bytes(raw)
            def stage_call():
                self.assertFalse(stage.exists())
                if fail:raise OSError('original stage error')
                return {}
            m=types.SimpleNamespace(OUTPUT_ROOT=str(stage),INPUT_ROOT=str(inputs),stage_fixed=stage_call);now=[1.];original_save=g.save_json
            def save(path,value):
                result=original_save(path,value)
                if late and path.name=='RESULT.json':now[0]=61.
                return result
            with mock.patch.object(g,'preflight',return_value=(raws,m,{})),mock.patch.object(g,'load',return_value=m),mock.patch.object(g,'postflight',return_value={'bytes':1,'files':69}),mock.patch.object(g,'checked',return_value=b''),mock.patch.object(g,'process_limits'),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer') as timer,mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g,'save_json',side_effect=save),contextlib.redirect_stdout(io.StringIO()):
                if fail:
                    with self.assertRaisesRegex(OSError,'original stage error'):g.execute(source,out,0.)
                elif late:
                    with self.assertRaisesRegex(ValueError,'final receipt'):g.execute(source,out,0.)
                else:g.execute(source,out,0.)
                self.assertEqual(timer.call_args_list,[mock.call(g.signal.ITIMER_REAL,59.)])
            if fail:
                self.assertFalse((out/'RESULT.json').exists());self.assertEqual(json.loads((out/'FAILURE.json').read_bytes())['error_type'],'OSError')
            else:
                result=json.loads((out/'RESULT.json').read_bytes());self.assertFalse(result['terminal_success']);self.assertFalse(result['package_tools_executed'])
                if late:self.assertFalse((out/'FAILURE.json').exists())
    def test_nonteminal_evidence_and_no_precreated_stage(self):self.outer()
    def test_late_save_never_terminal_success(self):self.outer(late=True)
    def test_failure_original_error_saved(self):self.outer(fail=True)
    def test_inherited_timer_rejected_before_staging(self):
        with mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(1.,0.)),mock.patch.object(g,'preflight') as pre:
            with self.assertRaisesRegex(ValueError,'inherited timer'):g.execute(args.worker_source,Path('/not-used'),0.)
            pre.assert_not_called()

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+extra,verbosity=2)
