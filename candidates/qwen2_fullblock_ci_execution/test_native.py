import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import native as n

class NativeTests(unittest.TestCase):
    def test_default_no_io(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('read')),patch.object(Path,'exists',side_effect=AssertionError('stat')):
            self.assertEqual(n.build()['status'],'NOT_EXECUTED')
    def test_arithmetic_pins_real(self):
        self.assertEqual(n.sources(n.ROOT),n.SOURCE_HASHES)
    def test_unbound_receipt(self):
        for v in (None,True,'0'*63,'G'*64,{'sha256':'0'*64}):
            with self.subTest(v=v),self.assertRaises(ValueError):n.load(receipt_sha256=v)
    def test_wrong_root(self):
        with self.assertRaises(ValueError):n.build(Path('/tmp/wrong'),execute=True)
    def test_existing_build_refused(self):
        with tempfile.TemporaryDirectory() as d,patch.object(n,'location',return_value=Path(d)),patch.object(n,'sources',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError,'fresh'):n.build(execute=True)
    def test_source_drift(self):
        with patch.object(Path,'read_bytes',return_value=b'wrong'):
            with self.assertRaisesRegex(ValueError,'source drift'):n.sources(n.ROOT)
    def test_receipt_drift_before_import(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); (out/'official_bf16_compile.json').write_bytes(b'bad')
            with patch.object(n,'location',return_value=out),patch.object(n,'sources',return_value={}),patch.object(n.inputs,'safe_path',return_value=out/'official_bf16_compile.json'):
                with self.assertRaisesRegex(ValueError,'receipt drift'):n.load(receipt_sha256='0'*64)
if __name__=='__main__':unittest.main()
