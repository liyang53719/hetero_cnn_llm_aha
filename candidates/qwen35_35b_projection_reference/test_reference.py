"""Tiny arithmetic boundaries and evidence gates; no torch, model or network."""
import ast
import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from .run_reference import FLAGS, SOURCE, ROOT, compare, record


class ReferenceBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory()
        library=Path(cls.directory.name)/'reference.so'
        subprocess.run([shutil.which('gcc'),*FLAGS,str(SOURCE/'reference.c'),
                        '-o',str(library),'-lm'],check=True,capture_output=True,timeout=30)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.reference_run.argtypes=[ctypes.c_uint,ctypes.c_uint,*([ctypes.c_void_p]*5)]

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_fma_ties_gradual_underflow_and_ftz_rejection(self):
        self.assertEqual(self.lib.reference_self_test(),0)
        self.assertEqual(self.lib.reference_environment(),0)

    def test_invalid_shape_and_profile_reject_before_pointer_access(self):
        # Deliberately unusable non-null pointers prove invalid geometry cannot
        # reach an input read, allocation, native call or arithmetic loop.
        pointers=[ctypes.c_void_p(1)]*5
        for m,mode in ((0,0),(1,0),(17,0),(129,0),(16,2),(128,0xffffffff)):
            with self.subTest(m=m,mode=mode):
                self.assertEqual(self.lib.reference_run(m,mode,*pointers),-1)

    def test_missing_buffer_rejects_before_arithmetic(self):
        pointers=[ctypes.c_void_p(1)]*5
        for index in range(5):
            values=pointers.copy();values[index]=None
            with self.subTest(buffer=index):
                self.assertEqual(self.lib.reference_run(16,0,*values),-1)

    def test_recovery_admission_is_explicit_and_non_destructive(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "out"
            argv = [sys.executable, "-O", "-m", "candidates.qwen35_35b_projection_reference.run_reference",
                    "--m", "16", "--out", str(outside)]
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fresh and under ignored work", result.stderr)
            self.assertFalse(outside.exists())
        invalid_out = ROOT / "work" / "invalid_digest_never_created"
        self.assertFalse(invalid_out.exists())
        result = subprocess.run([sys.executable, "-O", "-m", "candidates.qwen35_35b_projection_reference.run_reference",
            "--m", "16", "--out", str(invalid_out), "--manifest-sha256", "not_a_sha"],
            cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Independent manifest and RMS summary SHA256", result.stderr)
        self.assertFalse(invalid_out.exists())

    def test_run_guards_survive_python_optimization(self):
        # The full optimized bad-identity run is retained in the task evidence.
        # This fast regression disallows assertion-based admission guards.
        tree=ast.parse((SOURCE/'run_reference.py').read_text())
        self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(tree)))


class EvidenceGates(unittest.TestCase):
    def test_q_error_cannot_be_diluted_by_exact_kv(self):
        import numpy as np
        from .finalize import require_joint_gate
        expected=np.zeros((16,8192),dtype='<u2')
        actual=expected.copy();actual[:,:2048]=0x3c00  # BF16 0.0078125.
        result=compare(actual,expected,np)
        self.assertEqual(result['mean_abs'],0.001953125)
        self.assertTrue(result['overall_gate_pass'])
        self.assertEqual(result['segments']['q']['mean_abs'],0.0078125)
        self.assertEqual(result['per_segment_original_gate'],dict(q=False,k=True,v=True))
        self.assertFalse(result['gate_pass'])
        with self.assertRaisesRegex(ValueError,'each Q/K/V'):
            require_joint_gate(result)
        result['gate_pass']=True  # Even a stale overall-only PASS is refused.
        with self.assertRaisesRegex(ValueError,'each Q/K/V'):
            require_joint_gate(result)

    def test_output_tampering_is_rejected_before_comparison(self):
        from .finalize import verified_bf16
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'output.bf16le'
            path.write_bytes(bytes(16*8192*2));spec=record(path)
            self.assertEqual(verified_bf16(path,spec,16).shape,(16,8192))
            raw=bytearray(path.read_bytes());raw[0]=1;path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'SHA256'):
                verified_bf16(path,spec,16)

    def test_failed_gate_persists_report_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            code=("from pathlib import Path; import sys; "
                  "from candidates.qwen35_35b_projection_reference.run_reference import finish_report; "
                  "finish_report(Path(sys.argv[1]), "
                  "{'results': {'pair_hi_first_two_k1024': {'gate_pass': False}}, 'total_numeric_seconds': 0.0})")
            process=subprocess.run([sys.executable,'-O','-c',code,directory],
                                   cwd=ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(process.returncode,1,process.stderr)
            report=json.loads((Path(directory)/'report.json').read_text())
            self.assertEqual(report['status'],'FAIL_PAIR_PROFILE_ORIGINAL_GATES')
            self.assertIn('FAIL_PAIR_PROFILE_ORIGINAL_GATES',process.stdout)


if __name__=='__main__':unittest.main()
