"""Synthetic arithmetic and fixed-loader tests only; no real inputs or native code."""
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import types
import unittest
from fractions import Fraction
from unittest import mock

HERE = Path(__file__).resolve().parent
PREPARE_PIN = (8378, '3a52a7ec16680ea6b9e0553563ab51d1415ae0f703cb1916abbe0748bd495167')


def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in (
            'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen'):
        raise RuntimeError('cold native/network forbidden')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'torch', 'ctypes'):
        raise RuntimeError('cold numerical/native import forbidden')


sys.addaudithook(audit)
raw = (HERE / 'prepare_reference.py').read_bytes()
if (len(raw), hashlib.sha256(raw).hexdigest()) != PREPARE_PIN:
    raise RuntimeError('test loader identity')
P = types.ModuleType('fixed_prepare_reference')
exec(compile(raw, str(HERE / 'prepare_reference.py'), 'exec'), P.__dict__)
O = P.load_oracle(HERE)


class Arithmetic(unittest.TestCase):
    def test_roundtrip_all_finite_bf16(self):
        for b in range(65536):
            if b & 0x7f80 == 0x7f80:
                continue
            self.assertEqual(O.encode(O.decode(b, 16), 16, zero_sign=b >> 15), b)

    def test_rne_even_and_odd(self):
        self.assertEqual(O.encode(1 + Fraction(1, 1 << 24)), 0x3f800000)
        self.assertEqual(O.encode(1 + Fraction(3, 1 << 24)), 0x3f800002)
        self.assertEqual(O.encode(-1 - Fraction(1, 1 << 24)), 0xbf800000)
        self.assertEqual(O.encode(-1 - Fraction(3, 1 << 24)), 0xbf800002)

    def test_zero_sign(self):
        self.assertEqual(O.encode(0), 0)
        self.assertEqual(O.encode(0, zero_sign=1), 0x80000000)
        self.assertEqual(O.add32(0x80000000, 0x80000000), 0x80000000)
        self.assertEqual(O.add32(0x80000000, 0), 0)
        self.assertEqual(O.fma32(0x80000000, 0x3f800000, 0x80000000), 0x80000000)
        self.assertEqual(O.fma32(0xbf800000, 0x3f800000, 0x3f800000), 0)

    def test_subnormal_ties(self):
        self.assertEqual(O.encode(Fraction(1, 1 << 150)), 0)
        self.assertEqual(O.encode(Fraction(3, 1 << 150)), 2)
        self.assertEqual(O.encode(Fraction(-1, 1 << 150)), 0x80000000)
        self.assertEqual(O.encode(Fraction(-3, 1 << 150)), 0x80000002)

    def test_subnormal_to_normal_boundary(self):
        halfway = Fraction((1 << 24) - 1, 1 << 150)
        self.assertEqual(O.encode(halfway), 0x00800000)
        self.assertEqual(O.encode(-halfway), 0x80800000)

    def test_overflow_rejected_and_max_finite_retained(self):
        for sign in (1, -1):
            with self.assertRaises(O.Rejected):
                O.encode(sign * (1 << 128))
            self.assertEqual(O.encode(sign * O.decode(0x7f7fffff)), 0x7f7fffff | (0x80000000 if sign < 0 else 0))

    def test_nonfinite_rejected(self):
        for b in (0x7f800000, 0xff800000, 0x7fc00001):
            with self.assertRaises(O.Rejected):
                O.decode(b)

    def test_generic_fma_counterexample(self):
        a, b, c = 0x3f800001, 0x3f7ffffe, 0xbf800000
        self.assertEqual(O.fma32(a, b, c), 0xa8800000)
        self.assertEqual(O.add32(O.mul32(a, b), c), 0)

    def test_bf16_subnormal_fma_counterexample(self):
        a, b = self.sparse({1: Fraction(1, 1 << 126), 0: Fraction(1, 1 << 126)})
        b[1], b[0] = O.encode(Fraction(1, 1 << 23)), O.encode(Fraction(1, 1 << 24))
        self.assertEqual(O.typed_dot(a, b), 2)
        self.assertEqual(O.typed_dot(a, b, fused=False), 1)

    @staticmethod
    def sparse(terms):
        a, b = [0] * 1536, [0x3f800000] * 1536
        for k, value in terms.items():
            a[k] = O.encode(value)
            if a[k] & 0xffff:
                raise ValueError('micro input not BF16')
        return a, b

    def test_partial_partition_counterexample(self):
        a, b = self.sparse({1: 1, 1025: 1 << 24, 1024: -(1 << 24)})
        self.assertEqual(O.typed_dot(a, b), 0x3f800000)
        self.assertEqual(O.typed_dot(a, b, blocks=(1536,)), 0)
        self.assertEqual(O.math_dot(a, b), 1)

    def test_pair_order_counterexample(self):
        a, b = self.sparse({1: 1 << 24, 2: 1, 3: -(1 << 24)})
        self.assertEqual(O.typed_dot(a, b), 0x3f800000)
        self.assertEqual(O.typed_dot(a, b, high_first=False), 0)
        self.assertEqual(O.math_dot(a, b), 1)

    def test_bias_and_bf16_contamination(self):
        a, b = self.sparse({1: 1, 0: Fraction(1, 256)})
        qraw = O.typed_dot(a, b)
        self.assertEqual(qraw, 0x3f808000)
        self.assertEqual(O.encode(O.decode(qraw), 16), 0x3f80)
        with_bias = O.add32(qraw, O.encode(Fraction(1, 128)))
        self.assertEqual(with_bias, 0x3f818000)
        self.assertEqual(O.encode(O.decode(with_bias), 16), 0x3f82)

    def test_wide_capacity_and_cancellation(self):
        largest = O.bf16_product_units(0x7f7f, 0x7f7f)
        self.assertLessEqual(largest.bit_length(), 522)
        total = 1536 * largest
        self.assertLessEqual(total.bit_length(), 533)
        self.assertLessEqual((196608 * (total + (1 << 394))).bit_length(), 552)
        self.assertEqual(total + 1536 * O.bf16_product_units(0xff7f, 0x7f7f), 0)
        self.assertEqual(O.bf16_product_units(1, 1), 1)

    def test_decode_product_integer_equivalence(self):
        rng = random.Random(314159)
        for _ in range(1000):
            a, b = rng.randrange(65536), rng.randrange(65536)
            if a & 0x7f80 == 0x7f80 or b & 0x7f80 == 0x7f80:
                continue
            def split(u):
                e = (u >> 7) & 255
                return ((u & 127) | (128 if e else 0)), (e - 1 if e else 0), bool(u >> 15)
            x, xs, xn = split(a); y, ys, yn = split(b)
            expected = (x * y) << (xs + ys)
            if xn != yn:
                expected = -expected
            self.assertEqual(O.bf16_product_units(a, b), expected)

    def test_exact_dot_independent_of_order(self):
        a, b = self.sparse({1: 1 << 24, 2: 1, 3: -(1 << 24)})
        self.assertEqual(O.math_dot(a, b), O.math_dot(list(reversed(a)), list(reversed(b))))

    def test_ulp_zero_and_signed_values(self):
        self.assertEqual(O.ulp_distance(0, 0x80000000), 0)
        self.assertEqual(O.ulp_distance(1, 0x80000001), 2)
        self.assertEqual(O.ulp_distance(0x3f800000, 0x3f800001), 1)

    def test_shape_and_blocks_rejected(self):
        for args in (([], []), ([0], []), ([0] * 1537, [0] * 1537)):
            with self.assertRaises(O.Rejected):
                O.math_dot(*args)
        with self.assertRaises(O.Rejected):
            O.typed_dot([0] * 4, [0] * 4, blocks=(1, 3))


class FixedSource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pc1-cold-')
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_same_buffer_oracle_load(self):
        o = P.load_oracle(HERE)
        self.assertEqual(o.fma32(0x3f800001, 0x3f7ffffe, 0xbf800000), 0xa8800000)
    def test_local_native_bytes_fixed(self):
        data = P.local_sources(HERE)
        self.assertEqual(len(data['dot16.inc']), 1078)
        self.assertIn(b'const int blocks[2]={1024,512}', data['pc1_reference_main.cpp'])
        self.assertIn(b'std::array<std::uint64_t,9>', data['exact_math.hpp'])
    def test_tamper_rejected_before_compile(self):
        p = self.root / 'exact_oracle.py';p.write_bytes((HERE / p.name).read_bytes() + b'\n')
        with self.assertRaises(P.Rejected):
            P.load_oracle(self.root)
    def test_same_size_hash_tamper(self):
        p = self.root / 'exact_oracle.py';b = bytearray((HERE / p.name).read_bytes());b[0] ^= 1;p.write_bytes(b)
        with self.assertRaises(P.Rejected):
            P.load_oracle(self.root)
    def test_symlink_file_rejected(self):
        (self.root / 'exact_oracle.py').symlink_to(HERE / 'exact_oracle.py')
        with self.assertRaises(OSError):
            P.load_oracle(self.root)
    def test_symlink_parent_rejected(self):
        (self.root / 'linked').symlink_to(HERE, target_is_directory=True)
        with self.assertRaises(OSError):
            P.load_oracle(self.root / 'linked')
    def test_relocation_no_cwd_dependency(self):
        target = self.root / 'source';target.mkdir()
        for name in P.LOCAL_PINS:
            shutil.copyfile(HERE / name, target / name)
        self.assertEqual(P.load_oracle(target).encode(Fraction(3, 1 << 150)), 2)
    def test_relative_and_traversal_rejected(self):
        for path in (Path('exact_oracle.py'), self.root / '..' / 'x'):
            with self.assertRaises(P.Rejected):
                P.fixed_bytes(path, (0, hashlib.sha256(b'').hexdigest()))
    def test_missing_result_not_success(self):
        with self.assertRaises(FileNotFoundError):
            P.verify_complete_outputs(self.root)
    def test_preflight_input_failure_no_destination(self):
        destination = self.root / 'new'
        with mock.patch.object(P, 'verify_repository', return_value=({}, {})), \
                mock.patch.object(P, 'fixed_bytes', side_effect=P.Rejected('BYTE_IDENTITY')):
            with self.assertRaises(P.Rejected):
                P.prepare(self.root, HERE, self.root/'n', self.root/'actual', self.root/'w', destination)
        self.assertFalse(destination.exists())
    def test_synthetic_preparation_never_uses_actual_as_reference(self):
        source = {name: b'cold source' for name in P.NATIVE_FILES}
        destination = self.root / 'prepared'
        paths = {self.root/'reference': b'n0', self.root/'actual': b'n0', self.root/'weight': b'wq'}
        with mock.patch.object(P, 'verify_repository', return_value=(source, {})), \
                mock.patch.object(P, 'fixed_bytes', side_effect=lambda path, pin: paths[path]):
            result = P.prepare(self.root, HERE, self.root/'reference', self.root/'actual', self.root/'weight', destination)
        self.assertFalse(result['accepted_n0_used_as_reference'])
        self.assertFalse(result['native_executed'])
        self.assertIsNone(result['official_raw_numeric_pass'])
        self.assertEqual((destination/'inputs'/'independent_n0.f32le').read_bytes(), b'n0')
        self.assertEqual(sorted(p.name for p in (destination/'inputs').iterdir()), ['independent_n0.f32le', 'wq.bf16le'])
    def test_different_actual_rejected(self):
        destination = self.root/'new'
        with mock.patch.object(P, 'verify_repository', return_value=({}, {})), \
                mock.patch.object(P, 'fixed_bytes', side_effect=[b'a', b'b', b'w']):
            with self.assertRaises(P.Rejected):
                P.prepare(self.root, HERE, self.root/'n', self.root/'actual', self.root/'w', destination)
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
