"""Exact two-file bounded projection; never uploads raw process/build payloads."""
import argparse,hashlib,importlib.util,json,math,pathlib,re,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
PREP=('jdk','compile_tools','jars','verilator','idma','matrix','fresh_host','binding')
INNER=('compile155','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4','driver_tu_only')
CAP=2*1024**2;SUMMARY_CAP=65536
def need(v,m='bounded frontend metadata contract'):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def unique(pairs):
 d={}
 for k,v in pairs:need(k not in d);d[k]=v
 return d
def read(p,cap):
 need(not any(x.is_symlink() for x in (p,*p.parents)) and p.is_file() and 0<p.stat().st_size<=cap)
 b=p.read_bytes();need(len(b)<=cap);x=json.loads(b,object_pairs_hook=unique);need(type(x)is dict);return x
def safe_number(x):
 return x if type(x)in(int,float) and math.isfinite(x) and 0<=x<=2**53 else None
def stage(path,name):
 if not path.exists():return {'name':name,'observation':'UNAVAILABLE'}
 try:r=read(path,16<<20)
 except (ValueError,OSError):return {'name':name,'observation':'UNAVAILABLE_OR_INVALID'}
 code=r.get('native_exit');need(code is None or type(code)is int and -255<=code<=255)
 errors=r.get('errors');need(type(errors)is list)
 cleanup=r.get('cleanup_proof')or{};log=r.get('log_capture')or{}
 need(type(cleanup)is dict and type(log)is dict)
 good=(code==0 and not errors and cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and log.get('pipe_eof_observed')is True and log.get('gzip_finalized')is True)
 return {'name':name,'observation':'SAVED_RESULT','native_exit':code,'error_count':len(errors),'strict_complete':good,'elapsed_seconds':safe_number(r.get('elapsed_seconds')),'observed_peak_rss':safe_number(r.get('observed_peak_rss')),'cleanup_complete':cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','pipe_eof_observed':log.get('pipe_eof_observed')is True,'gzip_finalized':log.get('gzip_finalized')is True}
def checker(repo):
 path=repo/'candidates/ci_frontend_pipeline_r2_20261029/frontend_observation_metadata.py'
 pins=read(D/'SOURCE_PINS.json',16<<20)['files'];seen=set()
 # Recheck complete source dependency closure independently at export time.
 for row in pins:
  rel=P(row['path']);need(not rel.is_absolute() and '..' not in rel.parts and str(rel)not in seen)
  seen.add(str(rel));p=repo/rel
  need(not any(x.is_symlink()for x in (p,*p.parents)) and p.is_file() and p.stat().st_size==row['bytes'] and sha(p.read_bytes())==row['sha256'],'reviewed export dependency closure')
 need(str(path.relative_to(repo))in seen,'reviewed projector pin')
 sys.path.insert(0,str(path.parent));spec=importlib.util.spec_from_file_location('frontend_observed_projector',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def export(repo,work,identity,clock,out):
 started=time.monotonic();need(clock['schema']=='SAME_JOB_START_V1' and clock['job_budget_seconds']==21000)
 need(clock['run_id']==identity['run_id'] and clock['launch_commit']==identity['launch_commit'])
 need(type(clock['started_monotonic'])in(int,float) and 0<=started-clock['started_monotonic']<21000)
 need(set(identity)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'})
 need(type(identity['run_id'])is int and identity['run_id']>0)
 need(all(type(identity[k])is str and re.fullmatch('[0-9a-f]{40}',identity[k])for k in ('source_commit','launch_commit','launch_manifest_blob_sha')))
 need(identity['source_commit']!=identity['launch_commit'] and identity['artifact_name']=='hetero-observer-frontend-summary-'+str(identity['run_id']))
 need(identity['launch_manifest_path']=='ci_launch/observer_fixed4096_frontend_make_driver_20261030_once.json')
 need(work.is_absolute() and not any(x.is_symlink()for x in (work,*work.parents)))
 need(not out.exists() and not any(x.is_symlink()for x in (out,*out.parents)))
 phases=[stage(work/('stage_'+n)/'RESULT.json',n)for n in PREP]+[stage(work/'frontend'/n/'RESULT.json',n)for n in INNER]
 raw_path=work/'frontend/FRONTEND_QUALIFICATION.json';state='OBSERVATION_UNAVAILABLE';qualification=None
 if raw_path.exists():
  try:
   raw=read(raw_path,CAP-SUMMARY_CAP);qualification=checker(repo).project_qualification(raw,identity)
   need(all(r.get('strict_complete')is True for r in phases),'actual24 strict stage receipts')
   state='FRONTEND_QUALIFICATION_OBSERVED_UNREVIEWED'
  except (ValueError,KeyError,TypeError,OSError):state='METADATA_REJECTED';qualification=None
 elif any(r.get('observation')=='SAVED_RESULT'for r in phases):state='INCOMPLETE_NO_QUALIFICATION_RECEIPT'
 if qualification is None:
  qualification={'schema':'FRONTEND_QUALIFICATION_UNAVAILABLE_V1','status':state,'artifact_identity':identity,'archive_link_executed':False,'numerical_pass':False,'sv_accepted':False}
 summary={'schema':'OBSERVER_FRONTEND_SAFE_SUMMARY_V1','status':state,'scope':'FULL4096_SV_FRONTEND_MAKE_SINGLE_DRIVER_TU_ONLY','artifact_identity':identity,'matrix_macs':4096,'registered_profiles':[0,1,2,3,4],'prefill_tokens':128,'full_block_profiles_completed':0,'final_rtl_replay':False,'numerical_pass':False,'sv_accepted':False,'archive_link_executed':False,'stages':phases,'cpu_capability_observation':qualification.get('cpu_capability_observation',{'avx512f':None,'runtime_qualified':False})}
 qb=(json.dumps(qualification,sort_keys=True,indent=2)+'\n').encode();need(len(qb)<=CAP-SUMMARY_CAP)
 summary['qualification_file']={'name':'frontend-qualification.json','bytes':len(qb),'sha256':sha(qb)}
 sb=(json.dumps(summary,sort_keys=True,indent=2)+'\n').encode();need(len(sb)<=SUMMARY_CAP and len(sb)+len(qb)<=CAP)
 need(time.monotonic()-started<300 and time.monotonic()-clock['started_monotonic']<21000,'bounded export and whole-job deadlines')
 out.mkdir()
 for n,b in [('frontend-summary.json',sb),('frontend-qualification.json',qb)]:
  with (out/n).open('xb')as f:f.write(b)
 return summary
def main():
 a=argparse.ArgumentParser()
 for n in ('repo','work','identity','job-start','output'):a.add_argument('--'+n,type=P,required=True)
 v=a.parse_args();export(v.repo.resolve(),v.work,read(v.identity,SUMMARY_CAP),read(v.job_start,SUMMARY_CAP),v.output)
if __name__=='__main__':main()
