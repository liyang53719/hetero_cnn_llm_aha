"""Deterministic E0 reference for Qwen Gated DeltaNet recurrent decode."""
from __future__ import annotations
from dataclasses import dataclass
import math,struct
from typing import Sequence

def f32(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def sigmoid(x):
    x=f32(x); z=f32(math.exp(-abs(x))); return f32(1/(1+z)) if x>=0 else f32(z/(1+z))
def softplus(x):
    x=f32(x); return x if x>20 else f32(math.exp(x)) if x<-20 else f32(math.log1p(math.exp(x)))
def silu(x):return f32(f32(x)*sigmoid(x))
def dot(a,b):
    if len(a)!=len(b):raise ValueError('dot width')
    acc=0.0
    for x,y in zip(a,b,strict=True):acc=f32(acc+f32(f32(x)*f32(y)))
    return acc
def l2norm(v,eps=1e-6):
    s=0.0
    for x in v:s=f32(s+f32(f32(x)*f32(x)))
    inv=f32(1/math.sqrt(f32(s+eps)));return tuple(f32(f32(x)*inv) for x in v)
def rmsnorm_gated(v,g,w,eps=1e-6):
    if not(len(v)==len(g)==len(w)):raise ValueError('width')
    s=0.0
    for x in v:s=f32(s+f32(f32(x)*f32(x)))
    inv=f32(1/math.sqrt(f32(f32(s/len(v))+eps)))
    return tuple(f32(f32(f32(x)*inv)*f32(wi)*silu(gi)) for x,gi,wi in zip(v,g,w,strict=True))
@dataclass(frozen=True)
class Geometry:
    qk_heads:int;v_heads:int;key_dim:int;value_dim:int
    def __post_init__(self):
        if min(self.qk_heads,self.v_heads,self.key_dim,self.value_dim)<=0 or self.v_heads%self.qk_heads:raise ValueError('geometry')
    @property
    def repeat(self):return self.v_heads//self.qk_heads
    @property
    def state_bytes(self):return self.v_heads*self.key_dim*self.value_dim*4
@dataclass
class State:
    geometry:Geometry;data:list
    @classmethod
    def zeros(cls,g):return cls(g,[[[0.0]*g.value_dim for _ in range(g.key_dim)] for _ in range(g.v_heads)])
    def copy(self):return State(self.geometry,[[list(row) for row in head] for head in self.data])

def step(*,geometry,query,key,value,a,b,z,a_log,dt_bias,norm_weight,state=None,eps=1e-6):
    g=geometry; state=(state or State.zeros(g)).copy()
    if len(query)!=g.qk_heads or len(key)!=g.qk_heads or len(value)!=g.v_heads:raise ValueError('heads')
    qscale=f32(1/math.sqrt(g.key_dim));q=[tuple(f32(v*qscale) for v in l2norm(x,eps)) for x in query];k=[l2norm(x,eps) for x in key];outs=[]
    for vh in range(g.v_heads):
        qh=vh//g.repeat; beta=sigmoid(b[vh]); decay=f32(math.exp(f32(-f32(math.exp(f32(a_log[vh])))*softplus(f32(a[vh]+dt_bias[vh])))))
        m=state.data[vh]
        for i in range(g.key_dim):
            for j in range(g.value_dim):m[i][j]=f32(m[i][j]*decay)
        mem=[]
        for j in range(g.value_dim):
            acc=0.0
            for i in range(g.key_dim):acc=f32(acc+f32(m[i][j]*k[qh][i]))
            mem.append(acc)
        delta=[f32(f32(value[vh][j]-mem[j])*beta) for j in range(g.value_dim)]
        for i in range(g.key_dim):
            for j in range(g.value_dim):m[i][j]=f32(m[i][j]+f32(k[qh][i]*delta[j]))
        raw=[]
        for j in range(g.value_dim):
            acc=0.0
            for i in range(g.key_dim):acc=f32(acc+f32(m[i][j]*q[qh][i]))
            raw.append(acc)
        outs.append(rmsnorm_gated(raw,z[vh],norm_weight,eps))
    return tuple(outs),state
@dataclass
class ConvState:
    channels:int;kernel:int;history:list
    @classmethod
    def zeros(cls,c,k):return cls(c,k,[[0.0]*max(0,k-1) for _ in range(c)])
def causal_conv_step(values,weights,state,activation='silu'):
    out=[];hist=[]
    for c in range(state.channels):
        win=state.history[c]+[f32(values[c])];acc=0.0
        for x,w in zip(win,weights[c],strict=True):acc=f32(acc+f32(x*f32(w)))
        out.append(silu(acc) if activation=='silu' else acc);hist.append(win[1:])
    return tuple(out),ConvState(state.channels,state.kernel,hist)


def _outer_add(matrix, left, right, scale_value=1.0):
    scale_value=f32(scale_value)
    for i,x in enumerate(left):
        sx=f32(f32(x)*scale_value)
        for j,y in enumerate(right):matrix[i][j]=f32(matrix[i][j]+f32(sx*f32(y)))


def delta_rule_recurrent(*,geometry,query,key,value,log_decay,beta,state=None,eps=1e-6):
    """Reference recurrent Gated-Delta core before gated RMSNorm/out projection."""
    g=geometry;tokens=len(query)
    if not(tokens==len(key)==len(value)==len(log_decay)==len(beta)):raise ValueError('sequence length')
    state=(state or State.zeros(g)).copy();outputs=[];qscale=f32(1/math.sqrt(g.key_dim))
    for t in range(tokens):
        q=[tuple(f32(x*qscale) for x in l2norm(head,eps)) for head in query[t]]
        k=[l2norm(head,eps) for head in key[t]];token_out=[]
        for vh in range(g.v_heads):
            qh=vh//g.repeat;decay=f32(math.exp(f32(log_decay[t][vh])));m=state.data[vh]
            for i in range(g.key_dim):
                for j in range(g.value_dim):m[i][j]=f32(m[i][j]*decay)
            mem=[]
            for j in range(g.value_dim):
                acc=0.0
                for i in range(g.key_dim):acc=f32(acc+f32(m[i][j]*k[qh][i]))
                mem.append(acc)
            delta=[f32(f32(value[t][vh][j]-mem[j])*f32(beta[t][vh])) for j in range(g.value_dim)]
            _outer_add(m,k[qh],delta)
            raw=[]
            for j in range(g.value_dim):
                acc=0.0
                for i in range(g.key_dim):acc=f32(acc+f32(m[i][j]*q[qh][i]))
                raw.append(acc)
            token_out.append(tuple(raw))
        outputs.append(tuple(token_out))
    return tuple(outputs),state


def delta_rule_chunk(*,geometry,query,key,value,log_decay,beta,chunk_size=64,state=None,eps=1e-6):
    """Chunked Gated-Delta core matching the official float32 fallback algebra."""
    g=geometry;tokens=len(query)
    if chunk_size<=0:raise ValueError('chunk_size')
    if not(tokens==len(key)==len(value)==len(log_decay)==len(beta)):raise ValueError('sequence length')
    state=(state or State.zeros(g)).copy();outputs=[[None for _ in range(g.v_heads)] for _ in range(tokens)];qscale=f32(1/math.sqrt(g.key_dim))
    qnorm=[[tuple(f32(x*qscale) for x in l2norm(head,eps)) for head in token] for token in query]
    knorm=[[l2norm(head,eps) for head in token] for token in key]
    for vh in range(g.v_heads):
        qh=vh//g.repeat;m=state.data[vh]
        for base in range(0,tokens,chunk_size):
            stop=min(tokens,base+chunk_size);count=stop-base
            q=[qnorm[t][qh] for t in range(base,stop)];k=[knorm[t][qh] for t in range(base,stop)]
            v=[tuple(f32(x) for x in value[t][vh]) for t in range(base,stop)]
            b=[f32(beta[t][vh]) for t in range(base,stop)];gvals=[f32(log_decay[t][vh]) for t in range(base,stop)]
            gcum=[];acc=0.0
            for item in gvals:acc=f32(acc+item);gcum.append(acc)
            decay=[[0.0]*count for _ in range(count)]
            for i in range(count):
                for j in range(i+1):decay[i][j]=f32(math.exp(f32(gcum[i]-gcum[j])))
            tri=[[0.0]*count for _ in range(count)]
            for i in range(count):
                for j in range(i):tri[i][j]=f32(-f32(f32(b[i]*dot(k[i],k[j]))*decay[i][j]))
                row=list(tri[i][:i]);updated=[]
                for col in range(i):
                    val=row[col]
                    for p in range(i):val=f32(val+f32(row[p]*tri[p][col]))
                    updated.append(val)
                tri[i][:i]=updated
            for i in range(count):tri[i][i]=1.0
            vbeta=[[f32(x*b[i]) for x in v[i]] for i in range(count)]
            kbeta=[[f32(x*b[i]) for x in k[i]] for i in range(count)]
            transformed_v=[];k_cum=[]
            for i in range(count):
                vv=[]
                for d in range(g.value_dim):
                    s=0.0
                    for p in range(count):s=f32(s+f32(tri[i][p]*vbeta[p][d]))
                    vv.append(s)
                transformed_v.append(vv)
                kk=[]
                for d in range(g.key_dim):
                    s=0.0
                    for p in range(count):s=f32(s+f32(tri[i][p]*f32(kbeta[p][d]*f32(math.exp(gcum[p])))))
                    kk.append(s)
                k_cum.append(kk)
            vnew=[]
            for i in range(count):
                prime=[]
                for d in range(g.value_dim):
                    s=0.0
                    for p in range(g.key_dim):s=f32(s+f32(k_cum[i][p]*m[p][d]))
                    prime.append(s)
                vnew.append([f32(transformed_v[i][d]-prime[d]) for d in range(g.value_dim)])
            for i in range(count):
                qstate=[];eg=f32(math.exp(gcum[i]))
                for d in range(g.value_dim):
                    s=0.0
                    for p in range(g.key_dim):s=f32(s+f32(f32(q[i][p]*eg)*m[p][d]))
                    qstate.append(s)
                out=[]
                for d in range(g.value_dim):
                    s=qstate[d]
                    for j in range(i+1):s=f32(s+f32(f32(dot(q[i],k[j])*decay[i][j])*vnew[j][d]))
                    out.append(s)
                outputs[base+i][vh]=tuple(out)
            final_decay=f32(math.exp(gcum[-1]))
            for i in range(g.key_dim):
                for j in range(g.value_dim):m[i][j]=f32(m[i][j]*final_decay)
            for i in range(count):
                factor=f32(math.exp(f32(gcum[-1]-gcum[i])))
                _outer_add(m,k[i],vnew[i],factor)
    return tuple(tuple(heads) for heads in outputs),state
