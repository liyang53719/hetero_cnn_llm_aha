import sys,struct,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'numeric'))
from resident_compare import expand_bf16_bits,compare_fp32_bits,compare_full128
class Compare(unittest.TestCase):
 def test_bits(self):
  ref=struct.pack('<HHH',0x3f80,0x8000,1)
  self.assertEqual(expand_bf16_bits(ref),struct.pack('<III',0x3f800000,0x80000000,0x10000))
  self.assertEqual(compare_fp32_bits(expand_bf16_bits(ref),ref)['byte_mismatches'],0)
 def test_actual_not_rounded(self):
  self.assertEqual(compare_fp32_bits(struct.pack('<I',0x3f800001),struct.pack('<H',0x3f80))['byte_mismatches'],1)
 def test_bad_size(self):
  with self.assertRaises(ValueError):expand_bf16_bits(b'1')
  with self.assertRaises(ValueError):compare_fp32_bits(b'',b'12')
 def test_missing_terminal(self):
  with self.assertRaises(ValueError):compare_full128(Path('.'),'partial',{})
if __name__=='__main__':unittest.main()
