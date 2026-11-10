import unittest,numpy as np
from conv_reference import conv4,bf16,fp,exp_negative,div,add,mul,F
class ConvReferenceTest(unittest.TestCase):
 def test_cold_tap_order_and_history(self):
  raw=bf16(np.arange(1,7,dtype='<f4')[:,None].repeat(32,axis=1)/8)
  for tap in range(4):
   weights=np.zeros((32,4),dtype='<u2');weights[:,tap]=bf16(np.array(1,dtype='<f4'))
   actual,history=conv4(raw,weights)
   x=np.zeros((6,32),dtype='<f4');delay=3-tap;x[delay:]=fp(raw[:6-delay])
   expected=bf16(mul(div(F(1),add(F(1),exp_negative(x))),x))
   np.testing.assert_array_equal(actual,expected)
   np.testing.assert_array_equal(history,raw[-4:].T)
 def test_zero_weights(self):
  raw=bf16(np.arange(128*32,dtype='<f4').reshape(128,32)/256)
  actual,_=conv4(raw,np.zeros((32,4),dtype='<u2'))
  self.assertFalse(np.any(actual))
if __name__=='__main__':unittest.main()
