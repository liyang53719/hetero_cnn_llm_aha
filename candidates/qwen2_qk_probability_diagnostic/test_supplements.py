import ast
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile
from candidates.qwen2_qk_probability_diagnostic import audit_saved,mask_recheck,model

class SupplementTests(unittest.TestCase):
    def test_both_cold(self):
        self.assertEqual(audit_saved.run()['status'],'NOT_EXECUTED')
        self.assertEqual(mask_recheck.run()['status'],'NOT_EXECUTED')
        self.assertNotIn('torch',sys.modules)
        self.assertNotIn('numpy',sys.modules)
    def test_saved_reader_preserves_signed_zero(self):
        header=repr({'descr':'<f4','fortran_order':False,'shape':(2,)})+'\n'
        raw=b'\x93NUMPY'+bytes([1,0])+struct.pack('<H',len(header))+header.encode()+struct.pack('<2I',0,0x80000000)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sample.npz'
            with zipfile.ZipFile(path,'w') as z:z.writestr('a.npy',raw)
            shape,words=audit_saved.read_arrays(path)['a']
            self.assertEqual(shape,(2,));self.assertEqual(list(words),[0,0x80000000])
    def test_mask_is_fixed_finite_word(self):
        source=Path(mask_recheck.__file__).read_text()
        self.assertIn('0xff7f if k>q else 0',source)
        self.assertIn("pins['mask_contract']['native_sha256']",source)
        self.assertIn("execute(20)",source);self.assertIn("execute(21)",source)
    def test_supplement_separate_destination(self):
        self.assertNotEqual(mask_recheck.OUT,mask_recheck.OLD)
        self.assertEqual(mask_recheck.OLD,audit_saved.OUT)
    def test_no_qk_rerun_in_mask(self):
        source=Path(mask_recheck.__file__).read_text()
        self.assertNotIn('batch.run(',source)
        self.assertNotIn('torch.matmul(',source)
        self.assertNotIn('Linear(',source)
    def test_exact_owner_source_unchanged(self):
        self.assertEqual(model.sha(model.OWNER),model.OWNER_SHA)

if __name__=='__main__':unittest.main()
