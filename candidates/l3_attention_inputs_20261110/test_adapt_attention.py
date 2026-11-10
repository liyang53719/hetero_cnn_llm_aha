import unittest,numpy as np
from adapt_attention import transpose_weight,fp,ordered_dot
class LayoutTest(unittest.TestCase):
 def test_ascending_k_address(self):
  w=np.arange(512*1024,dtype='<u2').reshape(512,1024);mapped=transpose_weight(w);data=np.frombuffer(mapped.tobytes(),dtype='<u2')
  for k,n in [(0,0),(1,31),(31,256),(1023,511)]:self.assertEqual(data[k*512+n],w[n,k])
 def test_exact_bf16_lift(self):
  a=np.array([0,0x8000,1,0x7f80,0xff80,0x7fc1],dtype='<u2')
  np.testing.assert_array_equal(fp(a).view('<u4'),a.astype('<u4')<<16)
 def test_wrong_dtype_rejected(self):
  with self.assertRaises(ValueError):transpose_weight(np.zeros((2,2),dtype='<f4'))
if __name__=='__main__':unittest.main()
