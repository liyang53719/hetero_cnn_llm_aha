"""Explicit software-only Softplus with the new inner decay approximation.

Old softplus/opcode7 and all old request dispatches are unchanged. The new
compound has no production opcode binding. The inner exp is an internal
serial phase of this SAME Scalar, not an additional public request/service.
"""
from .scalar import DecayScalar
from ..qwen35_gdn_prefill.prep.scalar import SOFT_COEFFICIENTS
from ..qwen35_gdn_prefill.rms_owner import ArithmeticFault,finite,require,word

SOFTPLUS_OPERATION='softplus_ieee_decay_candidate'

class GateScalar(DecayScalar):
    def __init__(self,*,enable_softplus=False,enable_ieee_exp=False,enable_gate_softplus=False):
        require(type(enable_gate_softplus) is bool,'explicit gate Softplus flag')
        super().__init__(enable_softplus=enable_softplus,enable_ieee_exp=enable_ieee_exp)
        self.enable_gate_softplus=enable_gate_softplus
        self.gate_inner_exp_calls=0
    def op(self,client,operation,a,b=0):
        if operation!=SOFTPLUS_OPERATION:return super().op(client,operation,a,b)
        require(self.client is client,'gate Softplus requires exclusive Scalar ownership')
        require(all(type(v) is int and 0<=v<1<<32 for v in (a,b)),'FP32 raw words')
        self.calls[operation]+=1
        if not (self.enable_softplus and self.enable_ieee_exp and self.enable_gate_softplus) or not finite(a) or not finite(b):
            raise ArithmeticFault('gate Softplus disabled/nonfinite')
        if a>>31 and a&0x7fffffff>=0x42a00000:
            raise ArithmeticFault('Softplus source domain rejects x <= -80')
        if not a>>31 and a>0x41a00000:return a
        self.gate_inner_exp_calls+=1
        exponential=self._evaluate_exp(a|0x80000000)
        denominator=self._soft_node('add',word(2),exponential)
        y=self._soft_node('div',exponential,denominator)
        square=self._soft_node('mul',y,y)
        horner=SOFT_COEFFICIENTS[7]
        for coefficient in reversed(SOFT_COEFFICIENTS[:7]):
            horner=self._soft_node('add',self._soft_node('mul',horner,square),coefficient)
        logarithm=self._soft_node('mul',self._soft_node('mul',word(2),y),horner)
        return self._soft_node('add',0 if a>>31 else a,logarithm)
