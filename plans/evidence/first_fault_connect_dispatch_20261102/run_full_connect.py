"""Actual artifact/input validators; synthetic offline authority and exact proc IO.
No execution capability. Must run under parent-reviewed strict supervisor.
"""
import argparse,ast,copy,hashlib,importlib.util,json,pathlib,sys,time,types,uuid
P=pathlib.Path
ap=argparse.ArgumentParser()
for n in ('repo','original-execution','output','offline-review'):ap.add_argument('--'+n,type=P,required=True)
for n in ('source-pins-sha256','offline-review-sha256'):ap.add_argument('--'+n,required=True)
a=ap.parse_args()
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def read(row):
 p=P(row['path']);need(p==p.resolve()and p.is_file()and not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'actual metadata pin');return json.loads(p.read_text())
def save(p,d):
 with p.open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return pin(p)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def forbid(event,args):
 if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn')or event.startswith('socket.'):raise RuntimeError('OFFLINE_FIXTURE_FORBIDS_PROCESS_NETWORK')
sys.addaudithook(forbid)
repo=a.repo.absolute();E=repo/'candidates/same_job_execution_20261030';N=E/'numeric';cp=E/'SOURCE_PINS.json';need(sha(cp)==a.source_pins_sha256,'current fixture catalog');catalog=json.loads(cp.read_text());pins={}
for row in catalog['files']:
 p=repo/row['path'];need(p==p.resolve()and p.is_file()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'actual source closure');pins[str(p)]=row['sha256']
original=a.original_execution.resolve();oldbinding=original/'run-CLOUD_BINDING.json';b=json.loads(oldbinding.read_text());oldrepo=P(b['repo']);oldidentity=read(b['executor_identity_pin']);oldmat=original/'run/materials/numeric/profile0/material'
out=a.output.absolute();need(not out.exists()and out==out.resolve()and all(not p.is_symlink()for p in(out,*out.parents)),'fresh offline fixture root');out.mkdir();control=out/'control';control.mkdir()
synthetic_commit=hashlib.sha1(b'OFFLINE_UNADMITTED_CONNECT_FIXTURE\0'+cp.read_bytes()).hexdigest()
identity=dict(oldidentity,source_commit=synthetic_commit,execution_id=str(uuid.uuid5(uuid.NAMESPACE_URL,str(out))),controller_pid=2147483001,start_tick=135791113)
identitypin=save(control/'SYNTHETIC_IDENTITY.json',identity)
# Only new source/catalog fields change. Builder and actual reviewed artifact stay original.
b=copy.deepcopy(b);b.update(repo=str(repo),identity=identity,executor_identity=identity,executor_identity_pin=identitypin,source_pins=pin(cp),pins=pins)
adapter=read(b['executor_adaptation']);buildercatalog=read(adapter['builder_source_pins']);oldmap={r['path']:r for r in buildercatalog['files']};newmap={r['path']:r for r in catalog['files']}
changes=[dict(path=k,old_sha256=oldmap.get(k,{}).get('sha256'),new_sha256=newmap.get(k,{}).get('sha256'))for k in sorted(set(oldmap)|set(newmap))if oldmap.get(k)!=newmap.get(k)]
changes_sha=hashlib.sha256(json.dumps(changes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
expected_review=dict(schema='HOST_ONLY_EXECUTOR_ADAPTATION_REVIEW_V1',status='SOURCE_ONLY_GO_NOT_NUMERICAL',builder_source_commit=adapter['builder_identity']['source_commit'],executor_source_commit=synthetic_commit,builder_source_pins_sha256=adapter['builder_source_pins']['sha256'],executor_source_pins_sha256=a.source_pins_sha256,artifact_manifest_sha256=b['artifact_manifest']['sha256'],changes_sha256=changes_sha,numerical_pass=False)
need(sha(a.offline_review)==a.offline_review_sha256 and json.loads(a.offline_review.read_text())==expected_review,'independently reviewed exact OFFLINE synthetic adapter')
adapter.update(executor_source_commit=synthetic_commit,executor_source_pins=pin(cp),changes=changes,review=pin(a.offline_review));b['executor_adaptation']=save(control/'SYNTHETIC_ADAPTER.json',adapter)
context={k:b[k]for k in ('repo','artifact_manifest','retained_materials','execution_mode')}
for key in ('p0_provider_reuse','reference_data_reuse'):
 d=read(b[key]);d['context']={k:b[k]for k in d['context']}
 if key=='p0_provider_reuse':
  for row in d['source_contract'].values():
   if P(row['path']).is_relative_to(oldrepo):row['path']=str(repo/P(row['path']).relative_to(oldrepo))
 b[key]=save(control/('SYNTHETIC_'+key.upper()+'.json'),d)
budget=read(b['cloud_budget']);budget['source_commit']=synthetic_commit
for key in ('executor_adaptation','p0_provider_reuse','reference_data_reuse'):budget[key]=b[key]
b['cloud_budget']=save(control/'SYNTHETIC_BUDGET.json',budget)
approval=read(b['execution_approval']);approval.update(source_commit=synthetic_commit,execution_id=identity['execution_id'],budget_sha256=b['cloud_budget']['sha256'])
for key in ('executor_adaptation','p0_provider_reuse','reference_data_reuse'):approval[key+'_sha256']=b[key]['sha256']
b['execution_approval']=save(control/'SYNTHETIC_APPROVAL_NOT_EXECUTABLE.json',approval)
bindingpin=save(control/'SYNTHETIC_CLOUD_BINDING.json',b)
# Exact historical-owner IO simulation: no gate function is mocked or replaced.
stat='2147483001 (offline-fixture) '+' '.join(['S']+['0']*18+[str(identity['start_tick'])])
procstat='/proc/'+str(identity['controller_pid'])+'/stat';read_text=P.read_text;real_mono=time.monotonic;io_counts={'stat':0,'boot':0,'clock':0}
def offline_read_text(self,*args,**kwargs):
 if str(self)==procstat:io_counts['stat']+=1;return stat
 if str(self)=='/proc/sys/kernel/random/boot_id':io_counts['boot']+=1;return identity['boot_id']+'\n'
 return read_text(self,*args,**kwargs)
def offline_monotonic():io_counts['clock']+=1;return identity['started_monotonic']+1
P.read_text=offline_read_text;time.monotonic=offline_monotonic
sys.path.insert(0,str(N));con=load('actual_complete_connect',N/'connect_owned.py');consumer=con.consumer;provider=load('actual_provider',N/'provider_from_frozen.py');core=load('actual_reuse',N/'p0_provider_data_reuse.py');emit=load('actual_emit',N/'emit_reused_p0_tsv.py')
owner=out/'synthetic_owner';owner.mkdir();cache=owner/'execution_cache';cache.mkdir();names=('HOME','TMPDIR','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR')
for name in names:(cache/name.lower()).mkdir()
env=read(pin(original/'run/materials/numeric/EXECUTION_ENVIRONMENT.json'));env.update(identity=identity,owner_root=str(owner),watched_roots=[str(owner)],cache_root=str(cache),cache_paths={name:str(cache/name.lower())for name in names});envpin=save(owner/'EXECUTION_ENVIRONMENT.json',env)
originalabi=pin(original/'run/materials/numeric/STARTUP_ABI.json');abi=read(originalabi);abi['owned_environment']=envpin;abi['environment']=dict(abi['environment'],**env['cache_paths']);original_environment=read(originalabi)['environment'];need(set(abi['environment'])==set(original_environment)and all(abi['environment'][k]==v for k,v in original_environment.items()if k not in names),'ABI non-cache environment keys unchanged');abi_changed_environment_keys=sorted(k for k in abi['environment']if abi['environment'][k]!=original_environment[k]);need(set(abi_changed_environment_keys)==set(names),'only all exact cache path keys changed');need({k:v for k,v in abi.items()if k not in ('owned_environment','environment')}=={k:v for k,v in read(originalabi).items()if k not in ('owned_environment','environment')},'only synthetic ABI authority fields change');abipin=save(owner/'HISTORICAL_ABI_SYNTHETIC_AUTHORITY.json',abi)
material=owner/'material';reference=b['references']['0']if 'references'in b else read(b['retained_materials'])['references']['0']['result'];materializer=repo/'candidates/same_job_materialization_20261029'
provider.initialize(repo,materializer,material,0,reference,b['reference_data_reuse'],context,pin(N/'reference_data_reuse.py'))
payloads={str(P(v['data']['path']).parent.parent)for v in read(b['p0_provider_reuse'])['raw_weights'].values()};need(len(payloads)==1,'exact single source payload');payload=P(next(iter(payloads)))
def stage(name,argv):
 if name=='p0_provider':core.materialize(P(b['p0_provider_reuse']['path']),b['p0_provider_reuse']['sha256'],material/'p0_provider')
 elif name=='p0_transport':emit.run(types.SimpleNamespace(provider=material/'p0_provider',output=material/'p0_transport',payload=payload,reuse_binding=P(b['p0_provider_reuse']['path']),reuse_binding_sha256=b['p0_provider_reuse']['sha256']))
 else:raise ValueError('unexpected provider dispatch')
provider.prepare(repo,materializer,material,0,'NO_SUBPROCESS',payload,reference,stage,pins,p0_provider_reuse=b['p0_provider_reuse'])
phase=json.loads((original/'run/materials/numeric/phases/p0_connect.json').read_text());argv=phase['argv'][3:];replace={'--existing-output':str(material),'--owned-environment':envpin['path'],'--owned-environment-sha256':envpin['sha256'],'--executor-identity':identitypin['path'],'--executor-identity-sha256':identitypin['sha256'],'--cloud-binding':bindingpin['path'],'--cloud-binding-sha256':bindingpin['sha256'],'--local-runtime-abi':abipin['path'],'--local-runtime-abi-sha256':abipin['sha256']}
for key,value in replace.items():argv[argv.index(key)+1]=value
parser=argparse.ArgumentParser();parser.add_argument('--existing-output',type=P,required=True);parser.add_argument('--profile',type=int,required=True);con.add_arguments(parser);args=parser.parse_args(argv)
# Retain each actual old complete function as a negative control, with the
# current real helper namespace. No verifier call or return is substituted.
oldconnect=oldrepo/'candidates/same_job_execution_20261030/numeric/connect_owned.py'
need(sha(oldconnect)==json.loads((oldrepo/'candidates/same_job_execution_20261030/numeric/CONNECTION_OWNED_SOURCE_PINS.json').read_text())['connect_owned.py'],'actual old dispatch source pin')
oldtree=ast.parse(oldconnect.read_text());old_failures=[]
for name in ('preflight','connect'):
 fn=next(n for n in oldtree.body if isinstance(n,ast.FunctionDef)and n.name==name)
 ns=dict(con.__dict__);exec(compile(ast.Module(body=[fn],type_ignores=[]),str(oldconnect),'exec'),ns)
 try:
  if name=='preflight':ns[name](copy.copy(args))
  else:ns[name](copy.copy(args),material)
 except ValueError as err:
  need(str(err)=='independently admitted first fault artifact','old dispatch must fail exact missing context');old_failures.append(name)
 else:raise ValueError('old dispatch unexpectedly accepted')
con.preflight(args);print('OFFLINE_CHECKPOINT actual_preflight_pass',flush=True)
con.connect(args,material);print('OFFLINE_CHECKPOINT actual_connect_pass',flush=True)
consumer_argv=json.loads((material/'CONSUMER_ARGV.json').read_text())['consumer_argv'][2:]+['--execution-mode','P0_FIRST_FAULT_DIAGNOSTIC','--validate-only']
need('--validate-only'in consumer_argv,'no DUT mode');sys.argv=['consumer_owned.py']+consumer_argv
consumer.main();print('OFFLINE_CHECKPOINT actual_consumer_validate_only_pass',flush=True)
P.read_text=read_text;time.monotonic=real_mono
safe=dict(scope='ACTUAL_ARTIFACT_FULL_CONNECT_WITH_SYNTHETIC_OFFLINE_AUTHORITY',actual_artifact_manifest=b['artifact_manifest'],actual_closed_abi=originalabi,source_catalog=pin(cp),synthetic_source_commit=synthetic_commit,synthetic_authority=True,proc_time_only_io_simulation=io_counts,verifier_functions_mocked=False,old_complete_function_missing_context_rejections=old_failures,complete_preflight=True,complete_connect=True,complete_consumer_validate_only=True,reference_and_program_fresh_containment=True,derived_abi_only_authority_environment_changed=True,derived_abi_changed_keys=['owned_environment','environment'],derived_abi_changed_environment_keys=abi_changed_environment_keys,new_runtime_abi_pass=False,dut_executed=False,numerical_pass=False,execution_admitted=False)
save(out/'SAFE_RESULT.json',safe);print(json.dumps(safe))
