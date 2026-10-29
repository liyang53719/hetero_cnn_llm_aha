"""Exact scalar/hash summary whitelist only. Never uploads logs/env/inputs/SV/C++."""
import argparse,json,pathlib,re
STAGES=['jdk','jars','verilator','idma','matrix','binding']
FRONT=['compile155','original_high','helper_compile','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4']
def summarize(root,commit):
 if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('commit')
 out={'schema':'FRONTEND_ONLY_SUMMARY_V1','source_commit':commit,'scope':'CHISEL_TEST_BACKEND_PREPARATION_NO_NUMERICS_NO_FINAL_RTL_REPLAY','completed':False,'stages':[]}
 for name,p in [(n,root/('stage_'+n)/'RESULT.json') for n in STAGES]+[(n,root/'frontend'/n/'RESULT.json') for n in FRONT]:
  if not p.is_file():continue
  if p.is_symlink() or p.stat().st_size>1_000_000:raise ValueError('receipt bound')
  r=json.loads(p.read_text());row={'stage':name}
  for k in ['native_exit','elapsed_seconds','observed_peak_rss']:
   x=r.get(k)
   if x is not None and (type(x) not in (int,float) or abs(x)>10**15):raise ValueError('scalar receipt type')
   row[k]=x
  row['error_count']=len(r.get('errors',[]));row['cleanup_recorded']=bool(r.get('cleanup_proof'));out['stages'].append(row)
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
