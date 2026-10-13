import ctypes,struct,unittest
from .scalar import DecayScalar,OPERATION,ArithmeticFault,word,PrepScalar

class ScalarTests(unittest.TestCase):
 def scalar(self,enabled=True):
  s=DecayScalar(enable_ieee_exp=enabled);owner=object();s.client=owner;return s,owner
 def test_exact_range_boundaries_and_real_gate(self):
  # Fixed published Torch/independent range probe witnesses, not a general exp tolerance.
  values={0:0x3f800000,0x80000000:0x3f800000,0x80000001:0x3f800000,
   0xc2a00000:0x05bfecba,0xc2aeac4f:0x00800026,0xc2aeac50:0x007fffe6,
   0xc2aeac51:0x007fffa6,0xc2b72752:0x0001d7fd,0xc2b72754:0x0001d7fb,
   0xc2ce8ed0:1,0xc2cff1b3:1,0xc2cff1b4:1,0xc2cff1b5:0,0xff7fffff:0}
  s,o=self.scalar()
  for x,y in values.items():
   with self.subTest(x=hex(x)):self.assertEqual(s.op(o,OPERATION,x),y)
 def test_legacy_default_and_op4_stay_unchanged(self):
  s,o=self.scalar(False)
  with self.assertRaises(ArithmeticFault):s.op(o,OPERATION,word(-80))
  s.enable_ieee_exp=True
  p=PrepScalar();p.client=o
  for x in [0.,-1.,-79.5,-80.,-91.58,2.]:
   self.assertEqual(s.op(o,'exp_negative',word(x)),p.op(o,'exp_negative',word(x)))
  self.assertEqual(s.op(o,'exp_negative',word(-91.58)),0)
  self.assertGreater(s.op(o,OPERATION,word(-91.58)),0)
 def test_finite_nonpositive_and_ownership(self):
  s,o=self.scalar()
  for x in [0x7f800000,0xff800000,0x7fc00000,0x7f800001,0x3f800000]:
   with self.assertRaises(ArithmeticFault):s.op(o,OPERATION,x)
  with self.assertRaises(ValueError):s.op(object(),OPERATION,word(-1))
 def test_fixed_single_scalar_node_counters(self):
  s,o=self.scalar();self.assertIsInstance(s,PrepScalar)
  s.op(o,OPERATION,word(-91.58))
  self.assertEqual(s.calls[OPERATION],1)
  self.assertEqual(s.decay_internal_calls,{'mul':13,'add':9,'integer_rne':1})
  self.assertEqual(dict(s.internal_calls),{})
  s.op(o,'add',word(1),word(2));self.assertEqual(s.calls['add'],1)
  self.assertIs(s.client,o)
 def test_non_rne_environment_rejected(self):
  c=ctypes.CDLL(None);old=c.fegetround()
  try:
   self.assertEqual(c.fesetround(0x400),0)
   with self.assertRaises(ValueError):DecayScalar(enable_ieee_exp=True)
  finally:c.fesetround(old)
 def test_small_normal_diagnostic_difference_is_not_hidden(self):
  s,o=self.scalar()
  # One ULP above pinned Torch witness is retained, no quantization/clipping.
  self.assertEqual(s.op(o,OPERATION,0xc2a00001),0x05bfec5b)
  self.assertNotEqual(s.op(o,OPERATION,0xc2a00001),0x05bfec5a)
if __name__=='__main__':unittest.main()
