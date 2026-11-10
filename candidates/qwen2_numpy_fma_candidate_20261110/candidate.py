"""TEMP vectorized BF16-input/FP32-accumulator FMA candidate.
No np.matmul/dot/einsum. Separate FP64 multiplication and addition, one FP32 cast.
Inputs/outputs uint32 words; scalar SFU remains independent exact Python.
"""
import numpy as np

def bf16_words(x):
    x=np.asarray(x,dtype=np.uint32)
    if np.any((x&0x7f800000)==0x7f800000):raise ValueError('finite FP32 inputs required')
    y=(x+np.uint32(0x7fff)+((x>>16)&1))&np.uint32(0xffff0000)
    if np.any((y&0x7f800000)==0x7f800000):raise ValueError('BF16 conversion overflow')
    return y

def fma_bf16_words(a,b,c):
    a,b,c=np.broadcast_arrays(np.asarray(a,dtype=np.uint32),np.asarray(b,dtype=np.uint32),np.asarray(c,dtype=np.uint32))
    if np.any((a&65535)!=0) or np.any((b&65535)!=0):raise ValueError('a/b must already be BF16 lifted')
    if any(np.any((x&0x7f800000)==0x7f800000) for x in (a,b,c)):raise ValueError('finite operands required')
    product=np.multiply(a.view(np.float32).astype(np.float64),b.view(np.float32).astype(np.float64),dtype=np.float64)
    total=np.add(product,c.view(np.float32).astype(np.float64),dtype=np.float64)
    with np.errstate(over='ignore',under='ignore'):
        result=total.astype(np.float32)
    return result.view(np.uint32)

def dense(a,w):
    a=bf16_words(a);w=bf16_words(w)
    if a.ndim!=2 or w.ndim!=2 or a.shape[1]!=w.shape[0]:raise ValueError('[M,K] and [K,N] required')
    # Convert once; retain EXACT increasing K accumulation for each output.
    af=a.view(np.float32).astype(np.float64);wf=w.view(np.float32).astype(np.float64)
    acc=np.zeros((a.shape[0],w.shape[1]),dtype=np.float32)
    for k in range(a.shape[1]):
        product=np.multiply(af[:,k,None],wf[k,None,:],dtype=np.float64)
        total=np.add(product,acc.astype(np.float64),dtype=np.float64)
        with np.errstate(over='ignore',under='ignore'):acc=total.astype(np.float32)
        if not np.all(np.isfinite(acc)):raise ValueError('nonfinite Dense output; no hardware status acceptance')
    return acc.view(np.uint32)
