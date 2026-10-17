"""Actual run admission through real snapshot verification; zero numerical work.

The sole sentinel is the second reduced-entry runtime call: the first belongs
inside real verify_snapshot; the second precedes any output directory, input
load, owner construction or job. No gate or prerequisite verifier is replaced.
"""
import hashlib,json,os,time
from pathlib import Path

def execute(snapshot_path,*,output):
 from ..attention_packed_m128_entry import contract
 from ..dense_block_reduce import check_public_numeric as entry
 sources=contract.snapshot();started=time.monotonic()
 context=dict(profile=contract.PROFILE,attempt=1,pid=os.getpid(),started=started,
  work_deadline=started+2424,outer_deadline=started+2430,
  source_manifest_sha256=hashlib.sha256((json.dumps(sources,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest())
 path=Path(snapshot_path);raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
 original=entry.runtime;calls=[];completed=[]
 class BoundaryReached(Exception):pass
 def runtime(*args,**kwargs):
  calls.append((args,kwargs))
  if len(calls)==2:raise BoundaryReached()
  value=original(*args,**kwargs);completed.append(True);return value
 entry.runtime=runtime
 try:
  try:entry.run(output,path,digest,wall_budget=2400,enable_raw_kv=True,fresh_profile=True,enable_packed=True,run_context=context)
  except BoundaryReached:pass
  else:raise AssertionError('run did not reach exact pre-work boundary')
 finally:entry.runtime=original
 if len(calls)!=2 or completed!=[True] or Path(output).exists():raise AssertionError('probe executed work or missed real snapshot verification')
 if contract.snapshot()!=sources:raise AssertionError('source drift')
 return dict(status='PASS_ACTUAL_RUN_ADMISSION_ONLY',runtime_calls=2,real_snapshot_verified=True,
  numerical_work_started=False,output_directory_created=False,source_count=len(sources),snapshot_sha256=digest)

def negatives(snapshot_path,*,directory):
 """Invoke actual run for each rejected input; never replace admission gates."""
 import copy,shutil
 from ..attention_packed_m128_entry import contract
 from ..dense_block_reduce import check_public_numeric as entry
 directory=Path(directory);directory.mkdir()
 shutil.copytree(Path(snapshot_path).parent/'frozen_sources',directory/'frozen_sources')
 sources=contract.snapshot();started=time.monotonic()
 context=dict(profile=contract.PROFILE,attempt=1,pid=os.getpid(),started=started,
  work_deadline=started+2424,outer_deadline=started+2430,
  source_manifest_sha256=hashlib.sha256((json.dumps(sources,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest())
 snapshot=json.loads(Path(snapshot_path).read_bytes());seen=[]
 def write(path,value):
  raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();path.write_bytes(raw)
  return hashlib.sha256(raw).hexdigest()
 def reject(label,value,expected,**flags):
  path=directory/(label+'.json');digest=write(path,value);out=directory/(label+'_output')
  original=entry.runtime;calls=[]
  def guarded(*a,**k):
   calls.append(True)
   if len(calls)>1:raise AssertionError('rejected input reached post-verification runtime')
   return original(*a,**k)
  entry.runtime=guarded
  options=dict(enable_raw_kv=True,fresh_profile=True,enable_packed=True);options.update(flags)
  try:
   try:entry.run(out,path,digest,wall_budget=2400,run_context=context,**options)
   except (ValueError,FileNotFoundError) as error:
    if expected=='missing_path':
     if not isinstance(error,FileNotFoundError) or str(directory/'absent') not in str(error):raise AssertionError('wrong missing-path cause') from error
    elif expected not in str(error):raise AssertionError('wrong rejection cause: '+label) from error
    seen.append(dict(case=label,error_class=type(error).__name__,reason=expected,runtime_calls=len(calls)))
   else:raise AssertionError('invalid run admitted: '+label)
  finally:entry.runtime=original
  if out.exists():raise AssertionError('rejected input created output')
 for row in (16,True,128.0):
  value=copy.deepcopy(snapshot);value['rows']=row;reject('row_'+str(row),value,'linked packed public21 rows must be exactly 128')
 reject('raw_off',snapshot,'explicit fresh/raw profile',enable_raw_kv=False);reject('raw_integer',snapshot,'explicit fresh/raw profile',enable_raw_kv=1)
 reject('packed_off',snapshot,'explicit packed profile',enable_packed=False);reject('fresh_off',snapshot,'explicit fresh/raw profile',fresh_profile=False)
 value=copy.deepcopy(snapshot);value['fresh_assets']['profile']='qwen2-public-pv16-packed-m16-linked-v1';reject('wrong_profile',value,'M128 snapshot profile')
 manifest=json.loads(Path(snapshot['fresh_assets']['manifest']).read_bytes())
 for label,key in (('missing_m16','m16_prerequisite'),('missing_origin','origin')):
  m=copy.deepcopy(manifest);m[key]=str(directory/'absent')
  if key=='origin':m['origin_manifest']['path']=str(directory/'absent/private/assets/ASSETS.json')
  mp=directory/(label+'_manifest.json');mh=write(mp,m)
  value=copy.deepcopy(snapshot);value['fresh_assets'].update(manifest=str(mp),manifest_sha256=mh)
  reject(label,value,'missing_path')
 value=copy.deepcopy(snapshot);value['independent_reference']['result_sha256']='0'*64
 reject('reference_digest',value,'fresh independent reference/profile drift')
 value=copy.deepcopy(snapshot);value['reference']['inputs']={}
 reject('reference_identity',value,'original input/tool/public identity changed: reference')
 # Drift affects only the new disposable installed tree; restore exact bytes.
 target=contract.ROOT/'candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py';raw=target.read_bytes()
 try:
  target.write_bytes(raw+b'\n# deliberate source drift negative\n')
  reject('source_drift',snapshot,'linked source drift:')
 finally:target.write_bytes(raw)
 if contract.snapshot()!=sources:raise AssertionError('negative probe did not restore source')
 return dict(status='PASS_ACTUAL_RUN_REJECTION_CASES',cases=seen,numerical_work_started=False)
