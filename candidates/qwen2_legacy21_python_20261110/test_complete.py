import unittest,hashlib,json,struct,math
from fractions import Fraction
import numpy as np
import legacy_reference as c
import operators as o

def fixture(m=2,hd=16,heads=1,kvheads=1,zero=False):
 h=hd*heads;kv=hd*kvheads;f=16
 x=np.full((m,h),0x3e800000,dtype=np.uint32)
 def weight(k,n):
  a=np.zeros((k,n),dtype=np.uint32)
  if not zero:
   for i in range(min(k,n)):a[i,i]=0x3e000000
  return a
 return dict(x=x,gamma0=np.full(h,o.ONE,dtype=np.uint32),gamma1=np.full(h,o.ONE,dtype=np.uint32),
  wq=weight(h,h),wk=weight(h,kv),wv=weight(h,kv),wo=weight(h,h),wg=weight(h,f),wu=weight(h,f),wd=weight(f,h),
  bq=np.zeros(h,dtype=np.uint32),bk=np.zeros(kv,dtype=np.uint32),bv=np.zeros(kv,dtype=np.uint32),
  cos=np.full((m,hd//2),o.ONE,dtype=np.uint32),sin=np.zeros((m,hd//2),dtype=np.uint32))

class Operators(unittest.TestCase):
 def test_sqrt_rounding(self):
  for word in [0,0x80000000,1,0x00800000,0x3f000000,0x3f800000,0x40000000,0x7f7fffff]:
   # Independent stdlib double sqrt cross-check for directed binary32 inputs only.
   f=struct.unpack('<f',struct.pack('<I',word))[0]
   expected=struct.unpack('<I',struct.pack('<f',math.sqrt(f)))[0]
   self.assertEqual(o.sqrt(word,c.Budget()),expected)
 def test_div(self):
  self.assertEqual(o.div(o.ONE,0x40400000,c.Budget()),0x3eaaaaab)
  with self.assertRaises(o.NumericalFault):o.div(o.ONE,0,c.Budget())
 def test_underflow_contract(self):
  self.assertEqual(o.mul(0x00800000,0x3f000000,c.Budget()),0x00400000)
  with self.assertRaises(o.NumericalFault):o.mul(1,0x3f000000,c.Budget())
 def test_exp(self):
  self.assertEqual(o.exp_negative(0,c.Budget()),o.ONE)
  self.assertEqual(o.exp_negative(0x42a00000,c.Budget()),0)
  self.assertEqual(o.exp_negative(0x3f800000,c.Budget()),o.exp_negative(0xbf800000,c.Budget()))
 def test_rms_terminal_bf16(self):
  y=o.rms(np.array([[o.ONE]*16],dtype=np.uint32),np.full(16,o.ONE,dtype=np.uint32),c.Budget())
  self.assertTrue(np.all(y==o.ONE))
 def test_qk_lane_fold(self):
  q=np.full((2,128),o.ONE,dtype=np.uint32)
  s=o.qk(q,q,c.Budget(),128)
  self.assertEqual(int(s[0,1,0]),c.mul(c.rounded(Fraction(128)),0x3db504f3,c.Budget()))
  p=o.softmax(s,c.Budget());self.assertEqual(p[0,1].tolist(),[0x3f000000]*2)
  self.assertTrue(np.all(o.pv(p,q,c.Budget(),128)==o.ONE))
 def test_silu_zero(self):
  self.assertEqual(o.silu(np.array([0],dtype=np.uint32),np.array([o.ONE],dtype=np.uint32),c.Budget()).tolist(),[0])
 def test_full21_zero_weights(self):
  x=fixture(zero=True);trace=[];y=c.run(x,c.Budget(100000),16,trace)
  self.assertEqual(len(trace),21);np.testing.assert_array_equal(y,x['x'])
 def test_full21_nonzero(self):
  x=fixture();a=[];b=[]
  y=c.run(x,c.Budget(100000),16,a);z=c.run(x,c.Budget(100000),16,b)
  np.testing.assert_array_equal(y,z);self.assertTrue(np.any(y!=x['x']))
  self.assertEqual(len(a),21)
 def test_full21_original_hd_gqa(self):
  x=fixture(m=1,hd=128,heads=2,kvheads=1,zero=True);trace=[]
  y=c.run(x,c.Budget(500000),128,trace)
  np.testing.assert_array_equal(y,x['x']);self.assertEqual(len(trace),21)

if __name__=='__main__':unittest.main()
