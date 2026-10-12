"""Small NumPy-only reference checks; no Torch, actual owner or RTL run.

The reused test_model oracle uses independent integer/rational FP32 operations.
Importing its helpers does not execute a scalar or an owner; explicit guards
below make any accidental dependency fail. Native integration gets a separate
small smoke run with frozen Torch, outside this unconditionally running suite.
"""
import ast
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import numpy as np

from . import reference as r
from .test_model import oracle_row, reference_exp, reference_softplus, ref_bf


def word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def bf(values):
    return struct.pack('<' + 'H' * len(values), *(ref_bf(word(x)) >> 16 for x in values))


def inputs(rows=1):
    conv = b''.join(bf([((i * 17 + token * 13) % 61 - 30) / 16 for i in range(6144)])
                    for token in range(rows))
    ab = b''.join(bf([(i - 8 + token) / 8 for i in range(16)] +
                    [(i - 7 - token) / 4 for i in range(16)]) for token in range(rows))
    alog = struct.pack('<16I', *(word((i - 7) / 19) for i in range(16)))
    bias = bf([(i - 8) / 32 for i in range(16)]) + bytes(32)
    return conv, ab, alog, bias


class FixedPrepReferenceTests(unittest.TestCase):
    def test_complete_m1_m3_match_integer_oracle_without_actual_scalar_or_owner(self):
        for rows in (1, 3):
            with self.subTest(rows=rows):
                conv, ab, alog, bias = inputs(rows)
                expected = b''.join(oracle_row(conv[t * 12288:(t + 1) * 12288],
                    ab[t * 64:(t + 1) * 64], alog, bias, 16) for t in range(rows))
                with mock.patch('candidates.qwen35_gdn_prefill.prep.scalar.PrepScalar',
                                side_effect=AssertionError('actual scalar forbidden')), \
                     mock.patch('candidates.qwen35_gdn_prefill.prep.model.InputPrepOwner',
                                side_effect=AssertionError('actual owner forbidden')):
                    actual, identity = r.fixed_prep(conv, ab, alog, bias, rows)
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), rows * 25600)
                self.assertEqual(identity['output_shape'], [rows, 6400])
                self.assertFalse(identity['scalar_or_owner_called'])
                self.assertTrue(identity['model_not_Chisel_tokens128'])
                self.assertEqual(identity['source_tokens'], 1)
                self.assertFalse(identity['rtl_executed'])
                self.assertFalse(identity['recurrence_implemented'])

    def test_softplus_and_exp_every_node_match_integer_oracle(self):
        words = [0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x800000,
                 word(-79.5), word(-20), word(20), word(20) + 1, 0x7f7fffff]
        words += [word(x / 13) for x in range(-120, 120, 3)]
        values = np.array(words, dtype='<u4').view('<f4')
        self.assertEqual(r._softplus(values).view('<u4').tolist(), [reference_softplus(x) for x in words])
        self.assertEqual(r._exp_negative(values).view('<u4').tolist(), [reference_exp(x) for x in words])
        for value in (-80, -100, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                r._softplus(np.array([value], dtype='<f4'))

    def test_v_raw_widen_beta_bf16_and_strict_positive_zero_padding(self):
        conv, ab, alog, bias = inputs()
        conv = bytearray(conv)
        v = [1, 0x8000, 0x3f81, 0xbf82] * 512
        conv[8192:] = struct.pack('<2048H', *v)
        raw, _ = r.fixed_prep(bytes(conv), ab, alog, bias, 1)
        output = np.frombuffer(raw, '<u4')
        self.assertEqual(output[4096:6144].tolist(), [x << 16 for x in v])
        gates = output[6144:].reshape(16, 16)
        self.assertTrue(np.all((gates[:, 1] & 0xffff) == 0))
        self.assertTrue(np.all(gates[:, 2:] == 0))
        changed_bias = bias[:32] + struct.pack('<16H', *([0x7fc0] * 16))
        self.assertEqual(raw, r.fixed_prep(bytes(conv), ab, alog, changed_bias, 1)[0])

    def test_a_log_original_fp32_low_bits_affect_gate(self):
        conv, ab, _, bias = inputs()
        log = word(-.371234)
        original = struct.pack('<16I', *([log] * 16))
        quantized = struct.pack('<16I', *([ref_bf(log)] * 16))
        self.assertNotEqual(log, ref_bf(log))
        full, _ = r.fixed_prep(conv, ab, original, bias, 1)
        rounded, _ = r.fixed_prep(conv, ab, quantized, bias, 1)
        self.assertNotEqual(r._roles(full, 1)['g'], r._roles(rounded, 1)['g'])

    def test_shape_and_source_domain_fail_closed(self):
        data = inputs()
        for rows in (0, 129, True):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                r.fixed_prep(*data, rows)
        for index in range(4):
            changed = list(data)
            changed[index] = changed[index][:-2]
            with self.subTest(short=index), self.assertRaises(ValueError):
                r.fixed_prep(*changed, 1)
        for role in ('conv', 'a', 'b', 'log', 'bias', 'gate'):
            conv, ab, alog, bias = data
            if role == 'conv':
                conv = struct.pack('<H', 0x7f80) + conv[2:]
            elif role == 'a':
                ab, bias = bf([-80] * 16 + [0] * 16), bytes(64)
            elif role == 'b':
                ab = bf([0] * 16 + [-80] * 16)
            elif role == 'log':
                alog = struct.pack('<16f', *([80] * 16))
            elif role == 'bias':
                bias = struct.pack('<H', 0x7f80) + bias[2:]
            else:
                alog = struct.pack('<16f', *([6] * 16))
            with self.subTest(role=role), self.assertRaises(ValueError):
                r.fixed_prep(conv, ab, alog, bias, 1)

    def test_legacy_div_underflow_and_mul6_finite_underflow_policy(self):
        tiny = np.array([1, 0x800000], dtype='<u4').view('<f4')
        self.assertEqual(int(r._node('mul', tiny[0], np.float32(.5)).view('<u4')), 0)
        with self.assertRaisesRegex(ValueError, 'inexact underflow'):
            r._node('div', tiny[1], np.float32(3), legacy=True)
        self.assertEqual(int(r._node('div', tiny[1], np.float32(2), legacy=True).view('<u4')), 0x400000)

    def test_native_requires_lowercase_default_before_torch_import(self):
        with mock.patch.dict('os.environ', {'ATEN_CPU_CAPABILITY': 'DEFAULT'}):
            with self.assertRaisesRegex(ValueError, 'ATEN_CPU_CAPABILITY=default'):
                r.native_prep(*inputs(), 1)

    def test_reference_has_no_actual_owner_or_scalar_imports(self):
        tree = ast.parse(Path(r.__file__).read_text())
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not name or not any(x in name for x in ('prep.model', 'scalar', 'rms_owner'))
                            for name in imports))


class ComparisonTests(unittest.TestCase):
    def test_ulp_signed_zero_and_nonfinite_are_explicit(self):
        expected = struct.pack('<4I', word(-1), word(1), 0, 0)
        actual = struct.pack('<4I', word(-1) + 1, word(1) + 1, 0x80000000, 0)
        result = r.compare_fp32(actual, expected)
        self.assertEqual(result['max_fp32_ulp'], 1)
        self.assertEqual(result['bit_mismatches'], 3)
        self.assertEqual(result['signed_zero_only_mismatches'], 1)
        self.assertFalse(result['nonfinite'])
        invalid = r.compare_fp32(struct.pack('<4I', 0x7fc00000, 0x7f800000, 0, 0), expected)
        self.assertEqual(invalid['actual_nonfinite'], 2)
        self.assertIsNone(invalid['max_abs'])
        self.assertIsNone(invalid['mean_abs'])
        self.assertIsNone(invalid['max_fp32_ulp'])
        json.dumps(invalid, allow_nan=False)

    def test_verify_fixed_only_gate_and_saved_diagnostic_artifacts(self):
        data = inputs()
        fixed, _ = r.fixed_prep(*data, 1)
        different = np.frombuffer(fixed, '<f4').copy()
        different[0] += np.float32(100)
        native = different.tobytes()
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(r, 'native_prep', return_value=(native, {})) as stub:
            report = r.verify_outputs(*data, 1, fixed, official_conv=data[0], official_ab=data[1],
                                      output=temp, phase='cold')
            self.assertTrue(report['passed'])
            self.assertEqual(report['passed_scope'], 'fixed_arithmetic_bitwise_conformance_only')
            self.assertEqual(stub.call_count, 2)
            self.assertEqual(report['official_stage_acceptance'], 'UNASSIGNED')
            for name in ('native_sameinput', 'native_official_inputs'):
                self.assertIsNone(report[name]['passed'])
                self.assertIsNone(report[name]['thresholds'])
                self.assertGreater(report[name]['roles']['query']['max_abs'], 99)
            self.assertEqual(set(report['fixed']['roles']), {'query', 'key', 'value', 'g', 'beta', 'gate_padding'})
            self.assertEqual(len(report['artifacts']), 4)
            for name, artifact in report['artifacts'].items():
                raw = Path(artifact['path']).read_bytes()
                self.assertEqual(raw, fixed if name in ('fixed', 'actual') else native)
                self.assertEqual(artifact['sha256'], r.sha(raw))
                self.assertEqual(artifact['bytes'], 25600)
            json.dumps(report, allow_nan=False)
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                r.verify_outputs(*data, 1, fixed, output=temp, phase='cold')

    def test_negative_zero_pad_and_nonfinite_actual_cannot_pass_fixed(self):
        data = inputs()
        fixed, _ = r.fixed_prep(*data, 1)
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(r, 'native_prep', return_value=(fixed, {})):
            for phase, index, value in (('pad', 6146, 0x80000000), ('nan', 6144, 0x7fc00000)):
                actual = np.frombuffer(fixed, '<u4').copy()
                actual[index] = value
                report = r.verify_outputs(*data, 1, actual.tobytes(), output=temp, phase=phase)
                self.assertFalse(report['passed'])
                if phase == 'pad':
                    self.assertFalse(report['fixed']['all_gate_padding_positive_zero'])
                    self.assertEqual(report['fixed']['roles']['gate_padding']['max_abs'], 0)
                else:
                    self.assertTrue(report['fixed']['roles']['g']['nonfinite'])
                json.dumps(report, allow_nan=False)

    def test_official_inputs_must_be_paired_and_safe_phase_required(self):
        data = inputs()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'provided together'):
                r.verify_outputs(*data, 1, bytes(25600), official_conv=data[0], output=temp, phase='cold')
            with self.assertRaisesRegex(ValueError, 'phase'):
                r.verify_outputs(*data, 1, bytes(25600), output=temp, phase='../cold')


if __name__ == '__main__':
    unittest.main()
