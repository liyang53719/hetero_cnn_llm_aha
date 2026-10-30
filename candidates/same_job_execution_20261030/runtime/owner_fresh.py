"""Fresh owning-job installation provenance and lease. No inherited receipt identity.
Caller must supply separately reviewed binding and actual owning-controller receipt
index pins; these do not authenticate arbitrary self-authored JSON. Never imports a framework."""
import argparse,contextlib,fcntl,hashlib,importlib.util,json,pathlib,platform,shutil,sys
P=pathlib.Path
_policy_spec=importlib.util.spec_from_file_location('samejob_profile_policy', P(__file__).resolve().parent.parent/'profile_policy.py');profile_policy=importlib.util.module_from_spec(_policy_spec);_policy_spec.loader.exec_module(profile_policy)
HELPER_SHA='e853a724acefd26e7b3ef1f6883003376eaf968b808db505793e731ca0b1d302'
KEYS=('qwen2','qwen35_08b','qwen35_35b');MAP=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
SCHEMA='SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256')
def read(p):
 p=P(p);need(p.is_file() and not p.is_symlink() and p.stat().st_size<=64<<20,'regular bounded metadata');return json.loads(p.read_text())
def digest(p):return sha(p).hexdigest()
def exact(p,h):
 p=P(p);need(p.is_absolute() and p.is_file() and not p.is_symlink() and digest(p)==h,'exact admitted input drift');return p
def helper(path):
 p=exact(path,HELPER_SHA);spec=importlib.util.spec_from_file_location('unchanged_owner_utilities',p);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s);return s
def identity(v):
 need(set(v)=={'run_id','source_commit','launch_commit'},'exact owning-job identity fields')
 need(type(v['run_id'])is int and v['run_id']>0,'actual CI run id')
 for key in ('source_commit','launch_commit'):
  h=v[key];need(type(h)is str and len(h)==40 and all(c in '0123456789abcdef'for c in h),'exact commit')
 need(v['source_commit']!=v['launch_commit'],'separate launch/source commit')
 return v

def owned(path,job):
 p=P(path);need(p.is_absolute() and '..'not in p.parts and p==p.resolve(),'canonical owned path')
 need(p.is_relative_to(job),'path outside owning job');return p

def native_contract(r,key,b,job):
 need(r['native_exit']==0 and r['errors']==[] and r['status']=='PASS_PROCESS_ONLY','native install only')
 need(r['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','owned-group cleanup')
 need(r['log_capture']['pipe_eof_observed'] is True and r['log_capture']['gzip_finalized'] is True,'complete lossless log')
 need(r['argv']==b['runtimes'][key]['argv'],'actual independently admitted invocation')
 need(r['caps']==b['runtimes'][key]['caps'],'actual admitted budgets')

def binding(path,expected_sha):
 path=exact(path,expected_sha);b=read(path)
 need(b['schema']=='FRESH_JOB_THREE_RUNTIME_INSTALL_BINDING_V1','new installation binding')
 profile_policy.require_source_pin(b['pins'])
 job=P(b['owner_root']);need(job.is_absolute() and job==job.resolve() and job.is_dir(),'owning root')
 owned(path,job);identity(b['identity'])
 need(set(b['runtimes'])==set(profile_policy.runtimes(b)),'exact eligible installation definitions')
 need(b['scope']=='INSTALL_AND_SOURCE_BIND_ONLY_NO_REFERENCE_DUT','installation-only scope')
 need(b['helper']in b['pins'] and b['pins'][b['helper']]==HELPER_SHA,'original helper source')
 for role in ('python','admitted_runner','phase_script'):
  need(b[role]in b['pins'],'reviewed role source/tool pin '+role)
 for path,h in b['pins'].items():exact(path,h)
 need(type(b['archives'])is list and len(b['archives'])==53,'all53 unique original runtime archives')
 seen=set()
 for row in b['archives']:
  ap=exact(row['path'],row['sha256']);need(ap.stat().st_size==row['bytes'] and row['sha256']not in seen,'archive exact size/unique digest');seen.add(row['sha256'])
  need(b['pins'].get(str(ap))==row['sha256'],'archive independently prebound')
 phase_binding=exact(b['phase_binding']['path'],b['phase_binding']['sha256']);need(phase_binding.stat().st_size==b['phase_binding']['bytes'] and b['pins'].get(str(phase_binding))==b['phase_binding']['sha256'],'prebound phase configuration')
 for key,r in b['runtimes'].items():
  root=owned(r['root'],job);home=owned(r['home'],job);site=owned(r['site'],job)
  need(home==(root if key=='qwen2'else root/'work/runtime') and site==home/'site-packages','original installed layout')
  for field in ('native_path','phase_result_path'):owned(r[field],job)
  need(r['argv']==[b['python'],'-S','-B',b['phase_script'],'--binding',str(phase_binding),'--binding-sha256',b['phase_binding']['sha256'],'--runtime',key],'reviewed exact fresh phase invocation')
  need(type(r['caps'])is dict and r['caps']['wall_seconds']>0 and r['caps']['rss_bytes']>0,'finite admitted install resources')
 return b,job

def evidence(binding_path,binding_sha,index_path,index_sha,verify_all_inputs=True):
 b,job=binding(binding_path,binding_sha);s=helper(b['helper'])
 index_path=exact(index_path,index_sha);owned(index_path,job);index=read(index_path)
 need(index['schema']=='FRESH_JOB_THREE_RUNTIME_RECEIPTS_V1' and identity(index['identity'])==b['identity'],'actual controller receipt identity')
 need(index['binding']==s.pin(binding_path) and set(index['entries'])==set(profile_policy.runtimes(b)),'actual controller binds original admission')
 profile_policy.require_same(b,index)
 entries={}
 for key in profile_policy.runtimes(b):
  layout=b['runtimes'][key];root=P(layout['root']);home=P(layout['home']);site=P(layout['site']);rows=index['entries'][key]
  need(set(rows)=={'native','phase_result','installation','sidecar'},'exact actual receipt pins')
  native=s.checked(rows['native']);need(native==P(layout['native_path']),'native receipt role path');r=read(native);native_contract(r,key,b,job)
  phase_path=s.checked(rows['phase_result']);need(phase_path==P(layout['phase_result_path']),'phase receipt role path');result=s.read(phase_path)
  need(result['scope']=='FRESH_INSTALL_ARCHIVE_SOURCE_BOUND_NOT_REFERENCE_TESTED' and result['runtime']==key,'current install-only result')
  installation=s.checked(rows['installation']);need(installation==home/'runtime_install.json','original install receipt role')
  need(s.checked(rows['sidecar'])==home/'SOURCE_SIDECAR.json','original sidecar role')
  for name,p in [('installation',installation),('wrapper',home/'python.sh'),('sidecar',home/'SOURCE_SIDECAR.json'),('python',P(b['python']))]:
   need(s.checked(result[name])==p,'actual result path/bytes')
  need(result['site']==str(site),'canonical installed site')
  install=read(installation)
  if key=='qwen2':
   need(install['status']=='INSTALLED_ISOLATED_NOT_REFERENCE_TESTED' and install['python'].startswith('3.12.'),'Qwen2 install-only ABI')
   need(install['wheel_lock']['sha256']==s.QWEN2_LOCK_SHA,'original Qwen2 lock')
   lock=read(s.checked(install['wheel_lock']))
   need(install['installed_wheels']==[{'name':x['name'],'sha256':x['sha256']} for x in lock['packages'] if x['role']=='runtime'],'all25 original packages')
   need(s.checked(install['python_executable'])==P(b['python']),'installed Python')
  else:
   need(install['status']=='PASS_OFFLINE_LOCKED_INSTALL' and set(install['checks'])==set(s.INSTALL_CHECKS) and all(install['checks'][k] is True for k in s.INSTALL_CHECKS),'Qwen35 original install checks')
   t=install['trust_boundary'];need(t['host_interpreter']==b['python'] and t['sha256']==result['python']['sha256'] and t['python'].startswith('3.12.'),'Qwen35 installed Python')
  s.wrapper_policy(home/'python.sh',key,home,root,P(b['python']))
  if verify_all_inputs:s.sidecar(site,home/'SOURCE_SIDECAR.json',key)
  else:need(digest(home/'SOURCE_SIDECAR.json')==s.CONTRACT[key][1],'exact independent sidecar')
  entries[key]={'runtime':key,'revision':s.CONTRACT[key][0],'import_root':str(root),'home':str(home),'site':str(site),'wrapper':s.pin(home/'python.sh'),'installation':s.pin(installation),'installation_run':s.pin(native),'sidecar':s.pin(home/'SOURCE_SIDECAR.json'),'python':result['python'],'phase_result':s.pin(phase_path),'status':'INSTALL_AND_SOURCE_BOUND_NOT_REFERENCE_TESTED'}
 return b,s,entries
def validate_tree(s,e):
 actual=s.tree(e['import_root'],e['python']['path']);need(actual==read(s.checked(e['tree_manifest'])),'installed tree drift')
 if e['runtime']!='qwen2':
  for name,x in read(P(e['installation']['path']))['artifacts'].items():
   rel=P(x['path']);need(not rel.is_absolute() and '..' not in rel.parts,'installer provenance path')
   need(actual.get(str(rel))=={'bytes':x['bytes'],'sha256':x['sha256']},'installed provenance drift')
def bind(binding_path,binding_sha,index_path,index_sha,out):
 b,s,entries=evidence(binding_path,binding_sha,index_path,index_sha);job=P(b['owner_root']);out=P(out).resolve();owned(out,job)
 need(not out.exists(),'fresh owner output')
 need(all(not out.is_relative_to(P(e['import_root'])) and not P(e['import_root']).is_relative_to(out) for e in entries.values()),'metadata/import separation')
 out.mkdir();(out/'OWNER.lock').touch()
 for key,e in entries.items():
  p=out/(key+'_TREE.json');p.write_text(json.dumps(s.tree(e['import_root'],e['python']['path']),sort_keys=True,separators=(',',':'))+'\n');e['tree_manifest']=s.pin(p);validate_tree(s,e)
 evidence(binding_path,binding_sha,index_path,index_sha)
 m={'execution_policy':profile_policy.checked(b),'schema':SCHEMA,'identity':b['identity'],'owner_root':str(job),'binding':s.pin(binding_path),'receipt_index':s.pin(index_path),'admitted_runner':s.pin(b['admitted_runner']),'helper':s.pin(b['helper']),'entries':entries,'profile_mapping':list(MAP),'reference_qualified':False,'numerical_qualified':False,'memory_peak_qualification':'INCOMPLETE_SYNCHRONOUS_CENSUS_GAPS','lifecycle':'RETAIN_UNTIL_ALL_FIVE_CONSUMERS_RELEASED_NO_AUTODELETE'}
 p=out/'SHARED_RUNTIMES_FRESH_JOB_V3.json';p.write_text(json.dumps(m,indent=2)+'\n');return s.pin(p)

def verify(manifest,expected_sha,job):
 job=P(job).resolve();p=exact(manifest,expected_sha);owned(p,job);m=read(p)
 need(m['schema']==SCHEMA and m['owner_root']==str(job),'fresh job owner identity')
 need(m['profile_mapping']==list(MAP) and set(m['entries'])==set(profile_policy.runtimes(m)),'five to three exact mapping')
 need(m['reference_qualified'] is False and m['numerical_qualified'] is False and m['memory_peak_qualification']=='INCOMPLETE_SYNCHRONOUS_CENSUS_GAPS' and m['lifecycle']=='RETAIN_UNTIL_ALL_FIVE_CONSUMERS_RELEASED_NO_AUTODELETE','no qualification escalation')
 b,s,actual=evidence(m['binding']['path'],m['binding']['sha256'],m['receipt_index']['path'],m['receipt_index']['sha256'])
 profile_policy.require_same(b,m)
 need(b['owner_root']==str(job) and identity(m['identity'])==b['identity'],'same owning-job identity')
 for key in ('binding','receipt_index'):need(s.pin(m[key]['path'])==m[key],'metadata input drift')
 need(s.pin(b['admitted_runner'])==m['admitted_runner'] and s.pin(b['helper'])==m['helper'],'controller/helper identities')
 for k,e in actual.items():
  expected=dict(m['entries'][k]);expected.pop('tree_manifest');need(expected==e,'entry identity drift')
  tree=P(m['entries'][k]['tree_manifest']['path']);need(tree.parent==p.parent,'tree manifest owner directory');s.checked(m['entries'][k]['tree_manifest'])
 return m,s
@contextlib.contextmanager
def lease(manifest,expected_sha,job,profile,out):
 need(type(profile)is int and profile in range(5),'profile');job=P(job).resolve();out=P(out).resolve()
 m,s=verify(manifest,expected_sha,job)
 profile_policy.require_profile(m,profile)
 need(out.is_relative_to(job) and out.exists(),'owned existing output')
 need(all(not out.is_relative_to(P(e['import_root'])) and not P(e['import_root']).is_relative_to(out) for e in m['entries'].values()),'output/import separation')
 need(not out.is_relative_to(P(manifest).parent) and not P(manifest).parent.is_relative_to(out),'output/metadata separation')
 lock=P(manifest).parent/'OWNER.lock';need(lock.is_file() and not lock.is_symlink(),'owner lock')
 with lock.open('rb') as f:
  fcntl.flock(f,fcntl.LOCK_SH)
  need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64','original ABI')
  need(shutil.disk_usage(out).free>=8*(1<<30),'original free8GiB gate')
  if profile==0:need('avx512f' in P('/proc/cpuinfo').read_text().split(),'original P0 AVX512')
  m,s=verify(manifest,expected_sha,job);e=m['entries'][MAP[profile]];validate_tree(s,e)
  try:yield {e['runtime']:{'wrapper':e['wrapper']['path'],'site':e['site'],'receipt':e['installation'],'sidecar':e['sidecar']}}
  finally:verify(manifest,expected_sha,job);validate_tree(s,e);fcntl.flock(f,fcntl.LOCK_UN)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--binding',type=P,required=True);ap.add_argument('--binding-sha256',required=True);ap.add_argument('--receipt-index',type=P,required=True);ap.add_argument('--receipt-index-sha256',required=True);ap.add_argument('--output',type=P,required=True);ap.add_argument('--execute-reviewed-bind',action='store_true');a=ap.parse_args();need(a.execute_reviewed_bind,'strict outer-supervised metadata bind only');print(json.dumps(bind(a.binding,a.binding_sha256,a.receipt_index,a.receipt_index_sha256,a.output)))
