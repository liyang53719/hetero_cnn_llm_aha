"""Long-K adapter checks using unchanged integer FMA and independent C fmaf."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gdn_dense_reference as dense


class GdnDenseReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.executable, cls.tools = dense.compile_reference(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def case(k):
        a = np.zeros(k, dtype='<u2'); w = np.zeros((k, 256), dtype='<u2')
        # Cancellation straddles the previous fixed-K boundary. Any intermediate
        # BF16 rounding loses the small increment before the final cancellation.
        for row, activation, weight in [(0, 0x3f80, 0x3f80),
                                         (1023, 0x3b80, 0x3f00),
                                         (k-1, 0xbf80, 0x3f80)]:
            a[row] = activation; w[row, :] = weight
        w[0, 1] = 0xbf80
        return a, w

    def test_uninterrupted_long_k_every_step_flags_and_terminal_rne(self):
        for k in (2048, 3584):
            with self.subTest(k=k), tempfile.TemporaryDirectory() as scratch:
                a, w = self.case(k)
                result, receipt = dense.project_and_crosscheck(a, w, self.executable, scratch)
                actual = np.frombuffer(result['bf16'], dtype='<u2')
                self.assertEqual(int(actual[0]), 0x3b00)
                self.assertEqual(receipt['matrix_accumulator_steps'], k * 256)
                self.assertEqual(receipt['integer_step_sha256'], receipt['c_step_sha256'])
                self.assertTrue(receipt['uninterrupted_fp32_accumulation'])
                self.assertEqual(receipt['terminal_bf16_roundings'], 1)

    def test_k1024_entry_is_original_integer_implementation(self):
        a = np.zeros(1024, dtype='<u2');w = np.zeros((1024, 256), dtype='<u2')
        a[0] = 0x3f81;w[0, :] = 0x3f81
        expected = dense.integer.projection_trace(a, w)
        actual = dense.projection_trace(a, w)
        for key in expected:
            np.testing.assert_array_equal(actual[key], expected[key])
        with tempfile.TemporaryDirectory() as scratch:
            result, receipt = dense.project_and_crosscheck(a, w, self.executable, scratch)
        self.assertEqual(result['bf16'], np.asarray(expected['bf16'], dtype='<u2').tobytes())
        self.assertEqual(receipt['k'], 1024)

    def test_unsupported_shape_and_nonfinite_fail_before_c(self):
        for k in (0, 512, 1025, 4096):
            with self.subTest(k=k), self.assertRaises(ValueError):
                dense.projection_trace(np.zeros(k, dtype='<u2'), np.zeros((k, 256), dtype='<u2'))
        a, w = self.case(2048);a[2] = 0x7f80
        with self.assertRaises(ValueError):
            dense.projection_trace(a, w)

    def test_c_rejects_unsupported_header_and_truncated_input(self):
        for k in (512, 1025, 4096, 2048):
            with tempfile.TemporaryDirectory() as scratch:
                p=Path(scratch);np.array([k,256],dtype='<u4').tofile(p/'input')
                done=subprocess.run([str(self.executable),str(p/'input'),str(p/'output')],capture_output=True)
                self.assertEqual(done.returncode,3)
