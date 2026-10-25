"""Pure source-binding fixtures and readonly AST evidence; no DUT/native import."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

SOURCE_ROOT = None
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_fullgraph_service_trace_test',HERE/'service_trace.py')
subject=importlib.util.module_from_spec(spec);spec.loader.exec_module(subject)


class BindingFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.profile={'source_root':str(self.root),'files':{}}
        self.saved={};self.modules=[]
        methods='\n'.join('    def '+name+'(self, *args): return True' for name in subject.METHODS if name!='acquire')
        sources=[
            ('ffn_attention.matrix_service','MatrixService',
             'class MatrixService:\n    def __init__(self): raise RuntimeError("no service construction")\n    def acquire(self, owner, mode, tag): return True\n'+methods+'\n'),
            ('official_bf16.dense_silu','OfficialMatrixService',
             'class OfficialMatrixService(MatrixService):\n    def acquire(self, owner, mode, tag):\n        return super().acquire(owner, mode, tag)\n'),
            ('dense_block_reduce.matrix_binding','ProfiledMatrixService',
             'class ProfiledMatrixService(OfficialMatrixService):\n    pass\n')]
        previous={}
        for name,cls,source in sources:
            path=self.root/'candidates/qwen2_resident_matrix'/(name.replace('.','/')+'.py')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source)
            fullname=subject.ROOT_MODULE+name
            self.saved[fullname]=sys.modules.get(fullname)
            module=types.ModuleType(fullname);module.__file__=str(path);vars(module).update(previous)
            exec(compile(source,str(path),'exec'),vars(module));sys.modules[fullname]=module
            self.profile['files'][str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            previous[cls]=getattr(module,cls);self.modules.append(module)
        self.base,self.official,self.profiled=[getattr(m,c) for m,c in zip(self.modules,('MatrixService','OfficialMatrixService','ProfiledMatrixService'))]
        self.service=object.__new__(self.profiled)
        class Trace:
            METHODS=subject.METHODS
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def _return(self,*args):return 'unchanged callback'
            def stop(self):self.closed=True
            def seal(self):return tuple(self.events)
        self.runtime=types.SimpleNamespace(ServiceTrace=Trace)
        self.bind_calls=[]
        def bind(method,path,pin,cls,name,ast_test):
            self.assertFalse(ast_test)
            self.assertEqual(method.__code__.co_filename,str(path))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),pin)
            self.bind_calls.append((cls,name))
            return method.__code__
        self.bind=bind

    def tearDown(self):
        for name,old in self.saved.items():
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old
        self.temp.cleanup()

    def test_specs_without_service_construction(self):
        specs=subject.service_specs(self.profiled,self.profile)
        self.assertEqual(len(specs),9)
        self.assertIs(specs['acquire'][0],self.official.acquire)
        self.assertEqual(specs['acquire'][3],'OfficialMatrixService')
        for name in subject.METHODS[1:]:
            self.assertIs(specs[name][0],getattr(self.base,name))
            self.assertEqual(specs[name][3],'MatrixService')

    def test_factory_reuses_callbacks_exactly(self):
        trace=subject.make_trace(self.runtime,self.service,self.profile,self.bind)
        for name in ('__enter__','__exit__','_return','stop','seal'):
            self.assertIs(getattr(type(trace),name),getattr(self.runtime.ServiceTrace,name))
        self.assertIs(trace.service,self.service)
        self.assertEqual(trace.events,[])
        self.assertEqual(self.bind_calls,[('OfficialMatrixService','acquire')]+[('MatrixService',n) for n in subject.METHODS[1:]])

    def test_acquire_wrapper_only_no_double_count(self):
        trace=subject.make_trace(self.runtime,self.service,self.profile,self.bind)
        self.assertIn(self.official.acquire.__code__,trace.codes)
        self.assertNotIn(self.base.acquire.__code__,trace.codes)
        self.assertEqual(list(trace.codes.values()).count('acquire'),1)

    def test_normal_wrapper_return_frame_locals_available(self):
        code=self.official.acquire.__code__
        self.assertEqual(code.co_varnames[:4],('self','owner','mode','tag'))
        self.assertTrue(self.service.acquire(object(),'normal',12))

    def test_wrong_service_type(self):
        with self.assertRaisesRegex(ValueError,'MRO'):subject.service_specs(self.official,self.profile)

    def test_subclass_rejected(self):
        class Foreign(self.profiled):pass
        with self.assertRaisesRegex(ValueError,'MRO'):subject.service_specs(Foreign,self.profile)

    def test_source_byte_change_rejected(self):
        path=Path(self.modules[1].__file__);path.write_text(path.read_text()+'# change\n')
        with self.assertRaisesRegex(ValueError,'source pin'):subject.service_specs(self.profiled,self.profile)

    def test_module_origin_replaced_rejected(self):
        self.modules[0].__file__=str(self.root/'other.py')
        with self.assertRaisesRegex(ValueError,'origin'):subject.service_specs(self.profiled,self.profile)

    def test_module_class_replaced_rejected(self):
        self.modules[2].ProfiledMatrixService=type('Foreign',(),{})
        with self.assertRaisesRegex(ValueError,'class identity'):subject.service_specs(self.profiled,self.profile)

    def test_class_override_rejected(self):
        self.profiled.acquire=lambda *a:True
        with self.assertRaisesRegex(ValueError,'override'):subject.service_specs(self.profiled,self.profile)

    def test_instance_override_rejected(self):
        self.service.acquire=types.MethodType(self.base.acquire,self.service)
        with self.assertRaisesRegex(ValueError,'substitution'):subject.make_trace(self.runtime,self.service,self.profile,self.bind)

    def test_other_lifecycle_override_rejected(self):
        self.official.abort=lambda *a:None
        with self.assertRaisesRegex(ValueError,'override'):subject.service_specs(self.profiled,self.profile)

    def test_duplicate_code_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            subject.make_trace(self.runtime,self.service,self.profile,lambda *a:self.base.acquire.__code__)

    def test_binding_failure_not_swallowed(self):
        def reject(*args):raise ValueError('strict binder rejected')
        with self.assertRaisesRegex(ValueError,'strict binder rejected'):
            subject.make_trace(self.runtime,self.service,self.profile,reject)

    def test_trace_contract_change_rejected(self):
        self.runtime.ServiceTrace.METHODS=()
        with self.assertRaisesRegex(ValueError,'contract'):subject.make_trace(self.runtime,self.service,self.profile,self.bind)


class OriginalSourceAstEvidence(unittest.TestCase):
    def test_original_acquire_override_has_only_dense_guard_and_super_return(self):
        # Read-only original source evidence, not executing this AST as a DUT.
        pins=__import__('json').loads((HERE/'SOURCE_PINS.json').read_text())
        source_root=SOURCE_ROOT
        relative='candidates/qwen2_resident_matrix/official_bf16/dense_silu.py'
        path=source_root/relative
        self.assertTrue(path.is_file(), 'explicit readonly source root required')
        node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='OfficialMatrixService')
        method=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=='acquire')
        self.assertEqual([a.arg for a in method.args.args],['self','owner','mode','tag'])
        self.assertEqual(len(method.body),2)
        self.assertIsInstance(method.body[0],ast.If)
        self.assertEqual(ast.unparse(method.body[0].test),"mode == 'dense'")
        self.assertIsInstance(method.body[1],ast.Return)
        self.assertEqual(ast.unparse(method.body[1].value),'super().acquire(owner, mode, tag)')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         pins['source_files'][relative]['sha256'])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    args, remaining=parser.parse_known_args()
    SOURCE_ROOT=args.source_root.resolve(strict=True)
    unittest.main(argv=[sys.argv[0]]+remaining)
