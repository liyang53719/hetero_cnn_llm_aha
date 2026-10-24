"""Opt-in tiny REAL Vector16 native integration, never a full-block/RTL pass.

No automatic build. Supply fresh receipt-bound GDN_VECTOR16_LIBRARY and
GDN_VECTOR16_FINITE_MUL_UF_LIBRARY explicitly; otherwise these tests are skipped.
The oracle uses exact Fraction arithmetic, not NumPy/PyTorch or the native result.
"""
from collections import Counter
from fractions import Fraction
import json
import os
from pathlib import Path
import unittest

from . import vector as v


STIMULI = v.ROOT / 'candidates/qwen35_uf_predicate_r2/STIMULI.json'
STIMULI_SHA256 = '695f2e8f6649cbe03723410fbef29d766bdf09b21dfb24e75bb0050d9260faf8'


def exact(word):
    exponent = (word >> 23) & 255
    if exponent == 255:
        raise ValueError('finite oracle operands only')
    significand = (word & 0x7fffff) | (0x800000 if exponent else 0)
    value = Fraction(significand) * Fraction(2) ** ((exponent or 1) - 150)
    return -value if word >> 31 else value


def oracle(operation, a, b, backend):
    x, y = exact(a), exact(b)
    result = x * y if operation == 'mul' else x + y
    negative = result < 0 or (result == 0 and
        (bool((a ^ b) >> 31) if operation == 'mul' else a == b == 0x80000000))
    sign, magnitude = int(negative) << 31, abs(result)
    # Exact midpoint to infinity under RNE, followed by binary search over all
    # finite nonnegative binary32 words. This is independent of the C++ predicate.
    if magnitude >= exact(0x7f7fffff) + Fraction(2) ** 103:
        return sign | 0x7f800000, 5
    low, high = 0, 0x7f7fffff
    while low < high:
        mid = (low + high + 1) // 2
        if exact(mid) <= magnitude:
            low = mid
        else:
            high = mid - 1
    rounded = low
    if low < 0x7f7fffff:
        lower, upper = magnitude - exact(low), exact(low + 1) - magnitude
        if upper < lower or upper == lower and low & 1:
            rounded += 1
    inexact = exact(rounded) != magnitude
    tiny = (magnitude < Fraction((1 << 25) - 1, 1 << 151)
            if operation == 'mul' and backend == v.FINITE_MUL_UF_BACKEND
            else rounded < 0x00800000)
    return sign | rounded, int(inexact) | (2 if inexact and tiny else 0)


class BackendNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = (('GDN_VECTOR16_LIBRARY', v.LEGACY_BACKEND),
                 ('GDN_VECTOR16_FINITE_MUL_UF_LIBRARY', v.FINITE_MUL_UF_BACKEND))
        if not all(os.environ.get(name) for name, _ in names):
            raise unittest.SkipTest('explicit two receipt-bound native libraries not supplied; no native run')
        raw = STIMULI.read_bytes()
        if v.sha(raw) != STIMULI_SHA256:
            raise ValueError('fixed native stimulus source changed')
        cls.cases = json.loads(raw)['finite_single_lane_cases']
        if len(cls.cases) != 70:
            raise ValueError('exact seventy finite source cases required')
        cls.libraries = {backend: Path(os.environ[name]) for name, backend in names}
        cls.before = {backend: v.verify_library(path, arithmetic_backend=backend)[2]
                      for backend, path in cls.libraries.items()}

    @classmethod
    def tearDownClass(cls):
        for backend, path in cls.libraries.items():
            if v.verify_library(path, arithmetic_backend=backend)[2] != cls.before[backend]:
                raise AssertionError('native source/library identity changed during tests')

    def vector(self, backend, policy):
        instance = v.Vector16(self.libraries[backend], arithmetic_backend=backend, exception_policy=policy)
        self.assertIs(type(instance), v.Vector16)
        self.assertEqual(instance.fatal_mask, v.POLICY_MASKS[policy])
        client = object()
        self.assertTrue(instance.acquire(client))
        self.assertEqual(instance.lib.gdn_vector16_environment(), 0)
        return instance, client

    def test_all_seventy_finite_single_ops_both_backends_and_policies(self):
        for backend in v.ARITHMETIC_BACKENDS:
            for policy in v.POLICY_MASKS:
                instance, client = self.vector(backend, policy)
                binding = instance.arithmetic_identity()
                for case in self.cases:
                    with self.subTest(backend=backend, policy=policy, case=case['id']):
                        operation = 'mul' if case['op'] else 'add'
                        a, b = int(case['a'], 16), int(case['b'], 16)
                        expected, flags = oracle(operation, a, b, backend)
                        if flags & instance.fatal_mask:
                            with self.assertRaises(v.VectorArithmeticFault) as caught:
                                instance.op(client, operation, [a], [b])
                            diagnostic = caught.exception.diagnostic
                            self.assertEqual(diagnostic['result_words'][0], expected)
                            self.assertEqual(diagnostic['exception_flags'], flags)
                        else:
                            self.assertEqual(instance.op(client, operation, [a], [b]), [expected])
                        self.assertEqual(instance.lane_flags[0], flags)
                self.assertEqual(binding, instance.arithmetic_identity())

    def test_host_batch_matches_separate_issues_and_fault_stage_at_representative_lane_widths(self):
        # Positive/negative minnormal boundary, exact threshold, exact subnormal,
        # tiny tie, overflow, and a value that distinguishes Mul+Add from FMA.
        cases = ((0x00800000, 0x3f7fffff, 0), (0x80800000, 0x3f7fffff, 0),
                 (0x00f80000, 0x3f042108, 0), (0x00800000, 0x3f000000, 0),
                 (1, 0x3f000000, 0x3f800000), (0x7f7fffff, 0x40000000, 0),
                 (0x3f800001, 0x3f7ffffe, 0xbf800000))
        for backend in v.ARITHMETIC_BACKENDS:
            for policy in v.POLICY_MASKS:
                for lanes in (1, 7, 16):
                    for a, b, total in cases:
                        with self.subTest(backend=backend, policy=policy, lanes=lanes, a=hex(a)):
                            single, one = self.vector(backend, policy)
                            batch, two = self.vector(backend, policy)
                            args = ([a] * lanes, [b] * lanes, [total] * lanes)
                            try:
                                product = single.op(one, 'mul', args[0], args[1])
                                expected = single.op(one, 'add', args[2], product)
                            except v.VectorArithmeticFault as error:
                                with self.assertRaises(v.VectorArithmeticFault) as caught:
                                    batch.mul_add(two, *args)
                                self.assertEqual(error.diagnostic, caught.exception.diagnostic)
                            else:
                                self.assertEqual(batch.mul_add(two, *args), expected)
                            self.assertEqual(single.calls, batch.calls)
                            self.assertEqual(single.lane_ops, batch.lane_ops)
                            self.assertEqual(single.flags, batch.flags)
                            self.assertEqual(batch.host_calls, Counter(mul_add=1))

    def test_default_constructor_and_backend_mismatch_rejection(self):
        legacy = v.Vector16(self.libraries[v.LEGACY_BACKEND])
        self.assertEqual(legacy.backend_identity.backend, v.LEGACY_BACKEND)
        self.assertEqual(legacy.exception_policy, v.LEGACY_POLICY)
        for selected, other in ((v.LEGACY_BACKEND, v.FINITE_MUL_UF_BACKEND),
                                (v.FINITE_MUL_UF_BACKEND, v.LEGACY_BACKEND)):
            with self.assertRaisesRegex(ValueError, 'strict host build receipt'):
                v.Vector16(self.libraries[other], arithmetic_backend=selected)


if __name__ == '__main__':
    unittest.main()
