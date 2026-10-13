"""Bounded AST/contract/C-selftests; no Torch, weight download or full matmul."""
import ast
import copy
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
spec = importlib.util.spec_from_file_location('o_reference_candidate', HERE / 'o_reference.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class OriginalAstTests(unittest.TestCase):
    def test_original_constructor_flatten_and_single_full_n_call(self):
        nodes, identity = r.operators()
        self.assertEqual(identity['operator_lines'], [[495, 495], [615, 615], [617, 617]])
        self.assertEqual(identity['ast_sha256'], '043c1882dba0c176d946d6dabb556f23ffecde763bae4355062cf3d9c786e4cf')
        self.assertEqual((identity['k'], identity['n'], identity['heads'], identity['head_dim']),
                         (4096, 2048, 32, 128))
        self.assertEqual(len([n for n in ast.walk(nodes[-1]) if isinstance(n, ast.Call)]), 1)
        self.assertFalse(identity['original_bias'])

    def test_symbolic_execution_preserves_original_shapes_and_count(self):
        nodes, _ = r.operators()
        for m in (16, 128):
            calls = []

            class Tensor:
                def __init__(self, shape):
                    self.shape = shape

                def reshape(self, batch, sequence, inferred):
                    if self.shape != (m * 32, 128) or (batch, sequence, inferred) != (1, m, -1):
                        raise ValueError('unexpected original flatten')
                    calls.append(('flatten', self.shape, batch, sequence, inferred))
                    return Tensor((1, m, 4096))

            class Linear:
                def __init__(self, in_features, out_features, *, bias):
                    calls.append(('construct', in_features, out_features, bias))

                def __call__(self, core):
                    calls.append(('linear', core.shape))
                    return Tensor((1, m, 2048))

            obj = SimpleNamespace(value_dim=4096, hidden_size=2048)
            scope = dict(self=obj, nn=SimpleNamespace(Linear=Linear),
                         core_attn_out=Tensor((m * 32, 128)), batch_size=1, seq_len=m)
            for node in nodes:
                exec(r.compile_node(node), scope)
            self.assertEqual(calls, [('construct', 4096, 2048, False),
                                     ('flatten', (m * 32, 128), 1, m, -1),
                                     ('linear', (1, m, 4096))])
            self.assertEqual(scope['output'].shape, (1, m, 2048))

    def test_old_projection_shapes_rejected(self):
        for m, n, k in ((16, 8192, 2048), (128, 4096, 2048), (16, 32, 2048),
                        (16, 2048, 2048), (1, 2048, 4096), (True, 2048, 4096)):
            with self.subTest(m=m, n=n, k=k), self.assertRaisesRegex(ValueError, 'N2048, K4096'):
                r.geometry(m, n, k)

    def test_no_assert_guards_or_inherited_thresholds(self):
        source = (HERE / 'o_reference.py').read_text()
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(source))))
        for inherited in ('0.03125', '0.005'):
            self.assertNotIn(inherited, source)
        self.assertEqual([recipe['mode'] for recipe in r.RECIPES], list(range(5)))
        self.assertEqual([recipe['partial_adds_per_output'] for recipe in r.RECIPES], [0, 0, 1, 3, 3])


class ProducerContractTests(unittest.TestCase):
    def fixture(self, directory):
        size = 16 * 4096 * 2
        raw = bytes(size)
        ip = directory / 'gated_norm.actual.bf16le'
        ip.write_bytes(raw)
        owner = dict(complete=True, output_published=True, staging_complete=True, status=None,
                     output_sha256=r.sha(raw), counts=dict(write_bytes=size, read_bytes=2 * size + 512),
                     owner=dict(scope='GDN_GATED_NORM_SOFTWARE_OWNER', active_heads=32, row_bytes=8192,
                                production_geometry=True, test_only_zero_filled_heads=0, status=None,
                                accepted=dict(owner_results=1, read_requests=4104, write_requests=2048,
                                              write_acks=2048, memory_responses=6152),
                                acknowledged_write_bytes=size,
                                identity=dict(grouped_source=dict(source_sha256={
                                    r.rms.SOURCE: r.rms.SOURCE_SHA, r.rms.CONFIG: r.rms.CONFIG_SHA}))))
        snapshot = {'example/source.py': '1' * 64}
        summary = dict(tokens=16, gated_norm_requested=True, source_sha256=snapshot,
                       source_sha256_after=copy.deepcopy(snapshot), sources_unchanged=True,
                       gated_norm_diagnostics=dict(actual_sha256=r.sha(raw), expected_sha256='2' * 64,
                                                   passed=None, thresholds=None, bit_mismatches=1),
                       execution=dict(tokens=16, status='PASS_TYPED_GATED_NORM_PREFIX_EXECUTION_ONLY',
                                      terminals=[dict(stage=s, status=None) for s in r.STAGES],
                                      stages=[dict(stage=s, report=owner if s == 'gated_norm' else
                                                   dict(complete=True)) for s in r.STAGES]),
                       observations=[dict(stage='gated_norm', owner=owner,
                                          output=dict(path=str(ip), bytes=size, sha256=r.sha(raw)))])
        sp = directory / 'summary.json'
        sp.write_text(json.dumps(summary))
        return raw, ip, sp, summary

    def verify(self, directory, summary):
        path = directory / 'summary.json'
        path.write_text(json.dumps(summary))
        return r.actual_gated_norm_input(directory, r.sha(path.read_bytes()), 16)

    def test_actual_publication_accepted_without_substituting_reference(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            raw, ip, sp, summary = self.fixture(d)
            got, got_ip, got_sp, evidence = self.verify(d, summary)
            self.assertEqual((got, got_ip, got_sp), (raw, ip, sp))
            self.assertEqual(evidence['producer_terminal_count'], 10)
            self.assertFalse(evidence['reference_input_substitution'])
            self.assertNotEqual(r.sha(got), summary['gated_norm_diagnostics']['expected_sha256'])

    def test_raw_hash_length_and_summary_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            raw, ip, sp, summary = self.fixture(d)
            pin = r.sha(sp.read_bytes())
            for changed in (b'\x01' + raw[1:], raw[:-2]):
                ip.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, 'raw length/SHA'):
                    r.actual_gated_norm_input(d, pin, 16)
            ip.write_bytes(raw)
            sp.write_text(sp.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'summary pin'):
                r.actual_gated_norm_input(d, pin, 16)

    def test_bad_publication_terminal_source_and_acknowledgement_rejected(self):
        mutators = [
            lambda x: x.update(tokens=128),
            lambda x: x.update(gated_norm_requested=False),
            lambda x: x.update(sources_unchanged=False),
            lambda x: x['source_sha256_after'].update({'example/source.py': '3' * 64}),
            lambda x: x['execution']['terminals'].pop(),
            lambda x: x['execution']['terminals'][-1].update(status='failed'),
            lambda x: x['execution']['terminals'][-1].pop('status'),
            lambda x: x['execution']['stages'][0]['report'].update(complete=False),
            lambda x: x['observations'][0]['owner'].update(complete=False),
            lambda x: x['observations'][0]['owner'].update(output_published=False),
            lambda x: x['observations'][0]['owner']['owner']['accepted'].update(owner_results=0),
            lambda x: x['observations'][0]['owner']['owner']['accepted'].update(write_acks=2047),
            lambda x: x['observations'][0]['owner']['owner'].update(test_only_zero_filled_heads=1),
            lambda x: x['observations'][0]['owner']['owner'].update(acknowledged_write_bytes=0),
            lambda x: x['observations'][0]['output'].update(bytes=16 * 2048 * 2),
            lambda x: x['observations'].append(copy.deepcopy(x['observations'][0])),
        ]
        for i, mutate in enumerate(mutators):
            with self.subTest(case=i), tempfile.TemporaryDirectory() as td:
                d = Path(td)
                _, _, _, summary = self.fixture(d)
                mutate(summary)
                with self.assertRaises((ValueError, KeyError)):
                    self.verify(d, summary)

    def test_reference_named_input_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as other:
            d = Path(td)
            raw, _, _, summary = self.fixture(d)
            for p in (d / 'gated_norm.reference.bf16le', Path(other) / 'gated_norm.actual.bf16le'):
                p.write_bytes(raw)
                summary['observations'][0]['output']['path'] = str(p)
                with self.assertRaisesRegex(ValueError, 'no reference substitute or path escape'):
                    self.verify(d, summary)



class DiagnosticContractTests(unittest.TestCase):
    def test_bitexact_is_never_admission_and_shape_is_complete(self):
        raw = bytes(16 * 2048 * 2)
        exact = r.diagnostics(raw, raw, 16)
        self.assertIsNone(exact['passed'])
        self.assertIsNone(exact['thresholds'])
        self.assertFalse(exact['native_acceptance'])
        self.assertFalse(exact['recipe_admitted'])
        self.assertTrue(exact['bitexact_observed'])
        changed = bytearray(raw)
        changed[2 * 2048:2 * 2048 + 2] = b'\x80\x3f'
        diag = r.diagnostics(bytes(changed), raw, 16)
        self.assertEqual(diag['first_coordinate'], dict(row=1, column=0))
        self.assertEqual(diag['max_abs'], 1.0)
        self.assertIsNone(diag['passed'])
        with self.assertRaisesRegex(ValueError, 'complete MxN2048'):
            r.diagnostics(raw[:-2], raw[:-2], 16)


class StrictCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.native, cls.evidence = r.build_reference(Path(cls.directory.name))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_exact_abi_and_k8_selftests(self):
        self.assertEqual((self.native.o_reference_n(), self.native.o_reference_k(),
                          self.native.o_reference_modes()), (2048, 4096, 5))
        self.assertEqual(self.native.o_reference_self_test(), 0)
        self.assertEqual(self.native.o_reference_environment(), 0)
        self.assertTrue(self.evidence['selftest_passed'])

    def test_bad_shapes_modes_and_missing_buffers_rejected_before_dereference(self):
        invalid = [C.c_void_p(1)] * 5
        for m, mode in ((0, 0), (1, 0), (17, 0), (129, 0), (16, 5), (128, 0xffffffff)):
            self.assertEqual(self.native.o_reference_run(m, mode, *invalid), -1)
        for index in range(5):
            pointers = invalid.copy()
            pointers[index] = None
            self.assertEqual(self.native.o_reference_run(16, 0, *pointers), -1)

    def test_compiler_libm_source_disassembly_hash_evidence(self):
        for name in ('compiler', 'reference_source', 'reference_library', 'libm', 'disassembly',
                     'dynamic_symbols', 'ldd', 'compiler_version'):
            rec = self.evidence[name]
            self.assertEqual(r.sha(Path(rec['path']).read_bytes()), rec['sha256'])
        self.assertIn('-ffp-contract=off', self.evidence['compile_argv'])
        self.assertIn('-frounding-math', self.evidence['compile_argv'])
        self.assertIn('-fno-builtin-fmaf', self.evidence['compile_argv'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
