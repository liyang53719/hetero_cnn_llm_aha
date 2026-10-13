"""Explicit dual-exp gate compound: unchanged old op7 and one Scalar."""
import unittest
from .gate_scalar import GateScalar,SOFTPLUS_OPERATION
from .scalar import OPERATION
from ..qwen35_gdn_prefill.prep.scalar import PrepScalar,SOFT_COEFFICIENTS
from ..qwen35_gdn_prefill.rms_owner import word,ArithmeticFault

class GateScalarTests(unittest.TestCase):
 def scalar(self,**kw):
  s=GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True,**kw);c=object();s.client=c;return s,c
 def test_old_opcode_default_and_disable_remain(self):
  a,c=self.scalar();b=PrepScalar(enable_softplus=True);b.client=c
  for x in (-79.,-4.25,-0.,0.,1.,20.,20.5):self.assertEqual(a.op(c,'softplus',word(x)),b.op(c,'softplus',word(x)))
  d=GateScalar();d.client=c
  with self.assertRaises(ArithmeticFault):d.op(c,SOFTPLUS_OPERATION,word(1))
 def test_nested_exp_is_internal_not_second_public_request(self):
  s,c=self.scalar();self.assertEqual(s.op(c,SOFTPLUS_OPERATION,word(-4.25)),0x3c680dd6)
  self.assertEqual(dict(s.calls),{SOFTPLUS_OPERATION:1});self.assertEqual(s.gate_inner_exp_calls,1)
  self.assertEqual(s.decay_internal_calls['integer_rne'],1)
  self.assertEqual(s.soft_internal_calls,{'add':9,'div':1,'mul':10})
  before=dict(s.decay_internal_calls);self.assertEqual(s.op(c,SOFTPLUS_OPERATION,word(20.5)),word(20.5));self.assertEqual(before,dict(s.decay_internal_calls))
 def test_domain_ownership_and_boundary(self):
  s,c=self.scalar()
  for x in (-80.,-81.,float('inf'),float('nan')):
   with self.assertRaises(ArithmeticFault):s.op(c,SOFTPLUS_OPERATION,word(x))
  with self.assertRaises(ValueError):s.op(object(),SOFTPLUS_OPERATION,word(1))
  s.op(c,SOFTPLUS_OPERATION,word(20));self.assertEqual(s.gate_inner_exp_calls,1)
 def test_independent_expanded_tail_matches_compound(self):
  for x in (-79.,-10.,-4.25,-.1,-0.,0.,.1,1.,20.):
   s,c=self.scalar();a=word(x);e=s.op(c,OPERATION,a|0x80000000)
   den=s._soft_node('add',word(2),e);y=s._soft_node('div',e,den);sq=s._soft_node('mul',y,y);h=SOFT_COEFFICIENTS[7]
   for co in reversed(SOFT_COEFFICIENTS[:7]):h=s._soft_node('add',s._soft_node('mul',h,sq),co)
   log=s._soft_node('mul',s._soft_node('mul',word(2),y),h)
   expected=s._soft_node('add',0 if a>>31 else a,log)
   self.assertEqual(s.op(c,SOFTPLUS_OPERATION,a),expected)
if __name__=='__main__':unittest.main()
