"""Exact scalar/hash summary whitelist only. Never uploads logs/env/inputs/SV/C++."""
import argparse,json,pathlib,re
from safe_diagnostics import stage_diagnostics
STAGES=['jdk','jars','verilator','idma','matrix','binding']
FRONT=['compile155','original_high','helper_compile','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4']
def summarize(root,commit):
 if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('commit')
 out={'schema':'FRONTEND_ONLY_SUMMARY_V2','source_commit':commit,'scope':'CHISEL_TEST_BACKEND_PREPARATION_NO_NUMERICS_NO_FINAL_RTL_REPLAY','completed':False,'stages':[]}
 for name,p in [(n,root/('stage_'+n)/'RESULT.json') for n in STAGES]+[(n,root/'frontend'/n/'RESULT.json') for n in FRONT]:
  if not p.is_file():continue
  if p.is_symlink() or p.stat().st_size>1_000_000:raise ValueError('receipt bound')
  r=json.loads(p.read_text());row={'stage':name}
  for k in ['native_exit','elapsed_seconds','observed_peak_rss']:
   x=r.get(k)
   if x is not None and (type(x) not in (int,float) or abs(x)>10**15):raise ValueError('scalar receipt type')
   row[k]=x
  row['diagnostics']=stage_diagnostics(r,p.parent/'frontend.log.gz')
  row['error_count']=len(r.get('errors',[]));row['cleanup_recorded']=bool(r.get('cleanup_proof'));out['stages'].append(row)
 p=root/'jdk.json'
 if p.is_file() and not p.is_symlink() and p.stat().st_size<=1_000_000:
  j=json.loads(p.read_text())
  if j.get('status')=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION':
   public=[]
   for row in j.get('files',[]):
    e=row.get('external_dependency',{})
    if row.get('path')=='lib/security/cacerts' and e.get('resolved_target')=='/etc/ssl/certs/java/cacerts' and type(e.get('bytes')) is int and 0<=e['bytes']<=4*1024**2 and re.fullmatch('[0-9a-f]{64}',e.get('sha256','')):public.append({'alias_relative':row['path'],'resolved_target':e['resolved_target'],'bytes':e['bytes'],'sha256':e['sha256']})
   out['jdk_public_external_dependencies']=public
  codes={'JDK_UNKNOWN_EXTERNAL_ALIAS','JDK_EXTERNAL_TARGET_NOT_BOUNDED_REGULAR','JDK_RELEASE_IDENTITY_MISMATCH','JDK_ARCH_MISMATCH','RUNNER_IMAGE_MISMATCH','JDK_PROBE_LOG_CAP','JDK_RUNTIME_IDENTITY_MISMATCH','JDK_EXTERNAL_SYMLINK','JDK_TREE_BUDGET','JDK_PROBE_TIMEOUT','JDK_PROBE_NONZERO','JDK_FILESYSTEM_ERROR','JDK_UNCLASSIFIED_FAILURE'}
  if j.get('status')=='FAIL_JDK_INVENTORY' and j.get('failure_code') in codes:out['jdk_failure_code']=j['failure_code']
  if j.get('failure_code') in {'JDK_UNKNOWN_EXTERNAL_ALIAS','JDK_EXTERNAL_TARGET_NOT_BOUNDED_REGULAR'}:
   meta=j.get('external_alias_metadata',{})
   if set(meta)<= {'alias_relative','resolved_target','bytes'} and all(isinstance(meta.get(k),str) and len(meta[k])<=1024 and '\n' not in meta[k] for k in ('alias_relative','resolved_target')) and (meta.get('bytes') is None or type(meta['bytes']) is int):out['jdk_external_alias_metadata']=meta
 p=root/'frontend/FRONTEND_ONLY_RESULT.json'
 if p.is_file():
  r=json.loads(p.read_text());out['completed']=r['status']=='PASS_FRONTEND_CODEGEN_ONLY_NO_BINARY_NO_NUMERICS'
  for k in ['sv_sha256','source_manifest_sha256','driver_sha256','frontend_receipt_sha256']:
   if not re.fullmatch('[0-9a-f]{64}',r[k]):raise ValueError('hash')
   out[k]=r[k]
 return out
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--work',type=pathlib.Path,required=True);a.add_argument('--commit',required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args();r=summarize(v.work,v.commit);raw=json.dumps(r,indent=2)+'\n'
 if len(raw)>32768 or v.output.exists():raise ValueError('new bounded summary')
 v.output.write_text(raw);print(raw)
