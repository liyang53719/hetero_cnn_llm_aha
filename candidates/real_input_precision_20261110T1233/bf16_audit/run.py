import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json,hashlib,time,collections,importlib.util
import numpy as np
from convert import reference,rope_source,tensor_source
R=Path(__file__).resolve().parent;ROOT=R.parents[1];old=ROOT/'round_20261110T1133/l3_exact';sys.path.insert(0,str(old))
import run as chain
chain.R=R
counts=collections.Counter();calls=[];phase='matrix_scalar'
def cast(a):
 bits=np.asarray(a,dtype='<f4').view('<u4');unique,inv,mults=np.unique(bits,return_inverse=True,return_counts=True);ys=[];fs=collections.Counter()
 for u,n in zip(unique,mults):
  y,f=reference(u)
  if (y,f)!=rope_source(u) or y!=tensor_source(u):raise ValueError('source/reference mismatch '+hex(int(u)))
  if int(u)&0x7f800000==0x7f800000:raise ValueError('nonfinite actual input')
  ys.append(y);fs[str(f)]+=int(n);counts[phase+'_flag_'+str(f)]+=int(n)
 y=np.array(ys,dtype='<u2')[inv].reshape(bits.shape)
 old_y=((bits.astype('<u8')+32767+((bits>>16)&1))>>16).astype('<u2')
 if not np.array_equal(y,old_y):raise ValueError('saved recipe mismatch')
 calls.append(dict(phase=phase,elements=int(bits.size),input_sha256=hashlib.sha256(bits.tobytes()).hexdigest(),output_sha256=hashlib.sha256(y.tobytes()).hexdigest(),mathematical_flags=dict(fs)))
 return y
chain.bf=cast
t=time.monotonic();result=chain.main()
phase='rope'
tr=chain.data('trig');c=chain.fp(tr[:,None,:32]);s=chain.fp(tr[:,None,32:])
for n in ('q','k'):
 x=chain.arr(n+'n');a=chain.fp(x[...,:32]);b=chain.fp(x[...,32:64]);y=x.copy()
 ac=chain.fp(cast(chain.op(a,c,'mul')));bs=chain.fp(cast(chain.op(b,s,'mul')));ass=chain.fp(cast(chain.op(a,s,'mul')));bc=chain.fp(cast(chain.op(b,c,'mul')))
 y[...,:32]=cast(chain.op(ac,-bs,'add'));y[...,32:64]=cast(chain.op(ass,bc,'add'));chain.same(n+'rope',y,chain.arr(n+'r'))
# Reconstruct four norm pre-conversion results with pinned already-qualified
# separate FP32 arithmetic. This does NOT rerun/reclaim exact arithmetic audit.
phase='norm_conversion'
path=ROOT/'round_20261110T1033/l3_exact/run.py';spec=importlib.util.spec_from_file_location('norm_replay',path);norm=importlib.util.module_from_spec(spec);spec.loader.exec_module(norm);norm.R=R
norm.bf16=cast
norm.audit=lambda a,b,kind: norm.add(a,b) if kind=='add' else norm.mul(a,b)
norm_result=norm.main()
# All stored BF16 inputs including weights widen by exact bit concatenation.
widen=collections.Counter()
for n in chain.m:
 a=chain.data(n);u=a.astype('<u4')<<16
 if not np.array_equal((u>>16).astype('<u2'),a):raise ValueError('widen mismatch')
 widen['words']+=int(a.size);widen['nonfinite']+=int(np.count_nonzero((a&0x7f80)==0x7f80))
out=dict(status='PASS_SOURCE_CONTRACT_REAL_L3_M128_CONVERSION_ONLY',hardware_pass=False,seconds=time.monotonic()-t,calls=calls,flags=dict(counts),widen=dict(widen),saved_output_checks=chain.reports,norm_output_checks=norm.stages,inputs=chain.pins,norm_inputs=norm.hashes,limits=['No Chisel/RTL/Host execution','TensorMath exposes NO conversion flags: computed flags do not become hardware status','PartialRope flags are independently modelled not hardware measured','No L0 qualification','No input quantization from original full precision weights: inputs already BF16','No utilization measurement'])
(R/'RESULT.json').write_text(json.dumps(out,indent=2));print(json.dumps(dict(status=out['status'],seconds=out['seconds'],flags=out['flags'],widen=out['widen'],calls=len(calls)),indent=2))
