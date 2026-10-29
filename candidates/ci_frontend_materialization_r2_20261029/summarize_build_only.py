"""Build-only evidence extension; preserves frontend status without numeric PASS."""
import argparse,json,pathlib,re
from summarize_frontend import summarize,encode_summary
from frontend_telemetry import typed_metrics
from safe_diagnostics import stage_diagnostics
from build_error_samples import full_build_errors,sample
BUILD=['archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link']
def build_summary(root,commit):
 result=summarize(root,commit);result['schema']='BUILD_ONLY_SUMMARY_V1';result['completed']=False
 for name,p in [('compile_tools',root/'stage_compile_tools/RESULT.json')]+[(n,root/'frontend'/n/'RESULT.json')for n in BUILD]:
  if not p.is_file():continue
  if p.is_symlink()or p.stat().st_size>16*1024**2:raise ValueError('bounded build receipt')
  r=json.loads(p.read_text());row=dict(stage=name,telemetry=typed_metrics(r),diagnostics=stage_diagnostics(r,p.parent/'frontend.log.gz'))
  for key in ('native_exit','elapsed_seconds','observed_peak_rss'):
   x=r.get(key)
   if x is not None and (type(x)not in (int,float) or not -10**15<x<10**15):raise ValueError('bounded numeric build metric')
   row[key]=x
  if r.get('native_exit')not in (None,0):row['build_errors']=full_build_errors(r,p.parent/'frontend.log.gz')
  result['stages'].append(row)
 failure=root/'frontend/BUILD_ADMISSION_FAILURE.json'
 if failure.is_file()and not failure.is_symlink()and failure.stat().st_size<=8192:
  f=json.loads(failure.read_text());entry={}
  entry['phase']=f.get('phase')if f.get('phase')in ('admit_build','prepare','run','pack')else 'UNKNOWN_PHASE'
  entry['exception_class']=f.get('exception_class')if f.get('exception_class')in ('ValueError','OSError','FileNotFoundError','PermissionError','KeyError')else 'UNKNOWN_EXCEPTION'
  error=f.get('sanitized_error',{})
  if isinstance(error,dict):
   h=error.get('raw_message_sha256');n=error.get('raw_message_bytes');message=error.get('message')
   if isinstance(h,str)and re.fullmatch('[0-9a-f]{64}',h):entry['raw_error_sha256']=h
   if type(n)is int and 0<=n<=1024**2:entry['raw_error_bytes']=n
   if isinstance(message,str)and len(message.encode())<=1024:entry['diagnostic']=sample(message.encode(),0)
  result['build_admission_failure']=entry
 p=root/'frontend/BUILD_ONLY_RESULT.json'
 if p.is_file()and not p.is_symlink()and p.stat().st_size<=65536:
  r=json.loads(p.read_text());a=r['artifact'];manifest=a['manifest'];h=manifest['sha256']
  if not re.fullmatch('[0-9a-f]{64}',h)or r['status']!='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS':raise ValueError('build result identity')
  if any(type(a.get(k))is not int or not 0<=a[k]<=4*1024**3 for k in ('files','expanded_bytes'))or type(manifest.get('bytes'))is not int or not 0<=manifest['bytes']<=65536:raise ValueError('artifact bounded scalars')
  result['completed']=True;result['artifact']={'manifest_sha256':h,'manifest_bytes':manifest['bytes'],'files':a['files'],'expanded_bytes':a['expanded_bytes'],'scope':a['scope']}
 return result
def encode_build_summary(result):
 # Never lose termination evidence when optional compiler excerpts fill the cap.
 try:return encode_summary(result)
 except ValueError:
  import copy
  slim=copy.deepcopy(result);slim['build_diagnostics_truncated']=True
  for row in slim.get('stages',[]):
   errors=row.get('build_errors',{})
   if 'samples'in errors:errors['samples']=[];errors['samples_truncated']=True
  return encode_summary(slim)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--work',type=pathlib.Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();raw=encode_build_summary(build_summary(a.work,a.commit))
 if a.output.exists():raise ValueError('fresh summary');
 a.output.write_text(raw);print(raw)
