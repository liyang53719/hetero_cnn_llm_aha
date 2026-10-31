"""Only original BUILD_ONLY bootstrap. No runtime, model data or DUT execution."""
import argparse,hashlib,json,math,os,pathlib,platform,shutil,subprocess,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
BUILD_SECONDS=7200
WHOLE_SECONDS=9000
EXPORT_RESERVE_SECONDS=900
TREE=12_081_306_272

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p,cap=1<<20):
 need(p.is_file()and all(not x.is_symlink()for x in(p,*p.parents))and 0<p.stat().st_size<=cap,'bounded regular metadata');return json.loads(p.read_text())
def source_pins(repo):
 path=repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json';doc=read(path,2<<20);seen=set()
 for row in doc['files']:
  rel=P(row['path']);need(not rel.is_absolute()and '..'not in rel.parts and str(rel)not in seen,'unique relative source path');seen.add(str(rel));p=repo/rel
  need(p.is_file()and all(not q.is_symlink()for q in(p,*p.parents))and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'immutable active source closure')
 need(all(str(p.relative_to(repo))in seen for p in D.glob('*.py')),'builder wrapper in active source closure')
 return sha(path)
def run(a):
 repo=a.repo.resolve();work=a.work;identity=read(a.identity);clock=read(a.job_start)
 need(D.is_relative_to(repo)and subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'reviewed checkout')
 subprocess.run(['git','-C',str(repo),'diff','--quiet','HEAD','--'],check=True)
 need(clock['schema']=='SPLIT_BUILD_JOB_START_V1'and clock['job_budget_seconds']==WHOLE_SECONDS and clock['run_id']==identity['run_id']and clock['launch_commit']==identity['launch_commit'],'original first-step clock')
 need(str(identity['run_id'])==os.environ['GITHUB_RUN_ID']and identity['launch_commit']==os.environ['GITHUB_SHA']and os.environ['GITHUB_RUN_ATTEMPT']=='1','actual first run')
 started=clock['started_monotonic'];need(type(started)in(int,float)and math.isfinite(started)and 0<=time.monotonic()-started and time.monotonic()-started+BUILD_SECONDS+EXPORT_RESERVE_SECONDS<=WHOLE_SECONDS,'complete build/export fit remaining envelope')
 need(work.is_absolute()and not work.exists()and all(not p.is_symlink()for p in(work,*work.parents)),'fresh canonical work root')
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','builder interpreter architecture')
 # AVX512 is a cloud P0 runtime gate, not a requirement for compilation.
 memory={x.split(':')[0]:int(x.split()[1])*1024 for x in P('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:')}
 need(memory['MemAvailable']>=13<<30 and shutil.disk_usage(work.parent).free>=TREE+(8<<30),'original build memory/disk admission')
 closure=source_pins(repo);work.mkdir();(work/'shared').mkdir()
 material=repo/'candidates/ci_frontend_materialization_r2_20261029';sys.path.insert(0,str(material));import fresh_host
 fresh=dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k]for k in('run_id','source_commit','launch_commit')});fresh_host.validate_contract(fresh,identity);fresh_host.reject_injection(os.environ)
 contract=work/'fresh-host-contract.json'
 with contract.open('x')as f:json.dump(fresh,f,sort_keys=True);f.write('\n')
 with (work/'BUILD_INVOCATION.json').open('x')as f:json.dump(dict(schema='SPLIT_BUILD_INVOCATION_V1',artifact_identity=identity,source_pins_sha256=closure,job_started_monotonic=started,maximum_build_seconds=BUILD_SECONDS,whole_seconds=WHOLE_SECONDS,numerical_pass=False),f)
 py=str(P('/usr/bin/python3').resolve());bootstrap=repo/'candidates/same_job_execution_20261030/controller/bootstrap_samejob.py'
 args=[py,'-B',str(bootstrap),'--repo',str(repo),'--pipeline',str(repo/'candidates/ci_frontend_pipeline_r2_20261029'),'--work',str(work/'shared/build'),'--shared-owned-root',str(work/'shared'),'--materialization-dir',str(material),'--job-started-monotonic',str(started),'--remaining-tail-reserve-seconds',str(EXPORT_RESERVE_SECONDS),'--maximum-build-seconds',str(BUILD_SECONDS),'--reviewed-repo-sha',identity['source_commit'],'--artifact-identity',str(a.identity),'--fresh-host-contract',str(contract),'--fresh-host-contract-sha256',sha(contract),'--execute-reviewed-once']
 os.execve(py,args,dict(os.environ)) # bootstrap forwards GH_TOKEN only to its original idma acquisition.
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in('repo','work','identity','job-start'):p.add_argument('--'+n,type=P,required=True)
 run(p.parse_args())
