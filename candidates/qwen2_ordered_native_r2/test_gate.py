"""Cold stdlib admission tests. Never calls main/load_library/run_owner."""
import argparse,ast,hashlib,importlib.util,json,os,sys,tempfile,unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--source-root',type=Path,default=HERE.parents[2]);args,rest=parser.parse_known_args();SOURCE_ROOT=args.source_root.resolve(strict=True);sys.argv[:]=[sys.argv[0],*rest]
import worker
if Path(worker.__file__).resolve()!=HERE/'worker.py':raise ImportError('worker origin')

class Gate(unittest.TestCase):
    def config(self,path):
        files={str(path):dict(bytes=1,sha256=hashlib.sha256(b'x').hexdigest()),str(Path(sys.executable).resolve()):dict(bytes=Path(sys.executable).stat().st_size,sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest())}
        graph=dict(schema=1,roots=[str(path)],files={str(path):dict(files[str(path)],needed=[],soname=None,interpreter=None)},edges=[],loader_environment={'LD_LIBRARY_PATH':'','LD_PRELOAD':''})
        return dict(commit='a672a56feef9b661f6682bedfcbd702d1ddbc3fa',profile='reuse_qk2_legacy_pv0_attention_component',files=files,elf=str(path),inputs={n:dict(path=str(path)) for n in ('qr','kr','v')},git_environment={'GIT_DIR':str(path.parent)},runtime_graph=graph,runtime_graph_sha256=hashlib.sha256((json.dumps(graph,indent=2)+'\n').encode()).hexdigest())
    def test_exact_helper_existing_decorator(self):
        import harness
        source=SOURCE_ROOT/'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py'
        ns=harness.load_exact(source)
        self.assertEqual(ns['ref_add'](0x3f800000,0x3f800000),0x40000000)
    def test_original_finish_releases_scalar_before_terminal_ack(self):
        path=SOURCE_ROOT/'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py'
        tree=ast.parse(path.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PrefixOwner');fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_finish')
        ns={'OwnerResult':lambda *args:args};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
        scalar=SimpleNamespace(client=None,calls=Counter());owner=SimpleNamespace(scalar=scalar,poison=False,scalar_baseline=Counter(),job=SimpleNamespace(tag=1),ack_bytes=64,clock=9,start_clock=1)
        scalar.client=owner;scalar.release=lambda x:setattr(scalar,'client',None)
        ns['_finish'](owner)
        self.assertEqual(owner.state,'finish');self.assertIsNone(scalar.client)
    def test_claim_prevents_repeated_output_alias(self):
        import launch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text('{}')
            launch.claim(p,1,'hash',Path(d)/'one')
            with self.assertRaises(FileExistsError):launch.claim(p,1,'hash',Path(d)/'two')
    def test_m2_requires_m1_terminal(self):
        import launch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text('{}')
            with self.assertRaises(FileNotFoundError):launch.claim(p,2,'hash',Path(d)/'two')
    def test_integrity_window_does_not_open_other_reference(self):
        g=self.guard();g.terminal=True;g.integrity=True;g.config['files']={'/pinned/test.npz':{}}
        g.audit('open',('/pinned/test.npz','r',0))
        with self.assertRaises(ValueError):g.audit('open',('/reference/att.f32le','r',0))
    def reviewed_fixture(self,root):
        import admission
        names=('admission.py','harness.py','worker.py','launch.py','runtime_closure.py')
        pins={}
        for name in names:
            f=root/name;f.write_text('pass\n');pins[name]=admission.sha(f)
        config=root/'CONFIG.json';config.write_text(json.dumps({'files':{str(root/name):{'sha256':pins[name]} for name in names}},indent=2)+'\n')
        review=root/'REVIEW.json';review.write_text(json.dumps(dict(status='PASS_STATIC_REVIEW_REQUIRES_ROOT_EXECUTION_AUTHORIZATION',config_sha256=admission.sha(config),limits=dict(cpu_seconds=30,address_space_bytes=1<<30,wall_seconds=45,cpus=1),executable_sources=pins)))
        return config,review,admission.sha(review)
    def test_exact_review_config_one_byte_change_rejected(self):
        import admission
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=self.reviewed_fixture(root);admission.validate_review(c,r,h,root)
            c.write_bytes(c.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'exact reviewed'):admission.validate_review(c,r,h,root)
    def test_reviewed_executable_source_change_rejected(self):
        import admission
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=self.reviewed_fixture(root);(root/'worker.py').write_text('changed\n')
            with self.assertRaisesRegex(ValueError,'executable source'):admission.validate_review(c,r,h,root)
    def test_review_receipt_byte_change_rejected(self):
        import admission
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c,r,h=self.reviewed_fixture(root);r.write_bytes(r.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'receipt identity'):admission.validate_review(c,r,h,root)
    def test_unknown_maps_all_preserved_before_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);lines=[]
            for name in ('first.so','second.so'):
                f=root/name;f.write_bytes(b'\x7fELFfixture');lines.append('100-200 r--p 0000 00:00 %d %s\n'%(f.stat().st_ino,f))
            raw=''.join(lines)
            with self.assertRaisesRegex(ValueError,'evidence preserved'):worker.verify_maps({'files':{}},root,raw)
            self.assertEqual((root/'MAPS_BEFORE_AUDIT.txt').read_text(),raw)
            report=json.loads((root/'MAP_AUDIT.json').read_text());self.assertEqual(len(report['failures']),2);self.assertEqual(report['status'],'FAIL_UNKNOWN_OR_CHANGED_MAPPING')
    def test_stage_receipt_written_independently(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);worker.emit(root,'ARM_TERMINAL_ACKED',{'native_fmas':1});worker.emit(root,'FAILED_RETAINED',{'detail':'unknown mapping'})
            self.assertEqual([json.loads(x)['stage'] for x in (root/'STAGES.jsonl').read_text().splitlines()],['ARM_TERMINAL_ACKED','FAILED_RETAINED'])
    def graph_fixture(self,root):
        files={}
        for name in ('root.so','libz.so.1'):
            p=root/name;p.write_bytes(b'fixture');files[str(p)]=dict(bytes=7,sha256=hashlib.sha256(b'fixture').hexdigest())
        a=str(root/'root.so');z=str(root/'libz.so.1')
        nodes={a:dict(files[a],needed=['libz.so.1'],soname='root.so',interpreter=None),z:dict(files[z],needed=[],soname='libz.so.1',interpreter=None)}
        return dict(schema=1,roots=[a],files=nodes,edges=[dict(kind='needed',needed='libz.so.1',link=z,target=z,**{'from':a})],loader_environment={'LD_LIBRARY_PATH':'','LD_PRELOAD':''}),files
    def test_missing_needed_library_rejected(self):
        from runtime_closure import verify_graph
        with tempfile.TemporaryDirectory() as d:
            graph,files=self.graph_fixture(Path(d));verify_graph(graph,files);del graph['files'][str(Path(d)/'libz.so.1')]
            with self.assertRaises(ValueError):verify_graph(graph,files)
    def test_missing_needed_edge_rejected(self):
        from runtime_closure import verify_graph
        with tempfile.TemporaryDirectory() as d:
            graph,files=self.graph_fixture(Path(d));graph['edges']=[]
            with self.assertRaisesRegex(ValueError,'edge set incomplete'):verify_graph(graph,files)
    def test_unreachable_extra_library_rejected(self):
        from runtime_closure import verify_graph
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);graph,files=self.graph_fixture(root);p=root/'compiler';p.write_bytes(b'extra');pin=dict(bytes=5,sha256=hashlib.sha256(b'extra').hexdigest());files[str(p)]=pin;graph['files'][str(p)]=dict(pin,needed=[],soname=None,interpreter=None)
            with self.assertRaisesRegex(ValueError,'unreachable'):verify_graph(graph,files)
    def test_good_manifest_cold(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'one';p.write_bytes(b'x');worker.check_manifest(self.config(p))
    def test_manifest_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'one';p.write_bytes(b'y')
            with self.assertRaises(ValueError):worker.check_manifest(self.config(p))
    def test_implicit_profile_rejected(self):
        c=self.config(Path('/missing'));c['profile']='default'
        with self.assertRaises(ValueError):worker.check_manifest(c)
    def guard(self):return worker.Isolation(dict(elf='/pinned/library.so',oracle_harness='/pinned/oracle.py',inputs={n:dict(path='/input/'+n+'.f32le') for n in ('qr','kr','v')}))
    def test_oracle_read_before_terminal_rejected(self):
        with self.assertRaises(ValueError):self.guard().audit('open',('/pinned/oracle.py','r',0))
    def test_oracle_after_terminal_allowed(self):
        g=self.guard();g.terminal=True;g.audit('open',('/pinned/oracle.py','r',0))
    def test_expected_payload_never_allowed(self):
        for terminal in (False,True):
            g=self.guard();g.terminal=terminal
            with self.assertRaises(ValueError):g.audit('open',('/input/att.f32le','r',0))
    def test_declared_input_allowed(self):self.guard().audit('open',('/input/qr.f32le','r',0))
    def test_only_pinned_cdll(self):
        g=self.guard();g.audit('ctypes.dlopen',('/pinned/library.so',));g.audit('ctypes.dlopen',(None,))
        with self.assertRaises(ValueError):g.audit('ctypes.dlopen',('/other.so',))
    def test_compiler_and_network_rejected(self):
        g=self.guard()
        with self.assertRaises(ValueError):g.audit('subprocess.Popen',('g++',['g++','x.cpp'],None,None))
        with self.assertRaises(ValueError):g.audit('socket.connect',())
    def test_only_original_git_queries(self):
        g=self.guard()
        with patch.dict(os.environ,PATH='/usr/bin:/bin'):g.audit('subprocess.Popen',('git',['git','rev-parse','HEAD'],None,None))
        with self.assertRaises(ValueError):g.audit('subprocess.Popen',('git',['git','checkout','old'],None,None))
    def test_real_service_constructors_not_replaced(self):
        t=ast.parse((HERE/'harness.py').read_text());f=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner')
        names=[n.func.id for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        self.assertEqual(names.count('ScalarService'),1);self.assertEqual(names.count('MatrixService'),1);self.assertEqual(names.count('OfficialAttentionOwner'),1)
    def test_reference_only_after_real_arms(self):
        text=(HERE/'worker.py').read_text();self.assertLess(text.index('arm=run_owner('),text.index('guard.terminal=True'));self.assertLess(text.index('guard.terminal=True'),text.index('comparison=compare_original('))
    def test_launcher_no_retry_and_caps(self):
        text=(HERE/'launch.py').read_text();self.assertIn('a.output.mkdir()',text);self.assertIn('timeout=45',text);self.assertIn('(30,30)',text);self.assertNotIn('compile_fresh',text)
    def test_no_numeric_packages_imported(self):
        self.assertFalse(any(n.split('.')[0] in ('numpy','torch') for n in sys.modules))
if __name__=='__main__':unittest.main()
