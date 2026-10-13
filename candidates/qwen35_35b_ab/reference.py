"""Independent original A/B N32 operators and strict C recipes, no owner execution."""
import argparse,ast,ctypes as C,hashlib,json,os,shutil,signal,subprocess,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from . import payload
from ..qwen35_35b_rms import reference as rms
from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
from ..qwen35_35b_projection_reference.run_reference import FLAGS,record
ROOT=Path(__file__).resolve().parents[2]

def require(ok,why):
    if not ok:raise ValueError('35B A/B reference: '+why)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def gate(actual,native):
    result=compare_finite_bf16(actual,native)
    result.update(passed=result['max_abs']<=.03125 and result['mean_abs']<=.005,
        thresholds=dict(max_abs=.03125,mean_abs=.005))
    return result

def operators():
    rms.source_identity()
    raw=(ROOT/rms.SOURCE).read_bytes();tree=ast.parse(raw)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Qwen3_5MoeGatedDeltaNet')
    init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    forward=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='forward')
    result={}
    for name in ('a','b'):
        assignment=next(n for n in init.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='in_proj_'+name for t in n.targets))
        call=next(n for n in forward.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
        require(ast.unparse(assignment)==f'self.in_proj_{name} = nn.Linear(self.hidden_size, self.num_v_heads, bias=False)','exact original constructor')
        require(ast.unparse(call)==f'{name} = self.in_proj_{name}(hidden_states)','exact original operator call')
        result[name]=(assignment,call)
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m',type=int,choices=(16,128),required=True)
    ap.add_argument('--payload',type=Path,required=True);ap.add_argument('--manifest-sha256',required=True)
    ap.add_argument('--rms-output',type=Path,required=True);ap.add_argument('--rms-summary-sha256',required=True)
    ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    out=args.out.resolve();require(not out.exists() and not args.out.is_symlink() and out.is_relative_to(ROOT/'work'),'fresh ignored output')
    out.mkdir();signal.alarm(120)
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest');require(torch.set_flush_denormal(False),'gradual underflow')
    runtime=rms.runtime_identity();ops=operators()
    _,values=payload.load(args.payload,args.manifest_sha256)
    summary_path=args.rms_output/'summary.json';summary_raw=summary_path.read_bytes()
    require(sha(summary_raw)==args.rms_summary_sha256,'independent RMS producer summary pin')
    summary=json.loads(summary_raw);case=next(c for c in summary['cases'] if c['name']==f'actual_embedding_rms_m{args.m}')
    ip=args.rms_output/f'actual_embedding_rms_m{args.m}.actual_output.bin';input_raw=ip.read_bytes()
    require(case['official_output']['bit_mismatches']==0 and case['owner']['output_published'],'actual RMS source accepted')
    require(len(input_raw)==args.m*2048*2 and sha(input_raw)==case['official_output']['actual_sha256'],'actual RMS raw identity')
    source=Path(__file__).with_name('reference.c')
    frozen={str(p):sha(p.read_bytes()) for p in (source,Path(__file__),Path(payload.__file__),ROOT/rms.SOURCE,ROOT/rms.CONFIG)}
    compiler=Path(shutil.which('gcc'));lib=out/'reference.so'
    command=[str(compiler),*FLAGS,str(source),'-o',str(lib),'-lm']
    subprocess.run(command,check=True,capture_output=True,timeout=30)
    disasm=subprocess.run(['objdump','-d',str(lib)],check=True,capture_output=True,text=True).stdout
    require('fmaf' in disasm,'actual external fmaf call evidence')
    (out/'reference.disassembly.txt').write_text(disasm)
    ldd=subprocess.run(['ldd',str(lib)],check=True,capture_output=True,text=True).stdout
    (out/'reference.ldd.txt').write_text(ldd)
    libm=Path(next(x.split()[2] for x in ldd.splitlines() if 'libm.so' in x))
    native=C.CDLL(str(lib));native.reference_self_test.restype=C.c_int
    require(native.reference_self_test()==0,'FMA/RNE/underflow/FTZ selftests')
    native.reference_run.argtypes=[C.c_uint,C.c_uint,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
    native.reference_run.restype=C.c_int
    report=dict(status='RUNNING',scope='OFFICIAL_A_AND_B_SEPARATE_N32_VS_INDEPENDENT_C_ONLY',m=args.m,n=32,k=2048,
        full_block=False,rtl_executed=False,actual_projection_owner_executed=False,
        no_n8192_profile_inheritance=True,input=record(ip),producer_report=record(summary_path),
        manifest=record(args.payload/'manifest.json'),source_frozen=frozen,runtime=runtime,
        compiler=record(compiler),compile_argv=command,reference_library=record(lib),libm=record(libm),
        disassembly=record(out/'reference.disassembly.txt'),ldd=record(out/'reference.ldd.txt'),
        selftest_passed=True,results={})
    started=time.monotonic()
    hidden=torch.frombuffer(bytearray(input_raw),dtype=torch.bfloat16).reshape(1,args.m,2048)
    a=np.frombuffer(input_raw,'<u2').copy()
    for name,(assignment,call) in ops.items():
        weight_raw=values['layers.0.linear_attn.in_proj_'+name+'.weight'];w=np.frombuffer(weight_raw,'<u2').copy().reshape(32,2048)
        obj=SimpleNamespace(hidden_size=2048,num_v_heads=32);scope=dict(self=obj,nn=torch.nn,hidden_states=hidden)
        with torch.device('meta'):exec(compile(ast.Module(body=[assignment],type_ignores=[]),rms.SOURCE,'exec'),scope)
        layer=getattr(obj,'in_proj_'+name);layer.weight=torch.nn.Parameter(torch.from_numpy(w).view(torch.bfloat16),requires_grad=False);layer.eval()
        require(layer.bias is None,'no bias')
        with torch.inference_mode(),torch.autocast(device_type='cpu',enabled=False):
            exec(compile(ast.Module(body=[call],type_ignores=[]),rms.SOURCE,'exec'),scope)
        y=scope[name];require(tuple(y.shape)==(1,args.m,32) and y.dtype==torch.bfloat16,'original fullN32 shape/dtype')
        official=y.contiguous().view(torch.uint16).numpy().tobytes();op=out/(name+'.official.bf16le');op.write_bytes(official)
        result=dict(official=record(op),weight_sha256=sha(weight_raw),operator=[ast.unparse(assignment),ast.unparse(call)],recipes={})
        for mode,label in ((0,'sequential_k2048'),(1,'pair_hi_first_two_k1024')):
            words=np.zeros((args.m,32),'<u2');pre=np.zeros((args.m,32),'<f4');counts=np.zeros(3,'<u8')
            require(native.reference_run(args.m,mode,a.ctypes.data,w.ctypes.data,words.ctypes.data,pre.ctypes.data,counts.ctypes.data)==0,'strict independent C recipe')
            path=out/(name+'.'+label+'.bf16le');path.write_bytes(words.tobytes())
            pp=out/(name+'.'+label+'.fp32le');pp.write_bytes(pre.tobytes())
            result['recipes'][label]=dict(gate(words.tobytes(),official),output=record(path),pre_bf16=record(pp),
                diagnostic_fma_calls=int(counts[0]),subnormal_intermediates=int(counts[1]),diagnostic_adds=int(counts[2]))
        report['results'][name]=result
    report['sources_unchanged']=all(sha(Path(p).read_bytes())==h for p,h in frozen.items())
    require(report['sources_unchanged'],'reference source drift')
    report['numeric_seconds']=time.monotonic()-started
    passed=all(x['recipes']['pair_hi_first_two_k1024']['passed'] for x in report['results'].values())
    report['status']='PASS_NEW_N32_PAIR_ORIGINAL_GATES' if passed else 'FAILED_NEW_N32_PAIR_ORIGINAL_GATES'
    (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    signal.alarm(0);print(json.dumps(dict(status=report['status'],m=args.m,seconds=report['numeric_seconds'])),flush=True)
    require(passed,'N32 pair calibration failed; not admitted to actual path')

if __name__=='__main__':main()
