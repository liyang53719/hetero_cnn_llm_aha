import unittest,struct,tempfile
from pathlib import Path
from prepare_host_inputs import transpose_words
from bind_real_bench import bind
class Tests(unittest.TestCase):
 def test_transpose_bits(self):
  # Distinct bit patterns include negative zero and a subnormal; no arithmetic.
  values=[0,0x80000000,1,0x3f800000,0xbf800000,0x7fc00001]
  raw=struct.pack('<6I',*values);got=transpose_words(raw,[2,3])
  self.assertEqual(struct.unpack('<6I',got),tuple(values[i] for i in [0,3,1,4,2,5]))
  self.assertEqual(transpose_words(got,[3,2]),raw)
 def test_bad_bytes(self):
  with self.assertRaises(ValueError):transpose_words(bytes(12),[2,2])
 def test_bench_uses_real_loads_and_4096(self):
  s=Path(__file__).with_name('host_real_inputs.cpp').read_text()
  start=s.index(' void initialize(');end=s.index(' uint64_t hashRange',start);init=s[start:end]
  self.assertEqual(init.count('   realInput('),13)
  self.assertNotIn('weight(A_WQ',init);self.assertNotIn('if(layer==0)for(',init)
  self.assertIn('OWNER_MATRIX_MACS==4096 && OWNER_BF16_WEIGHTS==0',init)
  self.assertNotIn('HOST_BLOCK_ALL_OWNERS_PASS',s)
if __name__=='__main__':unittest.main()
