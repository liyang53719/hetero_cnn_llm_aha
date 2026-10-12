"""NumPy-only independent recipe checks; original Torch runner is not invoked."""
import ast
import json
from pathlib import Path
import random
import struct
import unittest
from unittest.mock import patch

import numpy as np

from . import reference as r
from .test_model import bf, oracle, reference_exp
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import ref_add, ref_mul, ref_div, ref_bf


class IndependentRecipeTests(unittest.TestCase):
    def test_fixed_recipe_matches_integer_oracle_for_distinct_rows_and_both_ops(self):
        rng = random.Random(492)
        for rows, width in ((1, 32), (3, 64), (16, 32)):
            for op in (0, 1):
                with self.subTest(rows=rows, width=width, op=op):
                    a = bf([rng.uniform(-7, 7) for _ in range(rows * width)])
                    b = bf([rng.uniform(-3, 3) for _ in range(rows * width)])
                    actual, identity = r.fixed_elementwise(a, b, rows, op, width, test_geometry=True)
                    self.assertEqual(actual, oracle(a, b, op))
                    self.assertEqual(identity['shape'], [rows, width])
                    self.assertFalse(identity['scalar_or_owner_called'])
                    self.assertFalse(identity['native_acceptance'])
                    self.assertFalse(identity['native_numeric_diagnostics_executed'])
                    json.dumps(identity)

    def test_reference_has_no_owner_or_scalar_dependency_and_preserves_bf16_silu(self):
        source = ast.parse(Path(r.__file__).read_bytes())
        imports = [ast.unparse(node) for node in ast.walk(source)
                   if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any('model' in item or 'scalar' in item for item in imports))
        rng = random.Random(713)
        a = bf([rng.uniform(-4, 4) for _ in range(128)])
        b = bf([rng.uniform(-2, 2) for _ in range(128)])
        actual, _ = r.fixed_elementwise(a, b, 2, 'SiluMul', 64, test_geometry=True)
        self.assertNotEqual(actual, oracle(a, b, 1, round_silu=False))
        self.assertEqual(actual, oracle(a, b, 1))

    def test_exp_nodes_match_independent_integer_rounding_including_saturation(self):
        rng = random.Random(915)
        words = [0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x00800000,
                 0x429f0000, 0x42a00000, 0x7f7fffff]
        words.extend(struct.unpack('<I', struct.pack('<f', rng.uniform(-79, 79)))[0] for _ in range(80))
        actual = r._exp_negative(np.array(words, dtype='<u4').view('<f4')).view('<u4')
        np.testing.assert_array_equal(actual, [reference_exp(v) for v in words])

    def test_nodes_follow_independent_rational_rounding_and_legacy_underflow(self):
        pairs = [(1, 0x3fb851ec), (0x00800000, 0x3f000000), (0x80000000, 0x3f800000),
                 (0x3f800001, 0x3f7fffff), (0x3f808000, 0x3f800001)]
        a = np.array([x for x, _ in pairs], dtype='<u4').view('<f4')
        b = np.array([y for _, y in pairs], dtype='<u4').view('<f4')
        for name, ref in (('add', ref_add), ('mul', ref_mul), ('div', ref_div)):
            np.testing.assert_array_equal(r._node(name, a, b).view('<u4'), [ref(x, y) for x, y in pairs])
        tiny = np.array([0x00800000], dtype='<u4').view('<f4')
        with self.assertRaisesRegex(ValueError, 'inexact underflow'):
            r._node('div', tiny, np.float32(3), legacy=True)
        subnormal = np.array([1], dtype='<u4').view('<f4')
        self.assertEqual(int(r._node('mul', subnormal, np.float32(1.44)).view('<u4')[0]), 1)
        with self.assertRaisesRegex(ValueError, 'inexact underflow'):
            r._node('mul', subnormal, np.float32(1.44), legacy=True)

    def test_bf16_integer_ties_subnormals_and_signed_zero(self):
        words = [0, 0x80000000, 0x00008000, 0x00018000, 0x80008000, 0x80018000,
                 0x3f808000, 0x3f818000, 0xbf808000, 0xbf818000, 0x007f8000]
        np.testing.assert_array_equal(r._bf16(np.array(words, dtype='<u4').view('<f4')),
                                      [ref_bf(w) >> 16 for w in words])
        with self.assertRaisesRegex(ValueError, 'overflow'):
            r._bf16(np.array([0x7f7fffff], dtype='<u4').view('<f4'))

    def test_source_domain_signed_zero_and_positive_saturation(self):
        words = [0x8000, 0, 1, 0x8001, 2, 0x8002, 0xc29f, 0x42a0] * 4
        a, b = struct.pack('<32H', *words), bf([1] * 32)
        actual, _ = r.fixed_elementwise(a, b, 1, 1, 32, test_geometry=True)
        self.assertEqual(actual, oracle(a, b, 1))
        self.assertEqual(struct.unpack('<6H', actual[:12]), (0x8000, 0, 0, 0x8000, 1, 0x8001))
        for word in (0xc2a0, 0xc2a1):
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                r.fixed_elementwise(struct.pack('<32H', *([word] * 32)), b, 1, 1, 32, test_geometry=True)
        # Residual Add has no SiLU-specific negative gate restriction.
        raw = bf([-80] * 32)
        actual, _ = r.fixed_elementwise(raw, b, 1, 0, 32, test_geometry=True)
        self.assertEqual(actual, bf([-79] * 32))

    def test_geometry_nonfinite_and_source_drift_rejections(self):
        raw = bytes(64)
        bad = [dict(rows=0), dict(rows=129), dict(rows=True), dict(row_width=31),
               dict(row_width=64), dict(test_geometry=False), dict(op=2), dict(op=True)]
        for changes in bad:
            kwargs = dict(rows=1, op=0, row_width=32, test_geometry=True)
            kwargs.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                r.fixed_elementwise(raw, raw, **kwargs)
        for op in (0, 1):
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                r.fixed_elementwise(struct.pack('<32H', *([0x7fc0] * 32)), raw,
                                    1, op, 32, test_geometry=True)
        with patch.object(r, 'OWNER_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'source drift'):
            r.fixed_elementwise(raw, raw, 1, 0, 32, test_geometry=True)
        with patch.object(r, 'SOURCE_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'source drift'):
            r.fixed_elementwise(raw, raw, 1, 0, 32, test_geometry=True)


class OriginalSourceDiagnosticTests(unittest.TestCase):
    def test_compile_unchanged_official_expressions_without_torch(self):
        expressions = r._official_expressions((r.ROOT / r.SOURCE).read_bytes())
        self.assertEqual(len(expressions), 2)
        self.assertTrue(all(code.co_filename == r.SOURCE for code in expressions))
        self.assertEqual(eval(expressions[0], {}, dict(residual=3, hidden_states=4)), 7)
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            r._official_expressions((r.ROOT / r.SOURCE).read_bytes() + b'\n')

    def test_native_requires_frozen_backend_before_torch_import(self):
        with patch.dict('os.environ', {'ATEN_CPU_CAPABILITY': 'DEFAULT'}):
            with self.assertRaisesRegex(ValueError, 'set ATEN_CPU_CAPABILITY=default'):
                r.native_elementwise(bytes(2048), bytes(2048), 1, 0)

    def test_diagnostics_keep_signed_zero_and_have_no_native_acceptance_gate(self):
        report = r.compare_bf16(bytes.fromhex('0000803f'), bytes.fromhex('0080813f'))
        self.assertEqual(report['bit_mismatches'], 2)
        self.assertEqual(report['signed_zero_only_mismatches'], 1)
        self.assertEqual(report['max_bf16_ulp'], 1)
        self.assertIsNone(report['acceptance_threshold'])
        self.assertNotIn('passed', report)
        for actual, expected in ((b'', b''), (b'0', b'0'), (b'00', b'0000'),
                                 (bytes.fromhex('c07f'), bytes(2))):
            with self.assertRaises(ValueError):
                r.compare_bf16(actual, expected)


if __name__ == '__main__':
    unittest.main()
