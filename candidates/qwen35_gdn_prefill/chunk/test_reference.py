"""Bounded NumPy-only tests; no Torch, owner, Vector, scalar service or RTL.

The exp oracle rounds exact rational arithmetic with integer ties-to-even.
Recurrence is used only as an independent mathematical test oracle for small
synthetic inputs; fixed_chunk itself always performs true chunk64 solves.
"""
import ast
from fractions import Fraction
import json
import math
from pathlib import Path
import struct
import unittest
from unittest import mock

import numpy as np

from . import reference as r


def word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def rational(bits):
    sign = -1 if bits >> 31 else 1
    exponent, fraction = (bits >> 23) & 255, bits & 0x7fffff
    mantissa = fraction if exponent == 0 else 0x800000 + fraction
    power = -149 if exponent == 0 else exponent - 150
    return sign * Fraction(mantissa) * Fraction(2) ** power


def round_word(value):
    """Independent finite FP32 RNE with exact rational integer rounding."""
    sign = 0x80000000 if value < 0 else 0
    value = abs(value)
    if not value:
        return sign
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    if value < Fraction(2) ** exponent:
        exponent -= 1
    quantum = max(exponent - 23, -149)
    scaled = value / Fraction(2) ** quantum
    integer, remainder = divmod(scaled.numerator, scaled.denominator)
    integer += (2 * remainder > scaled.denominator or
                (2 * remainder == scaled.denominator and integer & 1))
    if integer == 0:
        return sign
    if quantum == -149 and integer < 0x800000:
        return sign | integer
    if integer >= 0x1000000:
        integer >>= 1
        quantum += 1
    return sign | ((quantum + 150) << 23) | (integer & 0x7fffff)


def exact_op(operation, a, b):
    av, bv = rational(a), rational(b)
    return round_word(av + bv if operation == 'add' else av * bv)


def integer_exp(bits):
    magnitude = bits & 0x7fffffff
    if magnitude >= word(80):
        return 0
    scaled = exact_op('mul', magnitude, word(1 / math.log(2)))
    exponent = int(rational(scaled))
    fraction = exact_op('add', scaled, word(-exponent))
    coefficients = [word((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    total = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        total = exact_op('add', exact_op('mul', total, fraction), coefficient)
    return exact_op('mul', total, word(2. ** -exponent))


def fixture(rows, *, heads=1, key_dim=2, value_dim=3, seed=73, decay=True):
    rng = np.random.default_rng(seed)
    data = np.zeros((rows, 6400), dtype='<f4')
    for head in range(heads):
        data[:, head * 128:head * 128 + key_dim] = rng.integers(-4, 5, (rows, key_dim)) / 64
        data[:, 2048 + head * 128:2048 + head * 128 + key_dim] = rng.integers(-4, 5, (rows, key_dim)) / 32
        data[:, 4096 + head * 128:4096 + head * 128 + value_dim] = rng.integers(-8, 9, (rows, value_dim)) / 8
        data[:, 6144 + head * 16] = -rng.integers(1, 5, rows) / 64 if decay else 0
        data[:, 6145 + head * 16] = .5
    return data.tobytes()


def mathematical_recurrence(raw, rows, heads, key_dim, value_dim, initial_state=None):
    data = np.frombuffer(raw, '<f4').reshape(rows, 6400).astype(np.float64)
    state = np.zeros((heads, key_dim, value_dim), dtype=np.float64) if initial_state is None else np.frombuffer(initial_state, '<f4').reshape(heads, key_dim, value_dim).astype(np.float64)
    output = np.empty((rows, heads, value_dim), dtype=np.float64)
    for token in range(rows):
        for head in range(heads):
            q = data[token, head * 128:head * 128 + key_dim]
            k = data[token, 2048 + head * 128:2048 + head * 128 + key_dim]
            v = data[token, 4096 + head * 128:4096 + head * 128 + value_dim]
            g, beta = data[token, 6144 + head * 16:6146 + head * 16]
            state[head] *= math.exp(g)
            correction = beta * (v - k @ state[head])
            state[head] += k[:, None] * correction[None, :]
            output[token, head] = q @ state[head]
    return output, state


class FixedChunkReferenceTests(unittest.TestCase):
    def test_original_exp_matches_integer_rne_including_saturation(self):
        words = [0, 0x80000000, 0x80000001, word(-.5), word(-1), word(-79.999),
                 word(-80), word(-100), 0xff7fffff]
        words += [word(-i / 17) for i in range(0, 1200, 31)]
        values = np.array(words, dtype='<u4').view('<f4')
        self.assertEqual(r._exp_negative(values).view('<u4').tolist(), [integer_exp(x) for x in words])
        for value in (1., float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                r._exp_negative(np.float32(value))

    def test_separate_rounding_and_ascending_k(self):
        a = np.array([[2. ** 24, 1, -2. ** 24]], dtype=np.float32)
        self.assertEqual(float(r._matmul(a, np.ones((3, 1), dtype=np.float32))[0, 0]), 0.)
        a = np.array([[1 + 2. ** -23, -1]], dtype=np.float32)
        b = np.array([[1 - 2. ** -23], [1]], dtype=np.float32)
        self.assertEqual(float(r._matmul(a, b)[0, 0]), 0.)
        self.assertNotEqual(float(np.multiply(a[0, 0].astype(np.float64), b[0, 0]) - 1), 0.)

    def test_underflow_faults_exact_subnormals_and_signed_zero(self):
        tiny = np.array([1, 0x00800000, 0x80000000], dtype='<u4').view('<f4')
        with self.assertRaisesRegex(ValueError, 'inexact underflow'):
            r._node('mul', tiny[0], np.float32(.5))
        self.assertEqual(int(r._node('mul', tiny[1], np.float32(.5)).view('<u4')), 0x00400000)
        self.assertEqual(int(r._node('add', tiny[2], tiny[2]).view('<u4')), 0x80000000)
        with self.assertRaisesRegex(ValueError, 'overflow'):
            r._node('mul', np.float32(np.finfo(np.float32).max), np.float32(2))

    def test_bf16_terminal_ties_even_and_overflow(self):
        values = np.array([0x3f808000, 0x3f818000, 0xbf808000, 0xbf818000,
                           0, 0x80000000, 0x3f808001], dtype='<u4').view('<f4')
        expected = [0x3f80, 0x3f82, 0xbf80, 0xbf82, 0, 0x8000, 0x3f81]
        self.assertEqual(np.frombuffer(r._bf16(values), '<u2').tolist(), expected)
        with self.assertRaisesRegex(ValueError, 'BF16 terminal overflow'):
            r._bf16(np.array([0x7f7fffff], dtype='<u4').view('<f4'))

    def test_unit_diagonal_and_strict_lower_forward_solve(self):
        lower = np.full((64, 64), np.float32(99))
        lower[np.tril_indices(64, -1)] = 0
        lower[1, 0], lower[2, 0], lower[2, 1] = .5, -.25, .125
        rhs = np.zeros((64, 2), dtype=np.float32)
        rhs[:3] = [[2, 4], [5, 7], [1, 2]]
        solved = r._solve(lower, rhs)
        np.testing.assert_array_equal(solved[:3], [[2, 4], [4, 5], [1, 2.375]])
        np.testing.assert_array_equal(solved[3:], np.zeros((61, 2)))

    def test_two_complete_chunks_match_independent_recurrence(self):
        # These small synthetic bounds test the formula; they are not native
        # production acceptance thresholds. Output additionally rounds to BF16.
        raw = fixture(128, heads=2)
        out, state, identity = r.fixed_chunk(raw, 128, heads=2, key_dim=2, value_dim=3)
        mathematical_out, mathematical_state = mathematical_recurrence(raw, 128, 2, 2, 3)
        expected_bf = np.frombuffer(r._bf16(mathematical_out.astype(np.float32)), '<u2').astype('<u4') << 16
        observed = (np.frombuffer(out, '<u2').astype('<u4') << 16).view('<f4')
        np.testing.assert_allclose(observed, expected_bf.view('<f4'), atol=2e-6, rtol=.008)
        np.testing.assert_allclose(np.frombuffer(state, '<f4').reshape(2, 2, 3), mathematical_state,
                                   atol=3e-6, rtol=5e-5)
        self.assertEqual(identity['chunks'], 2)
        self.assertEqual(identity['pad_size'], 0)
        self.assertEqual(identity['exp_stats']['calls'], 2 * 2 * (1 + 64 + 64 + 2080))
        self.assertFalse(identity['scalar_or_owner_called'] or identity['vector_called'])
        self.assertFalse(identity['rtl_executed'] or identity['native_acceptance'])
        json.dumps(identity, allow_nan=False)

    def test_m65_padding_and_m128_split64_carry_are_byte_exact(self):
        raw = fixture(128)
        all_out, all_state, _ = r.fixed_chunk(raw, 128, heads=1, key_dim=2, value_dim=3)
        first, carried, _ = r.fixed_chunk(raw[:64 * 25600], 64, heads=1, key_dim=2, value_dim=3)
        second, final, _ = r.fixed_chunk(raw[64 * 25600:], 64, carried, heads=1, key_dim=2, value_dim=3)
        self.assertEqual(all_out, first + second)
        self.assertEqual(all_state, final)
        out65, state65, identity = r.fixed_chunk(raw[:65 * 25600], 65, heads=1, key_dim=2, value_dim=3)
        one, state1, _ = r.fixed_chunk(raw[64 * 25600:65 * 25600], 1, carried,
                                      heads=1, key_dim=2, value_dim=3)
        self.assertEqual(out65, first + one)
        self.assertEqual(state65, state1)
        self.assertEqual((identity['chunks'], identity['pad_size']), (2, 63))

    def test_full_width_state_preserves_fp32_low_bits_and_output_is_bf16(self):
        data = np.zeros((1, 6400), dtype='<f4')
        state = np.full((1, 128, 128), np.uint32(word(.2) + 1), dtype='<u4').tobytes()
        out, final, identity = r.fixed_chunk(data.tobytes(), 1, state, heads=1)
        self.assertEqual(final, state)
        self.assertEqual(out, bytes(256))
        self.assertEqual(identity['state_shape'], [1, 128, 128])
        self.assertEqual(identity['output_shape'], [1, 1, 128])
        self.assertTrue(np.any(np.frombuffer(final, '<u4') & 0xffff))

    def test_all_sixteen_heads_are_selected_and_packed_in_token_order(self):
        data = np.zeros((2, 6400), dtype='<f4')
        for head in range(16):
            data[:, head * 128] = .5
            data[:, 2048 + head * 128] = 1
            data[:, 4096 + head * 128] = head + 1
            data[:, 6145 + head * 16] = 1
        out, state, identity = r.fixed_chunk(data.tobytes(), 2, heads=16, key_dim=1, value_dim=1)
        expected = np.tile(np.arange(1, 17, dtype=np.float32) / 2, (2, 1, 1))
        self.assertEqual(out, r._bf16(expected))
        self.assertEqual(state, np.arange(1, 17, dtype='<f4').tobytes())
        self.assertEqual(identity['heads'], 16)

    def test_exp_saturation_is_retained_and_recorded(self):
        data = np.zeros((1, 6400), dtype='<f4')
        data[0, 6144] = -80
        initial = np.ones((1, 1, 1), dtype='<f4').tobytes()
        output, state, identity = r.fixed_chunk(data.tobytes(), 1, initial,
                                               heads=1, key_dim=1, value_dim=1)
        self.assertEqual(output, bytes(2))
        self.assertEqual(state, bytes(4))
        self.assertEqual(identity['exp_stats']['saturated_abs_ge_80'], 65)

    def test_prepared_input_and_source_fail_closed(self):
        raw = fixture(1)
        for rows in (0, 129, True):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                r.fixed_chunk(raw, rows, heads=1)
        for kwargs in ({'heads': 0}, {'heads': 17}, {'key_dim': 129}, {'value_dim': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                r.fixed_chunk(raw, 1, **kwargs)
        with self.assertRaisesRegex(ValueError, 'complete FP32'):
            r.fixed_chunk(raw[:-4], 1)
        for index, bits, message in ((6146, 0x80000000, 'positive zero'), (6144, word(1), 'gate domain'),
                (6145, word(2), 'gate domain'), (6145, word(.5) + 1, 'BF16-widened'),
                (4096, word(1) + 1, 'BF16-widened'), (0, 0x7fc00000, 'nonfinite')):
            changed = np.frombuffer(raw, '<u4').copy()
            changed[index] = bits
            with self.subTest(index=index, bits=bits), self.assertRaisesRegex(ValueError, message):
                r.fixed_chunk(changed.tobytes(), 1, heads=1, key_dim=2, value_dim=3)
        with self.assertRaisesRegex(ValueError, 'initial state'):
            r.fixed_chunk(raw, 1, b'', heads=1, key_dim=2, value_dim=3)
        with mock.patch.dict(r.SOURCE_HASHES, {r.SOURCE: '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                r.fixed_chunk(raw, 1, heads=1, key_dim=2, value_dim=3)

    def test_no_candidate_or_torch_import_in_fixed_path(self):
        tree = ast.parse(Path(r.__file__).read_text())
        imports = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not any(x in name for x in ('model', 'scalar', 'vector', 'rms_owner'))
                            for name in imports))
        real_import = __import__
        def guarded(name, *args, **kwargs):
            if any(name == x or name.endswith('.' + x) for x in ('torch', 'scalar', 'model', 'vector')):
                raise AssertionError('actual/native implementation import forbidden')
            return real_import(name, *args, **kwargs)
        with mock.patch('builtins.__import__', side_effect=guarded):
            r.fixed_chunk(fixture(1), 1, heads=1, key_dim=2, value_dim=3)


class NativeBindingAndComparisonTests(unittest.TestCase):
    def test_native_ast_retains_complete_suffix_without_rescaling(self):
        source = (r.ROOT / r.SOURCE).read_bytes()
        tree = ast.parse(source)
        original = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and
                        n.name == 'torch_chunk_gated_delta_rule')
        start = next(i for i, n in enumerate(original.body) if isinstance(n, ast.Assign) and
                     ast.unparse(n) == 'query = query * scaling') + 1
        module, identity = r._native_ast(source)
        binding = ast.parse(r.NATIVE_BINDING).body
        transformed = module.body[0]
        self.assertEqual([ast.dump(n) for n in transformed.body[len(binding):]],
                         [ast.dump(n) for n in original.body[start:]])
        self.assertEqual(transformed.decorator_list, [])
        names = {n.id for n in ast.walk(module) if isinstance(n, ast.Name)}
        self.assertNotIn('scaling', names)
        self.assertNotIn('l2norm', names)
        self.assertIn('initial_dtype = torch.bfloat16', ast.unparse(module))
        self.assertIn('torch.linalg.solve_triangular', ast.unparse(module))
        self.assertTrue(identity['suffix_unchanged'])
        with self.assertRaisesRegex(ValueError, 'source hash'):
            r._native_ast(source + b'\n')

    def test_native_requires_frozen_backend_before_torch_import(self):
        with mock.patch.dict('os.environ', {'ATEN_CPU_CAPABILITY': 'DEFAULT'}):
            with self.assertRaisesRegex(ValueError, 'ATEN_CPU_CAPABILITY=default'):
                r.native_prepared_chunk(bytes(25600), 1)
        with self.assertRaisesRegex(ValueError, 'complete 16-head'):
            r.native_prepared_chunk(bytes(25600), 1, heads=1)

    def test_native_comparison_has_no_invented_acceptance_gate(self):
        actual, expected = struct.pack('<2H', 0x3f80, 0x8000), struct.pack('<2H', 0x3f81, 0)
        state = struct.pack('<2I', word(1) + 1, word(-1))
        target = struct.pack('<2I', word(1), word(-1))
        native = r.compare_outputs(actual, state, expected, target, native=True)
        self.assertIsNone(native['passed'])
        self.assertIsNone(native['thresholds'])
        self.assertEqual(native['output']['max_ulp'], 1)
        self.assertEqual(native['output']['signed_zero_only_mismatches'], 1)
        self.assertEqual(native['state']['max_ulp'], 1)
        self.assertFalse(r.compare_outputs(actual, state, expected, target)['passed'])
        self.assertTrue(r.compare_outputs(actual, state, actual, state)['passed'])
        invalid = r.compare_bytes(struct.pack('<2I', 0x7fc00000, 0x7f800000), target, dtype='fp32')
        self.assertTrue(invalid['nonfinite'])
        self.assertIsNone(invalid['max_abs'])
        self.assertIsNone(invalid['max_ulp'])
        nan = struct.pack('<I', 0x7fc00000)
        self.assertFalse(r.compare_outputs(actual, nan, actual, nan)['passed'])
        json.dumps([native, invalid], allow_nan=False)


if __name__ == '__main__':
    unittest.main()
