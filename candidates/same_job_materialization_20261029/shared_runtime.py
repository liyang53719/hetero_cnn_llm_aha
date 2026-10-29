"""Owning-job three-runtime reuse. No install, arithmetic, DUT, or deletion.
The external binding SHA is the owning controller's trust input, not attestation.
Bind creates streaming snapshots; each selected lease rehashes its tree before/after use.
"""
import argparse,contextlib,fcntl,hashlib,importlib.util,json,os,pathlib,sys,shlex,shutil,platform
P=pathlib.Path
SAMPLE_SOURCE_SHA='57e6170d4110a63576bc5275e18ed51be965c9a1c28500f98767a87e8de25182'
QWEN2_LOCK_SHA='92e02a64b81a3433206ce85bfe1d65593088f0c4a40dbb0db3c3dd45d5ce0889'
INSTALL_CHECKS=('all_inputs_sha_verified_before_use','canonical_native_cache_transformers_install_succeeded','fresh_runtime','native_built_wheel_retained','native_pep610_unmodified','no_network_or_unexpected_spawn_observed','offline_locked_wheel_install_succeeded','parent_and_backend_audit_guard_observed','pinned_bootstrap_pip','safe_zip_inventory','transformers_stage_merged_without_collision_or_metadata_edits')
KEYS=('qwen2','qwen35_08b','qwen35_35b')
MAP=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
CONTRACT={
 'qwen2':('4.40.1','17d159b19e98d6f104bbaba1bd62ea2de96b5bcde8185230135c6a96d445628f'),
 'qwen35_08b':('14e738b5d0cc69aa27a95dde272aea41fde44f2f','8a6ba34b3e85bac5427d25a44e97659f6eeaa341392e1bc6d35906434422aada'),
 'qwen35_35b':('42ca97014c85d71a88ad60d55f08cb9fb4d26e2c','79078825f230ffecf33fff9b838d40b155217b025accf26e961927a25a475743')}
def need(x,s):
 if not x:raise ValueError(s)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def read(p,cap=16<<20):
 p=P(p);need(p.is_file() and not p.is_symlink() and p.stat().st_size<=cap,'bounded regular JSON');return json.loads(p.read_text())
def checked(v,root=None):
 p=P(v['path']);need(p.is_absolute() and p.is_file() and not p.is_symlink(),'absolute regular pin')
 if root is not None:inside(p,root)
 need(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'pinned bytes drift '+str(p));return p
def inside(p,root):
 p=P(p);root=P(root);need(p.is_absolute() and p.resolve().is_relative_to(root.resolve()),'owning job boundary');return p

def tree(site,python=None):
 """All runtime import-root bytes/aliases, including root/src and extra modules.
 Internal directory aliases are represented, not followed; target is also walked.
 Only the pinned host Python file may be an external symlink target.
 """
 site=P(site);need(site.is_dir() and not site.is_symlink(),'real import-root directory');rows={}
 for base,dirs,files in os.walk(site,followlinks=False):
  for name in dirs+files:
   p=P(base)/name;rel=str(p.relative_to(site))
   if p.is_symlink():
    target=p.resolve();need(target.exists(),'dangling import-root alias')
    need(target.is_relative_to(site.resolve()) or (python is not None and target==P(python).resolve() and target.is_file()),'external import-root alias')
    rows[rel]={'symlink':os.readlink(p),'resolved':str(target),'kind':'directory' if target.is_dir() else 'file'}
    if target.is_file():rows[rel].update(bytes=target.stat().st_size,sha256=sha(target))
   elif p.is_file():rows[rel]={'bytes':p.stat().st_size,'sha256':sha(p)}
   else:need(p.is_dir(),'import-root special file');rows[rel]={'kind':'directory'}
 need(rows,'empty installed import root');return rows

def wrapper_policy(wrapper,key,home,import_root,python):
 text=P(wrapper).read_text();lines=text.splitlines();need(lines[:3]==['#!/usr/bin/env bash','set -euo pipefail','RUNTIME="$(cd "$(dirname "$0")" && pwd)"'],'original wrapper prelude')
 tail=shlex.split(lines[-1]);alias=P(tail[1] if key=='qwen2' else tail[4]);need(alias.resolve()==P(python).resolve(),'wrapper interpreter alias')
 common=['unset PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE LD_PRELOAD LD_LIBRARY_PATH']
 if key=='qwen2':
  expected=lines[:3]+['export PYTHONPATH="$RUNTIME/site-packages"',*common,'export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1','export ATEN_CPU_CAPABILITY=avx512 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4','exec '+shlex.quote(str(alias))+' -S -B "$@"']
 else:
  expected=lines[:3]+['ROOT='+shlex.quote(str(import_root)),'export PYTHONPATH="$RUNTIME/site-packages:$ROOT/src:$ROOT"',*common,'export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1','export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 ATEN_CPU_CAPABILITY=default','export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1','CPU="$('+shlex.quote(str(alias))+" -S -c 'import os; print(min(os.sched_getaffinity(0)))')"+chr(34),'exec taskset -c "$CPU" '+shlex.quote(str(alias))+' -S -B "$@"']
 need(text=='\n'.join(expected)+'\n','original CPU/thread/import wrapper policy')
 return alias

def sidecar(site,path,key):
 need(sha(path)==CONTRACT[key][1],'exact original sidecar for profile family');s=read(path)
 need(s['framework_revision']==CONTRACT[key][0],'framework revision')
 for module,h in s['module_sha256'].items():
  p=inside(P(site)/s['module_relative_paths'][module],site);need(p.is_file() and not p.is_symlink() and sha(p)==h,'installed module '+module)
 for rel,h in s['native_file_sha256'].items():
  p=inside(P(site)/rel,site);need(p.is_file() and not p.is_symlink() and sha(p)==h,'installed native '+rel)
 return s

def verify_install_source(sp,h,python_pin):
 is_python=str(sp)==python_pin['path']
 limit=64<<20 if is_python else 16<<20
 need(sp.is_file() and not sp.is_symlink() and sp.stat().st_size<=limit,'bounded original installation source')
 if is_python:need(h==python_pin['sha256'] and sp.stat().st_size==python_pin['bytes'],'original interpreter source role')
 need(sha(sp)==h,'original installation source drift')

def validate_entry(e,key,job,full_tree=True):
 need(e['runtime']==key and e['revision']==CONTRACT[key][0],'family/version mismatch')
 home=inside(e['home'],job);site=inside(e['site'],home);import_root=inside(e['import_root'],job)
 need(home==(import_root if key=='qwen2' else import_root/'work/runtime'),'original runtime layout')
 need(site==home/'site-packages','canonical installed site')
 wrapper=checked(e['wrapper'],home);need(wrapper==home/'python.sh','canonical wrapper')
 installation=checked(e['installation'],home);need(installation==home/'runtime_install.json','canonical install receipt')
 install=read(installation);sample=read(checked(e['sample_receipt'],job))
 need(sample['scope']=='NATIVE_INSTALL_ONLY_NOT_REFERENCE_OR_DUT' and sample['stage']==key and sample['no_historical_pass_transfer'] is True,'actual sample install identity')
 native=read(checked(e['installation_run'],job));need(native['native_exit']==0 and native['errors']==[] and native['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','actual install process and cleanup')
 ib=checked(e['install_binding'],job);ibdoc=read(ib);sample_source=checked(e['sample_source'],job)
 need(e['sample_source']['sha256']==SAMPLE_SOURCE_SHA and ibdoc['source_pins'].get(str(sample_source))==SAMPLE_SOURCE_SHA,'original sample source')
 need(ibdoc['schema']=='OFFLINE_RUNTIME_SAMPLING_BINDING_V1' and P(ibdoc['output'])/key==import_root,'native installation binding output role')
 for source,h in ibdoc['source_pins'].items():
  verify_install_source(P(source),h,e['python'])
 argv=native['argv']
 need(len(argv)==7 and argv[1:]==['-B',str(sample_source),'--binding',str(ib),'--stage',key] and P(argv[0]).resolve()==P(e['python']['path']).resolve(),'exact original installation invocation')
 need(sample['installation_receipt']==str(installation) and sample['installation_receipt_sha256']==e['installation']['sha256'],'sample to install binding')
 if key=='qwen2':
  need(install['status']=='INSTALLED_ISOLATED_NOT_REFERENCE_TESTED' and install['python'].startswith('3.12.'),'Qwen2 install-only status/ABI');python=install['python_executable']
  need(install['wheel_lock']['sha256']==QWEN2_LOCK_SHA,'original Qwen2 wheel lock');lock=read(checked(install['wheel_lock']))
  need(install['installed_wheels']==[{'name':x['name'],'sha256':x['sha256']} for x in lock['packages'] if x['role']=='runtime'],'original Qwen2 package set')
 else:
  need(install['status']=='PASS_OFFLINE_LOCKED_INSTALL' and set(install['checks'])==set(INSTALL_CHECKS) and all(install['checks'][k] is True for k in INSTALL_CHECKS),'Qwen35 install-only checks');t=install['trust_boundary'];need(t['python'].startswith('3.12.'),'original Python ABI');python={'path':t['host_interpreter'],'sha256':t['sha256'],'bytes':P(t['host_interpreter']).stat().st_size}
 need(checked(e['python'])==checked(python),'exact installed interpreter');need(e['python']['sha256']==python['sha256'],'interpreter identity')
 wrapper_policy(wrapper,key,home,import_root,P(e['python']['path']))
 sidecar(site,checked(e['sidecar'],job),key)
 need(e['status']=='INSTALL_AND_SOURCE_BOUND_NOT_REFERENCE_TESTED','no reference qualification transfer')
 if full_tree:
  actual=tree(import_root,e['python']['path']);need(actual==read(checked(e['tree_manifest'],job),64<<20),'installed tree drift')
  if key!='qwen2':
   need(bool(install['artifacts']),'native installer provenance retained')
   for name,record in install['artifacts'].items():
    rel=P(record['path']);need(not rel.is_absolute() and '..' not in rel.parts,'installed artifact relative path')
    need(actual.get(str(rel))=={'bytes':record['bytes'],'sha256':record['sha256']},'original installer artifact drift '+name)
 return {'wrapper':str(wrapper),'site':str(site),'receipt':e['installation'],'sidecar':e['sidecar']}

def verify(manifest,expected_sha,job):
 manifest=P(manifest);job=P(job).resolve();inside(manifest,job);need(sha(manifest)==expected_sha,'external shared manifest pin');m=read(manifest)
 need(m['schema']=='SHARED_THREE_RUNTIME_OWNER_V1' and m['owner_root']==str(job),'owning identity')
 need(m['profile_mapping']==list(MAP) and set(m['entries'])==set(KEYS),'all five original runtime mapping')
 need(m['lifecycle']=='RETAIN_UNTIL_ALL_FIVE_CONSUMERS_RELEASED_NO_AUTODELETE' and m['reference_qualified'] is False,'explicit lifecycle and qualification')
 need(len({e['home'] for e in m['entries'].values()})==3,'three distinct framework installations')
 return m

def preflight_path(manifest,expected_sha,job,out):
 m=verify(manifest,expected_sha,job);out=inside(P(out).resolve(),P(job).resolve())
 protected=[P(e['import_root']).resolve() for e in m['entries'].values()]+[P(manifest).resolve().parent]
 need(all(not out.is_relative_to(p) and not p.is_relative_to(out) for p in protected),'profile output overlaps shared ownership')
 return m

@contextlib.contextmanager
def lease(manifest,expected_sha,job,profile,out):
 need(type(profile)is int and profile in range(5),'profile');job=P(job).resolve();out=inside(P(out).resolve(),job)
 m=preflight_path(manifest,expected_sha,job,out);lock=P(manifest).parent/'OWNER.lock';need(lock.is_file() and not lock.is_symlink(),'owner lock absent')
 # Shared flock holds runtime ownership through reference+provider+bundle completion.
 # A killed process releases kernel lock; evidence remains. This module never deletes.
 with lock.open('rb') as fd:
  fcntl.flock(fd,fcntl.LOCK_SH)
  m=verify(manifest,expected_sha,job);key=MAP[profile];e=m['entries'][key]
  need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64','original Python/x86_64 host ABI')
  need(all(not out.is_relative_to(P(x['import_root']).resolve()) for x in m['entries'].values()),'profile output must not mutate shared runtime')
  need(shutil.disk_usage(out).free>=8*(1<<30),'original 8GiB free setup/acquisition gate')
  if profile==0:need('avx512f' in P('/proc/cpuinfo').read_text().split(),'original P0 AVX512 gate')
  r=validate_entry(e,key,job)
  try:yield {key:r}
  finally:validate_entry(e,key,job);fcntl.flock(fd,fcntl.LOCK_UN)

def bind(binding,binding_sha,out):
 """Bind existing installs+fresh archive-derived sidecars. Never imports a framework.
 Caller must supply reviewed original sidecars; absent sidecars fail closed.
 Snapshotting is only baseline consistency, not independent wheel attestation.
 """
 binding=P(binding);need(sha(binding)==binding_sha,'reviewed installation binding');b=read(binding)
 need(b['schema']=='EXISTING_THREE_INSTALLS_BINDING_V1' and set(b['entries'])==set(KEYS),'three original installs')
 job=P(b['owner_root']).resolve();out=inside(P(out).resolve(),job);need(not out.exists(),'fresh shared metadata output')
 # Validate all families before writing any identity. Explicit input pins cover
 # installation, wrapper, Python, sample receipt and sidecar; no inferred PASS.
 entries={}
 for key,e in b['entries'].items():
  e=dict(e,runtime=key,revision=CONTRACT[key][0],status='INSTALL_AND_SOURCE_BOUND_NOT_REFERENCE_TESTED')
  validate_entry(e,key,job,False);entries[key]=e
 need(all(not out.is_relative_to(P(e['import_root']).resolve()) for e in entries.values()),'shared metadata outside import roots')
 out.mkdir();(out/'OWNER.lock').touch()
 for key,e in entries.items():
  p=out/(key+'_TREE.json');p.write_text(json.dumps(tree(e['import_root'],e['python']['path']),sort_keys=True,separators=(',',':'))+'\n');e['tree_manifest']=pin(p)
  validate_entry(e,key,job)
 m=dict(schema='SHARED_THREE_RUNTIME_OWNER_V1',owner_root=str(job),binding=pin(binding),profile_mapping=list(MAP),entries=entries,lifecycle='RETAIN_UNTIL_ALL_FIVE_CONSUMERS_RELEASED_NO_AUTODELETE',reference_qualified=False)
 p=out/'SHARED_RUNTIMES.json';p.write_text(json.dumps(m,indent=2)+'\n');return pin(p)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--binding',type=P,required=True);ap.add_argument('--binding-sha256',required=True);ap.add_argument('--output',type=P,required=True);ap.add_argument('--execute-reviewed-bind',action='store_true');a=ap.parse_args();need(a.execute_reviewed_bind,'explicit bind authorization required');print(json.dumps(bind(a.binding,a.binding_sha256,a.output)))
