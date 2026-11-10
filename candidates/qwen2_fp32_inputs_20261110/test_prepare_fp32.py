import unittest,struct,tempfile
from pathlib import Path
from prepare_fp32 import lift,prepare
class PreparationTests(unittest.TestCase):
 def test_exact_bits(self):
  values=[0,0x8000,1,0x7f,0x80,0x3f80,0x7f80,0xff80,0x7fc1]
  self.assertEqual(lift(struct.pack('<9H',*values)),struct.pack('<9I',*(x<<16 for x in values)))
 def test_odd_bytes_rejected(self):
  with self.assertRaises(ValueError):lift(b'\x01')
 def test_missing_inputs_do_not_create_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);out=p/'output'
   with self.assertRaises(FileNotFoundError):prepare(p,out)
   self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
