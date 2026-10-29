#!/usr/bin/env python3
"""Select a whole original block; reuse original HTTPS range/header/digest code."""
import argparse,concurrent.futures,importlib.util,json,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
MODELS=['qwen2_1p5b','qwen3_5_0p8b','qwen3_5_0p8b','qwen3_5_35b_a3b','qwen3_5_35b_a3b']
COUNTS=[12,14,11,18,15]
def need(v,s):
 if not v:raise ValueError(s)
def selected_plan(repo,profile):
 need(type(profile)is int and profile in range(5),'profile')
 metadata=repo/'candidates/five_profile_input_recovery_20261028';sys.path.insert(0,str(metadata))
 import reconstruct_plan as rp
 full=rp.verified_plan(metadata) # independently rebuild/check ALL original 70 metadata first
 prefix=('model.layers.' if profile==0 else 'model.language_model.layers.')+str(3 if profile in (2,4) else 0)+'.'
 specs=[s for s in full['specs'] if s['model']==MODELS[profile] and s['name'].startswith(prefix)]
 need(len(specs)==COUNTS[profile] and len({s['name'] for s in specs})==len(specs),'complete selected block inventory')
 if profile in (3,4):
  experts=[s for s in specs if '.experts.' in s['name']]
  need(len(experts)==2 and all(s['shape'][0]==256 for s in experts),'all 256 experts, no selected-expert pruning')
 urls={s['url'] for s in specs};headers=[h for h in full['headers'] if h['url'] in urls]
 need({h['url'] for h in headers}==urls,'all selected shard headers')
 return dict(full,profile=profile,specs=specs,headers=headers,body_cap=sum(s['bytes'] for s in specs)+sum(h['header']['bytes'] for h in headers))
def execute(repo,out,profile):
 plan=selected_plan(repo,profile)
 need(not out.exists(),'fresh output required');need(shutil.disk_usage(out.parent).free>=8*1024**3,'need 8 GiB free')
 p=repo/'candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py'
 spec=importlib.util.spec_from_file_location('original_range_acquirer',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.OUT=out;m.BODY_CAP=plan['body_cap'];m.PREVIOUS=None;out.mkdir();m.write_json(out/'ACQUISITION_PLAN.json',plan)
 try:
  for h in plan['headers']:
   b=m.fetch(h['url'],0,h['header']['bytes']-1,h['file_bytes'],'shard-header');need(m.digest(b)==h['header']['sha256'],'downloaded header SHA mismatch')
   d=out/'headers';d.mkdir(exist_ok=True);(d/(m.digest(b)+'.bin')).write_bytes(b)
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(m.acquire,sorted(plan['specs'],key=lambda s:(s['bytes'],s['name']))))
  m.write_json(out/'SUMMARY.json',dict(status='ACQUIRED_COMPLETE_SELECTED_PROFILE_TENSORS_ONLY',profile=profile,tensors=len(results),tensor_bytes=sum(r['actual_bytes'] for r in results),totals=m.totals,reference_executed=False,dut_executed=False))
 except BaseException as e:
  m.stop.set();m.write_json(out/'FAILURE.json',dict(status='FAIL_ACQUISITION_PRESERVE_PARTIALS_NO_RETRY',error=repr(e),totals=m.totals));raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',type=int,choices=range(5),required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();need(a.execute,'explicit --execute required');execute(a.repo.resolve(),a.output.resolve(),a.profile)
