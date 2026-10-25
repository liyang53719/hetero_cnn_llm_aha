"""Pure-stdlib synthetic import/audit tests. No task, native, or DUT imports."""
import __future__,ast,contextlib,hashlib,importlib,importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import _frozen_importlib_external as frozen
import _io
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from common import file_id
from runtime_admission import PhaseAudit

ACTIVE=None
ORACLE=None

def oracle_first(event,args):
    if ORACLE is not None and event=='open' and args and str(args[0]) in ORACLE.paths:
        ORACLE.denied.append(dict(event=event,target=str(args[0]),reason='synthetic sealed oracle'))
        raise PermissionError('synthetic oracle first denial')

def router_second(event,args):
    if ACTIVE is not None:ACTIVE.audit(event,args)

sys.addaudithook(oracle_first)
sys.addaudithook(router_second)

class Cold:
    def __init__(self,config):self.config=config;self.blocked=[];self.checking=set()
    def audit(self,event,args):
        if event!='open' or not isinstance(args[0],(str,bytes,os.PathLike)):return
        path=Path(os.fsdecode(args[0])).resolve();name=str(path)
        if path.suffix=='.pyc':
            self.blocked.append(dict(kind='bytecode_cache_not_admitted',detail=name))
            raise PermissionError('cold cache denial')
        if name in self.checking:return
        if name not in self.config['runtime_files']:
            self.blocked.append(dict(kind='unapproved_read',detail=name));raise PermissionError('cold unknown')
        self.checking.add(name)
        try:
            if file_id(path)!=self.config['runtime_files'][name]:
                self.blocked.append(dict(kind='pinned_file_drift',detail=name));raise PermissionError('cold drift')
        finally:self.checking.remove(name)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.out=self.root/'out';self.out.mkdir()
        self.cfg=dict(elf=str(self.root/'synthetic.so'),oracle_files={},runtime_files={},provider_files={})
        self.oracle=SimpleNamespace(state='SEALED',denied=[],paths=set())
        self.cold=Cold(self.cfg);self.router=PhaseAudit(self.cfg,self.cold,self.oracle,self.out)
    def tearDown(self):self.temp.cleanup()
    def source(self,name='fixture',raw=b'VALUE = 7\ndef identity(x):\n    return x\n'):
        path=self.root/(name+'.py');path.write_bytes(raw);self.cfg['runtime_files'][str(path)]=file_id(path);return path
    @contextlib.contextmanager
    def active(self,native=True):
        global ACTIVE,ORACLE
        if native and self.router.phase=='NORMAL':self.router.leave_normal()
        ACTIVE=self.router;ORACLE=self.oracle
        try:yield
        finally:ACTIVE=None;ORACLE=None
    def load(self,path,name='synthetic'):
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    def clean(self):
        self.router.require_clean();self.assertEqual(self.router.denied,[])
        self.assertTrue(all(x['status']=='EXPECTED_PINNED_SOURCE_FALLBACK' for x in self.router.cache_fallback.events))
    def fails_clean(self):
        with self.assertRaises(ValueError):self.router.require_clean()

    def test_pinned_source_exec_and_cache_bytes_never_read(self):
        path=self.source();cache=Path(importlib.util.cache_from_source(str(path)));cache.parent.mkdir();cache.write_bytes(b'not usable cache, MUST NOT read')
        reads=[];original=_io.open_code
        def traced(name):
            reads.append(str(name));return original(name)
        with patch.object(_io,'open_code',traced),self.active():
            module=self.load(path);self.assertEqual(module.VALUE,7);self.clean()
        row=self.router.report()['bytecode_cache_events'][0]
        self.assertTrue(row['source_open_observed'] and row['source_bytes_verified'] and row['exec_code_verified'])
        self.assertFalse(row['cache_bytes_admitted']);self.assertEqual(row['compiled_code_sha256'],row['exec_code_sha256'])
        self.assertEqual(len(self.router.cache_fallback.events),1)
    def test_unknown_cache_direct_open_sticky(self):
        with self.active():
            with self.assertRaises(PermissionError):open(self.root/'unknown.pyc','rb')
            self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'cache_without_exact_source_loader')
    def test_unknown_source_loader_sticky(self):
        path=self.source();self.cfg['runtime_files'].clear()
        with self.active():
            with self.assertRaises(PermissionError):self.load(path)
            self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'cache_source_not_pinned')
    def test_drifted_source_sticky(self):
        path=self.source();path.write_bytes(b'VALUE = 8\n')
        with self.active():
            with self.assertRaises(PermissionError):self.load(path)
            self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'read_source_provider_drift')
    def test_no_fallback_open_sticky(self):
        path=self.source();original=_io.open_code
        def broken(name):
            if str(name)==str(path):raise OSError('synthetic source cannot open')
            return original(name)
        with patch.object(_io,'open_code',broken),self.active():
            with self.assertRaises(OSError):self.load(path)
            self.fails_clean()
        self.assertEqual(self.router.cache_fallback.events[0]['status'],'REJECTED_UNRESOLVED')
    def test_source_open_not_completed_read(self):
        path=self.source();original=_io.open_code
        class ReadFailure:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):return self
            def __exit__(self,*args):self.stream.close()
            def read(self):raise OSError('synthetic read failure after open')
        def broken(name):
            value=original(name);return ReadFailure(value) if str(name)==str(path) else value
        with patch.object(_io,'open_code',broken),self.active():
            with self.assertRaises(OSError):self.load(path)
            self.fails_clean()
        row=self.router.cache_fallback.events[0];self.assertTrue(row['source_open_observed']);self.assertFalse(row['source_bytes_verified'])
    def test_wrong_pinned_source_sticky(self):
        path=self.source();wrong=self.source('wrong');original=_io.open_code
        def redirected(name):return original(str(wrong) if str(name)==str(path) else name)
        with patch.object(_io,'open_code',redirected),self.active():
            with self.assertRaises(PermissionError):self.load(path)
            self.fails_clean()
        self.assertIn('cache_fallback_wrong_source',[x['kind'] for x in self.router.denied])
    def test_compile_actual_bytes_not_earlier_hash(self):
        path=self.source();original=_io.open_code
        class SwappedRead:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):return self
            def __exit__(self,*args):self.stream.close()
            def read(self):return b'VALUE = 999\n'
        def swapped(name):
            value=original(name);return SwappedRead(value) if str(name)==str(path) else value
        with patch.object(_io,'open_code',swapped),self.active():
            with self.assertRaises(PermissionError):self.load(path)
            self.fails_clean()
        self.assertIn('cache_fallback_source_bytes_drift',[x['kind'] for x in self.router.denied])
    def test_compile_without_exec_unresolved(self):
        path=self.source()
        with patch.object(frozen,'exec',lambda *a,**k:None,create=True),self.active():
            self.load(path);self.fails_clean()
        row=self.router.cache_fallback.events[0];self.assertTrue(row['source_bytes_verified']);self.assertFalse(row['exec_code_verified'])
    def test_wrong_executed_code_sticky(self):
        path=self.source();wrong=compile(b'VALUE = 999\n',str(path),'exec');original=exec
        def swapped(code,globals):return original(wrong,globals)
        with patch.object(frozen,'exec',swapped,create=True),self.active():
            with self.assertRaises(PermissionError):self.load(path)
            self.fails_clean()
        self.assertIn('cache_fallback_exec_code_mismatch',[x['kind'] for x in self.router.denied])
    def test_module_body_failure_not_claimed_success(self):
        path=self.source(raw=b'raise RuntimeError("synthetic module body failure")\n')
        with self.active():
            with self.assertRaises(RuntimeError):self.load(path)
            self.clean()
        self.assertTrue(self.router.cache_fallback.events[0]['module_body_completed_not_claimed'])
    def test_dynamic_qualified_runtime_fields_loader(self):
        path=self.source('capture')
        with self.active():
            self.assertEqual(self.load(path,'_qualified_runtime_fields').VALUE,7);self.clean()
        self.assertEqual(self.router.cache_fallback.events[0]['module'],'_qualified_runtime_fields')
    def test_normal_then_native_multiple_loader_invocations(self):
        first=self.source('one');second=self.source('two')
        with self.active(native=False):
            self.load(first,'normal_one');self.router.leave_normal()
            self.load(second,'native_two');self.load(first,'native_again');self.clean()
        self.assertEqual([x['phase'] for x in self.router.cache_fallback.events],['NORMAL','NATIVE','NATIVE'])
        self.assertEqual(len(self.cold.blocked),1)
        with self.assertRaises(ValueError):self.router.leave_normal()
    def test_unwitnessed_old_normal_cache_denial_not_excused(self):
        self.cold.blocked.append(dict(kind='bytecode_cache_not_admitted',detail='/unknown.pyc'))
        with self.assertRaises(ValueError):self.router.leave_normal()
    def test_normal_unresolved_never_transitions(self):
        path=self.source()
        with patch.object(frozen,'exec',lambda *a,**k:None,create=True),self.active(native=False):
            self.load(path)
            with self.assertRaises(ValueError):self.router.leave_normal()
        self.assertEqual(self.router.phase,'NORMAL')
    def test_oracle_first_denial_never_reclassified(self):
        path=self.source();sealed=self.root/'oracle.bin';sealed.write_bytes(b'no secret fixture');self.oracle.paths.add(str(sealed))
        with self.active():
            with self.assertRaises(PermissionError):sealed.read_bytes()
            self.load(path);self.fails_clean()
        self.assertTrue(self.router.oracle.denied);self.assertEqual(self.router.denied,[])
        self.assertEqual(len(self.router.cache_fallback.events),1)
        self.assertTrue(self.router.report()['oracle_denied'])
    def test_oracle_first_cache_denial_never_reclassified(self):
        path=self.source();cache=importlib.util.cache_from_source(str(path));self.oracle.paths.add(cache)
        with self.active():
            self.load(path);self.fails_clean()
        self.assertTrue(self.oracle.denied);self.assertEqual(self.router.cache_fallback.events,[])
    def test_hashing_not_fallback_source_open_or_self_recursion(self):
        path=self.source();calls=[];original=Path.open
        def counted(p,*args,**kwargs):
            if p==path:calls.append(str(p))
            return original(p,*args,**kwargs)
        with patch.object(Path,'open',counted),self.active():
            self.load(path);self.clean()
        self.assertEqual(len(calls),1);self.assertEqual(len(self.router.cache_fallback.events),1)
    def test_no_unbounded_provider_or_network_permission(self):
        with self.active():
            for event,args in [('open',(str(self.root/'unapproved.bin'),'rb',0)),('socket.connect',())]:
                with self.assertRaises(PermissionError):self.router.audit(event,args)
            self.fails_clean()
    def test_existing_sticky_denial_survives_valid_fallback(self):
        path=self.source()
        with self.active():
            with self.assertRaises(PermissionError):self.router.audit('socket.connect',())
            self.load(path);self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'network_or_child_process_forbidden')
    def test_cache_under_output_is_still_denied(self):
        path=self.out/'cached.pyc';path.write_bytes(b'synthetic')
        with self.active():
            with self.assertRaises(PermissionError):path.read_bytes()
            self.fails_clean()
    def test_code_with_future_nested_functions_and_classes(self):
        path=self.source(raw=b'from __future__ import annotations\nclass A:\n def f(self, x: A) -> A:\n  def inner(): return x\n  return inner()\nVALUE = 7\n')
        with self.active():self.load(path);self.clean()
    def test_prior_success_does_not_qualify_direct_cache_read(self):
        path=self.source();cache=importlib.util.cache_from_source(str(path))
        with self.active():
            self.load(path)
            with self.assertRaises(PermissionError):open(cache,'rb')
            self.fails_clean()
        self.assertEqual(len(self.router.cache_fallback.events),2)
        self.assertEqual(self.router.cache_fallback.events[1]['status'],'REJECTED')
    def test_cache_symlink_to_source_not_admitted(self):
        path=self.source();cache=Path(importlib.util.cache_from_source(str(path)));cache.parent.mkdir();cache.symlink_to(path)
        with self.active():
            self.load(path);self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'cache_source_path_mismatch')
    def test_direct_cache_symlink_not_admitted(self):
        path=self.source();cache=self.root/'alias.pyc';cache.symlink_to(path)
        with self.active():
            with self.assertRaises(PermissionError):cache.read_bytes()
            self.fails_clean()
    def test_exact_source_loader_subclass_not_admitted(self):
        path=self.source()
        class CustomLoader(importlib.machinery.SourceFileLoader):pass
        loader=CustomLoader('custom',str(path));spec=importlib.util.spec_from_loader('custom',loader);module=importlib.util.module_from_spec(spec)
        with self.active():
            loader.exec_module(module);self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'cache_without_exact_source_loader')
    def test_loader_method_replacement_not_admitted(self):
        path=self.source();original=importlib.machinery.SourceFileLoader.source_to_code
        def replacement(self,*args,**kwargs):return original(self,*args,**kwargs)
        with patch.object(importlib.machinery.SourceFileLoader,'source_to_code',replacement),self.active():
            self.load(path);self.fails_clean()
        self.assertEqual(self.router.denied[0]['kind'],'cache_without_exact_source_loader')
    def test_compile_hashing_does_not_reopen_source(self):
        path=self.source();calls=[];original=_io.open_code
        def counted(name):calls.append(str(name));return original(name)
        with patch.object(_io,'open_code',counted),self.active():self.load(path);self.clean()
        self.assertEqual(calls.count(str(path)),1)
    def test_normal_raw_denial_is_retained_and_exact(self):
        path=self.source()
        with self.active(native=False):
            self.load(path);before=[dict(row) for row in self.cold.blocked];self.router.leave_normal()
        self.assertEqual(self.cold.blocked,before);self.assertEqual(len(before),1)

    def test_worker_final_policy_refresh_order(self):
        tree=ast.parse((HERE/'worker.py').read_text());function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='execute')
        final=next(x for x in function.body if isinstance(x,ast.Try)).finalbody
        calls=[x for node in final for x in ast.walk(node) if isinstance(x,ast.Call)]
        self.assertTrue(any(isinstance(x.func,ast.Attribute) and x.func.attr=='require_clean' for x in calls))
        self.assertEqual(sum(isinstance(x.func,ast.Attribute) and x.func.attr=='run_actual' for x in ast.walk(tree) if isinstance(x,ast.Call)),1)

if __name__=='__main__':unittest.main(verbosity=2)
