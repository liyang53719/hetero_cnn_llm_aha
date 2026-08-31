#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'work/results/l5_q128_rope_gqa/vectors'
def read(name):return np.array([int(x,16) for x in (base/name).read_text().split()],np.uint32).view(np.float32).reshape(128,12,128)
def bf16(x):
 b=np.asarray(x,np.float32).view(np.uint32).copy();b=(b+np.uint32(0x7fff)+((b>>np.uint32(16))&np.uint32(1)))&np.uint32(0xffff0000);return b.view(np.float32)
q,k,v=(read(n) for n in ('q_rope.memh','k_gqa.memh','v_gqa.memh'));expected=np.array([int(x,16) for x in (ROOT/'work/results/l5_q128_mlo/vectors/attention.memh').read_text().split()],np.uint32).view(np.float32).reshape(128,12,128);scale=np.float32(1/np.sqrt(128))
def run(two_term):
 out=np.zeros_like(q)
 for token in range(128):
  for head in range(12):
   gm=np.float32(-np.inf);gl=np.float32(0);go=np.zeros(128,np.float32)
   for start in range(0,token+1,32):
    stop=min(token+1,start+32);scores=(k[start:stop,head]@q[token,head])*scale;m=np.float32(scores.max());weights=np.exp((scores-m).astype(np.float32)).astype(np.float32);hi=bf16(weights);terms=[hi,bf16((weights-hi).astype(np.float32))] if two_term else [hi];length=np.float32(weights.sum());o=sum(((term[:,None]*v[start:stop,head]).sum(0,dtype=np.float32) for term in terms),np.zeros(128,np.float32))
    if gl==0:gm,gl,go=m,length,o
    else:new_m=np.float32(max(gm,m));alpha=np.float32(np.exp(np.float32(gm-new_m)));beta=np.float32(np.exp(np.float32(m-new_m)));gl=np.float32(gl*alpha+length*beta);go=(go*alpha+o*beta).astype(np.float32);gm=new_m
   out[token,head]=go/gl
 error=np.abs(out.astype(np.float64)-expected.astype(np.float64));return {'max_abs':float(error.max()),'mean_abs':float(error.mean()),'relative_l2':float(np.linalg.norm(error.ravel())/np.linalg.norm(expected.astype(np.float64).ravel()))}
single=run(False);hilo=run(True);result={'schema_version':1,'status':'PASS','threshold':0.002,'single_bf16':single,'bf16_hi_plus_residual':hilo,'decision':'USE_BF16_HI_PLUS_RESIDUAL_64_PV_STEPS','single_bf16_pass':single['max_abs']<=0.002,'hilo_pass':hilo['max_abs']<=0.002}
assert not result['single_bf16_pass'] and result['hilo_pass'];out=ROOT/'reports/execution/l5_probability_hilo_result.json';out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
