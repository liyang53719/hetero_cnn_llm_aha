"""Qwen3.8-Flash-Next-only E0 references: QSA, Gated Residual and PLE."""
from __future__ import annotations
from dataclasses import dataclass
import math
from .gated_deltanet import f32,l2norm,sigmoid,silu
MASK=(1<<64)-1;G=0x9E3779B97F4A7C15;M1=0xBF58476D1CE4E5B9;M2=0x94D049BB133111EB
def splitmix(x):
    x=(x+G)&MASK;x=((x^(x>>30))*M1)&MASK;x=((x^(x>>27))*M2)&MASK;return (x^(x>>31))&MASK
def multipliers(vocab,ngram,layer,seed=1234):
    bound=max(1,((1<<63)-1)//vocab//2);base=seed+10007*layer
    return tuple(2*(splitmix((base+G*(i+1))&MASK)%bound)+1 for i in range(ngram))
def ngram_indices(tokens,*,ngram_size,heads_per_ngram,sizes,offsets,mults,sentinel=0):
    out=[]
    for pos in range(len(tokens)):
        row=[]
        for n in range(2,ngram_size+1):
            mix=0
            for sh in range(n):
                tok=sentinel if pos-sh<0 else int(tokens[pos-sh]);term=(tok*mults[sh])&MASK;mix=term if sh==0 else mix^term
            st=(n-2)*heads_per_ngram
            for h in range(st,st+heads_per_ngram):row.append(offsets[h]+mix%sizes[h])
        out.append(tuple(row))
    return tuple(out)
def qsa_select(*,queries,keys,visible,token_budget,compress_ratio):
    complete=len(visible)//compress_ratio;top=token_budget//compress_ratio;scores=[]
    nq=[l2norm(q) for q in queries]
    for b in range(complete):
        ids=visible[b*compress_ratio:(b+1)*compress_ratio];pool=[f32(sum(keys[t][d] for t in ids)/compress_ratio) for d in range(len(keys[0]))];pool=l2norm(pool)
        score=sum(max(0.0,sum(q[d]*pool[d] for d in range(len(pool)))) for q in nq)/math.sqrt(len(pool));scores.append((score,b))
    blocks=[b for _,b in sorted(scores,key=lambda x:(-x[0],x[1]))[:top]];sel=[]
    for b in blocks:sel.extend(visible[b*compress_ratio:(b+1)*compress_ratio])
    sel.extend(visible[complete*compress_ratio:]);return tuple(sel)
def group_rmsnorm(x,branches,hidden,eps=1e-6):
    out=[]
    for b in range(branches):
        c=x[b*hidden:(b+1)*hidden];inv=f32(1/math.sqrt(f32(sum(f32(v*v) for v in c)/hidden+eps)));out.extend(f32(v*inv) for v in c)
    return tuple(out)
def gated_residual(x,read_gates,inject_gates,block,branches,hidden):
    n=group_rmsnorm(x,branches,hidden);mix=[]
    for d in range(hidden):mix.append(f32(sum(n[b*hidden+d]*sigmoid(read_gates[b*hidden+d]) for b in range(branches))/branches))
    y=list(map(f32,x))
    for b in range(branches):
        scale=f32(2*sigmoid(inject_gates[b]/branches))
        for d in range(hidden):y[b*hidden+d]=f32(y[b*hidden+d]+f32(block[d]*scale))
    return tuple(mix),tuple(y)
@dataclass
class DilatedConvState:
    channels:int;kernel:int;dilation:int;history:list
    @classmethod
    def zeros(cls,c,k,d):return cls(c,k,d,[[0.0]*((k-1)*d) for _ in range(c)])
def dilated_conv_step(values,weights,state):
    outs=[];hist=[]
    for c in range(state.channels):
        ext=state.history[c]+[f32(values[c])];last=len(ext)-1;acc=0.0
        for tap,w in enumerate(reversed(weights[c])):acc=f32(acc+f32(ext[last-tap*state.dilation]*w))
        outs.append(silu(acc));hist.append(ext[-((state.kernel-1)*state.dilation):])
    return tuple(outs),DilatedConvState(state.channels,state.kernel,state.dilation,hist)
