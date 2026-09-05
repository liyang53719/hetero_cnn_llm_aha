#!/usr/bin/env python3
"""Full-token post-projection golden; never reuse rows across RoPE positions."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/results/q1024_post_projection'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path, width):
    return np.asarray([(int(line, 16) >> (width*i)) & ((1 << width)-1)
                       for line in path.read_text().splitlines()
                       for i in range(512//width)], dtype=np.uint32 if width==32 else np.uint16)

def pack(path, values, width=16):
    flat=values.reshape(-1); n=512//width
    with path.open('w') as f:
        for start in range(0, len(flat), n):
            f.write(f'{sum(int(v) << (width*i) for i,v in enumerate(flat[start:start+n])):0128x}\n')

def f32(values):
    return (values.astype(np.uint32)<<16).view(np.float32)

def bf16(values):
    bits=np.asarray(values,dtype=np.float32).view(np.uint32)
    return ((bits+np.uint32(0x7fff)+((bits>>16)&1))>>16).astype(np.uint16)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    fixture=ROOT/'work/results/qwen2_q1024_projection_fixtures'
    manifest=json.loads((ROOT/'reports/execution/Q1024_PROJECTION_FIXTURES_RESULT.json').read_text())
    source={};outputs={};max_error=0.0
    scale=1<<46
    angles=[1_000_000.0**(-2*d/128) for d in range(64)]
    bc=[round(math.cos(a)*scale) for a in angles];bs=[round(math.sin(a)*scale) for a in angles]
    c=[scale]*64;s=[0]*64;cs=[];ss=[]
    def rnd(v): return -(((-v)+(1<<45))>>46) if v<0 else (v+(1<<45))>>46
    for pos in range(1024):
        cs.append([v/scale for v in c]);ss.append([v/scale for v in s])
        c,s=([rnd(c[d]*bc[d]-s[d]*bs[d]) for d in range(64)],
             [rnd(c[d]*bs[d]+s[d]*bc[d]) for d in range(64)])
    cs=np.asarray(cs,np.float32)[:,None,:];ss=np.asarray(ss,np.float32)[:,None,:]
    dc=np.asarray([[math.cos(p*a) for a in angles] for p in range(1024)],np.float32)[:,None,:]
    ds=np.asarray([[math.sin(p*a) for a in angles] for p in range(1024)],np.float32)[:,None,:]
    for kind,columns in [('q',1536),('k',256),('v',256)]:
        rawpath=fixture/f'{kind}_token_major.memh'
        report=ROOT/f'reports/execution/Q1024_CONTINUOUS_{kind.upper()}_RESULT.json'
        evidence=json.loads(report.read_text())
        assert evidence['status']=='PASS_Q1024_SINGLE_PROJECTION_NUMERICAL'
        assert sha(rawpath)==manifest['output'][kind]['sha256']
        assert evidence['counters']['checked_bf16']==1024*columns
        biaspath=ROOT/f'work/results/qwen2_canonical_q_tile16_all/{kind}_bias_fp32.memh'
        raw=load(rawpath,16).reshape(1024,columns)
        bias=load(biaspath,32).view(np.float32);assert bias.size==columns
        biased=bf16(f32(raw)+bias[None,:])
        pack(OUT/f'{kind}_biased_expected.memh',biased)
        source[str(rawpath.relative_to(ROOT))]=sha(rawpath)
        source[str(biaspath.relative_to(ROOT))]=sha(biaspath)
        source[str(report.relative_to(ROOT))]=sha(report)
        if kind!='v':
            x=f32(biased).reshape(1024,columns//128,128);a=x[:,:,:64];b=x[:,:,64:]
            def rotate(co,si):
                return bf16(np.concatenate((a*co-b*si,a*si+b*co),axis=2)).reshape(1024,columns)
            actual=rotate(cs,ss);direct=rotate(dc,ds)
            max_error=max(max_error,float(np.max(np.abs(f32(actual)-f32(direct)))))
            pack(OUT/f'{kind}_rope_expected.memh',actual)
    assert max_error<=0.002,max_error
    pack(OUT/'positions.memh',np.arange(1024,dtype=np.uint32),32)
    for p in sorted(OUT.glob('*expected.memh')):outputs[p.name]=sha(p)
    result=dict(status='PASS_REFERENCE_ONLY',rows=1024,source_sha256=source,output_sha256=outputs,
                recurrence_direct_max_error=max_error,
                boundary='Inputs are golden tensors proven bit-exact by completed full projection RTL; not captured final DDR; post-projection numerical composition, not uninterrupted model timing')
    (OUT/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'rows':1024,'max_error':max_error}))

if __name__=='__main__':main()
