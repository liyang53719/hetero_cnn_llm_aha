"""Explicit approximate P7 decay policy with FP32 gradual-underflow range.

One caller-owned PrepScalar; old op4/default and production opcode5 stay intact.
This is not correctly-rounded exp, Torch bitexactness, or a Chisel binding.
"""
from collections import Counter
import ctypes
import numpy as np
from ..qwen35_gdn_prefill.prep.scalar import PrepScalar
from ..qwen35_gdn_prefill.conv.scalar import EXP_COEFFICIENTS,LOG2_RECIPROCAL
from ..qwen35_gdn_prefill.rms_owner import ArithmeticFault,finite,value,word,require

OPERATION='exp_negative_ieee_rne'
POLICY='candidate_p7_split_ln2_gradual_underflow_v1'
LN2_HI=0x3f317200
LN2_LO=0x35bfbe8e
MIN_NORMAL=0x00800000

class DecayScalar(PrepScalar):
    def __init__(self,*,enable_softplus=False,enable_ieee_exp=False):
        require(type(enable_ieee_exp) is bool,'explicit decay enable')
        super().__init__(enable_softplus=enable_softplus)
        self.enable_ieee_exp=enable_ieee_exp
        self.decay_internal_calls=Counter()
        if enable_ieee_exp:
            require(ctypes.CDLL(None).fegetround()==0,'decay requires host FE_TONEAREST')
            with np.errstate(all='ignore'):
                half=word(np.multiply(value(MIN_NORMAL),np.float32(.5),dtype=np.float32))
                doubled=word(np.add(value(1),value(1),dtype=np.float32))
            require(half==0x00400000 and doubled==2,'decay requires gradual subnormal input/output')
    def _node(self,op,a,b):
        self.decay_internal_calls[op]+=1
        with np.errstate(all='ignore'):
            fn=np.multiply if op=='mul' else np.add
            out=word(fn(value(a),value(b),dtype=np.float32))
        if not finite(out):raise ArithmeticFault('decay internal invalid/overflow/nonfinite')
        return out
    def op(self,client,operation,a,b=0):
        if operation!=OPERATION:return super().op(client,operation,a,b)
        require(self.client is client,'decay request without Scalar ownership')
        require(all(type(x) is int and 0<=x<1<<32 for x in (a,b)),'decay raw FP32 words')
        self.calls[operation]+=1
        if not self.enable_ieee_exp:raise ArithmeticFault('explicit IEEE decay candidate disabled')
        if not finite(a) or not finite(b) or (not a>>31 and a&0x7fffffff):
            raise ArithmeticFault('decay requires finite nonpositive FP32')
        return self._evaluate_exp(a)
    def _evaluate_exp(self,a):
        """Validated compound-internal evaluator; caller owns the same Scalar."""
        magnitude=a&0x7fffffff
        # exp(-104) is strictly below half of the smallest FP32 subnormal.
        # This bounds integer conversion for arbitrarily negative finite inputs;
        # it does not replace the final RNE near the actual ~103.97208 boundary.
        if magnitude>=0x42d00000:
            self.decay_internal_calls['proven_rne_zero_guard']+=1
            return 0
        z=self._node('mul',magnitude,LOG2_RECIPROCAL)
        self.decay_internal_calls['integer_rne']+=1
        k=int(np.rint(value(z)))
        require(0<=k<=150,'bounded decay exponent')
        kf=word(float(k))
        hi=self._node('mul',kf,LN2_HI)
        reduced=self._node('add',magnitude,hi^0x80000000)
        lo=self._node('mul',kf,LN2_LO)
        reduced=self._node('add',reduced,lo^0x80000000)
        fraction=self._node('mul',reduced,LOG2_RECIPROCAL)
        p=EXP_COEFFICIENTS[7]
        for c in reversed(EXP_COEFFICIENTS[:7]):p=self._node('add',self._node('mul',p,fraction),c)
        if k<=126:return self._node('mul',p,(127-k)<<23)
        # p*2^(126-k) remains normal; only the last multiply may underflow.
        normal=self._node('mul',p,(253-k)<<23)
        return self._node('mul',normal,MIN_NORMAL)
