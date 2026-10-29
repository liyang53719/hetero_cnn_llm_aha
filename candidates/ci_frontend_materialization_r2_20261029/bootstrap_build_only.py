"""NEW BUILD_ONLY bootstrap to actual archive/link; unpublished and not executed.
Uses concrete audited materializers. No workflow dispatch, cache reuse or rerun.
"""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time,shutil,re
D=pathlib.Path(__file__).resolve().parent
def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser()
 for n in ['repo','pipeline','work']:a.add_argument('--'+n,type=pathlib.Path,required=True)
 a.add_argument('--reviewed-repo-sha',required=True);a.add_argument('--artifact-identity',type=pathlib.Path,required=True);a.add_argument('--execute-reviewed-once',action='store_true');v=a.parse_args()
 R=v.repo.resolve();P=v.pipeline.resolve();W=v.work.resolve()
 identity=json.loads(v.artifact_identity.read_text())
 need(set(identity)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'V2 six-field artifact identity')
 need(type(identity['run_id'])is int and identity['run_id']>0 and re.fullmatch('[A-Za-z0-9_.-]{1,128}',identity['artifact_name']),'bounded run/name')
 need(all(re.fullmatch('[0-9a-f]{40}',identity[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')) and re.fullmatch(r'ci_launch/[A-Za-z0-9_.-]+\.json',identity['launch_manifest_path']),'exact V2 commits and launch path')
 need(identity['source_commit']==v.reviewed_repo_sha and identity['source_commit']!=identity['launch_commit'],'distinct checked-out source and launch')
 need(str(identity['run_id'])==os.environ['GITHUB_RUN_ID'] and identity['launch_commit']==os.environ['GITHUB_SHA'] and os.environ['GITHUB_RUN_ATTEMPT']=='1','actual first build run identity')
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 need(event.get('before')==identity['source_commit'] and event.get('after')==identity['launch_commit'] and event.get('ref')=='refs/heads/main','actual reviewed two-commit push')
 need(v.execute_reviewed_once and not W.exists(),'explicit mode and fresh work root')
 need(subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()==v.reviewed_repo_sha,'reviewed source commit')
 need(P.is_relative_to(R) and D.is_relative_to(R),'published candidate source under reviewed checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True)
 need(os.environ.get('ImageVersion')=='20261026.354.1','explicit new image identity required on roll')
 W.mkdir();sys.path.insert(0,str(P));import supervise_multiroot as supervise
 py=str(pathlib.Path('/usr/bin/python3').resolve());gh=str(pathlib.Path('/usr/bin/gh').resolve());java=pathlib.Path(os.environ['JAVA_HOME_21_X64'])/'bin/java'
 env={k:os.environ[k] for k in ['PATH','HOME','ImageVersion','ImageOS','JAVA_HOME_21_X64'] if k in os.environ};env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',MAKEFLAGS='-j1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 pins={str(p):sha(p) for root in (P,D) for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.json','.scala','.vlt','.tsv')}
 pins.update({py:sha(py),gh:sha(gh),'/usr/bin/dpkg-deb':sha('/usr/bin/dpkg-deb')})
 restore=R/'candidates/fresh_original_top_recovery_20261028/restore_inputs.py';pins[str(restore)]=sha(restore)
 stages=[];started=time.monotonic()
 def stage(name,argv,wall=300,rss=1,token=False):
  need(time.monotonic()-started+wall<1800,'bounded bootstrap shared30min budget')
  need(shutil.disk_usage(W).free>=1_500_000_000,'disk reserve')
  e=dict(env)
  if token:
   need(bool(os.environ.get('GH_TOKEN')),'existing job actions-read token required');e['GH_TOKEN']=os.environ['GH_TOKEN']
  caps=dict(wall_seconds=wall,cleanup_seconds=30,file_bytes=536870912,tree_bytes=12_081_306_272,log_bytes=16_777_216,raw_log_bytes=33_554_432,max_entries=100000,per_process_as_bytes=4*1024**3,per_process_cpu_seconds=wall,rss_bytes=rss*1024**3,cpu_seconds=wall,extra_watch_roots=[str(W),str(R)],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  r=supervise.execute(argv,str(W/('stage_'+name)),str(W/'bootstrap.lock'),caps,e,pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
  stages.append({k:r[k] for k in ['status','native_exit','elapsed_seconds','observed_peak_rss']});(W/'bootstrap_stages.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(r['native_exit']==0 and not r['errors'] and r['cleanup_proof'],'bootstrap failed '+name)
 stage('jdk',[py,'-B',str(D/'inventory_runner_jdk.py'),'--java-home',str(java.parent.parent),'--output',str(W/'jdk.json')])
 stage('jars',[py,'-B',str(R/'candidates/fresh_original_top_recovery_20261028/restore_inputs.py'),'--download-jars'],600)
 stage('verilator',[py,'-B',str(D/'materialize_verilator.py'),'--output',str(W/'verilator'),'--execute-reviewed-acquisition'])
 stage('idma',[py,'-B',str(D/'acquire_idma_artifact.py'),'--gh',gh,'--gh-sha256',sha(gh),'--output',str(W/'idma'),'--execute-reviewed-acquisition'],240,token=True)
 stage('matrix',[py,'-B',str(D/'recover_matrix_portable.py'),'--repo',str(R),'--output',str(W/'matrix')])
 stage('compile_tools',[py,'-B',str(P/'inventory_compile_tools.py'),'--output',str(W/'compile-tools.json')])
 stage('binding',[py,'-B',str(D/'materialize_frontend_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--canonical',str(D/'fixed-canonical-baseline.tsv'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')])
 # This entry owns its own stage-level process groups and aggregate memory budget.
 # Token is intentionally absent. Outer GitHub job timeout bounds all stages.
 binding=W/'FRONTEND_BINDING.json';bound=json.loads(binding.read_text());bound['mode']='BUILD_ONLY';bound['artifact_identity']=identity
 tool_inventory=json.loads((W/'compile-tools.json').read_text());need(tool_inventory['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1' and tool_inventory['qualification']=='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS','installed tool identity scope');bound['compile_tools']=tool_inventory['compile_tools'];bound['compile_tool_pins']=tool_inventory['pins'];bound['compile_aliases']=tool_inventory['aliases'];bound['compile_tool_manifest']=str(W/'compile-tools.json');bound['pins'][str(W/'compile-tools.json')]=sha(W/'compile-tools.json');bound['pins'].update(tool_inventory['pins'])
 bound['job_budget_seconds']=max(1,int(21000-(time.monotonic()-started)));binding.write_text(json.dumps(bound,indent=2)+'\n');binding.with_suffix('.sha256').write_text(sha(binding)+'\n')
 command=[py,'-B',str(P/'one_job_build_only.py'),'--binding',str(W/'FRONTEND_BINDING.json'),'--binding-sha256',sha(W/'FRONTEND_BINDING.json'),'--execute-reviewed-once']
 os.execve(py,command,env)
if __name__=='__main__':main()
