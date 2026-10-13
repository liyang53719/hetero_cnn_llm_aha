"""Fixed-backend exp diagnostics on a grid and retained real Prep boundaries.

This runs one new Scalar compound operation, not a new producer/chunk/block.
Raw inputs/outputs stay in ignored work. No numerical tolerance is assigned.
"""
import argparse,ctypes,json,os,signal,time
from pathlib import Path
import numpy as np
from .scalar import DecayScalar,OPERATION,POLICY,word,value
from ..qwen35_35b_rms import reference as rms
from ..qwen35_35b_prefill.run_prefix import record,checked_record,source_closure
ROOT=Path(__file__).resolve().parents[2]

def compare(a,b):
 a=np.asarray(a,dtype='<u4');b=np.asarray(b,dtype='<u4')
 af=a.view('<f4').astype(np.float64);bf=b.view('<f4').astype(np.float64);e=np.abs(af-bf)
 u=np.abs(a.astype(np.int64)-b.astype(np.int64));levels,counts=np.unique(u,return_counts=True)
 bad=np.flatnonzero(a!=b);maximum=int(np.argmax(u))
 return dict(elements=a.size,bit_mismatches=int(bad.size),max_ulp=int(u.max()),max_abs=float(e.max()),mean_abs=float(e.mean()),
  ulp_histogram={str(int(k)):int(v) for k,v in zip(levels,counts)},first_difference=None if not bad.size else int(bad[0]),
  max_ulp_index=maximum,zero_when_reference_positive=int(np.count_nonzero((a==0)&(b!=0))),
  actual_subnormal=int(np.count_nonzero((a>0)&(a<0x00800000))),reference_subnormal=int(np.count_nonzero((b>0)&(b<0x00800000))),
  thresholds=None,passed=None)

def chunk_inputs(g):
 rows,heads=g.shape;chunks=(rows+63)//64
 values=[];counts={};sequential=np.zeros((1,heads,chunks,64),dtype='<f4')
 def emit(name,x):values.append(x);counts[name]=counts.get(name,0)+1
 for h in range(heads):
  for c in range(chunks):
   running=np.float32(0)
   for i in range(64):
    t=c*64+i;running=np.add(running,g[t,h] if t<rows else np.float32(0),dtype=np.float32);sequential[0,h,c,i]=running
   emit('chunk_decay',running)
   for i in range(64):
    current=sequential[0,h,c,i];emit('cumulative',current)
    emit('remaining',np.add(running,-current,dtype=np.float32))
    for j in range(i+1):emit('pairwise',np.add(current,-sequential[0,h,c,j],dtype=np.float32))
 return np.asarray(values,dtype='<f4'),counts,sequential

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--m16',type=Path,required=True);ap.add_argument('--m128',type=Path,required=True)
 ap.add_argument('--m16-sha256',required=True);ap.add_argument('--m128-sha256',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 assert not a.out.exists() and not a.out.is_symlink() and a.out.resolve().is_relative_to(ROOT/'work')
 import torch
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 torch.set_float32_matmul_precision('highest');assert torch.set_flush_denormal(False)
 runtime=rms.runtime_identity();official=rms.source_identity();assert ctypes.CDLL(None).fegetround()==0
 signal.alarm(180);a.out.mkdir();start=time.monotonic()
 scalar=DecayScalar(enable_ieee_exp=True);client=object();scalar.client=client
 report=dict(scope='NEW_SINGLE_SCALAR_EXP_OPERATOR_DIAGNOSTICS_ON_EXISTING_PREP_OUTPUTS',status='RUNNING',policy=POLICY,
  runtime=runtime,official_source=official,source_sha256=source_closure(),software_scalar_executed=True,
  new_memory_producer_executed=False,new_chunk_executed=False,full_block=False,rtl_executed=False,
  correctly_rounded_exp_claim=False,torch_bitexact_claim=False,numerical_acceptance=None,thresholds=None,
  production_opcode= None,production_opcode5_still_unsupported=True,new_array=False,scalar_units=1,hardware_cycles=None,
  cases=[],cumsum_diagnostics=[])
 def save():
  report['host_seconds']=time.monotonic()-start;(a.out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 def raw_record(name,raw):
  p=a.out/name;p.write_bytes(raw);return record(p)
 def run(name,inputs,context):
  assert inputs.dtype==np.dtype('<f4') and np.isfinite(inputs).all() and (inputs<=0).all()
  words=inputs.reshape(-1).view('<u4');expected=torch.from_numpy(inputs.copy()).exp().numpy().reshape(-1).view('<u4').copy()
  new=np.empty(words.size,dtype='<u4');old=np.empty_like(new);before=dict(scalar.decay_internal_calls)
  for i,x in enumerate(words):
   new[i]=scalar.op(client,OPERATION,int(x));old[i]=scalar.op(client,'exp_negative',int(x))
  result=dict(name=name,context=context,input=raw_record(name+'.input.f32le',inputs.tobytes()),
   actual=raw_record(name+'.candidate.f32le',new.tobytes()),legacy=raw_record(name+'.legacy.f32le',old.tobytes()),
   reference=raw_record(name+'.torch.f32le',expected.tobytes()),candidate=compare(new,expected),old=compare(old,expected),
   actual_scalar_requests=2*words.size,new_compound_requests=words.size,
   internal_calls={k:v-before.get(k,0) for k,v in scalar.decay_internal_calls.items()})
  report['cases'].append(result);save()
 try:
  grid=np.linspace(-104,0,10001,dtype='<f4');run('grid10001',grid,dict(shape=[10001],sampling='inclusive FP32 linspace[-104,0]'))
  for m,p,digest in [(16,a.m16,a.m16_sha256),(128,a.m128,a.m128_sha256)]:
   rr=record(p/'summary.json');assert rr['sha256']==digest;s=json.loads(checked_record(rr))
   assert s['status']=='UPSTREAM_ORIGINAL_GATES_PASS_PREP_DIAGNOSTICS_ONLY' and s['sources_unchanged'] and s['native_artifacts_unchanged']
   for source,h in s['source_sha256'].items():assert rms.sha((ROOT/source).read_bytes())==h
   for item in s['native_artifact_records']:checked_record(item)
   observed=next(x for x in s['observations'] if x['stage']=='prep');raw=checked_record(observed['output'])
   assert s['execution']['terminals'][-1]=={'stage':'prep','status':None}
   core=np.frombuffer(raw,'<f4').reshape(m,12800);g=core[:,12288:].reshape(m,32,16)[...,0].copy()
   run(f'm{m}_individual_g',g,dict(shape=[m,32],producer_summary=rr,producer_output=observed['output'],no_new_producer_execution=True))
   exp_inputs,counts,sequential=chunk_inputs(g)
   run(f'm{m}_chunk_exp_inputs',exp_inputs,dict(counts=counts,cumsum_policy='existing sequential FP32 additions; candidate trajectory, not official cumsum admission',producer_summary=rr))
   decay=torch.from_numpy(g).unsqueeze(0).transpose(1,2).to(torch.float32,memory_format=torch.contiguous_format)
   padded=torch.nn.functional.pad(decay,(0,(-m)%64));chunked=padded.reshape(1,32,-1,64);native=chunked.cumsum(-1).numpy()
   high=np.cumsum(chunked.numpy(),axis=-1,dtype=np.float64).astype('<f4');err=np.abs(native.astype(np.float64)-sequential.astype(np.float64))
   report['cumsum_diagnostics'].append(dict(tokens=m,shape=list(chunked.shape),strides=list(chunked.stride()),
    sequential=raw_record(f'm{m}.sequential_cumsum.f32le',sequential.tobytes()),official=raw_record(f'm{m}.torch_cumsum.f32le',native.tobytes()),
    bit_mismatches=int(np.count_nonzero(native.view('<u4')!=sequential.view('<u4'))),max_abs=float(err.max()),
    fp64_then_fp32_observed_mismatches=int(np.count_nonzero(native.view('<u4')!=high.view('<u4'))),
    inference='sample observation only; no general claim about backend accumulation precision',passed=None))
  report['source_sha256_after']=source_closure();assert report['source_sha256_after']==report['source_sha256']
  report.update(status='DIAGNOSTICS_ONLY_NO_NEW_TOLERANCE',sources_unchanged=True,scalar_requests=dict(scalar.calls),
   decay_internal_calls=dict(scalar.decay_internal_calls),one_scalar_identity_retained=scalar.client is client)
 except BaseException as e:report.update(status='FAILED',error=dict(type=type(e).__name__,message=str(e)));save();raise
 finally:signal.alarm(0)
 save();print(json.dumps(dict(status=report['status'],seconds=report['host_seconds'])))
if __name__=='__main__':main()
