#!/usr/bin/env python3
"""Isolated boundary sensitivity on archived golden; NOT RTL or full-model replay."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rounded(x):
    u=np.asarray(x,dtype=np.float32).view(np.uint32)
    return (((u+np.uint32(0x7fff)+((u>>16)&1))>>16)<<16).view(np.float32)
def main():
    base=ROOT/'work/results/qwen2_q1024_layer0_tail_backend'
    reportpath=ROOT/'reports/execution/qwen2_q1024_layer0_tail_backend_result.json'
    report=json.loads(reportpath.read_text())
    assert report['status']=='PASS_Q1024_LAYER0_TAIL_EXACT_BACKEND'
    def load(name):
        p=base/name;assert sha(p)==report['hashes'][name]
        data=np.fromfile(p,dtype='<f4').reshape(1024,1536);assert np.isfinite(data).all();return data
    o=load('oproj_fp32.bin');r=load('residual1_fp32.bin');d=load('down_fp32.bin');final=load('final_fp32.bin')
    inp=ROOT/'work/results/qwen2_q1024_layer0_tail_inputs'
    assert sha(inp/'manifest.json')==report['provenance']['input_manifest_sha256']
    im=json.loads((inp/'manifest.json').read_text());p=inp/'hidden_bf16.bin';assert sha(p)==im['hashes'][p.name]
    hidden=(np.fromfile(p,dtype='<u2').astype(np.uint32)<<16).view(np.float32).reshape(1024,1536)
    assert np.array_equal((o+hidden).view(np.uint32),r.view(np.uint32))
    assert np.array_equal((d+r).view(np.uint32),final.view(np.uint32))
    cases={
        'oproj_writeback_only':(rounded(o),o),
        'residual1_with_only_oproj_rounded':(rounded(o)+hidden,r),
        'residual1_with_output_also_rounded':(rounded(rounded(o)+hidden),r),
        'down_writeback_only':(rounded(d),d),
        'final_with_only_down_rounded':(rounded(d)+r,final),
        'final_rounding_both_inputs_and_output':(rounded(rounded(d)+rounded(r)),final)
    }
    metrics={}
    for name,(candidate,reference) in cases.items():
        error=np.abs(candidate.astype(np.float64)-reference.astype(np.float64))
        worst=np.unravel_index(np.argmax(error),error.shape)
        metrics[name]=dict(values=error.size,max_absolute_error=float(error.max()),mean_absolute_error=float(error.mean()),
                           values_over_0p002=int(np.count_nonzero(error>0.002)),worst_query_channel=list(map(int,worst)))
    result=dict(status='REFERENCE_BOUNDARY_SENSITIVITY_ONLY',reference_report_sha256=sha(reportpath),cases=metrics,
                threshold=0.002,policy_changed=False,rtl_measured_cycles=None,
                nonclaims=['Archived CPU golden, not current captured-attention tensor','Perturb isolated rounding boundaries while holding other nodes fixed',
                           'No postnorm/MLP propagation replay: final rounding case is not a complete BF16 end-to-end alternative',
                           'Does not approve a dtype policy or close a numerical RTL gate'])
    (ROOT/'reports/execution/Q1024_RESIDUAL_PRECISION_SENSITIVITY.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(metrics,indent=2))
if __name__=='__main__':main()
