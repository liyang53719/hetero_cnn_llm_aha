"""Pinned full-shape router reference and independent C reduction diagnostics.

Saved actual postnorm bytes are reference inputs only, never a new producer.
No numerical acceptance threshold or candidate softmax/topk owner is implied.
"""
import argparse, ast, ctypes as C, hashlib, json, shutil, signal, subprocess, time
from pathlib import Path
from . import payload
from ..qwen35_35b_rms import reference as rms
from ..qwen35_35b_projection_reference.run_reference import FLAGS, record

ROOT=Path(__file__).resolve().parents[2]
CLASS_SHA='b2ac8438aa26449aeafbb7a80b1af9f2b4fa85a6b96aec3229377976c2d73be1'

def require(ok,why):
    if not ok: raise ValueError('35B router reference: '+why)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def definition():
    rms.source_identity()
    config=json.loads((ROOT/rms.CONFIG).read_bytes())['text_config']
    require((config['hidden_size'],config['num_experts'],config['num_experts_per_tok'])==(2048,256,8),'original router geometry')
    raw=(ROOT/rms.SOURCE).read_bytes();tree=ast.parse(raw)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Qwen3_5MoeTopKRouter')
    source=b''.join(raw.splitlines(keepends=True)[cls.lineno-1:cls.end_lineno])
    require(sha(source)==CLASS_SHA,'complete original router class pin')
    return cls

def producer(directory,digest,m):
    p=Path(directory)/'summary.json';raw=p.read_bytes();require(sha(raw)==digest,'producer summary pin')
    s=json.loads(raw);require(s['tokens']==m and s['sources_unchanged'] and s['native_artifacts_unchanged'],'producer identity')
    xs=[x for x in s['observations'] if x['stage']=='post_attention_norm'];require(len(xs)==1,'one actual postnorm output')
    x=xs[0];o=x['owner'];require(o['complete'] and o['output_published'] and o['status'] is None,'actual published postnorm')
    # The pinned receipt may come from another checkout. Only its exact output
    # filename is relocated; bytes and original publication remain authenticated.
    recorded=Path(x['output']['path'])
    require(recorded.name=='post_attention_norm.actual.bf16le','producer output filename')
    path=(Path(directory)/recorded.name).resolve()
    require(path.is_relative_to(Path(directory).resolve()),'producer output directory')
    data=path.read_bytes();require(len(data)==m*2048*2 and sha(data)==x['output']['sha256']==o['output_sha256'],'actual postnorm bytes')
    return data,p,path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m',type=int,choices=(16,128),required=True)
    ap.add_argument('--producer',type=Path,required=True);ap.add_argument('--producer-sha256',required=True)
    ap.add_argument('--payload',type=Path,required=True);ap.add_argument('--manifest-sha256',required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--runtime-root',type=Path)
    args=ap.parse_args()
    out=args.out.resolve();require(not out.exists() and out.is_relative_to(ROOT/'work'),'fresh ignored output');out.mkdir()
    signal.alarm(180)
    import numpy as np
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest');require(torch.set_flush_denormal(False),'gradual underflow')
    runtime=rms.runtime_identity(args.runtime_root);cls=definition();raw,sp,ip=producer(args.producer,args.producer_sha256,args.m)
    _,values=payload.load(args.payload,args.manifest_sha256);weight=values['layers.0.mlp.gate.weight']
    source=Path(__file__).with_name('reference.c');paths=(source,Path(__file__),Path(payload.__file__),ROOT/rms.SOURCE,ROOT/rms.CONFIG)
    frozen={str(p):sha(p.read_bytes()) for p in paths}
    compiler=Path(shutil.which('gcc'));lib=out/'reference.so';command=[str(compiler),*FLAGS,str(source),'-o',str(lib),'-lm']
    subprocess.run(command,check=True,capture_output=True,timeout=30)
    disasm=subprocess.run(['objdump','-d',str(lib)],check=True,capture_output=True,text=True).stdout
    require('fmaf' in disasm,'external fmaf');(out/'disassembly.txt').write_text(disasm)
    ldd=subprocess.run(['ldd',str(lib)],check=True,capture_output=True,text=True).stdout;(out/'ldd.txt').write_text(ldd)
    libm=Path(next(x.split()[2] for x in ldd.splitlines() if 'libm.so' in x));native=C.CDLL(str(lib));native.reference_self_test.restype=C.c_int
    require(native.reference_self_test()==0,'strict FMA/RNE/subnormal/FTZ selftests')
    native.reference_run.argtypes=[C.c_uint,C.c_uint]+[C.c_void_p]*5;native.reference_run.restype=C.c_int
    scope={'nn':torch.nn,'torch':torch,'F':torch.nn.functional};exec(compile(ast.Module(body=[cls],type_ignores=[]),rms.SOURCE,'exec'),scope)
    from types import SimpleNamespace
    with torch.device('meta'): model=scope[cls.name](SimpleNamespace(num_experts_per_tok=8,num_experts=256,hidden_size=2048))
    model.weight=torch.nn.Parameter(torch.frombuffer(bytearray(weight),dtype=torch.bfloat16).reshape(256,2048),requires_grad=False)
    hidden=torch.frombuffer(bytearray(raw),dtype=torch.bfloat16).reshape(1,args.m,2048)
    with torch.inference_mode(),torch.autocast(device_type='cpu',enabled=False): logits,scores,indices=model(hidden)
    require(tuple(logits.shape)==(args.m,256) and logits.dtype==torch.bfloat16,'official full N256 output')
    def save(name,value):
        path=out/name;path.write_bytes(value);return record(path)
    official=logits.contiguous().view(torch.uint16).numpy().tobytes()
    report=dict(scope='OFFICIAL_FULL_ROUTER_REFERENCE_AND_INDEPENDENT_N256_C_DIAGNOSTICS',m=args.m,n=256,k=2048,
        actual_router_owner_executed=False,full_block=False,rtl_executed=False,numerical_acceptance=False,
        input=record(ip),producer_report=record(sp),payload_manifest=record(args.payload/'manifest.json'),
        source_frozen=frozen,runtime=runtime,class_sha256=CLASS_SHA,compiler=record(compiler),compile_argv=command,
        reference_library=record(lib),libm=record(libm),disassembly=record(out/'disassembly.txt'),ldd=record(out/'ldd.txt'),
        official_logits=save('official.logits.bf16le',official),official_scores=save('official.scores.bf16le',scores.contiguous().view(torch.uint16).numpy().tobytes()),
        official_indices=save('official.indices.i64le',indices.contiguous().numpy().astype('<i8').tobytes()),
        route_histogram=torch.bincount(indices.flatten(),minlength=256).tolist(),
        tie_policy='fixed Torch backend observed indices; no stable low-ID assumption',recipes={})
    from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
    a=np.frombuffer(raw,'<u2').copy();w=np.frombuffer(weight,'<u2').copy();start=time.monotonic()
    for mode,name in ((0,'sequential_k2048'),(1,'pair_hi_first_two_k1024')):
        y=np.zeros((args.m,256),'<u2');pre=np.zeros((args.m,256),'<f4');counts=np.zeros(3,'<u8')
        require(native.reference_run(args.m,mode,a.ctypes.data,w.ctypes.data,y.ctypes.data,pre.ctypes.data,counts.ctypes.data)==0,'independent C recipe')
        report['recipes'][name]=dict(diagnostics=compare_finite_bf16(y.tobytes(),official),output=save(name+'.bf16le',y.tobytes()),pre_bf16=save(name+'.fp32le',pre.tobytes()),fma_calls=int(counts[0]),subnormal_intermediates=int(counts[1]),adds=int(counts[2]))
    report['sources_unchanged']=all(sha(Path(p).read_bytes())==h for p,h in frozen.items());require(report['sources_unchanged'],'source drift')
    report.update(status='COMPLETED_REFERENCE_DIAGNOSTICS_ONLY',numeric_seconds=time.monotonic()-start)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');signal.alarm(0)
    print(json.dumps({k:report[k] for k in ('status','m','numeric_seconds')}),flush=True)
if __name__=='__main__':main()
