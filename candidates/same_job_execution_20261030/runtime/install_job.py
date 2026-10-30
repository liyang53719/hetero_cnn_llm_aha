"""Three serial real offline installs from already acquired original53 archives.
NEW owning job, unchanged installer functions; no downloads/reference/DUT/upload.
Uses original published strict supervisor. Metadata owner binding is generated
before installs; actual receipt index only after three complete native results.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,platform,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
KEYS=('qwen2','qwen35_08b','qwen35_35b')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def save(p,v):
 with P(p).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def complete(r):return (r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True

def run(b,binding_path,binding_sha):
 need(b['schema']=='FRESH_JOB_RUNTIME_CONTROLLER_V1','fresh controller binding')
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64'and 'avx512f'in P('/proc/cpuinfo').read_text().split(),'original Python3.12/x86_64/P0 AVX512 before installation')
 need(set(b['identity'])=={'run_id','source_commit','launch_commit'},'samejob identity')
 need(str(b['identity']['run_id'])==os.environ.get('GITHUB_RUN_ID')and b['identity']['launch_commit']==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','actual owning first CI job')
 need(type(b['job_started_monotonic'])in(int,float)and 0<=time.monotonic()-b['job_started_monotonic']<21000,'inherited fulljob deadline')
 need(type(b['install_wall_seconds'])is int and type(b['metadata_wall_seconds'])is int and type(b['remaining_job_reservation_seconds'])is int and b['remaining_job_reservation_seconds']>=0 and 0<b['install_wall_seconds']<=1800 and 0<b['metadata_wall_seconds']<=1800,'reviewed phase wall within original cap')
 need(3*(b['install_wall_seconds']+30)+b['metadata_wall_seconds']+30+b['remaining_job_reservation_seconds']<=21000-(time.monotonic()-b['job_started_monotonic']),'reserve all three plus remaining actual job before installation')
 pins=dict(b['pins']);pins[str(binding_path)]=binding_sha
 for p,h in pins.items():need(sha(p)==h,'admitted source/tool/archive drift')
 for p in (D/'install_job.py',D/'runtime_phase.py',D/'owner_fresh.py',D/'bind_phase.py',D/'source/prepare_runtimes.py',P(b['python']),P(b['helper'])):need(pins.get(str(p))==sha(p),'explicit role pin')
 for source_root in (D/'source',P(b['repo'])/'src'):
  need(source_root.is_dir(),'required installer source root')
  for path in source_root.rglob('*'):
   if path.is_file()and path.suffix in ('.py','.json')and '__pycache__'not in path.parts:
    need(not path.is_symlink()and pins.get(str(path))==sha(path),'complete copied installer source closure')
 root=P(b['owner_root']);need(root.is_absolute()and not root.exists()and not any(p.is_symlink()for p in (root,*root.parents)),'new canonical owned root');root.mkdir()
 for n in ('cache','installs','runs','results','environment'): (root/n).mkdir()
 roots=[P(x)for x in b['owned_roots']];need(any(root.is_relative_to(p)for p in roots),'whole owner watched')
 for p in roots:need(p.is_dir()and p==p.resolve(),'canonical existing watched root')
 need(len(b['archives'])==53,'complete unique53 original archives');seen=set()
 spec=importlib.util.spec_from_file_location('original_locked_runtime',D/'source/prepare_runtimes.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 q,specs,_=m.artifacts();expected={x['filename']:(x['bytes'],x['sha256'])for x in q}
 for v in specs.values():
  for x in [*v['artifacts'],v['transformers']]:
   value=(x['bytes'],x['sha256']);need(x['filename']not in expected or expected[x['filename']]==value,'no inconsistent shared archive');expected[x['filename']]=value
 need(len(expected)==53,'locked original union count')
 for row in b['archives']:
  p=P(row['path']);need(p.name not in seen and pins.get(str(p))==row['sha256']and expected[p.name]==(row['bytes'],row['sha256'])and p.stat().st_size==row['bytes'],'complete exact original archive');seen.add(p.name)
  need(any(p.is_relative_to(q)for q in roots),'archive root watched');os.link(p,root/'cache'/p.name)
 phase=dict(repo=b['repo'],python=b['python'],source_dir=str(D/'source'),cache=str(root/'cache'),install_root=str(root/'installs'),result_root=str(root/'results'),pins=pins)
 phasepath=root/'INSTALL_PHASE_BINDING.json';save(phasepath,phase);pins[str(phasepath)]=sha(phasepath)
 caps=dict(wall_seconds=b['install_wall_seconds'],cleanup_seconds=30,file_bytes=2<<30,tree_bytes=12_081_306_272,watch_tree_bytes=12_081_306_272,extra_watch_roots=b['owned_roots'],min_free_disk_bytes=1610612736,log_bytes=16777216,raw_log_bytes=33554432,max_entries=150000,per_process_as_bytes=4<<30,per_process_cpu_seconds=b['install_wall_seconds'],rss_bytes=3<<30,cpu_seconds=b['install_wall_seconds'])
 owner_binding=dict(schema='FRESH_JOB_THREE_RUNTIME_INSTALL_BINDING_V1',scope='INSTALL_AND_SOURCE_BIND_ONLY_NO_REFERENCE_DUT',owner_root=str(root),identity=b['identity'],python=b['python'],admitted_runner=str(D/'install_job.py'),phase_script=str(D/'runtime_phase.py'),helper=b['helper'],phase_binding=pin(phasepath),pins=pins,archives=b['archives'],runtimes={})
 for k in KEYS:
  r=root/'installs'/k;home=r if k=='qwen2'else r/'work/runtime'
  owner_binding['runtimes'][k]=dict(root=str(r),home=str(home),site=str(home/'site-packages'),native_path=str(root/'runs'/k/'RESULT.json'),phase_result_path=str(root/'results'/(k+'_RESULT.json')),argv=[b['python'],'-S','-B',str(D/'runtime_phase.py'),'--binding',str(phasepath),'--binding-sha256',sha(phasepath),'--runtime',k],caps=caps)
 ownerpath=root/'OWNER_BINDING.json';save(ownerpath,owner_binding);execution_pins=dict(pins);execution_pins[str(ownerpath)]=sha(ownerpath)
 sys.path.insert(0,b['supervisor_dir']);import supervise_multiroot as supervisor
 for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):need(pins.get(str(P(b['supervisor_dir'])/name))==sha(P(b['supervisor_dir'])/name),'published supervisor closure')
 entries={}
 for k in KEYS:
  need(time.monotonic()-b['job_started_monotonic']+caps['wall_seconds']+30+b['remaining_job_reservation_seconds']<=21000,'fulljob remaining phase deadline')
  home=root/'environment'/k;home.mkdir();tmp=home/'tmp';tmp.mkdir()
  env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',HOME=str(home),TMPDIR=str(tmp),XDG_CACHE_HOME=str(home),HF_HOME=str(home),TRANSFORMERS_CACHE=str(home),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  r=supervisor.execute(owner_binding['runtimes'][k]['argv'],str(root/'runs'/k),b['lock'],caps,env,execution_pins,resource_gate={'min_available_memory':4<<30,'min_disk_free':8<<30})
  need(complete(r)and r['native_exit']==0 and not r['errors'],'actual install/cleanup failure; no retry')
  pr=root/'results'/(k+'_RESULT.json');result=json.loads(pr.read_text());entries[k]=dict(native=pin(root/'runs'/k/'RESULT.json'),phase_result=pin(pr),installation=result['installation'],sidecar=result['sidecar'])
  save(root/'results'/(k+'_NATIVE_VERIFIED.json'),dict(native=entries[k]['native'],scope='INSTALL_ONLY_NO_NUMERICAL_PASS'))
 index=root/'RECEIPT_INDEX.json';save(index,dict(schema='FRESH_JOB_THREE_RUNTIME_RECEIPTS_V1',identity=b['identity'],binding=pin(ownerpath),entries=entries))
 need(time.monotonic()-b['job_started_monotonic']+b['metadata_wall_seconds']+30+b['remaining_job_reservation_seconds']<=21000,'fulljob bind deadline')
 owner_output=root/'runs/bind/owner';metadata=root/'BIND_METADATA.json'
 save(metadata,dict(owner_module=str(D/'owner_fresh.py'),owner_module_sha256=sha(D/'owner_fresh.py'),owner_binding=str(ownerpath),owner_binding_sha256=sha(ownerpath),receipt_index=str(index),receipt_index_sha256=sha(index),output=str(owner_output)))
 bindpins=dict(execution_pins);bindpins[str(index)]=sha(index);bindpins[str(metadata)]=sha(metadata)
 for row in entries.values():
  for v in row.values():bindpins[v['path']]=v['sha256']
 bindcaps=dict(caps,wall_seconds=b['metadata_wall_seconds'],per_process_cpu_seconds=b['metadata_wall_seconds'],cpu_seconds=b['metadata_wall_seconds'],rss_bytes=256<<20,per_process_as_bytes=1<<30,tree_bytes=64<<20)
 bindrun=root/'runs/bind'
 r=supervisor.execute([b['python'],'-B',str(D/'bind_phase.py'),'--binding',str(metadata),'--sha256',sha(metadata)],str(bindrun),b['lock'],bindcaps,env,bindpins,resource_gate={'min_available_memory':1<<30,'min_disk_free':8<<30})
 need(complete(r)and r['native_exit']==0 and not r['errors'],'owner bind failed; preserve actual identity')
 owner=owner_output/'SHARED_RUNTIMES_FRESH_JOB_V3.json';doc=json.loads(owner.read_text());need(doc['schema']=='SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3'and doc['identity']==b['identity'],'actual fresh owner schema/identity')
 save(root/'INSTALL_CONTROLLER_RESULT.json',dict(scope='FRESH_JOB_THREE_INSTALLS_NOT_REFERENCE_DUT',binding=pin(ownerpath),receipt_index=pin(index),owner_bound=True,owner=pin(owner),bind_native=pin(bindrun/'RESULT.json'),memory_peak_qualification='INCOMPLETE_SAMPLED'))
 return ownerpath,index,owner

def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();need(sha(v.binding)==v.binding_sha256,'independent controller binding');run(json.loads(v.binding.read_text()),v.binding.resolve(),v.binding_sha256)
if __name__=='__main__':main()
