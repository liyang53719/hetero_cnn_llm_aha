#!/usr/bin/env python3
"""Independent C-fenv/actual-RTL review, deterministic finite raw-bit pairs."""
import argparse, ctypes, hashlib, importlib, json, os, pathlib, random, subprocess, sys
p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--verilator',type=pathlib.Path);a=p.parse_args()
root=a.root.resolve();out=pathlib.Path(__file__).resolve().parent
verilator=a.verilator or root/'work/rope_hardware_oracle/bin/verilator'
commands=[]
def run(command,log=None):
 command=list(map(str,command));commands.append(command)
 result=subprocess.run(command,cwd=root,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if log:(out/log).write_text(result.stdout)
 return result.stdout
run(['cc','-O0','-frounding-math','-shared','-fPIC',out/'fenv_reference.c','-lm','-o',out/'fenv_reference.so'],'c_build.log')
lib=ctypes.CDLL(str(out/'fenv_reference.so'));lib.op.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.c_int,ctypes.POINTER(ctypes.c_int)];lib.op.restype=ctypes.c_uint32
def operation(x,y,mul):
 flags=ctypes.c_int();value=lib.op(x,y,mul,ctypes.byref(flags))
 if value&0x7f800000==0x7f800000:raise ValueError('overflow')
 return value,flags.value
def pair(inp):
 e,o,c,s=inp
 ec,f0=operation(e,c,1);os,f1=operation(o,s,1);es,f2=operation(e,s,1);oc,f3=operation(o,c,1)
 er,f4=operation(ec,os^0x80000000,0);orr,f5=operation(es,oc,0)
 return (*inp,er,orr,f0|f1|f2|f3|f4|f5)
rows=[];rng=random.Random(465743);rejected=0
for inp in [(0x800000,0x800000,0x3f7fffff,0),(1,3,0x3f000000,0x3f000000),(0,0,0x3f800000,0),(0x80000000,0x80000000,0x3f800000,0)]:rows.append(pair(inp))
while len(rows)<10000:
 inp=tuple(rng.getrandbits(32) for _ in range(4))
 if any(x&0x7f800000==0x7f800000 for x in inp):continue
 try:rows.append(pair(inp))
 except ValueError:rejected+=1
vectors=out/'rawbits.memh';vectors.write_text(''.join(f'{row[6]:02x}'+''.join(f'{x:08x}' for x in row[5::-1])+'\n' for row in rows))
sys.path.insert(0,str(root/'src'));oracle=importlib.import_module('heteronpu.rope_hardware_oracle')
hist={}
for row in rows:
 if oracle.pair_rne(*row[:4])!=tuple(row[4:]):raise SystemExit('oracle mismatch against independent C fenv')
 hist[row[6]]=hist.get(row[6],0)+1
rtl=root/'work/generated/rope_hardware_oracle/HeteroRoPEHardwarePrimitives.sv'
sources=[rtl,root/'rtl/sfu/fp32_rope_pair.sv',root/'rtl/sfu/fp32_rope_pair_pipe.sv',out/'tb_rawbits.sv']
run([verilator,'--binary','--timing','-Wno-fatal','-j','4','--top-module','rope_review_rawbits','--Mdir',out/'rawobj','-o','tb',*sources],'rawbuild.log')
log=run([out/'rawobj/tb','+VECTORS='+str(vectors)],'rawrun.log')
if 'REVIEW RAWBITS PASS both_wrappers=10000 cycles=130021' not in log:raise SystemExit('missing independent review pass')
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
report={'status':'PASS_INDEPENDENT_FINITE_COMPONENT_REVIEW','scope':'two existing FP32 RoPE pair wrappers only; separate C fenv per-operation expected bits and flags; finite domain excluding intermediate overflow','seed':465743,'directed_pairs':4,'total_pairs_per_wrapper':len(rows),'random_overflow_rejections':rejected,'expected_flags_histogram':hist,'oracle_vs_C_fenv_mismatches':0,'rtl_vs_C_fenv_mismatches':0,'rtl_cycles':130021,'compiler':run(['cc','--version']).splitlines()[0],'verilator':run([verilator,'--version']).strip(),'python':sys.version,'commands':commands,'review_file_sha256':{f.name:sha(f) for f in [out/'run_review.py',out/'fenv_reference.c',out/'tb_rawbits.sv',vectors,out/'rawbuild.log',out/'rawrun.log',out/'c_build.log']},'repo_source_sha256':{str(f.relative_to(root)):sha(f) for f in [*sources[:3],root/'src/heteronpu/rope_hardware_oracle.py']},'cautions':['Not a full Qwen3.5 block test, coefficient generator, partial-RoPE owner/layout test, BF16 cast RTL test, physical timing/resource test, or MAC utilization result.','C fenv flags are an independently exercised x86-64 host reference; this is test evidence, not a formal all-input proof.']}
(out/'review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['status','total_pairs_per_wrapper','expected_flags_histogram','oracle_vs_C_fenv_mismatches','rtl_vs_C_fenv_mismatches','rtl_cycles']},indent=2))
