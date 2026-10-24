"""Static/fake-frame collector tests only: NEVER run an Attention recipe."""
import argparse,os,resource,signal
import ast
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_reference_capture_static', HERE / 'reference_capture.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(20,20));signal.alarm(25)
_parser=argparse.ArgumentParser(add_help=False);_parser.add_argument('--reference-pins',required=True,type=Path)
_args,_rest=_parser.parse_known_args();sys.argv[:]=[sys.argv[0],*_rest]
PINS=json.loads(_args.reference_pins.read_text())


def buffers():
    # Buffer module is stdlib-only allocation/serialization, not DUT arithmetic.
    spec = importlib.util.spec_from_file_location('_reference_test_buffers', PINS['buffer']['path'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PackedFields


def frame(code, line, owner, local, caller=None):
    return types.SimpleNamespace(f_code=code, f_lineno=line,
                                 f_locals=dict(local, self=owner), f_back=caller)


def setup(rows=1):
    source = r._sources(PINS)
    owner = object()
    codes = {'_attention': object(), '_matrix_step': object()}
    capture = r._Collector(owner, rows, buffers(), source, codes)
    return capture


def fake_complete(rows=1):
    c = setup(rows)
    owner = c.owner
    for h in range(12):
        for t in range(rows):
            for k in range(t + 1):
                context = frame(c.codes['_attention'], 0, owner,
                                dict(head=h, token=t, key=k, probability=0x3f800000,
                                     maximum=0x3f800000, total=0x40000000, inverse=0x3f000000, col=0))
                c._line(frame(c.codes['_matrix_step'], c.points['matrix'], owner,
                              dict(opcode=0x23, last=True, lanes=(0x3f800000,) * 16), context))
                c._line(frame(c.codes['_attention'], c.points['score'], owner,
                              dict(head=h, token=t, key=k, total=0x40000000,
                                   dot=0x40000000, score=0x3e350000)))
                c._line(frame(c.codes['_attention'], c.points['exp'], owner,
                              dict(head=h, token=t, probabilities=[None] * k, probability=0x3f800000)))
            for col in range(0, 128, 16):
                for k in range(t + 1):
                    context = frame(c.codes['_attention'], 0, owner,
                                    dict(head=h, token=t, key=k, probability=0x3f800000,
                                         maximum=0x3f800000, total=0x40000000, inverse=0x3f000000, col=col))
                    c._line(frame(c.codes['_matrix_step'], c.points['matrix'], owner,
                                  dict(opcode=0x24, last=k == t, lanes=(0x3f800000,) * 16,
                                       a=(0x3f80,) + (0,) * 15), context))
                c._line(frame(c.codes['_attention'], c.points['store'], owner,
                              dict(head=h, token=t, col=col, output=(0x3f800000,) * 16)))
    return c


class ReferenceStaticTests(unittest.TestCase):
    def test_false_gate_rejected_before_any_source_read(self):
        for gate in (False, None, 1, 'true'):
            with self.subTest(gate=gate), patch.object(r, '_sources', side_effect=AssertionError('source read')):
                with self.assertRaisesRegex(ValueError, 'all DUT clean terminal'):
                    r.capture_reference(None, 1, (), None, {}, terminal_gate=gate)

    def test_gate_is_mandatory(self):
        with self.assertRaises(TypeError):
            r.capture_reference(None, 1, (), None, {})

    def test_source_role_drift(self):
        pins = dict(PINS)
        del pins['observer']
        with self.assertRaisesRegex(ValueError, 'source roles'):
            r._sources(pins)

    def test_source_hash_drift(self):
        pins = dict(PINS, observer=dict(PINS['observer'], sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'source drift'):
            r._sources(pins)

    def test_existing_sources_compile_without_execution(self):
        source = r._sources(PINS)
        for role, cls, name, extracted in (
            ('original_driver', 'OriginalSchedule', 'run', False),
            ('original_driver', 'OriginalSchedule', '_op', False),
            ('original_owner', 'OfficialAttentionOwner', '_attention', True),
            ('original_adapter', 'AttentionOwner', '_matrix_step', True),
            ('prefix_owner', 'PrefixOwner', '_read', True),
            ('arithmetic', None, 'exact', True)):
            code = r._expected(source[role], cls, name, extracted)
            self.assertIsInstance(code, types.CodeType)
            self.assertEqual(code.co_filename, source[role][0].as_posix())

    def test_original_loader_group_code_is_exact_without_execution(self):
        source = r._sources(PINS)
        raw = source['original_driver']
        for names in (('source_definitions',), r.DRIVER_DEFINITIONS):
            # Reproduce the OLD definitions loader literally, without exec.
            nodes = [node for node in ast.parse(raw[1]).body
                     if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
            original = compile(ast.Module(body=nodes, type_ignores=[]), str(raw[0]), 'exec')
            for node in nodes:
                if isinstance(node, ast.ClassDef):
                    cls = r._child(original, node.name)
                    for method in node.body:
                        if isinstance(method, ast.FunctionDef):
                            expected = r._expected(raw, node.name, method.name, False, definition_names=names)
                            self.assertEqual(r._child(cls, method.name), expected)
                else:
                    self.assertEqual(r._child(original, node.name),
                                     r._expected(raw, None, node.name, False, definition_names=names))

    def test_full_module_compile_does_not_alias_original_class_loader(self):
        source = r._sources(PINS)['original_driver']
        whole = r._expected(source, 'OriginalSchedule', '_response', False)
        selected = r._expected(source, 'OriginalSchedule', '_response', False,
                               definition_names=r.DRIVER_DEFINITIONS)
        self.assertNotEqual(whole, selected)

    def test_extracted_function_groups_match_old_loader_without_execution(self):
        sources = r._sources(PINS)
        for role, cls, names, target in (
                ('arithmetic', None, r.ARITHMETIC_DEFINITIONS, 'exact'),
                ('exp_recipe', None, r.EXP_DEFINITIONS, 'exp_negative'),
                ('prefix_owner', 'PrefixOwner', ('_read', '_write'), '_write'),
                ('original_adapter', 'AttentionOwner', ('_matrix_step', '_less'), '_matrix_step'),
                ('original_owner', 'OfficialAttentionOwner', ('_attention',), '_attention')):
            source = sources[role]
            body = ast.parse(source[1]).body
            if cls is not None:
                body = next(node for node in body if isinstance(node, ast.ClassDef) and node.name == cls).body
            nodes = []
            for node in body:
                if isinstance(node, ast.FunctionDef) and node.name in names:
                    node.decorator_list = []
                    nodes.append(node)
                elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
                    nodes.append(node)
            original = compile(ast.Module(body=nodes, type_ignores=[]), str(source[0]), 'exec')
            self.assertEqual(r._child(original, target), r._expected(source, cls, target, True, extracted_names=names))

    def test_loaded_wrong_code_rejected(self):
        source = r._sources(PINS)
        with self.assertRaisesRegex(ValueError, 'loaded reference code differs'):
            r._bind(lambda: None, source['original_driver'], 'OriginalSchedule', 'run')

    def test_changed_defaults_rejected_without_calling_arithmetic(self):
        source = r._sources(PINS)
        function = r._reuse(source['arithmetic'], None, 'ref_add')
        function.__defaults__ = (1,)
        with self.assertRaisesRegex(ValueError, 'defaults changed'):
            r._bind(function, source['arithmetic'], None, 'ref_add', extracted=True)

    def test_fake_m1_m2_copies_all_ten_fields(self):
        for rows in (1, 2):
            c = fake_complete(rows)
            report = c.report()
            self.assertEqual(set(report), set(r.FIELDS))
            self.assertEqual(report['dot_parts']['observed_words'], 16 * 12 * rows * (rows + 1) // 2)
            self.assertEqual(report['pv_raw']['observed_words'], 12 * rows * 128)
            self.assertEqual(report['softmax_fp32']['writes'], 8 * 12 * rows * (rows + 1) // 2)
            self.assertEqual(report['normalizer']['writes'], 24 * 12 * rows * (rows + 1) // 2)

    def test_reference_repeated_normalizer_is_not_dut_single_frequency(self):
        c = fake_complete(2)
        self.assertEqual(c.fields['normalizer']['frequency'][0], 8)
        self.assertEqual(c.fields['normalizer']['frequency'][3], 16)

    def test_future_cells_remain_absent(self):
        c = fake_complete(2)
        f = c.fields['scores_bf16']
        self.assertEqual((f['words'][1], f['observed'][1], f['frequency'][1]), (r.SENTINEL, 0, 0))

    def test_missing_field_rejected(self):
        c = fake_complete()
        del c.fields['dot_parts']
        with self.assertRaisesRegex(ValueError, 'field inventory'):
            c.report()

    def test_missing_presence_rejected(self):
        c = fake_complete()
        c.fields['scores_bf16']['observed'][0] = 0
        with self.assertRaises(ValueError):
            c.report()

    def test_future_write_rejected(self):
        c = fake_complete(2)
        c.fields['scores_bf16']['words'][1] = 0
        with self.assertRaisesRegex(ValueError, 'coverage incomplete'):
            c.report()

    def test_missing_probability_repeat_rejected(self):
        c = fake_complete()
        f = c.fields['softmax_fp32']
        f['frequency'][0] -= 1
        f['writes'] -= 1
        f['repeats'] -= 1
        with self.assertRaisesRegex(ValueError, 'coverage incomplete'):
            c.report()

    def test_inconsistent_repeat_rejected(self):
        c = fake_complete()
        with self.assertRaisesRegex(ValueError, 'inconsistent repeated'):
            c._put('softmax_fp32', (0, 0, 0), (0,))

    def test_matrix_caller_mismatch_rejected(self):
        c = setup()
        f = frame(c.codes['_matrix_step'], c.points['matrix'], c.owner,
                  dict(opcode=0x23, last=True, lanes=(0,) * 16))
        with self.assertRaisesRegex(ValueError, 'caller mismatch'):
            c._line(f)

    def test_trace_error_cannot_seal(self):
        c = fake_complete()
        c.error = 'synthetic missing reference event'
        with self.assertRaisesRegex(ValueError, 'collector failed'):
            c.report()

    def test_no_numeric_imports_or_actual_recipe_execution(self):
        self.assertFalse(any(name.split('.')[0] in ('numpy', 'torch', 'transformers') for name in sys.modules))
        tree = ast.parse(Path(__file__).read_text())
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                             and n.func.attr in ('run', 'ObservedOriginal') for n in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
