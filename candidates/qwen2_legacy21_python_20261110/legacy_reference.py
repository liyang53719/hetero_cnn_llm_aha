"""TEMP independent Python LegacyV0 reference. No C++/libm oracle or BLAS.
Finite arithmetic only; exceptions and resource budgets fail CLOSED.
Arrays carry uint32 FP32 storage words. Fraction arithmetic is intentionally slow.
"""
from fractions import Fraction
from dataclasses import dataclass
import json
import numpy as np
from rational_oracle import round_fraction

class IncompleteReference(RuntimeError): pass
class BudgetExceeded(RuntimeError): pass

@dataclass
class Budget:
    remaining: int = 100000
    def charge(self, n=1):
        if n > self.remaining: raise BudgetExceeded('bounded scalar-operation budget exhausted')
        self.remaining -= n

def fraction(u):
    u=int(u); e=(u>>23)&255; m=u&0x7fffff
    if e==255: raise IncompleteReference('nonfinite IEEE exception contract not implemented')
    power=e-150 if e else -149
    m=m+(1<<23) if e else m
    x=Fraction(m<<power) if power>=0 else Fraction(m,1<<-power)
    return -x if u>>31 else x

def rounded(x, negative_zero=False):
    u=round_fraction(x)
    if not x and negative_zero: u=0x80000000
    if u&0x7f800000==0x7f800000:
        raise IncompleteReference('overflow/status mapping not implemented')
    return u

def add(a,b,budget):
    budget.charge(); x=fraction(a)+fraction(b)
    return rounded(x, int(a)==0x80000000 and int(b)==0x80000000)

def mul(a,b,budget):
    budget.charge();return rounded(fraction(a)*fraction(b), bool((int(a)^int(b))>>31))

def bf16_rne(a):
    a=int(a); fraction(a)  # reject NaN/Inf rather than fabricate canonicalization
    return ((a+0x7fff+((a>>16)&1))>>16)&0xffff

def bf16_fma(a,b,c,budget):
    budget.charge(); a=bf16_rne(a)<<16;b=bf16_rne(b)<<16;c=int(c)
    x=fraction(a)*fraction(b)+fraction(c)
    # RNE exact cancellation +0; both negative zero terms preserve -0.
    negzero=not (a&0x7fffffff and b&0x7fffffff) and bool((a^b)>>31) and c==0x80000000
    return rounded(x,negzero)

def dense(a,w,budget):
    a=np.asarray(a,dtype=np.uint32);w=np.asarray(w,dtype=np.uint32)
    if a.ndim!=2 or w.ndim!=2 or a.shape[1]!=w.shape[0]:raise ValueError('Dense [M,K] @ [K,N] storage')
    m,k=a.shape;n=w.shape[1]
    if m*k*n>budget.remaining:raise BudgetExceeded('Dense rejected before allocation: requires '+str(m*k*n))
    out=np.zeros((m,n),dtype=np.uint32)
    for r in range(m):
        for c in range(n):
            acc=0
            for d in range(k):acc=bf16_fma(a[r,d],w[d,c],acc,budget)
            out[r,c]=acc
    return out

def binary_add(a,b,budget):
    a,b=np.broadcast_arrays(np.asarray(a,dtype=np.uint32),np.asarray(b,dtype=np.uint32))
    out=np.empty(a.shape,dtype=np.uint32)
    for idx in np.ndindex(a.shape):out[idx]=add(a[idx],b[idx],budget)
    return out

def rope(a,cos,sin,budget):
    # Supplied FP32 cos/sin table, NOT a replacement transcendental generator.
    a=np.asarray(a,dtype=np.uint32);cos=np.asarray(cos,dtype=np.uint32);sin=np.asarray(sin,dtype=np.uint32)
    if a.ndim!=3 or a.shape[2]%2 or cos.shape!=sin.shape or cos.shape!=(a.shape[0],a.shape[2]//2):raise ValueError('RoPE [M,heads,HD], tables [M,HD/2]')
    out=np.empty_like(a);half=a.shape[2]//2
    for t in range(a.shape[0]):
        for h in range(a.shape[1]):
            for i in range(half):
                x,y=int(a[t,h,i]),int(a[t,h,i+half]);c,s=int(cos[t,i]),int(sin[t,i])
                out[t,h,i]=add(mul(x,c,budget),mul(y,s,budget)^0x80000000,budget)
                out[t,h,i+half]=add(mul(x,s,budget),mul(y,c,budget),budget)
    return out

# Complete original public 21-command ordering; symbolic buffers, not host-filled intermediates.
SCHEDULE=[
 ('rms0','rms',('x','gamma0'),'norm0'),
 ('q','dense',('norm0','wq'),'q0'),('qb','add',('q0','bq'),'qb'),('qr','rope',('qb','cos','sin'),'q'),
 ('k','dense',('norm0','wk'),'k0'),('kb','add',('k0','bk'),'kb'),('kr','rope',('kb','cos','sin'),'k'),
 ('v','dense',('norm0','wv'),'v0'),('vb','add',('v0','bv'),'v'),('cache','append',('k','v'),'kv'),
 ('qk','qk',('q','k'),'scores'),('sm','softmax',('scores',),'prob'),('pv','pv',('prob','v'),'att'),
 ('out','dense',('att','wo'),'proj'),('res0','add',('x','proj'),'res'),('rms1','rms',('res','gamma1'),'norm1'),
 ('gate','dense',('norm1','wg'),'gate'),('up','dense',('norm1','wu'),'up'),('act','silu',('gate','up'),'act'),
 ('down','dense',('act','wd'),'down'),('res1','add',('res','down'),'y')]
IMPLEMENTED={'dense','add','rope','append','rms','qk','softmax','pv','silu'}

def run(inputs,budget=None,head_dim=128,trace=None):
    import operators as ops
    budget=budget or Budget();buffers=dict(inputs)
    for name,op,args,dst in SCHEDULE:
        values=[buffers[x] for x in args]
        if op=='dense':value=dense(*values,budget)
        elif op=='add':value=binary_add(*values,budget)
        elif op=='rope':
            a,c,s=values
            if a.ndim!=2 or a.shape[1]%head_dim:raise ValueError('flattened RoPE storage')
            value=rope(a.reshape(a.shape[0],-1,head_dim),c,s,budget).reshape(a.shape)
        elif op=='append':value=tuple(x.copy() for x in values)
        elif op in ('qk','pv'):value=getattr(ops,op)(*values,budget,head_dim=head_dim)
        else:value=getattr(ops,op)(*values,budget)
        buffers[dst]=value
        if trace is not None:trace.append((name,value))
    return buffers['y']
