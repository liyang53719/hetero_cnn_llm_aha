"""Read-only full-shape slicing and file-identity gates; no model execution."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np

from . import run_prefix as r


class EvidenceTests(unittest.TestCase):
    def test_original_full_shape_slice_and_unselected_changes(self):
        full = np.arange(16*8192, dtype=np.uint16).reshape(16, 8192) % 0x1000
        w = r.p.ColumnWindow(2048, 160)
        actual = full[:, 2048:2208].copy().astype('<u2').tobytes()
        self.assertEqual(r.compare_window(actual, full.astype('<u2').tobytes(), 16, w)['bit_mismatches'], 0)
        with self.assertRaises(ValueError):
            r.compare_window(actual, actual, 16, w)
        full[:, 0] = 0x3f80
        self.assertEqual(r.compare_window(actual, full.astype('<u2').tobytes(), 16, w)['bit_mismatches'], 0)

    def test_window_error_does_not_dilute_with_unselected_full_output(self):
        full = bytes(16*8192*2)
        bad = np.full((16, 160), 0x3c00, '<u2').tobytes()  # .0078125
        result = r.compare_window(bad, full, 16, r.p.ColumnWindow(0, 160))
        self.assertFalse(result['passed'])
        self.assertEqual(result['mean_abs'], .0078125)

    def test_full_qkv_gate_requires_each_complete_segment(self):
        full = bytes(16*8192*2)
        bad = np.zeros((16,8192), '<u2')
        bad[:, :2048] = 0x3c00
        result = r.compare_window(bad.tobytes(), full, 16, r.p.ColumnWindow(0,8192))
        self.assertTrue(result['whole_passed'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['segments']['q']['passed'])
        self.assertTrue(result['segments']['k']['passed'])
        self.assertTrue(result['segments']['v']['passed'])

    def test_actual_bytes_and_length_are_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.bin'
            path.write_bytes(b'original')
            identity = r.record(path)
            self.assertEqual(r.checked_record(identity), b'original')
            path.write_bytes(b'changed!')
            with self.assertRaises(ValueError):
                r.checked_record(identity)

    def test_verified_buffer_is_the_same_single_read_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source.bin'
            path.write_bytes(b'original')
            identity = r.record(path)
            with patch.object(Path, 'read_bytes', side_effect=[b'original', b'changed!']) as reader:
                self.assertEqual(r.checked_record(identity), b'original')
                self.assertEqual(reader.call_count, 1)
            path.write_bytes(b'original-more')
            with self.assertRaises(ValueError):
                r.checked_record(identity)

    def test_synthetic_relative_file_is_not_a_repository_source(self):
        from types import SimpleNamespace
        with patch.dict(r.sys.modules, {'synthetic_torch_classes': SimpleNamespace(__file__='_classes.py')}):
            self.assertNotIn('_classes.py', r.source_closure())
        with patch.dict(r.sys.modules, {'missing_real_source': SimpleNamespace(__file__=str(r.ROOT/'missing_real_source.py'))}):
            with self.assertRaises(FileNotFoundError):
                r.source_closure()


if __name__ == '__main__':
    unittest.main()
