"""Independent exact-rational LegacyV0 scalar/attention reference extension.
No host floating arithmetic in runtime operators; constants carry FP32 words.
"""
from fractions import Fraction
import numpy as np
import legacy_reference as core
ONE=0x3f800000
COEFF=(0x3f800000,0xbf317218,0x3e75fdf0,0xbd635847,0x3c1d955b,0xbaaec3ff,0x39218489,0xb77fe5fe)

class NumericalFault(RuntimeError):pass

def checked(exact,word):
    # BlockScalarFloat rejects underflow flag (tininess AFTER rounding AND inexact).
    if (int(word)&0x7f800000)==0 and core.fraction(word)!=exact:
        raise NumericalFault('Legacy scalar underflow/inexact is fatal')
    return word

def add(a,b,budget):
    return checked(core.fraction(a)+core.fraction(b),core.add(a,b,budget))
def mul(a,b,budget):
    return checked(core.fraction(a)*core.fraction(b),core.mul(a,b,budget))
def div(a,b,budget):
    budget.charge();a=int(a);b=int(b)
    if not b&0x7fffffff:raise NumericalFault('division by zero')
    q=core.fraction(a)/core.fraction(b)
    return checked(q,core.rounded(q,bool((a^b)>>31)))
def sqrt(a,budget):
    budget.charge();a=int(a);x=core.fraction(a)
    if x<0:raise NumericalFault('negative sqrt')
    if not x:return a # preserve -0
    # Search positive finite binary32 representations for adjacent bracketing roots.
    lo,hi=0,0x7f7fffff
    while lo<hi:
        mid=(lo+hi+1)//2;f=core.fraction(mid)
        if f*f<=x:lo=mid
        else:hi=mid-1
    if core.fraction(lo)**2==x:return lo
    upper=lo+1;midpoint=(core.fraction(lo)+core.fraction(upper))/2
    cmp=x-midpoint*midpoint
    result=upper if cmp>0 or (cmp==0 and lo&1) else lo
    if result&0x7f800000==0:raise NumericalFault('sqrt underflow/inexact')
    return result

def exp_negative(a,budget):
    a=int(a)&0x7fffffff;core.fraction(a)
    if a>=0x42a00000:return 0 # |a|>=80 original saturation
    # Compound exp nodes in original do not apply normal-op underflow rejection.
    z=core.mul(a,0x3fb8aa3b,budget);k=int(core.fraction(z))
    frac=core.add(z,core.rounded(Fraction(k))^0x80000000,budget)
    h=COEFF[7]
    for i in range(6,-1,-1):h=core.add(core.mul(h,frac,budget),COEFF[i],budget)
    return core.mul(h,(127-k)<<23,budget)

def rms(a,gamma,budget):
    a=np.asarray(a,dtype=np.uint32);gamma=np.asarray(gamma,dtype=np.uint32).reshape(-1)
    if a.ndim!=2 or a.shape[1]!=gamma.size:raise ValueError('RMS geometry')
    out=np.empty_like(a);reciprocal=core.rounded(Fraction(1,a.shape[1]))
    for r in range(a.shape[0]):
        total=0
        for x in a[r]:
            # Vector product then scalar sequential sum, NOT fused sum-of-squares.
            total=add(total,core.mul(x,x,budget),budget)
        mean=mul(total,reciprocal,budget)
        inv=div(ONE,sqrt(add(mean,0x358637bd,budget),budget),budget)
        for c in range(a.shape[1]):
            scaled=core.mul(a[r,c],inv,budget)
            out[r,c]=core.bf16_rne(core.mul(scaled,gamma[c],budget))<<16
    return out

def inverse_sqrt_constant(n):
    # F32.lit(1/math.sqrt(headDim)); used audited powers-of-two HD16/128.
    if n==128:return 0x3db504f3
    if n==16:return 0x3e800000
    raise core.IncompleteReference('unverified elaboration-time headDim constant')

def qk(q,k,budget,head_dim=128):
    q=np.asarray(q,dtype=np.uint32);k=np.asarray(k,dtype=np.uint32)
    if q.ndim!=2 or k.ndim!=2 or q.shape[0]!=k.shape[0] or q.shape[1]%head_dim or k.shape[1]%head_dim:raise ValueError('QK geometry')
    m=q.shape[0];heads=q.shape[1]//head_dim;kvheads=k.shape[1]//head_dim
    if heads%kvheads or head_dim%16:raise ValueError('GQA/16lane geometry')
    out=np.zeros((heads,m,m),dtype=np.uint32)
    for h in range(heads):
        kh=h//(heads//kvheads)
        for t in range(m):
            for key in range(t+1):
                lanes=[0]*16
                for d in range(0,head_dim,16):
                    for l in range(16):lanes[l]=core.bf16_fma(q[t,h*head_dim+d+l],k[key,kh*head_dim+d+l],lanes[l],budget)
                total=0
                for value in lanes:total=add(total,value,budget)
                out[h,t,key]=mul(total,inverse_sqrt_constant(head_dim),budget)
    return out

def softmax(scores,budget):
    scores=np.asarray(scores,dtype=np.uint32);out=np.zeros_like(scores)
    heads,m,n=scores.shape
    if n!=m:raise ValueError('causal square scores')
    for h in range(heads):
        for t in range(m):
            maximum=max(map(int,scores[h,t,:t+1]),key=core.fraction)
            total=0;es=[]
            for key in range(t+1):
                e=exp_negative(add(scores[h,t,key],maximum^0x80000000,budget),budget)
                es.append(e);total=add(total,e,budget)
            inv=div(ONE,total,budget)
            for key,e in enumerate(es):out[h,t,key]=mul(e,inv,budget)
    return out

def pv(prob,v,budget,head_dim=128):
    prob=np.asarray(prob,dtype=np.uint32);v=np.asarray(v,dtype=np.uint32)
    heads,m,n=prob.shape;kvheads=v.shape[1]//head_dim
    if m!=n or v.shape[0]!=m or v.shape[1]%head_dim or heads%kvheads:raise ValueError('PV geometry')
    out=np.empty((m,heads*head_dim),dtype=np.uint32)
    for h in range(heads):
        kh=h//(heads//kvheads)
        for t in range(m):
            for c in range(head_dim):
                acc=0
                for key in range(t+1):acc=core.bf16_fma(prob[h,t,key],v[key,kh*head_dim+c],acc,budget)
                out[t,h*head_dim+c]=acc
    return out

def silu(gate,up,budget):
    gate=np.asarray(gate,dtype=np.uint32);up=np.asarray(up,dtype=np.uint32)
    if gate.shape!=up.shape:raise ValueError('SiLU shape')
    out=np.empty_like(gate)
    for idx in np.ndindex(gate.shape):
        g=int(gate[idx]);e=exp_negative(g,budget)
        inv=div(ONE,add(ONE,e,budget),budget)
        signed=mul(inv,e if g>>31 else ONE,budget)
        value=mul(signed,g,budget)
        out[idx]=mul(value,up[idx],budget)
    return out
