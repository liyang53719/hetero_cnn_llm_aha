"""Small independent numerical/source/gate checks; NumPy only, no Torch/RTL.

The pinned native Torch runner is intentionally a separate local validation:
discovering this suite in the lightweight CI must not import or skip Torch.
"""
import ast
import json
from pathlib import Path
import random
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from . import reference as r
from .test_model import bf, oracle, reference_exp
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import ref_add, ref_mul, ref_bf


def rational_conv(raw, weights, history, rows, channels=32):
    x = np.frombuffer(raw, '<u2').reshape(rows, channels)
    w = np.frombuffer(weights, '<u2').reshape(channels, 4)
    h = np.frombuffer(history, '<u2').reshape(channels, 4).copy()
    result = []
    for row in x:
        for channel in range(channels):
            total = 0
            for sample, weight in zip(list(h[channel, 1:]) + [row[channel]], w[channel]):
                total = ref_add(total, ref_mul(int(sample) << 16, int(weight) << 16))
            result.append(ref_bf(total) >> 16)
        h = np.concatenate((h[:, 1:], row[:, None]), axis=1)
    return np.array(result, dtype='<u2').tobytes()


class FixedReferenceTests(unittest.TestCase):
    def test_array_recipe_matches_rational_cold_warm_and_both_boundaries(self):
        rng = random.Random(302)
        for rows in (1, 3, 4, 16):
            for cold in (True, False):
                with self.subTest(rows=rows, cold=cold):
                    raw = bf([rng.uniform(-3, 3) for _ in range(rows * 32)])
                    weights = bf([rng.uniform(-.5, .5) for _ in range(128)])
                    history = bytes(256) if cold else bf([rng.uniform(-2, 2) for _ in range(128)])
                    actual, identity = r.fixed_conv(raw, weights, rows, 32, None if cold else history)
                    silu, state = oracle(raw, weights, history, rows)
                    self.assertEqual(actual['conv'], rational_conv(raw, weights, history, rows))
                    self.assertEqual(actual['silu'], silu)
                    self.assertEqual(actual['history'], state)
                    self.assertFalse(identity['scalar_or_owner_called'])
                    self.assertFalse(identity['history_committed'])

    def test_no_owner_or_scalar_dependency_and_separate_add_order(self):
        source = ast.parse(Path(r.__file__).read_bytes())
        imports = [ast.unparse(node) for node in ast.walk(source)
                   if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any('model' in item or 'scalar' in item for item in imports))
        raw, weights = bf([1] * 32), bf([1] * 128)
        history = bf([0, 2**24, 1, -(2**24)] * 32)
        actual, _ = r.fixed_conv(raw, weights, 1, 32, history)
        self.assertEqual(actual['conv'], bf([1] * 32))

    def test_exp_independent_constants_nodes_saturation_and_gradual_underflow(self):
        rng = random.Random(301)
        words = [0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x800000,
                 0x429f0000, 0x42a00000, 0x7f7fffff]
        words.extend(struct.unpack('<I', struct.pack('<f', rng.uniform(-79, 79)))[0]
                     for _ in range(60))
        values = np.array(words, dtype='<u4').view('<f4')
        expected = np.array([reference_exp(word) for word in words], dtype='<u4')
        np.testing.assert_array_equal(r._exp_negative(values).view('<u4'), expected)
        tiny = np.array([1], dtype='<u4').view('<f4')
        self.assertEqual(int(r._node('mul', tiny, np.float32(1.44)).view('<u4')[0]), 1)
        with self.assertRaisesRegex(ValueError, 'inexact underflow'):
            r._node('mul', tiny, np.float32(1.44), legacy=True)

    def test_bf16_rounding_ties_and_signed_zero(self):
        words = np.array([0x3f808000, 0x3f818000, 0xbf808000, 0xbf818000,
                          0x80000000, 0], dtype='<u4')
        np.testing.assert_array_equal(r._bf16(words.view('<f4')),
                                      [0x3f80, 0x3f82, 0xbf80, 0xbf82, 0x8000, 0])

    def test_unused_oldest_history_and_raw_history_layout(self):
        history = np.array([[0x7fc0, 0x3f80, 0x4000, 0x4040]] * 32, dtype='<u2').tobytes()
        raw, weights = bf([-2] * 32), bf([0, 0, 0, 1] * 32)
        actual, _ = r.fixed_conv(raw, weights, 1, 32, history)
        self.assertEqual(actual['history'], bf([1, 2, 3, -2] * 32))
        self.assertEqual(actual['conv'], raw)
        self.assertNotEqual(actual['history'], np.tile(np.frombuffer(actual['silu'], '<u2')[:, None],
                                                     (1, 4)).tobytes())

    def test_fixed_domain_and_source_drift_rejections(self):
        weights = bf([0, 0, 0, 1] * 32)
        for value in (-80, -81, float('inf'), float('nan')):
            raw = struct.pack('<32H', *([struct.unpack('<I', struct.pack('<f', value))[0] >> 16] * 32))
            with self.subTest(value=value), self.assertRaises(ValueError):
                r.fixed_conv(raw, weights, 1, 32)
        result, _ = r.fixed_conv(bf([80] * 32), weights, 1, 32)
        self.assertEqual(result['silu'], bf([80] * 32))
        with self.assertRaisesRegex(ValueError, 'overflow'):
            r.fixed_conv(struct.pack('<32H', *([0x7f7f] * 32)), bf([0, 0, 0, 2] * 32), 1, 32)
        for rows, channels, raw in ((0, 32, bytes(64)), (129, 32, bytes(64)),
                                    (1, 31, bytes(62)), (True, 32, bytes(64)), (1, 32, bytes(62))):
            with self.assertRaises(ValueError):
                r.fixed_conv(raw, weights, rows, channels)
        with patch.object(r, 'OWNER_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'source drift'):
            r.fixed_conv(bytes(64), weights, 1, 32)


class NativeSourceAndGateTests(unittest.TestCase):
    def test_native_requires_case_sensitive_default_before_import(self):
        with patch.dict('os.environ', {'ATEN_CPU_CAPABILITY': 'DEFAULT'}):
            with self.assertRaisesRegex(ValueError, 'set ATEN_CPU_CAPABILITY=default'):
                r.native_conv(bytes(64), bytes(256), 1, 32)

    def test_extracts_exact_original_functions_without_torch_import(self):
        fake = SimpleNamespace(Tensor=object, nn=SimpleNamespace(Parameter=object,
            functional=SimpleNamespace(silu=object())))
        functions = r.original_conv_functions((r.ROOT / r.SOURCE).read_bytes(), fake)
        self.assertEqual(set(functions), {'causal_conv1d_fn', 'causal_conv1d_update'})
        self.assertEqual(functions['causal_conv1d_fn'].__code__.co_filename, r.SOURCE)
        self.assertEqual(functions['causal_conv1d_fn'].__defaults__, (None, None))
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            r.original_conv_functions((r.ROOT / r.SOURCE).read_bytes() + b'\n', fake)

    def test_diagnostics_preserve_signed_zero_and_reject_nonfinite(self):
        result = r.compare_bf16(bytes.fromhex('0000803f'), bytes.fromhex('0080813f'))
        self.assertEqual(result['bit_mismatches'], 2)
        self.assertEqual(result['signed_zero_only_mismatches'], 1)
        self.assertEqual(result['max_bf16_ulp'], 1)
        for left, right in ((b'', b''), (b'0', b'0'), (b'00', b'0000'),
                            (bytes.fromhex('c07f'), bytes(2))):
            with self.assertRaises(ValueError):
                r.compare_bf16(left, right)

    def test_original_gates_are_separate_and_actual_conv_is_missing(self):
        raw, weights = bf([1] * 32), bf([0, 0, 0, 1] * 32)
        fixed, identity = r.fixed_conv(raw, weights, 1, 32)
        # Mock only the heavyweight native invocation to verify gate wiring.
        # This is not native numerical evidence; fixed numerics are tested above.
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                r, 'native_conv', return_value=(fixed, identity)) as native:
            report = r.verify_outputs(raw, weights, 1, fixed['silu'], fixed['history'],
                official_qkv=raw, output=temporary, phase='cold16', channels=32)
            self.assertTrue(report['passed'])
            self.assertTrue(report['missing_actual_pre_silu'])
            self.assertFalse(report['actual_conv_gate_complete'])
            self.assertIsNone(report['native_sameinput']['conv']['passed'])
            self.assertEqual(native.call_count, 2)
            self.assertEqual(len(report['artifacts']), 11)
            for artifact in report['artifacts'].values():
                self.assertEqual(r.sha(Path(artifact['path']).read_bytes()), artifact['sha256'])
            self.assertEqual(report['endtoend']['thresholds'], dict(max_abs=.03125, mean_abs=.005))
            json.dumps(report)
        altered = dict(fixed, silu=bf([4] * 32))
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                r, 'native_conv', side_effect=[(altered, identity), (fixed, identity)]):
            report = r.verify_outputs(raw, weights, 1, fixed['silu'], fixed['history'],
                official_qkv=raw, output=temporary, phase='same_fail', channels=32)
            self.assertTrue(report['fixed']['passed'])
            self.assertFalse(report['native_sameinput']['passed'])
            self.assertTrue(report['endtoend']['passed'])
            self.assertFalse(report['passed'])
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                r, 'native_conv', side_effect=[(fixed, identity), (altered, identity)]):
            report = r.verify_outputs(raw, weights, 1, fixed['silu'], fixed['history'],
                official_qkv=raw, output=temporary, phase='end_fail', channels=32)
            self.assertTrue(report['fixed']['passed'])
            self.assertTrue(report['native_sameinput']['passed'])
            self.assertFalse(report['endtoend']['passed'])
            self.assertFalse(report['passed'])

    def test_raw_history_bitwise_gate_and_original_threshold_drift(self):
        raw, weights = bytes(64), bf([0, 0, 0, 1] * 32)
        fixed, identity = r.fixed_conv(raw, weights, 1, 32)
        history = bytes.fromhex('0080') + fixed['history'][2:]
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                r, 'native_conv', return_value=(fixed, identity)):
            report = r.verify_outputs(raw, weights, 1, fixed['silu'], history,
                official_qkv=raw, output=temporary, phase='history_fail', channels=32)
            self.assertEqual(report['fixed']['raw_history']['max_bf16_ulp'], 0)
            self.assertEqual(report['fixed']['raw_history']['bit_mismatches'], 1)
            self.assertFalse(report['fixed']['passed'])
            self.assertFalse(report['passed'])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / r.GATE_SOURCE
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'native_thresholds': {}}))
            with self.assertRaisesRegex(ValueError, 'thresholds changed'):
                r.verify_outputs(raw, weights, 1, fixed['silu'], fixed['history'],
                    official_qkv=raw, output=temporary, phase='drift', channels=32, root=temporary)

    def test_observed_actual_conv_participates_in_both_fixed_and_native_gates(self):
        raw, weights = bf([1] * 32), bf([0, 0, 0, 1] * 32)
        fixed, identity = r.fixed_conv(raw, weights, 1, 32)
        for altered_actual, altered_native in ((False, False), (True, False), (False, True)):
            actual = bf([2] * 32) if altered_actual else fixed['conv']
            native_result = dict(fixed, conv=bf([2] * 32)) if altered_native else fixed
            with tempfile.TemporaryDirectory() as temporary, patch.object(
                    r, 'native_conv', return_value=(native_result, identity)):
                report = r.verify_outputs(raw, weights, 1, fixed['silu'], fixed['history'],
                    official_qkv=raw, output=temporary, phase='observed', actual_conv=actual, channels=32)
                self.assertFalse(report['missing_actual_pre_silu'])
                self.assertTrue(report['actual_conv_gate_complete'])
                self.assertTrue(report['conv_gate_complete'])
                self.assertEqual(len(report['artifacts']), 12)
                self.assertEqual(report['fixed']['passed'], not altered_actual)
                self.assertEqual(report['native_sameinput']['conv']['passed'],
                                 not (altered_actual or altered_native))
                self.assertEqual(report['passed'], not (altered_actual or altered_native))


if __name__ == '__main__':
    unittest.main()
