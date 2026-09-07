#!/usr/bin/env python3
"""Recompute the seven second-layer GEMMs from ACTUAL predecessor tensors.

An independent ordered NumPy implementation, not the C++ DUT test oracle.
BF16 products are exact in binary64; round each multiply-add back to FP32.
The checker is limited to this finite, deterministic synthetic-weight recipe.
It neither runs RTL nor writes any input or output used by the DUT.
"""
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from audit_real2_boundary import read_tensor, bf16_rne, require


def weight_matrix(k: int,n: int,salt: int) -> np.ndarray:
    require(k>0 and n>0 and salt>=0,'weight dimensions/salt')
    i=np.arange(k,dtype=np.uint32)[:,None]
    j=np.arange(n,dtype=np.uint32)[None,:]
    u=i*np.uint32(1664525)+j*np.uint32(1013904223)
    u+=np.uint32((salt*2654435761)&0xffffffff)
    u^=u>>np.uint32(13)
    u*=np.uint32(2246822519)
    return ((u%np.uint32(31)).astype(np.int32)-15).astype(np.float32)*np.float32(1.0/256.0)


def dense(a: np.ndarray,w: np.ndarray) -> np.ndarray:
    require(a.ndim==2 and w.ndim==2 and a.shape[1]==w.shape[0] and a.size>0 and w.size>0,'dense geometry')
    aa=bf16_rne(a).astype(np.float64)
    ww=bf16_rne(w).astype(np.float64)
    accum=np.zeros((a.shape[0],w.shape[1]),dtype=np.float32)
    # Same increasing K order, but separate implementation from the C++ oracle.
    with np.errstate(over='raise',invalid='raise'):
        for k in range(w.shape[0]):
            accum=(aa[:,k,None]*ww[k,None,:]+accum.astype(np.float64)).astype(np.float32)
    require(bool(np.isfinite(accum).all()),'nonfinite accumulation')
    return accum


def audit(out: Path) -> dict:
    require((out/'gate.exit').read_text().strip()=='0' and (out/'simulation.exit').read_text().strip()=='0','unfinished DUT run')
    m=json.loads((out/'fixture/manifest.json').read_text())
    require((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'],m['layer_weight_salts'])==(16,2,1536,8960,[0,17]),'fixed real2 recipe required')
    plans=[('n0','wq','qraw',1536,1536,1),('n0','wk','kraw',1536,256,2),
           ('n0','wv','vraw',1536,256,3),('att','wo','o',1536,1536,4),
           ('n1','wg','gate',1536,8960,5),('n1','wu','up',1536,8960,6),
           ('act','wd','down',8960,1536,7)]
    reports=[];total=0
    for source,weight,target,k,n,salt in plans:
        start=time.monotonic()
        raw=read_tensor(out,'l1_'+source+'_actual.f32le',16*k)
        actual=read_tensor(out,'l1_'+target+'_actual.f32le',16*n)
        a=np.frombuffer(raw,dtype='<f4').reshape(16,k)
        w=weight_matrix(k,n,salt+17)
        expected=dense(a,w).astype('<f4').tobytes()
        mismatches=int(np.count_nonzero(np.frombuffer(actual,dtype='<u4')!=np.frombuffer(expected,dtype='<u4')))
        require(mismatches==0,'independent second-layer GEMM mismatch: '+target+' count='+str(mismatches))
        report={'input':source,'weight':weight,'output':target,'shape':[16,n,k],
                'checked_fp32':16*n,'bit_differences':0,'weight_salt':salt+17,
                'actual_input_sha256':hashlib.sha256(raw).hexdigest(),
                'actual_output_sha256':hashlib.sha256(actual).hexdigest(),
                'recomputed_output_sha256':hashlib.sha256(expected).hexdigest(),
                'cpu_check_seconds':round(time.monotonic()-start,4)}
        total+=16*n;reports.append(report);print(json.dumps(report),flush=True)
    return {'status':'PASS_REAL2_ACTUAL_PREDECESSOR_GEMM_RECOMPUTE','operations':reports,
            'checked_fp32':total,'bit_differences':0,'reference_tensor_files_used':False,
            'rtl_rerun':False,'scope':'Seven layer-one GEMMs from actual producer files, deterministic BF16 weights; not official model quality.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        if a.output:require(not a.output.exists(),'never overwrite a prior report')
        result=audit(a.evidence);text=json.dumps(result,indent=2)+'\n'
        if a.output:
            with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,KeyError,TypeError,FloatingPointError) as e:raise SystemExit('REAL2_DENSE_REJECTED: '+str(e))
