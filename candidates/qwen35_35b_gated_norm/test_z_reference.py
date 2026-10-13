"""Small source/shape/pin tests; no checkpoint, Torch import or full matmul."""
import ast
import ctypes as C
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if __package__:
    from . import z_reference as r
else:
    spec = importlib.util.spec_from_file_location('z_reference_candidate', HERE / 'z_reference.py')
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)


class OriginalAstTests(unittest.TestCase):
    def test_original_source_geometry_ast_and_call_count(self):
        nodes, identity = r.operators()
        self.assertEqual(identity['operator_lines'], [[500, 500], [523, 523], [524, 524]])
        self.assertEqual(identity['ast_sha256'], '261fc395f262ac66382bbc2d03ff78656082eee6d8a7a2f3f4c06ae77d01e0f4')
        self.assertEqual((identity['k'], identity['n'], identity['heads'], identity['head_dim']),
                         (2048, 4096, 32, 128))
        self.assertEqual(len([n for n in ast.walk(nodes[1]) if isinstance(n, ast.Call)]), 1)

    def test_full_n4096_original_call_then_exact_head_reshape_without_torch(self):
        # Execute original AST unchanged with symbolic shape-only stand-ins.
        # This proves only call shape/count, never numerical native equivalence.
        nodes, _ = r.operators()
        for m in (16, 128):
            calls = []

            class Tensor:
                def __init__(self, shape):
                    self.shape = shape

                def reshape(self, batch, sequence, inferred, head_dim):
                    self.assert_shape = (batch, sequence, inferred, head_dim)
                    if self.shape != (1, m, 4096) or (batch, sequence, inferred, head_dim) != (1, m, -1, 128):
                        raise ValueError('unexpected reshape')
                    return Tensor((1, m, 32, 128))

            class Linear:
                def __init__(self, in_features, out_features, *, bias):
                    calls.append(('construct', in_features, out_features, bias))

                def __call__(self, hidden):
                    calls.append(('linear', hidden.shape))
                    return Tensor((1, m, 4096))

            obj = SimpleNamespace(hidden_size=2048, value_dim=4096, head_v_dim=128)
            scope = dict(self=obj, nn=SimpleNamespace(Linear=Linear), hidden_states=Tensor((1, m, 2048)),
                         batch_size=1, seq_len=m)
            for node in nodes:
                exec(r.compile_node(node), scope)
            self.assertEqual(calls, [('construct', 2048, 4096, False), ('linear', (1, m, 2048))])
            self.assertEqual(scope['z'].shape, (1, m, 32, 128))

    def test_wrong_shapes_cannot_inherit_n8192_or_n32_profile(self):
        for m, n, k in ((16, 8192, 2048), (128, 32, 2048), (16, 4096, 1024),
                        (1, 4096, 2048), (True, 4096, 2048)):
            with self.subTest(m=m, n=n, k=k), self.assertRaisesRegex(ValueError, 'N4096'):
                r.geometry(m, n, k)

    def test_source_guard_has_no_asserts_or_old_gates(self):
        source = (HERE / 'z_reference.py').read_text()
        tree = ast.parse(source)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        self.assertNotIn('0.03125', source)
        self.assertNotIn('0.005', source)


class InputAndDiagnosticsTests(unittest.TestCase):
    def fixture(self, directory):
        raw = bytes(16 * 2048 * 2)
        input_path = directory / 'prefix16.actual_output.bin'
        input_path.write_bytes(raw)
        summary = dict(cases=[dict(name='prefix16', official_output=dict(
            bit_mismatches=0, actual_sha256=r.sha(raw), expected_sha256=r.sha(raw)),
            owner=dict(output_published=True, complete=True, output_sha256=r.sha(raw)))])
        summary_path = directory / 'summary.json'
        summary_path.write_text(json.dumps(summary))
        return raw, input_path, summary_path, summary

    def test_pinned_actual_rms_and_explicit_prefix_names(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            directory = Path(td)
            raw, ip, sp, _ = self.fixture(directory)
            result = r.actual_rms_input(directory, r.sha(sp.read_bytes()), 16, case_name='prefix16')
            self.assertEqual(result, (raw, ip, sp, 'prefix16'))

    def test_raw_tampering_summary_tampering_and_incomplete_publication_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            directory = Path(td)
            raw, ip, sp, summary = self.fixture(directory)
            pin = r.sha(sp.read_bytes())
            ip.write_bytes(b'\x01' + raw[1:])
            with self.assertRaisesRegex(ValueError, 'raw length/identity'):
                r.actual_rms_input(directory, pin, 16, case_name='prefix16')
            ip.write_bytes(raw)
            sp.write_text(sp.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'summary pin'):
                r.actual_rms_input(directory, pin, 16, case_name='prefix16')
            summary['cases'][0]['owner']['complete'] = False
            sp.write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, 'complete actual RMS'):
                r.actual_rms_input(directory, r.sha(sp.read_bytes()), 16, case_name='prefix16')

    def test_bitexact_remains_an_observation_without_any_gate(self):
        zeros = bytes(16 * 4096 * 2)
        exact = r.diagnostics(zeros, zeros, 16)
        self.assertIsNone(exact['passed'])
        self.assertIsNone(exact['thresholds'])
        self.assertTrue(exact['bitexact_observed'])
        changed = bytearray(zeros)
        changed[2 * 4096:2 * 4096 + 2] = b'\x80\x3f'
        diagnostic = r.diagnostics(bytes(changed), zeros, 16)
        self.assertIsNone(diagnostic['passed'])
        self.assertIsNone(diagnostic['thresholds'])
        self.assertFalse(diagnostic['bitexact_observed'])
        self.assertEqual(diagnostic['first_coordinate'], dict(row=1, column=0))
        self.assertEqual(diagnostic['max_abs'], 1.0)


class StrictCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(dir=HERE)
        cls.native, cls.evidence = r.build_reference(Path(cls.directory.name))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_fixed_new_n4096_entry_and_selftest(self):
        self.assertEqual((self.native.z_reference_n(), self.native.z_reference_k()), (4096, 2048))
        self.assertEqual(self.native.z_reference_self_test(), 0)
        self.assertEqual(self.native.z_reference_environment(), 0)
        self.assertTrue(self.evidence['selftest_passed'])

    def test_invalid_shapes_modes_and_missing_buffers_before_dereference(self):
        invalid = [C.c_void_p(1)] * 5
        for m, mode in ((0, 0), (1, 0), (17, 0), (129, 0), (16, 2), (128, 0xffffffff)):
            self.assertEqual(self.native.z_reference_run(m, mode, *invalid), -1)
        for index in range(5):
            pointers = invalid.copy()
            pointers[index] = None
            self.assertEqual(self.native.z_reference_run(16, 0, *pointers), -1)

    def test_linked_libm_compiler_disassembly_evidence(self):
        for name in ('compiler', 'reference_library', 'libm', 'disassembly',
                     'dynamic_symbols', 'ldd', 'compiler_version'):
            rec = self.evidence[name]
            self.assertEqual(r.sha(Path(rec['path']).read_bytes()), rec['sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
