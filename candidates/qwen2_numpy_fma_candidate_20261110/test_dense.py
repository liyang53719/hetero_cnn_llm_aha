import sys,pathlib,unittest
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'legacy_python'))
import legacy_reference as ref
from candidate import dense
class DenseParity(unittest.TestCase):
 def test_full_k(self):
  rng=np.random.default_rng(20261110)
  a=rng.uniform(-2,2,(5,37)).astype(np.float32).view(np.uint32)
  w=rng.uniform(-2,2,(37,9)).astype(np.float32).view(np.uint32)
  np.testing.assert_array_equal(dense(a,w),ref.dense(a,w,ref.Budget(2000)))
 def test_order(self):
  a=np.array([[0x4b800000,0x3f800000,0xcb800000]],dtype=np.uint32);w=np.full((3,1),0x3f800000,dtype=np.uint32)
  self.assertEqual(int(dense(a,w)[0,0]),0)
 def test_reject_nonfinite(self):
  with self.assertRaises(ValueError):dense(np.array([[0x7f800000]],dtype=np.uint32),np.array([[0]],dtype=np.uint32))
if __name__=='__main__':unittest.main()
