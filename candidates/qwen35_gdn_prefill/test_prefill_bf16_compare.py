"""Finite-domain output tests; no checkpoint, Torch, actual execution or RTL."""
import hashlib
import math
import struct
import unittest

import numpy as np

from . import full_compare
from heteronpu.matrix_norm_rope_candidate import compare_native
from .prefill_bf16_compare import DOMAIN, compare_finite_bf16, decode_finite


def raw(words):
    return np.asarray(words, '<u2').tobytes()


class FiniteBf16Test(unittest.TestCase):
    def test_exhaustive_finite_decode_matches_independent_struct_widen(self):
        words = np.arange(65536, dtype='<u2')
        finite = words[(words & 0x7f80) != 0x7f80]
        expected = np.array([struct.unpack('<f', struct.pack('<I', int(w) << 16))[0]
                             for w in finite], dtype=np.float64)
        actual = decode_finite(finite)
        self.assertEqual(finite.size, 65280)
        np.testing.assert_array_equal(actual.view('<u8'), expected.view('<u8'))

    def test_subnormal_extremes_signs_and_normal_boundary(self):
        words = [0x0001, 0x007f, 0x0080, 0x8001, 0x807f, 0x8080, 0, 0x8000]
        decoded = decode_finite(np.array(words, '<u2'))
        self.assertEqual(decoded[0], 2.0 ** -133)
        self.assertEqual(decoded[1], 127 * 2.0 ** -133)
        self.assertEqual(decoded[2], 2.0 ** -126)
        self.assertEqual(decoded[3], -(2.0 ** -133))
        self.assertEqual(math.copysign(1.0, decoded[-1]), -1.0)
        metrics = compare_finite_bf16(raw(words), raw([0] * len(words)))
        self.assertEqual(metrics['actual_subnormal_count'], 4)
        self.assertEqual(metrics['native_subnormal_count'], 0)
        self.assertGreater(metrics['max_abs'], 0)
        self.assertEqual(metrics['signed_zero_only_mismatches'], 1)

    def test_actual_cold128_counterexamples_keep_nonzero_error_and_raw_hash(self):
        actual, native = raw([0x8042, 0x005e]), raw([0x809f, 0x010d])
        metrics = full_compare.bf16_metric(actual, native)
        self.assertTrue(metrics['passed'])
        self.assertEqual(metrics['comparison_domain'], DOMAIN)
        self.assertEqual(metrics['actual_subnormal_count'], 2)
        self.assertEqual(metrics['native_subnormal_count'], 0)
        self.assertEqual(metrics['bit_mismatches'], 2)
        self.assertEqual(metrics['max_abs'], 188 * 2.0 ** -133)
        self.assertEqual(metrics['actual_sha256'], hashlib.sha256(actual).hexdigest())
        with self.assertRaisesRegex(ValueError, 'subnormal BF16'):
            compare_native(np.frombuffer(actual, '<u2'), np.frombuffer(native, '<u2'))

    def test_normal_only_legacy_metrics_remain_exact(self):
        words = np.arange(65536, dtype='<u2')
        normal = words[((words & 0x7f80) != 0) & ((words & 0x7f80) != 0x7f80)]
        expected = normal[::-1].copy()
        old = compare_native(normal, expected)
        new = full_compare.bf16_metric(normal.tobytes(), expected.tobytes())
        for key in ('elements', 'bit_mismatches', 'max_abs', 'mean_abs', 'thresholds'):
            self.assertEqual(new[key], old[key], key)
        self.assertEqual(new['passed'], old['pass'])
        self.assertEqual(new['actual_subnormal_count'], 0)

    def test_ulp_one_and_two_are_retained_across_subnormal_and_zero_boundaries(self):
        for a, b in ((1, 0), (0x8001, 0), (0x0080, 0x007f)):
            metric = full_compare.bf16_metric(raw([a]), raw([b]), gate='ulp')
            self.assertTrue(metric['passed'])
            self.assertEqual(metric['max_bf16_ulp'], 1)
        for a, b in ((2, 0), (0x8001, 1), (0x0080, 0x007e)):
            self.assertFalse(full_compare.bf16_metric(raw([a]), raw([b]), gate='ulp')['passed'])

    def test_subnormal_does_not_exempt_normal_error_from_any_threshold(self):
        for gate, value in (('node', .0315), ('output', .0501)):
            words = np.zeros(100, '<u2')
            words[0] = 1
            words[1] = struct.unpack('<I', struct.pack('<f', value))[0] >> 16
            # Round upward to put the normal error strictly outside max_abs.
            words[1] += 1
            metric = full_compare.bf16_metric(words.tobytes(), bytes(200), gate=gate)
            self.assertFalse(metric['passed'])
        for gate, word in (('node', 0x3c00), ('output', 0x3c80)):
            words = np.full(100, word, '<u2')
            words[0] = 1
            self.assertFalse(full_compare.bf16_metric(words.tobytes(), bytes(200), gate=gate)['passed'])

    def test_all_nonfinite_encodings_rejected_on_either_side(self):
        for word in range(65536):
            if word & 0x7f80 != 0x7f80:
                continue
            for a, b in ((raw([word]), raw([0])), (raw([0]), raw([word]))):
                with self.assertRaisesRegex(ValueError, 'nonfinite'):
                    compare_finite_bf16(a, b)

    def test_invalid_shapes_types_and_decoding_dtypes_rejected(self):
        for a, b in ((b'', b''), (b'\0', b'\0'), (bytes(2), bytes(4)),
                     (bytearray(2), bytes(2)), ([0], [0])):
            with self.assertRaises(ValueError):
                compare_finite_bf16(a, b)
        for words in ([], np.array([], '<u2'), np.array([1], '<f4'), np.array([1], '>u2')):
            with self.assertRaises(ValueError):
                decode_finite(words)


if __name__ == '__main__':
    unittest.main()
