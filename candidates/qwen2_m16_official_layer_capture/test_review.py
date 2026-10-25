"""Independent stdlib-only static/mock tests; no official execution."""
import ast
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest

class DenyNumerical(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'numpy', 'transformers'}:
            raise AssertionError('Numerical import forbidden in independent review: ' + fullname)
sys.meta_path.insert(0, DenyNumerical())
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reviewee_capture_tests', HERE / 'test_capture.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
c = t.c

class IndependentReviewTests(unittest.TestCase):
    def setUp(self):
        self.pins = c.load_pins()

    def complete_observer(self):
        o = c.Observer(self.pins['fields'])
        storage = b'base_v_payload'
        for name in c.FIELD_ORDER:
            f = self.pins['fields'][name]
            obj = o.objects['k'] if name == 'cache_k' else t.FakeTensor(f['shape'], f['dtype'], storage if name in ('v','cache_v') else name.encode())
            o.record(name, obj)
        o.attention_calls = o.softmax_calls = 1
        o.line_visits = {line: 1 for line in c.LINE_FIELDS}
        return o

    def test_pin_metadata_matches_prior_audit_all13(self):
        audit = json.loads((HERE/'INPUT_METADATA_PROJECTION.json').read_text())
        self.assertEqual(len(audit['raw13']), len(self.pins['raw13']))
        for old,new in zip(audit['raw13'],self.pins['raw13']):
            self.assertEqual({k:old[k] for k in new}, new)

    def test_geometry_and_original_gates_unchanged(self):
        old = json.loads((HERE/'GEOMETRY_PROJECTION.json').read_text())
        self.assertEqual(set(old['geometry']),set(self.pins['fields']))
        for name, f in old['geometry'].items():
            self.assertEqual(self.pins['fields'][name]['shape'], f['shape'])
            self.assertEqual(self.pins['fields'][name]['dtype'], f['native_dtype'])
            self.assertEqual(self.pins['fields'][name]['export_f32_bytes'],f['export_bytes'])
        self.assertEqual(self.pins['comparison_gates'], {'block_y':{'combine':'AND','max_abs_lte':0.05,'mean_abs_lte':0.01},'nonfinite_allowed':False,'operator_bf16':{'combine':'AND','max_abs_lte':0.03125,'mean_abs_lte':0.005},'rowsum_abs_error_lte':2e-5,'softmax_fp32':'DIAGNOSTIC_NO_APPROVED_COMPARISON_TOLERANCE'})

    def test_valid_aliases_then_v_storage_change_rejected(self):
        o=self.complete_observer()
        self.assertTrue(o.validate())
        o.metadata['cache_v']['original_storage_data_ptr'] += 1
        self.assertFalse(o.validate())
        self.assertTrue(any('cache_v' in e['error'] for e in o.errors))

    def test_missing_and_duplicate_line_events_rejected(self):
        o=self.complete_observer(); del o.line_visits[283]
        self.assertFalse(o.validate())
        o=self.complete_observer(); o.line_visits[283] = 2
        self.assertFalse(o.validate())

    def test_wrong_shape_and_device_rejected(self):
        for key,bad in [('shape',[1]),('device','cuda:0')]:
            o=self.complete_observer(); o.metadata['x'][key] = bad
            self.assertFalse(o.validate())

    def test_all_fp32_nonfinite_classes_detected(self):
        words = [0,0x80000000,0x7F7FFFFF,0xFF7FFFFF,0x7F800000,0xFF800000,0x7FC00001,0x7F800001]
        self.assertEqual(c.fp32_nonfinite_count(b''.join(struct.pack('<I',w) for w in words)),4)

    def test_nonfinite_export_adds_terminal_validation_error(self):
        o=c.Observer({'x':{'shape':[1],'dtype':'bfloat16'}})
        o.record('x',t.FakeTensor([1],payload=b'\x80\x7f'))
        with tempfile.TemporaryDirectory() as tmp:
            exports=c.export_snapshots(types.SimpleNamespace(uint8=object()),o,Path(tmp),{'fields':{'x':{'export_f32_bytes':4}}})
            self.assertEqual(exports['x']['nonfinite_count'],1)
            self.assertTrue(o.errors)

    def test_export_never_overwrites_existing_data(self):
        o=c.Observer({'x':{'shape':[1],'dtype':'bfloat16'}})
        o.record('x',t.FakeTensor([1],payload=b'\x80\x3f'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x.native.bin'; path.write_bytes(b'preserve')
            exports=c.export_snapshots(types.SimpleNamespace(uint8=object()),o,Path(tmp),{'fields':{'x':{'export_f32_bytes':4}}})
            self.assertEqual(path.read_bytes(),b'preserve')
            self.assertEqual(exports,{})
            self.assertTrue(o.errors)

    def test_softmax_wrong_original_input_does_not_replace_flow(self):
        o=c.Observer(self.pins['fields']); o.softmax_code=object(); o.float32=object()
        p=types.SimpleNamespace(f_lineno=300,f_locals={'attn_weights':object()}); o.attention_frame=p
        f=types.SimpleNamespace(f_code=o.softmax_code,f_back=p,f_locals={'input':object(),'dim':-1,'dtype':o.float32})
        self.assertIsNotNone(o.trace(f,'call',None))
        self.assertTrue(o.errors)
        self.assertEqual(o.values,{})

    def test_public_entry_is_literal_unconditional_disabled(self):
        tree=ast.parse((HERE/'capture.py').read_text())
        func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_capture')
        body=func.body[1:] if isinstance(func.body[0],ast.Expr) else func.body
        self.assertEqual(len(body),1); self.assertIsInstance(body[0],ast.Raise)
        self.assertEqual(body[0].exc.func.id,'ExecutionDisabled')
        self.assertFalse(set(sys.modules)&{'torch','numpy','transformers'})

    def test_trace_never_assigns_frame_state(self):
        tree=ast.parse((HERE/'capture.py').read_text())
        observer=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Observer')
        trace=next(n for n in observer.body if isinstance(n,ast.FunctionDef) and n.name=='trace')
        for n in ast.walk(trace):
            if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store):
                self.assertNotIn(n.attr,{'f_lineno','f_locals','f_code','f_trace'})

suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(t.CaptureTests),unittest.defaultTestLoader.loadTestsFromTestCase(IndependentReviewTests)])
result=unittest.TextTestRunner(verbosity=2).run(suite)
if set(sys.modules)&{'torch','numpy','transformers'}:
    raise AssertionError('Numerical module imported')
raise SystemExit(not result.wasSuccessful())
