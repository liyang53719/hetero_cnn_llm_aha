import unittest,tempfile,shutil
from pathlib import Path
from load_real_gdn_parameters import load
ROOT=Path(__file__).resolve().parents[2]/'hetero_cnn_llm_aha'
PAYLOAD=ROOT/'work/qwen35_layer0_payload'
class RealParameterTest(unittest.TestCase):
 def test_exact_shapes_and_bits(self):
  w,a,b=load(ROOT,PAYLOAD)
  self.assertEqual(w.shape,(6144,4));self.assertEqual(a.dtype.itemsize,4);self.assertEqual(b.dtype.itemsize,2)
  self.assertEqual(w.tobytes(),(PAYLOAD/'linear_attn.conv1d.weight.bin').read_bytes())
 def test_corruption_rejected(self):
  with tempfile.TemporaryDirectory() as p:
   dest=Path(p)
   for name in ['linear_attn.conv1d.weight','linear_attn.A_log','linear_attn.dt_bias']:shutil.copy2(PAYLOAD/(name+'.bin'),dest)
   q=dest/'linear_attn.conv1d.weight.bin';raw=bytearray(q.read_bytes());raw[0]^=1;q.write_bytes(raw)
   with self.assertRaises(ValueError):load(ROOT,dest)
if __name__=='__main__':unittest.main()
