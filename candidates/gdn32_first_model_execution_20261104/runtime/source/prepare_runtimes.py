#!/usr/bin/env python3
"""Fresh job-local exact official runtime for ONE selected profile. Default plan; no historical readiness transfer."""
import argparse,hashlib,json,os,platform,shlex,shutil,stat,subprocess,sys,time,urllib.parse,urllib.request,zipfile
from pathlib import Path,PurePosixPath
D=Path(__file__).resolve().parent
ALLOWED={'files.pythonhosted.org','download-r2.pytorch.org','github.com','codeload.github.com'}

def need(x,m):
 if not x:raise ValueError(m)
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def record(p):return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':digest(p)}
def allowed_url(url):
 p=urllib.parse.urlsplit(url);need(p.scheme=='https' and p.hostname in ALLOWED and not p.username and not p.password,'official HTTPS URL only');return url
class OfficialRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  allowed_url(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
def safe_relative(s):
 p=PurePosixPath(s);need(not p.is_absolute() and '..' not in p.parts and str(p) not in ('','.'),'safe relative artifact name');return p

def artifacts():
 q=json.loads((D/'QWEN2_WHEEL_LOCK.json').read_text());need(len(q['packages'])==26,'complete26 Qwen2 lock')
 qitems=[dict(x,bytes=x['size_bytes']) for x in q['packages']];torch=next(x for x in qitems if x['name']=='torch');specs={k:json.loads((D/k/'ARTIFACT_SPEC.json').read_text()) for k in ['qwen35_08b','qwen35_35b']}
 for key,s in specs.items():
  need(len(s['artifacts'])==38,'complete38 wheel lock')
  t=next(x for x in s['artifacts'] if x['name']=='torch');need((t['sha256'],t['bytes'])==(torch['sha256'],torch['bytes']),'same exact Torch');t['url']=torch['url']
 return qitems,specs,torch

def acquire(item,cache,ledger,budget):
 safe_relative(item['filename']);need('/' not in item['filename'],'single filename');url=allowed_url(item['url']);path=cache/item['filename'];size=item['bytes'];need(0<size<350*(1<<20),'bounded artifact')
 if path.exists():
  need(not path.is_symlink() and path.is_file() and path.stat().st_size==size and digest(path)==item['sha256'],'job-local shared artifact drift');ledger.append({'url':url,'sha256':item['sha256'],'bytes':size,'kind':'VERIFIED_SAME_JOB_SHARED_ARTIFACT'});return path
 partial=path.with_suffix(path.suffix+'.partial');need(not partial.exists(),'preserve failed partial');h=hashlib.sha256();count=0;start=time.monotonic()
 with urllib.request.build_opener(OfficialRedirect()).open(url,timeout=60) as r,partial.open('xb') as f:
  allowed_url(r.geturl());need(r.status==200 and r.headers.get('Content-Encoding','identity')=='identity','full unencoded response');length=r.headers.get('Content-Length');need(length is None or int(length)==size,'locked response length')
  while True:
   need(time.monotonic()-start<300,'artifact wall limit');need(time.monotonic()-budget['start']<1500,'whole acquisition time bound')
   b=r.read(min(1<<20,size-count+1))
   if not b:break
   count+=len(b);budget['bytes']+=len(b);need(count<=size and budget['bytes']<=900*(1<<20),'download body budgets');h.update(b);f.write(b)
 need(count==size and h.hexdigest()==item['sha256'],'locked artifact mismatch, partial retained');partial.rename(path)
 ledger.append({'url':url,'sha256':item['sha256'],'bytes':count,'kind':'FRESH_HASH_VERIFIED_DOWNLOAD'});return path

def check_wheel_metadata(item,path):
 metadata=item.get('wheel_metadata')
 if metadata is None:return
 with zipfile.ZipFile(path) as z:
  info=z.getinfo(metadata['member']);need(info.file_size==metadata['bytes'],'locked wheel metadata size')
  with z.open(info) as f:h=hashlib.sha256(f.read(1<<20)).hexdigest()
  need(h==metadata['sha256'],'locked wheel metadata bytes')

def bootstrap_pip(wheel,out):
 out.mkdir()
 with zipfile.ZipFile(wheel) as z:
  infos=z.infolist();need(len(infos)<16000 and sum(x.file_size for x in infos)<64*(1<<20),'pip unzip limits');need(len({x.filename for x in infos})==len(infos),'unique pip members')
  for i in infos:
   rel=safe_relative(i.filename);mode=(i.external_attr>>16)&0o170000;need(mode in (0,stat.S_IFREG,stat.S_IFDIR),'regular pip files only');p=out/str(rel)
   if i.is_dir():p.mkdir(parents=True,exist_ok=True);continue
   p.parent.mkdir(parents=True,exist_ok=True)
   with z.open(i) as src,p.open('xb') as dst:shutil.copyfileobj(src,dst,1<<20)

def execute(cmd,log,env):
 with log.open('xb') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=1200)
 need(r.returncode==0,'installer failure; retained '+str(log))
def environment():
 return {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PIP_CONFIG_FILE':'/dev/null','PIP_NO_INPUT':'1','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}

def qwen2_install(out,cache,items):
 home=out/'qwen2';home.mkdir();site=home/'site-packages';site.mkdir();boot=home/'bootstrap-pip';pip=next(x for x in items if x['name']=='pip');bootstrap_pip(cache/pip['filename'],boot)
 tmp=home/'tmp';tmp.mkdir()
 env=environment();env.update({'HOME':str(home),'PYTHONPATH':str(boot),'TMPDIR':str(tmp)})
 cmd=[sys.executable,'-S','-B','-m','pip','install','--no-index','--no-deps','--no-compile','--disable-pip-version-check','--target',str(site),*[str(cache/x['filename']) for x in items if x['role']=='runtime']]
 execute(cmd,home/'install.log',env)
 wrapper=home/'python.sh';wrapper.write_text('#!/usr/bin/env bash\nset -euo pipefail\nRUNTIME="$(cd "$(dirname "$0")" && pwd)"\nexport PYTHONPATH="$RUNTIME/site-packages"\nunset PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE LD_PRELOAD LD_LIBRARY_PATH\nexport PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\nexport ATEN_CPU_CAPABILITY=avx512 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4\nexec '+shlex.quote(sys.executable)+' -S -B "$@"\n');wrapper.chmod(0o755)
 receipt=home/'runtime_install.json';write(receipt,{'status':'INSTALLED_ISOLATED_NOT_REFERENCE_TESTED','python':sys.version,'python_executable':record(Path(sys.executable)),'wheel_lock':record(D/'QWEN2_WHEEL_LOCK.json'),'installed_wheels':[{'name':x['name'],'sha256':x['sha256']} for x in items if x['role']=='runtime'],'bootstrap_pip':pip['version'],'offline_no_deps':True,'baseline':'same25 locked runtime wheel artifacts; fresh pinned pip25.0.1 bootstrap, no historical install qualification transfer'})
 return home,site,wrapper,receipt

def qwen35_install(key,out,repo,cache,spec,ledger):
 root=out/key;root.mkdir();shutil.copytree(repo/'src',root/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));scripts=root/'scripts';scripts.mkdir()
 for name in ['install_qwen35_official_runtime.py','pip_qwen35_offline_driver.py','qwen35_runtime_network_guard.py','qwen35_backend_runner.py']:shutil.copyfile(D/key/name,scripts/name)
 work=root/'work';work.mkdir();acq=work/'acquisition';acq.mkdir();(acq/'wheels').mkdir()
 for x in spec['artifacts']:
  rel=safe_relative(x['relative_path']);need(str(rel)=='wheels/'+x['filename'],'locked wheel location');os.link(cache/x['filename'],acq/str(rel))
 arc=spec['transformers'];os.link(cache/arc['filename'],acq/arc['filename'])
 # Immutable artifact spec establishes exact allowed content; freshness is observed above, not inherited.
 lock={**spec,'status':'VERIFIED_ARTIFACTS_READY_NOT_INSTALLED','wheel_metadata_closure_checked':True,'installation_executed':False,'network_acquired_bytes':sum(x['bytes'] for x in ledger if x['kind']=='FRESH_HASH_VERIFIED_DOWNLOAD'),'fresh_ci_spec_sha256':digest(D/key/'ARTIFACT_SPEC.json')}
 write(acq/'official_runtime.lock.json',lock)
 with (acq/'network.jsonl').open('x') as f:
  for x in ledger:f.write(json.dumps(x)+'\n')
 write(acq/'window_extension.json',{'scope':'fresh job-local locked acquisition; no retained-runtime dependency','extension_used':False,'whole_job_budget_seconds':1500})
 runtime=work/'runtime';env=environment();env['HOME']=str(root)
 execute([sys.executable,'-S','-B',str(scripts/'install_qwen35_official_runtime.py'),'--root',str(root),'--acquisition',str(acq),'--runtime',str(runtime),'--expected-lock-sha256',digest(acq/'official_runtime.lock.json'),'--execute'],root/'install.log',env)
 receipt=runtime/'runtime_install.json';need(json.loads(receipt.read_text())['status']=='PASS_OFFLINE_LOCKED_INSTALL','native installer receipt')
 return runtime,runtime/'site-packages',runtime/'python.sh',receipt

def verify_sidecar(site,sidecar):
 r=json.loads(sidecar.read_text())
 for name,h in r['module_sha256'].items():
  p=site/r['module_relative_paths'][name];need(p.is_file() and digest(p)==h,'installed original module '+name)
 for rel,h in r['native_file_sha256'].items():need(digest(site/rel)==h,'installed original native file '+rel)

PROFILE_RUNTIME={0:'qwen2',1:'qwen35_08b',2:'qwen35_08b',3:'qwen35_35b',4:'qwen35_35b'}

def selected_runtime(profile):
 need(type(profile) is int and profile in PROFILE_RUNTIME,'one supported integer profile 0..4')
 return PROFILE_RUNTIME[profile]

def selected_artifacts(profile,items,specs):
 key=selected_runtime(profile)
 return items if key=='qwen2' else specs[key]['artifacts']+[specs[key]['transformers']]

def prepare(repo,out,profile,execute_reviewed=False):
 key=selected_runtime(profile)
 repo=repo.resolve();out=out.resolve();need((repo/'src/heteronpu').is_dir(),'actual hetero repo');need(not out.exists(),'fresh output required');items,specs,torch=artifacts();contract=json.loads((D/'RUNTIME_CONTRACT.json').read_text())
 plan={'status':'PLAN_NOT_EXECUTED','selected_profile':profile,'runtime_keys':[key],'output':str(out),'selected_wheel_count':len(items) if key=='qwen2' else len(specs[key]['artifacts']),'no_retained_runtime_dependency':True,'requires':'Python3.12 x86_64; P0 AVX512f only; >=8GiB disk; externally bounded single setup; no reference PASS transfer'}
 if not execute_reviewed:return plan
 need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64','exact CPU wheel ABI');need(key!='qwen2' or 'avx512f' in Path('/proc/cpuinfo').read_text().split(),'Qwen2 original AVX512 policy, no AVX2 fallback');need(shutil.disk_usage(out.parent).free>=8*(1<<30),'8GiB setup disk gate')
 # Entire package is pinned before any download or subprocess.
 manifest=json.loads((D/'SOURCE_MANIFEST.json').read_text())
 for r in manifest['files']:need(digest(D/r['path'])==r['sha256'],'reviewed runtime glue source '+r['path'])
 out.mkdir();cache=out/'artifacts';cache.mkdir();ledger=[];budget={'start':time.monotonic(),'bytes':0}
 try:
  allitems=selected_artifacts(profile,items,specs)
  for x in allitems:
   path=acquire(x,cache,ledger,budget);check_wheel_metadata(x,path)
  installed={key:qwen2_install(out,cache,items) if key=='qwen2' else qwen35_install(key,out,repo,cache,specs[key],ledger)}
  entries={}
  for key,(home,site,wrapper,installation) in installed.items():
   framework=next(x for x in items if x['name']=='transformers') if key=='qwen2' else specs[key]['transformers']
   sidecar=home/'SOURCE_SIDECAR.json'
   # Only the original archive-derived helper is called; it does not import Torch.
   execute([sys.executable,'-S','-B',str(D/'derive_sidecar.py'),'--revision',contract['entries'][key]['revision'],'--framework',str(cache/framework['filename']),'--framework-sha256',framework['sha256'],'--torch-wheel',str(cache/torch['filename']),'--output',str(sidecar)],home/'derive_sidecar.log',environment())
   need(digest(sidecar)==contract['entries'][key]['expected_sidecar_sha256'],'exact independent sidecar bytes');verify_sidecar(site,sidecar)
   receipt=home/'FRESH_RUNTIME_RECEIPT.json';write(receipt,{'status':'FRESH_INSTALLED_ARCHIVE_BOUND_NOT_REFERENCE_TESTED','runtime':key,'python':sys.version,'python_executable':record(Path(sys.executable)),'installation':record(installation),'sidecar':record(sidecar),'wrapper':record(wrapper),'source_manifest':record(D/'SOURCE_MANIFEST.json'),'installed_module_and_native_hashes_verified':True,'historical_reference_pass_transferred':False,'limits':'not runtime arithmetic qualification, full reference replay, Chisel or RTL'})
   entries[key]={'wrapper':str(wrapper.resolve()),'site':str(site.resolve()),'receipt':record(receipt),'sidecar':record(sidecar)}
  result={'status':'FRESH_SELECTED_RUNTIME_NOT_REFERENCE_TESTED','profile':profile,'selected_runtime':key,'entries':entries,'provider_python':entries[key]['wrapper']};write(out/'RUNTIMES.json',result);return result
 except BaseException as e:write(out/'FAILURE.json',{'status':'INCOMPLETE','error':repr(e),'partial_files_preserved':True,'network_bytes':budget['bytes']});raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--profile',required=True,type=int,choices=range(5));p.add_argument('--execute-reviewed',action='store_true');a=p.parse_args();print(json.dumps(prepare(a.repo,a.output,a.profile,a.execute_reviewed),indent=2))
