"""Actual chunk arithmetic methods replay on current guarded cumsum inputs.

One caller-owned Scalar/Vector. Saved Prep inputs are read-only evidence here;
this is neither a new producer nor a complete chunk memory execution.
"""
import argparse,ctypes,json,signal,time
from pathlib import Path
import numpy as np
from . import model as m,exp_policy as ep
from .cumsum import GuardedCumsum,GUARDED_CUMSUM
from .vector import Vector16,IEEE_POLICY
from ...qwen35_35b_exp.gate_scalar import GateScalar
from ...qwen35_35b_exp.probe import compare
from ...qwen35_35b_rms import reference as rms
from ...qwen35_35b_prefill.run_prefix import ROOT,record,checked_record,source_closure

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for k in ('m16','m128','vector','out'):ap.add_argument('--'+k,type=Path,required=True)
 for k in ('m16-sha256','m128-sha256'):ap.add_argument('--'+k,required=True)
 a=ap.parse_args();assert not a.out.exists() and not a.out.is_symlink() and a.out.resolve().is_relative_to(ROOT/'work')
 import torch
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 assert torch.set_flush_denormal(False) and ctypes.CDLL(None).fegetround()==0
 runtime=rms.runtime_identity();scalar=GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True)
 vector=Vector16(a.vector,exception_policy=IEEE_POLICY)
 owner=m.ChunkOwner(scalar,vector,heads=32,layout=m.GROUPED_35B,cumsum_policy=GUARDED_CUMSUM,exp_policy=ep.IEEE_EXP)
 assert scalar.acquire(owner) and vector.acquire(owner)
 a.out.mkdir();signal.alarm(180);start=time.monotonic()
 result=dict(scope='CHUNK_EXP_METHOD_REPLAY_ON_GUARDED_CUMSUM_TRAJECTORY',status='RUNNING',runtime=runtime,
  identity=m.source_identity(IEEE_POLICY,m.GROUPED_35B,GUARDED_CUMSUM,ep.IEEE_EXP),source_sha256=source_closure(),
  new_producer_executed=False,chunk_memory_owner_executed=False,full_chunk_executed=False,full_block=False,rtl_executed=False,
  thresholds=None,numerical_acceptance=None,hardware_cycles=None,duty=None,production_exp_bound=False,
  vector_binary=record(a.vector),vector_receipt=record(a.vector.with_suffix('.json')),cases=[])
 def save():
  result['seconds']=time.monotonic()-start;(a.out/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 def raw(name,x):
  p=a.out/name;p.write_bytes(x);return record(p)
 try:
  for n,p,digest in [(16,a.m16,a.m16_sha256),(128,a.m128,a.m128_sha256)]:
   rr=record(p/'summary.json');assert rr['sha256']==digest;s=json.loads(checked_record(rr))
   assert s['status']=='UPSTREAM_ORIGINAL_GATES_PASS_PREP_DIAGNOSTICS_ONLY' and s['sources_unchanged'] and s['native_artifacts_unchanged']
   for f,h in s['source_sha256'].items():assert rms.sha((ROOT/f).read_bytes())==h
   for r in s['native_artifact_records']:checked_record(r)
   obs=next(x for x in s['observations'] if x['stage']=='prep');b=checked_record(obs['output'])
   assert s['execution']['terminals'][-1]=={'stage':'prep','status':None}
   g=np.frombuffer(b,'<f4').reshape(n,12800)[:,12288:].reshape(n,32,16)[...,0].copy()
   t=torch.from_numpy(g).unsqueeze(0).transpose(1,2).to(torch.float32,memory_format=torch.contiguous_format)
   t=torch.nn.functional.pad(t,(0,(-n)%64)).reshape(1,32,-1,64);native_c=t.cumsum(-1).numpy().copy().view('<u4')
   xs=t.numpy().copy().view('<u4');cum=np.empty_like(xs);inputs=[];new=[];old=[];families={};vb=vector.calls.copy();sb=scalar.calls.copy();ib=scalar.decay_internal_calls.copy()
   def emit(name,x):
    families[name]=families.get(name,0)+1;inputs.append(x);new.append(owner._exp(x));old.append(scalar.op(owner,'exp_negative',x))
   for h in range(32):
    for c in range((n+63)//64):
     acc=GuardedCumsum(owner._cumsum_add)
     for i in range(64):cum[0,h,c,i]=acc.step(int(xs[0,h,c,i]))
     cs=[int(x) for x in cum[0,h,c]];emit('chunk_decay',cs[-1])
     for i in range(64):
      emit('cumulative',cs[i]);emit('remaining',owner._op('add',[cs[-1]],[cs[i]^0x80000000])[0])
      for j in range(i+1):emit('pairwise',owner._op('add',[cs[i]],[cs[j]^0x80000000])[0])
   assert np.array_equal(cum,native_c)
   inp=np.asarray(inputs,'<u4');actual=np.asarray(new,'<u4');legacy=np.asarray(old,'<u4')
   expected=torch.from_numpy(inp.view('<f4').copy()).exp().numpy().view('<u4').copy()
   result['cases'].append(dict(tokens=n,producer_summary=rr,producer_output=obs['output'],shape=list(t.shape),strides=list(t.stride()),
    cumsum=raw(f'm{n}.cumsum.f32le',cum.tobytes()),cumsum_reference=raw(f'm{n}.torch_cumsum.f32le',native_c.tobytes()),cumsum_bit_mismatches=0,
    input=raw(f'm{n}.input.f32le',inp.tobytes()),actual=raw(f'm{n}.actual.f32le',actual.tobytes()),
    legacy=raw(f'm{n}.legacy.f32le',legacy.tobytes()),reference=raw(f'm{n}.torch.f32le',expected.tobytes()),
    candidate=compare(actual,expected),old=compare(legacy,expected),families=families,
    vector_issues=dict(vector.calls-vb),scalar_requests=dict(scalar.calls-sb),decay_internal_calls=dict(scalar.decay_internal_calls-ib)))
   save()
  scalar.release(owner);vector.release(owner);result['source_sha256_after']=source_closure();assert result['source_sha256_after']==result['source_sha256']
  result.update(status='DIAGNOSTICS_COMPLETE_NO_NEW_TOLERANCE',sources_unchanged=True,exp_method_stats=dict(owner.exp_stats),
    vector_issues=dict(vector.calls),scalar_requests=dict(scalar.calls),decay_internal_calls=dict(scalar.decay_internal_calls))
 except BaseException as error:result.update(status='FAILED',error=repr(error));save();raise
 finally:signal.alarm(0)
 save();print(json.dumps({'status':result['status'],'cases':[{'tokens':x['tokens'],'candidate':x['candidate'],'families':x['families']} for x in result['cases']]}))
if __name__=='__main__':main()
