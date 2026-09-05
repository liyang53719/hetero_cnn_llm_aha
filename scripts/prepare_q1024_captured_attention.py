#!/usr/bin/env python3
"""Verify actual bias/RoPE files and feed captured tensors to attention RTL."""
import json
import re
from pathlib import Path
import numpy as np
from generate_q1024_post_projection_vectors import ROOT,OUT,sha,load,f32
from heteronpu.attention_e2_vectors import blocked_causal_row

def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    files={};count=0
    for kind,columns in [('q',1536),('k',256),('v',256)]:
        for op in (['bias','rope'] if kind!='v' else ['bias']):
            expected=OUT/f'{kind}_{"biased" if op=="bias" else "rope"}_expected.memh'
            actual=OUT/f'{kind}_{op}_actual.memh'
            assert sha(expected)==manifest['output_sha256'][expected.name]
            # Hex case is irrelevant to the actual bit comparison.
            a=load(actual,16);e=load(expected,16)
            assert a.size==1024*columns and np.array_equal(a,e),(kind,op)
            count+=a.size;files[actual.name]=sha(actual)
    logs={}
    for op,projections in [('bias',range(3)),('rope',range(2))]:
        for p in projections:
            path=OUT/f'{op}_p{p}.log';s=path.read_text()
            assert f'QWEN2_{op.upper()}_Q1024_MODEL_PASS projection={p}' in s
            assert not re.search(r'Error-|Fatal:|Error:',s)
            logs[path.name]=sha(path)
    result=dict(status='PASS_FULL1024_BIAS_ROPE_NUMERICAL_COMPOSITION',checked_bf16=count,
                bias_values=2097152,rope_values=1835008,actual_files_sha256=files,logs_sha256=logs,
                reference_manifest_sha256=sha(OUT/'manifest.json'),
                nonclaims=['Raw input is independently golden but proven bit-exact by completed projections, not captured projection DDR',
                           'Actual bias output feeds RoPE through file boundary',
                           'DMA is testbench memory service, not pinned iDMA; not full-model uninterrupted timing'])
    (ROOT/'reports/execution/Q1024_POST_PROJECTION_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    dest=OUT/'attention_vectors';dest.mkdir(exist_ok=True)
    tensors={}
    for kind,heads,op in [('q',12,'rope'),('k',2,'rope'),('v',2,'bias')]:
        bits=load(OUT/f'{kind}_{op}_actual.memh',16).reshape(1024,heads,128).transpose(1,0,2).copy()
        tensors[kind]=f32(bits)
        with (dest/f'{kind}_bf16.memh').open('w') as stream:
            stream.write(''.join(f'{int(v):04x}\n' for v in bits.reshape(-1)))
    expected=np.empty((12,1024,128),np.float32)
    for h in range(12):
        for row in range(1024):expected[h,row],_=blocked_causal_row(tensors['q'],tensors['k'],tensors['v'],h,row)
    assert np.isfinite(expected).all()
    with (dest/'expected_fp32.memh').open('w') as stream:
        stream.write(''.join(f'{int(v):08x}\n' for v in expected.view(np.uint32).reshape(-1)))
    # Direct diagnostic is disabled for this dataset, never compare these zeros.
    for name,n in [('tile_m',16),('tile_l',16),('tile_o',2048)]:
        (dest/f'{name}_fp32.memh').write_text('00000000\n'*n)
    result=dict(status='PASS_CAPTURED_RTL_INPUT_REFERENCE_PREPARATION_ONLY',sequence=1024,
                actual_files_sha256=files,hashes={p.name:sha(p) for p in dest.glob('*.memh')},
                golden='Frozen block128/32-key FP32 reference applied to captured BF16 RTL tensors',
                full_model_pass=False)
    (dest/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'post_projection_checked_bf16':count}))

if __name__=='__main__':main()
