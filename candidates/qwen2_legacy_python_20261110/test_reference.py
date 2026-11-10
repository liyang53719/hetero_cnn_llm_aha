import unittest
import numpy as np
from legacy_reference import *
class ReferenceTests(unittest.TestCase):
 def test_rne_ties(self):
  self.assertEqual(bf16_rne(0x3f808000),0x3f80)
  self.assertEqual(bf16_rne(0x3f818000),0x3f82)
 def test_signed_zeros(self):
  self.assertEqual(add(0x80000000,0x80000000,Budget()),0x80000000)
  self.assertEqual(add(0x3f800000,0xbf800000,Budget()),0)
  self.assertEqual(mul(0x80000000,0x3f800000,Budget()),0x80000000)
 def test_dense_order(self):
  # 2^24 + 1 - 2^24 sequential FP32 is 0, not reordered 1.
  a=np.array([[0x4b800000,0x3f800000,0xcb800000]],dtype=np.uint32)
  w=np.full((3,1),0x3f800000,dtype=np.uint32)
  self.assertEqual(int(dense(a,w,Budget())[0,0]),0)
 def test_rope_half_split(self):
  a=np.array([[[0x3f800000,0x40000000]]],dtype=np.uint32)
  self.assertEqual(rope(a,np.array([[0]],dtype=np.uint32),np.array([[0x3f800000]],dtype=np.uint32),Budget()).tolist(),[[[0xc0000000,0x3f800000]]])
 def test_broadcast_bias(self):
  self.assertEqual(binary_add([[0x3f800000],[0x40000000]],[0x3f800000],Budget()).tolist(),[[0x40000000],[0x40400000]])
 def test_full_forward_closed(self):
  self.assertEqual(len(SCHEDULE),21)
  with self.assertRaises(IncompleteReference):run({})
 def test_budget(self):
  with self.assertRaises(BudgetExceeded):dense(np.zeros((128,1536),dtype=np.uint32),np.zeros((1536,1),dtype=np.uint32),Budget(2))
 def test_nonfinite_closed(self):
  with self.assertRaises(IncompleteReference):add(0x7f800000,0,Budget())
 def test_gradual_ieee_scope(self):
  # Mathematical IEEE oracle, not proof original RTL permits underflow.
  self.assertEqual(mul(0x00800000,0x3f000000,Budget()),0x00400000)
if __name__=='__main__':unittest.main()
