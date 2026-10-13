"""Pinned same-input cumsum replay on retained actual Prep outputs.

Not a new producer execution, full chunk, or full block acceptance. The guarded
candidate only uses the existing Vector16; Torch is an independent reference.
"""
import argparse,ctypes,json,signal,time
from pathlib import Path
import numpy as np
from .cumsum import GuardedCumsum,GUARDED_CUMSUM
from .vector import Vector16
from . import model
from ..prep.layout import grouped_source_identity
from ...qwen35_35b_rms import reference as rms
from ...qwen35_35b_prefill.run_prefix import ROOT,record,checked_record,source_closure

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for name in ('m16','m128','out','vector'):ap.add_argument('--'+name,type=Path,required=True)
 for name in ('m16-sha256','m128-sha256'):ap.add_argument('--'+name,required=True)
 a=ap.parse_args();assert not a.out.exists() and not a.out.is_symlink() and a.out.resolve().is_relative_to(ROOT/'work')
 import torch
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 assert torch.set_flush_denormal(False) and ctypes.CDLL(None).fegetround()==0
 runtime=rms.runtime_identity();official=grouped_source_identity(ROOT)
 vector=Vector16(a.vector);client=object();assert vector.acquire(client)
 add=lambda x,y:vector.op(client,'add',[x],[y])[0]
 a.out.mkdir();signal.alarm(120);started=time.monotonic()
 result=dict(status='RUNNING',scope='SAME_INPUT_GUARDED_CUMSUM_COMPONENT_REPLAY',policy=GUARDED_CUMSUM,
  runtime=runtime,official_model_source=official,reference_operation='torch.cumsum(dim=-1)',
  new_producer_executed=False,full_chunk_executed=False,full_block=False,rtl_executed=False,
  numerical_acceptance=None,thresholds=None,hardware_cycles=None,duty=None,hardware_binding=False,
  matrix_mac=0,vector_mul_mac=0,source_sha256=source_closure(),cases=[])
 def save():
  result['seconds']=time.monotonic()-started;(a.out/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 def raw(name,b):
  p=a.out/name;p.write_bytes(b);return record(p)
 try:
  for n,p,digest in [(16,a.m16,a.m16_sha256),(128,a.m128,a.m128_sha256)]:
   receipt=record(p/'summary.json');assert receipt['sha256']==digest;s=json.loads(checked_record(receipt))
   assert s['status']=='UPSTREAM_ORIGINAL_GATES_PASS_PREP_DIAGNOSTICS_ONLY' and s['sources_unchanged'] and s['native_artifacts_unchanged']
   for f,h in s['source_sha256'].items():assert rms.sha((ROOT/f).read_bytes())==h
   for item in s['native_artifact_records']:checked_record(item)
   observation=next(x for x in s['observations'] if x['stage']=='prep');b=checked_record(observation['output'])
   assert s['execution']['terminals'][-1]=={'stage':'prep','status':None}
   g=np.frombuffer(b,'<f4').reshape(n,12800)[:,12288:].reshape(n,32,16)[...,0].copy()
   decay=torch.from_numpy(g).unsqueeze(0).transpose(1,2).to(torch.float32,memory_format=torch.contiguous_format)
   chunked=torch.nn.functional.pad(decay,(0,(-n)%64)).reshape(1,32,-1,64)
   reference=chunked.cumsum(-1).numpy().copy().view('<u4')
   words=chunked.numpy().copy().view('<u4');candidate=np.empty_like(words);before=vector.calls.copy();metadata=[]
   for h in range(32):
    for c in range((n+63)//64):
     accumulator=GuardedCumsum(add)
     for i in range(64):candidate[0,h,c,i]=accumulator.step(int(words[0,h,c,i]))
     metadata.append(dict(head=h,chunk=c,terms=accumulator.count,emin=accumulator.emin,emax=accumulator.emax))
   count=int(words.size);assert vector.calls['add']-before['add']==13*count
   result['cases'].append(dict(tokens=n,shape=list(chunked.shape),strides=list(chunked.stride()),producer_summary=receipt,
    producer_output=observation['output'],input=raw(f'm{n}.input.f32le',words.tobytes()),
    actual=raw(f'm{n}.actual.f32le',candidate.tobytes()),reference=raw(f'm{n}.torch.f32le',reference.tobytes()),
    bit_mismatches=int(np.count_nonzero(candidate!=reference)),accepted_guard_checks=count,
    real_token_terms=n*32,padding_terms=count-n*32,executed_add_issues=13*count,heads_chunks=metadata))
   save()
  vector.release(client);result['source_sha256_after']=source_closure();assert result['source_sha256_after']==result['source_sha256']
  result.update(status='COMPONENT_REPLAY_COMPLETE_NO_WHOLE_CHUNK_ACCEPTANCE',sources_unchanged=True,
    vector_calls=dict(vector.calls),vector_flags=dict(vector.flags),vector_binary=record(a.vector),vector_receipt=record(a.vector.with_suffix('.json')))
 except BaseException as error:
  result.update(status='FAILED',error=repr(error));save();raise
 finally:signal.alarm(0)
 save();print(json.dumps({'status':result['status'],'cases':[{k:x[k] for k in ('tokens','bit_mismatches','executed_add_issues')} for x in result['cases']]}))
if __name__=='__main__':main()
