#!/usr/bin/env python3
"""Post-seal independent typed-recipe raw QKV check; never official raw evidence."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_qkv_model import gates
from candidates.qwen2_live_qkv_model.runner import sha,save,require

WRAPPER='''#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
static void need(bool ok,const char* m){if(!ok)throw std::runtime_error(m);}
static float bf(float x){uint32_t u;std::memcpy(&u,&x,4);if((u&0x7f800000)!=0x7f800000)u=(u+0x7fff+((u>>16)&1))&0xffff0000;std::memcpy(&x,&u,4);return x;}
static float add(float a,float b){return a+b;}
#include "DOT16_PATH"
extern "C" int raw_qkv(const float* activation,const float* weights,float* result,int N){
  try {const int blocks[2]={1024,512};
    for(int m=0;m<16;m++)for(int col=0;col<N;col+=16){
      float sums[16]={};
      reference_qkv_pair_dot16(activation+m*1536,weights,1536,N,col,blocks,2,sums);
      for(int lane=0;lane<16;lane++)result[m*N+col+lane]=sums[lane];
    }return 0;
  } catch(...) {return -1;}
}
'''


def run(actual, data, destination):
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    started=time.monotonic();actual=Path(actual).resolve();DATA=gates.data_path(data);out=Path(destination).absolute()
    require(actual.parent==gates.OUTPUT_ROOT,'actual receipt outside approved numeric work root')
    gates.fresh_output(out,DATA)
    require(not out.exists(),'fresh raw verifier destination');out.mkdir()
    r=json.loads((actual/'RESULT.json').read_text())
    require(r['status']=='PASS_M16_OFFICIAL_OBSERVED_PRODUCERS_PC8_HELD' and
            r['held_boundary']['completed']==8 and not r['finalfence'],'actual run not sealed at required boundary')
    for p,digest in r['source_sha256_before'].items():require(sha(ROOT/p)==digest,'actual source drift '+p)
    dot=ROOT/'candidates/qwen2_resident_matrix/dense_block_reduce/reference/dot16.inc'
    profile=ROOT/'candidates/qwen2_resident_matrix/dense_block_reduce/reference/profile.json'
    require(sha(profile)=='07008af966dbe4d64b10f75c37e4d19e17159e3708543982a70c8ec996f1d5a5','profile identity')
    source=out/'raw_reference.cpp';source.write_text(WRAPPER.replace('DOT16_PATH',str(dot)))
    norm_source=ROOT/'candidates/qwen2_resident_matrix/official_bf16/test_owners.py'
    sources=gates.sources();sources[str(source.relative_to(ROOT))]=sha(source)
    compiler=Path(r['compile']['compiler']['path']);require(sha(compiler)==r['compile']['compiler']['sha256'],'compiler changed')
    binary=out/'raw_reference.so'
    argv=[str(compiler),'-shared','-fPIC','-O2','-std=c++17','-ffp-contract=off','-fno-fast-math',str(source),'-o',str(binary)]
    built=subprocess.run(argv,capture_output=True,text=True,timeout=30)
    (out/'compile.stdout.log').write_text(built.stdout);(out/'compile.stderr.log').write_text(built.stderr)
    report=dict(schema=1,status='STARTED',scope='independent typed-recipe pre-bias raw QKV only',
        actual_result_sha256=sha(actual/'RESULT.json'),official_raw_reference=False,old_pass_inherited=False,
        source_sha256_before=sources,compiler=r['compile']['compiler'],argv=argv,compile_returncode=built.returncode)
    save(out/'RESULT.json',report);require(built.returncode==0,'raw verifier compile failed')
    import numpy as np
    from scripts import qwen2_layer0_model_gate as gate
    from candidates.qwen2_resident_matrix.official_bf16.test_owners import numpy_norm
    validated_inputs,ready,evidence,preflight=gates.validate_inputs(DATA)
    tools={'python':Path(sys.executable).resolve(),'numpy_multiarray':Path(np._core._multiarray_umath.__file__).resolve(),
           'compiler':compiler,'reference_library':binary}
    report['tools_before']={n:dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for n,p in tools.items()}
    report['inputs_before']={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in validated_inputs.items()}
    report['raw_before']=preflight['raw_tensors']
    norm_inputs={n:(DATA/'inputs'/(n+'.bin')).read_bytes() for n in ('x','gamma0')}
    for n,raw in norm_inputs.items():require(hashlib.sha256(raw).hexdigest()==ready['roles'][n]['sha256'],'raw Norm input drift '+n)
    x=np.frombuffer(norm_inputs['x'],dtype='<u4').reshape(16,1536)
    gamma=np.frombuffer(norm_inputs['gamma0'],dtype='<u4')
    # Independent lane-vector expression of fixed RMS, starting only from readonly x/gamma.
    n0=np.asarray([numpy_norm(row,gamma)[0] for row in x],dtype='<u4').view('<f4')
    ref=json.loads((DATA/'reference/REFERENCE.json').read_text())
    n0_raw=(DATA/'reference/n0.f32le').read_bytes();require(hashlib.sha256(n0_raw).hexdigest()==ref['outputs']['n0']['sha256'],'official n0 hash')
    lib=C.CDLL(str(binary));fn=lib.raw_qkv
    fp=C.POINTER(C.c_float);fn.argtypes=[fp,fp,fp,C.c_int];fn.restype=C.c_int
    report.update(library_sha256=sha(binary),n0_reference_sha256=ref['outputs']['n0']['sha256'],comparisons={},
        independent_n0_comparison=gate.compare(n0,np.frombuffer(n0_raw,dtype='<f4').reshape(16,1536)),
        producer_inputs='readonly x/gamma0/wq/wk/wv only; no actual producer output used as an input',
        independence=gates.correspondence()['raw_reference_independence'],input_evidence=evidence)
    require(report['independent_n0_comparison']['bit_exact'],'independent RMS differs from official n0')
    for name,role,width in (('qraw','wq',1536),('kraw','wk',256),('vraw','wv',256)):
        raw=(DATA/'inputs'/(role+'.bin')).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==ready['roles'][role]['sha256'],'weight changed')
        weights=(np.frombuffer(raw,dtype='<u2').astype('<u4')<<16).view('<f4').reshape(1536,width)
        expected=np.empty((16,width),dtype='<f4')
        require(fn(n0.ctypes.data_as(fp),weights.ctypes.data_as(fp),expected.ctypes.data_as(fp),width)==0,'typed direct-dot failure')
        a_raw=(actual/(name+'.f32le')).read_bytes()
        record=next(p for p in r['producers'] if p['name']==name)
        require(hashlib.sha256(a_raw).hexdigest()==record['sha256'],'sealed actual changed')
        measured=np.frombuffer(a_raw,dtype='<f4').reshape(16,width)
        metrics=gate.compare(measured,expected)
        report['comparisons'][name]=dict(metrics=metrics,typed_recipe_bit_exact=metrics['bit_exact'],
            official_raw_numeric_pass=None,input_weight_sha256=ready['roles'][role]['sha256'])
        (out/(name+'.typed_recipe.f32le')).write_bytes(expected.tobytes())
        np.save(out/(name+'.error_f64.npy'),measured.astype('float64')-expected.astype('float64'),allow_pickle=False)
    report['source_sha256_after']={p:sha(ROOT/p) for p in sources}
    require(report['source_sha256_after']==sources,'typed verifier source drift')
    report['tools_after']={n:dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for n,p in tools.items()}
    report['inputs_after']={n:dict(bytes=len(v),sha256=sha(DATA/'inputs'/(n+'.bin'))) for n,v in validated_inputs.items()}
    report['raw_after']=gates.raw_identity(DATA)
    report['evidence_after']={p:sha(ROOT/p) for p in evidence}
    require(report['tools_after']==report['tools_before'] and report['inputs_after']==report['inputs_before'] and
            report['raw_after']==report['raw_before'] and report['evidence_after']==evidence,'typed verifier input/tool drift')
    require(sha(DATA/'reference/n0.f32le')==report['n0_reference_sha256'] and
            sha(actual/'RESULT.json')==report['actual_result_sha256'],'typed verifier reference/actual receipt drift')
    report.update(status='PASS_TYPED_RECIPE_RAW_BIT_EXACT' if all(v['typed_recipe_bit_exact'] for v in report['comparisons'].values()) else 'FAIL_TYPED_RECIPE_RAW',
        host_wall_seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        arithmetic='independent numpy_norm from readonly x/gamma0; unchanged reference_qkv_pair_dot16; input-major BF16 weights; blocks1024+512; adjacent high-before-low; independent FP32 partials and separate add',
        limitation='No official pre-bias raw tensor exists; this is a conditional typed-recipe check, not official raw validation or RTL simulation.')
    save(out/'RESULT.json',report);print(json.dumps({'status':report['status'],'seconds':report['host_wall_seconds']}),flush=True)
    return 0 if report['status']=='PASS_TYPED_RECIPE_RAW_BIT_EXACT' else 1


def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--actual-result',required=True)
    ap.add_argument('--data',required=True);ap.add_argument('--out',required=True);a=ap.parse_args(argv)
    # Never write through a user-supplied destination after admission failed.
    # A newly admitted run retains its intermediate receipt/logs; the caller
    # captures stderr. Existing evidence directories must remain untouched.
    return run(a.actual_result,a.data,a.out)


if __name__=='__main__':raise SystemExit(main())
