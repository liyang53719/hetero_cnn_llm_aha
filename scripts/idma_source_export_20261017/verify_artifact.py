#!/usr/bin/env python3
"""Final verification shares the source command's original 900-second cutoff.
Publish only an explicit metadata whitelist, never raw process identity proofs.
"""
import argparse,json,os,signal,time
from pathlib import Path
import export_source
TOP_KEYS=('status','scope','eda_executed','preprocessor_requested','hardware_compilation_executed','idma_pin','python_sha256','python_version','bender_sha256','uv_sha256','verilator_sha256','files_verified','manifest_sha256')
STAGE_KEYS=('exit','error','cleanup_complete','cleanup_scope','working_tree_symlinks','peak_sampled_tree_bytes','tree_limit_bytes','tree_limit_kind','file_hard_limit_bytes','stdout_bytes','stderr_bytes')
def projection(receipt,tools,total):
 return {'receipt':{**{k:receipt[k] for k in TOP_KEYS},'stages':[{k:s.get(k) for k in STAGE_KEYS} for s in receipt['stages']],'source_artifact_bytes':total},'tools':{k:{field:v[field] for field in ('sha256','archive_sha256','url')} for k,v in tools.items()}}
def main(root,tools_path):
 root=Path(root);tools_path=Path(tools_path)
 # Bounded read of small private control files before arming the shared deadline.
 def bounded_json(p):
  with p.open('rb') as f:data=f.read(4*1024*1024+1)
  if len(data)>4*1024*1024:raise ValueError('identity metadata oversized')
  return json.loads(data)
 def expired(sig,frame):raise TimeoutError('original source+verify deadline')
 previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,5)
 try:
  receipt=bounded_json(root/'receipt.json');stop=receipt['deadline_monotonic']
  if not isinstance(stop,(int,float)) or not time.monotonic()<stop:raise TimeoutError('original deadline already expired')
  signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic())
  if receipt['status']!='PASS_SOURCE_EXPORT_ONLY':raise ValueError('source export not successful')
  export_source.verify_export(root/'idma_export')
  total=sum(p.stat().st_size for p in (root/'idma_export').rglob('*') if p.is_file())
  if total>128*1024*1024:raise ValueError('source artifact exceeds 128MiB')
  tools=bounded_json(tools_path);safe=json.dumps(projection(receipt,tools,total),indent=2)
  if str(root) in safe or os.environ.get('RUNNER_TEMP','___never___') in safe:raise ValueError('runner path in safe metadata')
  (root/'SAFE_IDENTITY.json').write_text(safe+'\n')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('tools');a=p.parse_args();main(a.root,a.tools)
