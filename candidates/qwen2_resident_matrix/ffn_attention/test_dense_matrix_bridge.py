"""Actual tiny Dense driver retirement through the shared Matrix service.

Synthetic inputs, no checkpoint/official capture, no RTL or hardware cycles.
The unchanged legacy driver helper generates all input/write/ACK transactions.
"""
import ctypes as C
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest

from candidates.qwen2_resident_matrix.ffn_fullgroup import test_down_driver as f
from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as m


class DenseMatrixBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='qwen2_dense_matrix_bridge_')
        cls.path = Path(cls.temporary.name)
        library = os.environ.get('MATRIX_SERVICE_LIBRARY')
        if library is None:
            library = cls.path / 'matrix.so'
            subprocess.run(['g++', '-O2', '-std=c++17', '-shared', '-fPIC',
                '-ffp-contract=off', '-fno-fast-math', '-frounding-math',
                str(Path(m.__file__).with_name('matrix_numeric.cpp')), '-o', str(library)],
                check=True, capture_output=True, timeout=30)
        cls.lib = m.configure_library(C.CDLL(str(library)))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_actual_two_chunk_driver_result_seed_done_fences(self):
        self.assertEqual(self.lib.td_reset(), 0)
        service = m.MatrixService(self.lib)
        owner, job = f.make_owner_job(16, 256, 32, 128)
        memory = f.SyntheticMemory(16, 256, 32)
        self.assertTrue(service.acquire(owner, 'dense', job.tag))
        bridge = service.dense_library(owner)
        output = self.path / 'split'
        output.mkdir()
        report, actual = f.driver.execute_down(f.model, owner, bridge, memory, job,
            output, time.monotonic() + 20, f.Trace(), synthetic_geometry=True,
            matrix_bridge=bridge)
        expected = struct.unpack('<I', struct.pack('<f', 128.0))[0]
        self.assertEqual(list(actual), [expected] * (16 * 32))
        self.assertEqual(report['accepted']['response_handshakes'], 1)
        self.assertEqual(service.counts['dense_results'], 2)
        self.assertEqual(service.counts['dense_seed_acks'], 1)
        self.assertIs(service.owner, owner)
        self.assertFalse(service.acquire(object(), 'normal', 5))
        service.retire_owner_response(owner)
        service.release(owner)
        next_owner = object()
        self.assertTrue(service.acquire(next_owner, 'normal', 5))
        # This is a genuine no-work terminal in a fresh ownership domain.
        service.retire_owner_response(next_owner)
        service.release(next_owner)
        self.assertEqual(service.counts['owner_releases'], 2)


if __name__ == '__main__':
    unittest.main()
