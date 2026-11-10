"""Independent ordered FP32 causal Conv4 + BF16/SiLU boundary reference.
Synthetic inputs only. Not a trained-weight or hardware qualification.
"""
import numpy as np
from original_prep_reference import F,bf16,fp,mul,add,div,exp_negative

def conv4(inputs, weights):
    if inputs.dtype!=np.dtype('<u2') or weights.dtype!=np.dtype('<u2'):raise ValueError('inputs and weights require BF16 uint16 storage')
    if inputs.ndim!=2 or weights.shape!=(inputs.shape[1],4):raise ValueError('inputs [tokens,channels], weights [channels,4] required')
    history=np.zeros((inputs.shape[1],4),dtype='<u2'); out=[]
    for raw in inputs:
        total=np.zeros(inputs.shape[1],dtype='<f4')
        for tap in range(4):
            sample=raw if tap==3 else history[:,tap+1]
            total=add(total,mul(fp(sample),fp(weights[:,tap])))
        convolved=fp(bf16(total))
        if np.any((convolved<0)&(np.abs(convolved)>=80)):raise ValueError('negative exp saturation excluded by owner')
        e=exp_negative(convolved)
        reciprocal=div(F(1),add(F(1),e))
        sign=mul(reciprocal,np.where(convolved<0,e,F(1)))
        out.append(bf16(mul(sign,convolved)))
        history[:,:3]=history[:,1:].copy();history[:,3]=raw
    return np.stack(out),history
