"""Fresh cloud validation/leases for independently approved existing runtime bytes.
Original installation receipts are historical provenance only, never this run's PASS.
No library/wrapper writes, copying, linking, package install, download or cleanup.
"""
import contextlib,fcntl,hashlib,importlib.util,json,os,pathlib,platform,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
_dep_spec=importlib.util.spec_from_file_location('runtime_dependencies',P(__file__).resolve().parent/'runtime_dependencies.py');deps=importlib.util.module_from_spec(_dep_spec);_dep_spec.loader.exec_module(deps)
KEYS=('qwen2','qwen35_08b','qwen35_35b');VALIDATION_ORDER=('qwen35_35b','qwen2','qwen35_08b');MAP=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
SCHEMA='IMPORTED_THREE_RUNTIME_OWNER_CLOUD_V1'
SCOPE='IMPORT_VALIDATION_ONLY_NOT_INSTALL_OR_REFERENCE_PASS'
HELPER_SHA='e853a724acefd26e7b3ef1f6883003376eaf968b808db505793e731ca0b1d302'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def regular(p):
 p=P(p);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file(),'canonical regular runtime input');return p
def checked(v,cap=64<<20):
 need(type(v)is dict and set(v)=={'path','bytes','sha256'},'exact independent runtime pin');p=regular(v['path'])
 need(type(v['bytes'])is int and 0<=v['bytes']<=cap and pin(p)==v,'pinned runtime bytes');return p
def read(v,cap=16<<20):return json.loads(checked(v,cap).read_text())
def save(p,v):
 with P(p).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def module(name,path,pins):
 p=regular(path);need(pins.get(str(p))==sha(p),'runtime reuse producer source pin')
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def complete(r):
 return r.get('status')=='PASS_PROCESS_ONLY'and type(r.get('native_exit'))is int and r.get('native_exit')==0 and r.get('errors')==[] and (r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True

def admit(b,current=False):
 need(b.get('execution_context')=='CLOUD_EXECUTOR_V1','cloud-only runtime import')
 if deps.selected(b):deps.require_pins(b)
 need(b['pins'].get(str(D/'runtime_reuse.py'))==sha(D/'runtime_reuse.py'),'actual runtime reuse source pin')
 identity=module('reuse_executor_identity',D.parent/'executor_identity.py',b['pins'])
 (identity.verify_current if current else identity.verify_owner)(b['identity'])
 budget=module('reuse_cloud_budget',D.parent/'cloud_budget.py',b['pins']).admit(b)
 need(budget['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME'and budget['archive_mode']=='READ_EXISTING_PINNED_ARCHIVES','explicit approved runtime/archive reuse modes')
 need(b['runtime_reuse_manifest']==budget['runtime_reuse_manifest'],'runtime manifest hash bound by independently approved budget')
 need(b['job_budget_seconds']==budget['job_budget_seconds']and b['job_started_monotonic']==b['identity']['started_monotonic'],'same executor deadline')
 need(0<=time.monotonic()-b['job_started_monotonic']<b['job_budget_seconds'],'runtime import executor deadline expired')
 need(b['stage_resources']==budget['stage_resources']and b['reserved_other_owner_bytes']==budget['reserved_other_owner_bytes']==5<<30,'same reviewed runtime role/unknown-owner reserve')
 if 'aggregate_tree_cap_bytes'in b or 'aggregate_tree_cap_bytes'in budget:
  cap=budget.get('aggregate_tree_cap_bytes')
  need(type(b.get('aggregate_tree_cap_bytes'))is int and b['aggregate_tree_cap_bytes']==cap and (0<cap<=12_081_306_272 if 'fullprefill_disk_budget'in budget else cap==12037043872),'runtime exact reviewed aggregate cap')
 return budget

def manifest(b):
 m=read(b['runtime_reuse_manifest'])
 fields={'schema','scope','source_commit','python','entries','archives','reference_qualified','numerical_qualified'}
 if deps.selected(b):fields.add('execution_policy')
 need(type(m)is dict and set(m)==fields,'exact runtime reuse manifest')
 if deps.selected(b):deps.require_pins(b);deps.policy.require_same(b,m)
 need(m['schema']==deps.schema(b,'PINNED_EXISTING_THREE_RUNTIME_BYTES_V1',deps.SELECTED_INVENTORY)and m['scope']=='EXISTING_BYTES_ONLY_REVALIDATE_EVERY_EXECUTOR','runtime byte inventory only')
 need(m['source_commit']==b['identity']['source_commit']and m['reference_qualified']is False and m['numerical_qualified']is False,'no historical qualification transfer')
 need(type(m['entries'])is dict and set(m['entries'])==set(deps.policy.runtimes(b)if deps.selected(b)else KEYS),'exact three original runtimes')
 need(str(checked(m['python']))==str(P(b['python']).resolve()),'original exact current Python bytes')
 need(sha(b['helper'])==HELPER_SHA,'original helper unchanged');helper=module('reuse_original_helpers',b['helper'],b['pins'])
 for key,e in m['entries'].items():
  need(type(e)is dict and set(e)=={'runtime','revision','import_root','home','site','wrapper','installation','sidecar','whole_tree'},'exact runtime entry inventory')
  root=P(e['import_root']);home=P(e['home']);site=P(e['site'])
  need(root.is_absolute()and root==root.resolve()and root.is_dir()and all(not q.is_symlink()for q in(root,*root.parents)),'canonical read-only import root')
  need(home==(root if key=='qwen2'else root/'work/runtime')and site==home/'site-packages','unchanged original runtime layout')
  need(e['runtime']==key and e['revision']==helper.CONTRACT[key][0],'original official runtime revision')
  for name,expected in (('wrapper',home/'python.sh'),('installation',home/'runtime_install.json'),('sidecar',home/'SOURCE_SIDECAR.json')):need(P(e[name]['path'])==expected,'original runtime role path')
  need(e['sidecar']['sha256']==helper.CONTRACT[key][1],'original independent sidecar contract')
 if deps.selected(b):
  locked=module('reuse_original_archive_inventory',P(b['source_dir'])/'prepare_runtimes.py',b['pins'])
  deps.archive_rows(b,m['archives'],locked,lambda row:P(row['path']),check_metadata=False)
 else:need(type(m['archives'])is list and len(m['archives'])==53,'original53 approved archive pins')
 return m,helper

def verify_entry(b,key,m=None,helper=None):
 if m is None:m,helper=manifest(b)
 deps.require_runtime(b,key);need(key in m['entries'],'selected runtime inventory');e=m['entries'][key]
 for role in ('wrapper','installation','sidecar'):checked(e[role])
 expected=read(e['whole_tree'],64<<20)
 actual=helper.tree(e['import_root'],m['python']['path']);need(actual==expected,'fresh entire runtime byte/alias inventory')
 helper.wrapper_policy(e['wrapper']['path'],key,P(e['home']),P(e['import_root']),P(m['python']['path']))
 helper.sidecar(P(e['site']),P(e['sidecar']['path']),key)
 need(sha(m['python']['path'])==m['python']['sha256'],'current interpreter unchanged')
 return e

def original_archives(b,m):
 source=P(b['source_dir']);locked=module('reuse_original_archives',source/'prepare_runtimes.py',b['pins'])
 return deps.archive_rows(b,m['archives'],locked,lambda row:checked(row,512<<20))

def archive_evidence(b,m):
 archive=read(b['archive_validation_receipt']);need(complete(archive),'fresh archive validation cleanup/EOF')
 ab=read(b['archive_binding'])
 expected=[b['python'],'-B',str(D/'reuse_archives.py'),'--binding',b['archive_binding']['path'],'--binding-sha256',b['archive_binding']['sha256']]
 need(archive['argv']==expected,'actual original53 validation invocation')
 need(ab['identity']==b['identity']and ab['runtime_reuse_manifest']==b['runtime_reuse_manifest'],'archive binding same executor and approved bytes')
 if deps.selected(b):deps.policy.require_same(b,ab)
 need(P(b['archive_output_manifest']['path'])==P(ab['output'])/'ARCHIVES.json','archive result exact invocation output')
 result=read(b['archive_output_manifest'])
 deps.check_archive_fields(b,result,reuse=True)
 need(result['archives']==m['archives']and result['runtime_reuse_manifest']==b['runtime_reuse_manifest']and result['identity']==b['identity'],'current original53 validation output')
 return result

def verify(manifest_path,expected_sha,job):
 job=P(job).resolve();path=regular(manifest_path);need(path.is_relative_to(job)and sha(path)==expected_sha,'fresh owned reuse manifest pin')
 owner=json.loads(path.read_text());need(owner['schema']==deps.schema(owner,SCHEMA,deps.SELECTED_REUSE_OWNER) and owner['scope']==SCOPE and owner['reference_qualified']is False and owner['numerical_qualified']is False,'import validation only')
 b=read(owner['binding']);admit(b)
 policy=module('reuse_execution_policy',D.parent/'profile_policy.py',b['pins'])
 need('execution_policy'in b and 'execution_policy'in owner,'explicit runtime owner execution policy');policy.require_same(b,owner)
 need(owner['identity']==b['identity']and owner['owner_root']==str(job)==b['owner_root'],'actual current executor owner')
 m,helper=manifest(b);need(owner['runtime_reuse_manifest']==b['runtime_reuse_manifest']and set(owner['entries'])==set(deps.policy.runtimes(b)if deps.selected(b)else KEYS),'same independently approved three roots')
 need(owner['profile_mapping']==list(MAP),'registered five runtime mapping')
 archive_evidence(b,m)
 for key,e in owner['entries'].items():
  need(e['entry']==m['entries'][key],'exact approved entry, no aliases or relocated wrapper')
  need(P(e['validation_receipt']['path'])==job/'runs'/key/'RESULT.json'and P(e['validation_result']['path'])==job/'results'/(key+'_IMPORT_VALIDATED.json'),'new owning-job validation receipt paths')
  native=read(e['validation_receipt']);result=read(e['validation_result']);need(complete(native),'fresh runtime import supervisor cleanup/EOF')
  expected_argv=[b['python'],'-S','-B',str(D/'runtime_reuse_phase.py'),'--binding',owner['phase_binding']['path'],'--binding-sha256',owner['phase_binding']['sha256'],'--runtime',key]
  need(owner['phase_binding']==owner['binding']and e['argv']==expected_argv and native['argv']==expected_argv and e['caps']==phase_caps(b)and native['caps']==e['caps'],'fresh exact supervised import role')
  need(result==import_result(b,key,m['entries'][key]),'fresh import result exact identity and byte inventory')
 return owner,helper

@contextlib.contextmanager
def lease(manifest_path,expected_sha,job,profile,out):
 need(type(profile)is int and profile in range(5),'original five profiles');job=P(job).resolve();out=P(out).resolve();need(out.is_dir()and out.is_relative_to(job),'fresh owned consumer output')
 owner,helper=verify(manifest_path,expected_sha,job);b=read(owner['binding']);deps.policy.require_profile(b,profile);m,_=manifest(b)
 need(all(not out.is_relative_to(P(e['import_root']))and not P(e['import_root']).is_relative_to(out)for e in m['entries'].values()),'output never inside read-only runtime')
 lock=regular(P(manifest_path).parent/'OWNER.lock')
 with lock.open('rb')as f:
  fcntl.flock(f,fcntl.LOCK_SH)
  import shutil
  need(shutil.disk_usage(out).free>=8<<30,'original lease free8GiB floor')
  need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original runtime ABI')
  if profile==0:need('avx512f'in P('/proc/cpuinfo').read_text().split(),'original P0 AVX512')
  verify(manifest_path,expected_sha,job)
  key=MAP[profile];e=verify_entry(b,key,m,helper)
  try:yield {key:dict(wrapper=e['wrapper']['path'],site=e['site'],receipt=e['installation'],sidecar=e['sidecar'],validation_receipt=owner['entries'][key]['validation_receipt'])}
  finally:verify(manifest_path,expected_sha,job);verify_entry(b,key,m,helper);fcntl.flock(f,fcntl.LOCK_UN)

def import_result(b,key,entry):
 result=dict(schema=deps.schema(b,'FRESH_RUNTIME_IMPORT_VALIDATION_V1',deps.SELECTED_IMPORT),scope=SCOPE,identity=b['identity'],runtime=key,runtime_reuse_manifest=b['runtime_reuse_manifest'],whole_tree=entry['whole_tree'],smoke_import_exit=0,reference_qualified=False,numerical_qualified=False)
 if deps.selected(b):result['execution_policy']=deps.policy.checked(b)
 return result

def phase_caps(b):
 role=b['stage_resources']['install'];wall=b['install_wall_seconds']
 tree_cap=12_081_306_272;disk_floor=1610612736
 if 'aggregate_tree_cap_bytes'in b:
  budget=admit(b);tree_cap=budget['aggregate_tree_cap_bytes']
  if 'fullprefill_disk_budget'in budget:disk_floor=8<<30
 need(type(wall)is int and 0<wall<=1800,'original finite import validation wall')
 return dict(wall_seconds=wall,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=tree_cap,watch_tree_bytes=tree_cap,extra_watch_roots=b['owned_roots'],min_free_disk_bytes=disk_floor,log_bytes=16777216,raw_log_bytes=33554432,max_entries=150000,per_process_as_bytes=role['as_bytes'],per_process_cpu_seconds=wall,rss_bytes=role['rss_bytes'],cpu_seconds=wall)

def run(b,binding_path,binding_sha):
 need(pin(binding_path)['sha256']==binding_sha,'independently pinned reuse controller binding');admit(b,current=True);m,helper=manifest(b)
 policy=module('reuse_execution_policy',D.parent/'profile_policy.py',b['pins']);need('execution_policy'in b and (policy.checked(b)['mode']==policy.FULL or deps.selected(b)),'explicit original full-five or selected runtime policy')
 keys=tuple(key for key in VALIDATION_ORDER if key in deps.policy.runtimes(b))
 need(set(m['entries'])==set(keys),'exact permitted validation runtimes')
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original runtime ABI')
 if 0 in deps.policy.eligible(b):deps.policy.require_cpu(b,P('/proc/cpuinfo').read_text().split())
 for p,h in b['pins'].items():need(sha(p)==h,'reuse admitted source/tool drift')
 for name in ('runtime_reuse.py','runtime_reuse_phase.py'):
  path=D/name;need(b['pins'].get(str(path))==sha(path),'explicit reuse producer source')
 # Root whitelist comes only from the independently approved byte inventory.
 root=P(b['owner_root']);need(root.is_absolute()and not root.exists()and all(not p.is_symlink()for p in(root,*root.parents))and root.is_relative_to(P(b['job_root'])),'fresh metadata root')
 historical=[m['python'],b['runtime_reuse_manifest'],*m['archives'],*[e[k]for e in m['entries'].values()for k in ('whole_tree','installation','sidecar','wrapper')]]
 need(all(not P(v['path']).is_relative_to(root)for v in historical),'historical evidence never under new metadata/output root')
 need(all(not root.is_relative_to(P(e['import_root']))and not P(e['import_root']).is_relative_to(root)for e in m['entries'].values()),'fresh outputs never replace historical runtime evidence')
 watched=[P(p)for p in b['owned_roots']]
 for e in m['entries'].values():need(any(P(e['import_root']).is_relative_to(p)for p in watched),'approved read-only import root watched')
 for row in m['archives']:need(any(P(row['path']).is_relative_to(p)for p in watched),'original archive root watched')
 archive_evidence(b,m)
 limit=b['job_budget_seconds'];started=b['job_started_monotonic'];caps=phase_caps(b)
 need(type(b['remaining_job_reservation_seconds'])is int and b['remaining_job_reservation_seconds']>=0,'finite nonnegative remaining cloud reservation')
 need(time.monotonic()-started+len(keys)*(caps['wall_seconds']+30)+b['remaining_job_reservation_seconds']<=limit,'reserve all three validations plus remaining cloud work')
 root.mkdir();(root/'runs').mkdir();(root/'results').mkdir();(root/'environment').mkdir()
 phase=dict(b,result_root=str(root/'results'));phasepath=root/'REUSE_BINDING.json';save(phasepath,phase);phasepin=pin(phasepath)
 pins=dict(b['pins']);pins[str(phasepath)]=phasepin['sha256']
 for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):
  path=P(b['supervisor_dir'])/name;need(pins.get(str(path))==sha(path),'original strict supervisor source pin')
 sys.path.insert(0,b['supervisor_dir']);import supervise_multiroot as supervisor
 entries={}
 for key in keys:
  deps.require_runtime(b,key)
  pending=len(keys)-keys.index(key)
  need(time.monotonic()-started+pending*(caps['wall_seconds']+30)+b['remaining_job_reservation_seconds']<=limit,'same cloud lifecycle deadline not reset')
  home=root/'environment'/key;home.mkdir();env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  for name in ('HOME','TMPDIR','XDG_CACHE_HOME','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','TORCH_HOME','MPLCONFIGDIR','NUMBA_CACHE_DIR'):
   p=home/name.lower();p.mkdir();env[name]=str(p)
  argv=[b['python'],'-S','-B',str(D/'runtime_reuse_phase.py'),'--binding',str(phasepath),'--binding-sha256',phasepin['sha256'],'--runtime',key]
  output=root/'runs'/key
  receipt=supervisor.execute(argv,str(output),b['lock'],caps,env,pins,resource_gate=dict(min_available_memory=caps['rss_bytes']+(1<<30)+b['reserved_other_owner_bytes'],min_disk_free=8<<30))
  # Local diagnostic call-return only; never a substitute for runs/<key>/RESULT.json.
  save(root/'results'/(key+'_SUPERVISOR_RETURN.json'),receipt)
  need(complete(receipt),'fresh import validation failed or incomplete, no reuse of old PASS')
  entries[key]=dict(entry=m['entries'][key],argv=argv,caps=caps,validation_receipt=pin(output/'RESULT.json'),validation_result=pin(root/'results'/(key+'_IMPORT_VALIDATED.json')))
 out=root/'owner';out.mkdir();(out/'OWNER.lock').touch()
 result=dict(schema=deps.schema(b,SCHEMA,deps.SELECTED_REUSE_OWNER),scope=SCOPE,execution_policy=b['execution_policy'],identity=b['identity'],owner_root=str(root),binding=pin(phasepath),phase_binding=phasepin,runtime_reuse_manifest=b['runtime_reuse_manifest'],entries=entries,profile_mapping=list(MAP),reference_qualified=False,numerical_qualified=False)
 path=out/'IMPORTED_RUNTIMES_OWNER.json';save(path,result);verify(path,sha(path),root)
 return root,phasepath,path
