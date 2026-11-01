"""Offline bounded cloud receipt revalidation; no download, process or model run.
The caller supplies an independently trusted binding SHA, not one read from the
binding itself. Builder authentication remains outside this local consistency gate.
"""
import hashlib,json,pathlib,sys,types,math
P=pathlib.Path
D=P(__file__).resolve().parent

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap=16<<20):
 p=P(p);need(p.is_absolute()and p==p.resolve()and all(not x.is_symlink()for x in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,'bounded canonical receipt');return p
def pin(p):
 p=regular(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def checked(p):
 need(type(p)is dict and set(p)=={'path','bytes','sha256'},'exact file pin');f=regular(p['path']);need(pin(f)==p,'actual pinned bytes');return f
def read(p):return json.loads(regular(p).read_text())
def load(name,path):
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(P(path).read_bytes(),str(path),'exec'),m.__dict__);return m

def source_guard(binding):
 repo=D.parents[1];manifest=checked(binding['source_pins'])
 need(manifest==D/'SOURCE_PINS.json','fixed active source manifest')
 doc=read(manifest);need(doc['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1'and type(doc['files'])is list and 1<=len(doc['files'])<=2000,'source closure schema')
 files={}
 for r in doc['files']:
  need(type(r)is dict and set(r)=={'path','bytes','sha256'},'exact source row')
  rel=P(r['path']);need(not rel.is_absolute()and '..'not in rel.parts and str(rel)not in files,'unique source relative path')
  p=regular(repo/rel,32<<20);need(p.stat().st_size==r['bytes']and sha(p)==r['sha256'],'active source bytes');files[str(p)]=r['sha256']
 for p in (D/'executor_identity.py',D/'cloud_budget.py',D/'execution_mode.py',D/'profile_policy.py',D/'numeric/artifact_handoff.py',D/'numeric/dut_evidence.py',D/'numeric/required_acceptance.py',P(__file__).resolve()):
  need(files.get(str(p))==sha(p)and binding['pins'].get(str(p))==sha(p),'required helper in reviewed closure')
 if binding.get('executor_adaptation') is not None:
  p=D/'executor_adaptation.py';need(files.get(str(p))==sha(p)and binding['pins'].get(str(p))==sha(p),'reviewed executor adaptation source')
 if binding.get('retained_materials') is not None:
  p=D/'runtime/retained_materials.py';need(str(p)in files and files.get(str(p))==sha(p)and binding['pins'].get(str(p))==sha(p),'reviewed retained materials source')
 if binding.get('model_candidate_review')is not None:
  for name in ('candidate_admission.py','candidate_artifact_handoff.py'):
   p=D/'numeric'/name;need(files.get(str(p))==sha(p)and binding['pins'].get(str(p))==sha(p),'candidate helper in reviewed closure')
 return binding['source_pins']['sha256']

# Only fixed actual supervisor result locations; never glob arbitrary files.
STAGE_PATHS=tuple([(n,'runs/'+n+'/RESULT.json')for n in ('archives','weights')]+[(f'reference{i}',f'materials/references/profile{i}/actual/RESULT.json')for i in range(5)]+[(n,'materials/runs/'+n+'/RESULT.json')for n in ('qwen2','qwen35_08b','qwen35_35b','bind')]+[(n,'materials/numeric/runs/'+n+'/RESULT.json')for n in ('startup_abi','p0_p0_rope','p0_p0_provider','p0_p0_transport','p1_p12_provider','p2_p12_provider','p3_p34_provider','p4_p34_provider',*(f'p{i}_{phase}'for i in range(5)for phase in ('initialize','connect','dut')))])
RETAINED_SCOPE='REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT'
RESOURCE_ERRORS={'ValueError: sampled observed aggregate RSS cap':'SAMPLED_RSS_CAP','ValueError: sampled observed aggregate CPU cap':'SAMPLED_CPU_CAP','ValueError: sampled disk reserve':'SAMPLED_DISK_RESERVE','ValueError: sampled aggregate writable-root cap':'SAMPLED_WRITABLE_ROOT_CAP','ValueError: sampled stage output tree cap':'SAMPLED_STAGE_TREE_CAP','ValueError: file cap':'FILE_CAP','ValueError: sampled log cap':'SAMPLED_LOG_CAP','ValueError: locked memory gate':'LOCKED_MEMORY_GATE','ValueError: locked disk gate':'LOCKED_DISK_GATE','ValueError: wall cap':'WALL_CAP'}

def partial_stages(job):
 rows=[]
 for name,relative in STAGE_PATHS:
  path=job/relative
  if not path.exists()and not path.is_symlink():continue
  r=read(path);need(type(r)is dict,'stage receipt object')
  errors=r.get('errors');need(type(errors)is list and len(errors)<=4096 and all(type(e)is str for e in errors),'bounded stage errors')
  native=r.get('native_exit');need(native is None or type(native)is int and -255<=native<=255,'native stage exit')
  cleanup=r.get('cleanup_proof')or{};capture=r.get('log_capture')or{}
  need(type(cleanup)is dict and type(capture)is dict,'cleanup/capture objects')
  codes=sorted({RESOURCE_ERRORS[e]for e in errors if e in RESOURCE_ERRORS})
  row=dict(name=name,native_exit=native,errors_count=len(errors),cleanup_complete=cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof_observed=capture.get('pipe_eof_observed')is True,gzip_finalized=capture.get('gzip_finalized')is True,resource_reason_codes=codes,status='RESOURCE_LIMIT_OBSERVED'if codes else'INCOMPLETE_NATIVE_STAGE',elapsed_seconds=None,observed_peak_rss=None)
  for key in ('elapsed_seconds','observed_peak_rss'):
   value=r.get(key)
   if value is not None:
    need(type(value)in(int,float)and math.isfinite(value)and 0<=value<=2**63,'bounded sampled metric')
    if key=='observed_peak_rss':need(type(value)is int,'integer sampled RSS')
    row[key]=value
  rows.append(row)
 need(len(rows)<=40,'fixed stage count')
 return rows

def project(job,binding_path,binding_sha):
 unavailable=dict(schema='CLOUD_EXECUTION_SAFE_SUMMARY_V1',status='UNAVAILABLE',numerical_pass=False,final_rtl_executed=False)
 try:
  job=P(job);bp=regular(binding_path,1<<20);need(sha(bp)==binding_sha,'trusted owning binding hash');b=read(bp)
  need(b['job_root']==str(job)and job.is_absolute()and job==job.resolve(),'owning fixed job root')
  source_sha=source_guard(b)
  executor=load('summary_cloud_identity',D/'executor_identity.py').validate(b['identity'])
  manifest=checked(b['artifact_manifest']);frozen=read(manifest);candidate=frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
  handoff=load('summary_cloud_handoff',D/'numeric'/('candidate_artifact_handoff.py'if candidate else'artifact_handoff.py'));builder=handoff.builder_identity(b['artifact_identity'])
  need(candidate==('model_candidate_review'in b),'candidate artifact requires explicit reviewed branch')
  review=load('summary_candidate_admission',D/'numeric/candidate_admission.py').verify(b['model_candidate_review'],b)if candidate else None
  candidate_kwargs=dict(model_candidate_review=b['model_candidate_review'],current_source_pins_pin=b['source_pins'],repo=b['repo'])if candidate else{}
  retained_scope='DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS'if candidate else RETAINED_SCOPE
  need(builder==frozen['artifact_identity'],'actual frozen builder identity')
  adaptation=b.get('executor_adaptation');loader=b.get('workspace_loader')
  hp=checked(b['builder_handoff'])
  if adaptation is None:
   need(loader is None and executor['source_commit']==builder['source_commit'],'legacy same-source identity without adaptation')
   handoff_result=handoff.verify(hp,b['builder_handoff']['sha256'],manifest,b['artifact_manifest']['sha256'],frozen,executor,**candidate_kwargs)
   need(handoff_result['source_pins_sha256']==source_sha,'builder reviewed source closure equals actual executor closure')
  else:
   checked(adaptation);checked(loader)
   load('summary_executor_adaptation',D/'executor_adaptation.py').verify(adaptation,builder,executor,current_source_pins_pin=b['source_pins'],repo=D.parents[1])
   handoff_result=handoff.verify(hp,b['builder_handoff']['sha256'],manifest,b['artifact_manifest']['sha256'],frozen,executor,executor_adaptation=adaptation,**candidate_kwargs)
  cloud_budget=load('summary_cloud_budget',D/'cloud_budget.py');cloud_admission=cloud_budget.admit(b)
  need(cloud_admission.get('executor_adaptation')==adaptation and cloud_admission.get('workspace_loader')==loader,'approved adapter and loader identities')
  reuse=b.get('p0_provider_reuse');need(cloud_admission.get('p0_provider_reuse')==reuse,'approved P0 input-only reuse identity')
  if reuse is not None:checked(reuse)
  retained=b.get('retained_materials')
  need(cloud_admission.get('retained_materials')==retained,'approved retained materials identity')
  if retained is not None:
   checked(retained)
   retained_result=load('summary_retained_materials',D/'runtime/retained_materials.py').verify(retained,b)
   need(type(retained_result)is dict and retained_result.get('scope')==retained_scope,'retained materials input-only scope')
  source_identity=dict(builder_source_commit=builder['source_commit'],executor_source_commit=executor['source_commit'],executor_adaptation_sha256=adaptation['sha256']if adaptation is not None else None,workspace_loader_sha256=loader['sha256']if loader is not None else None)
  if retained is not None:source_identity.update(retained_materials_sha256=retained['sha256'],retained_materials_scope=retained_scope)
  if reuse is not None:source_identity.update(p0_provider_reuse_sha256=reuse['sha256'])
  if candidate:source_identity.update(candidate_scope=review['scope'],model_candidate_review_sha256=b['model_candidate_review']['sha256'],production_acceptance=False)
  mode=load('summary_cloud_mode',D/'execution_mode.py');admission=mode.admit(b)
  need(cloud_admission['execution_mode']==admission['mode']and cloud_admission['full_block_budget']==b.get('full_block_budget'),'approved cloud mode and full budget')
  if admission['mode']==mode.STAGE:need(cloud_admission.get('stage_coverage_budget')==b.get('stage_coverage_budget')and b.get('stage_coverage_budget')is not None,'approved stage diagnostic budget')
  flow_path=job/'FLOW_RESULT.json'
  if not flow_path.exists()and not flow_path.is_symlink():
   result=dict(schema=unavailable['schema'],status='INCOMPLETE_EXECUTION',numerical_pass=False,final_rtl_executed=False,profile_qualification='UNKNOWN_NOT_INFERRED_FROM_PARTIAL_STAGES',profiles_registered=list(range(5)),stages=partial_stages(job),binding_sha256=binding_sha,source_pins_sha256=source_sha,builder_handoff_sha256=b['builder_handoff']['sha256'],execution_approval_sha256=b['execution_approval']['sha256'],cloud_budget_sha256=b['cloud_budget']['sha256'])
   result.update(source_identity)
   need(len(json.dumps(result).encode())<=65536,'bounded incomplete summary');return result
  flow=read(flow_path);root=job/'materials/numeric';numeric_path=root/'RESULT.json';numeric=read(numeric_path)
  for key,value in [('identity',executor),('execution_approval',b['execution_approval']),('artifact_identity',builder),('execution_binding',pin(bp)),('builder_handoff',b['builder_handoff']),('artifact_manifest',b['artifact_manifest']),('numeric_result',pin(numeric_path))]:need(flow.get(key)==value,'fixed flow binding '+key)
  need(flow.get('retained_materials')==retained,'flow retained materials pin')
  need(flow.get('p0_provider_reuse')==reuse,'flow P0 input-only reuse pin')
  if adaptation is not None:need(flow.get('executor_adaptation')==adaptation and flow.get('workspace_loader')==loader,'flow adapter and loader pins')
  if candidate:need(flow.get('model_candidate_review')==b['model_candidate_review']and flow.get('scope')==review['scope'],'actual flow candidate scope')
  need(flow.get('hardware_definitions')==1 and flow.get('profiles')==list(range(5)),'one fixed five profile hardware')
  need(flow.get('execution_mode')==admission['mode']and numeric.get('execution_mode')==admission['mode'],'mode binding')
  if admission['mode']==mode.STAGE:
   need(flow.get('stage_coverage_budget')==b['stage_coverage_budget']and numeric.get('stage_budget_sha256')==admission['reviewed_budget_sha256']and numeric.get('full_budget_sha256')is None,'stage budget domain binding')
  else:need(numeric.get('full_budget_sha256')==admission['reviewed_budget_sha256']and numeric.get('stage_budget_sha256')is None,'legacy mode budget binding')
  sys.path.insert(0,str(D/'numeric'))
  acceptance=load('required_acceptance',D/'numeric/required_acceptance.py');sys.modules['required_acceptance']=acceptance
  evidence=load('cloud_dut_evidence',D/'numeric/dut_evidence.py')
  records=[];profiles=[]
  for i in range(5):
   rp=root/f'PROFILE_{i}_DIAGNOSTIC.json'
   if not rp.exists():continue
   record=read(rp);out=root/f'profile{i}/material/dut_result';report_path=out/'RESULT.json';start_path=out/f'profile{i}.started.json';outer_path=root/f'runs/p{i}_dut/RESULT.json'
   need(record.get('profile')==i and all(record.get(k)==pin(p)for k,p in [('report',report_path),('startup',start_path),('outer',outer_path)]),'fixed profile receipt paths')
   consumer=read(report_path);started=read(start_path)
   need(consumer.get('executor_identity')==executor and consumer.get('artifact_identity')==builder and consumer.get('builder_handoff_sha256')==b['builder_handoff']['sha256'],'actual consumer dual identity')
   if adaptation is not None:need(consumer.get('executor_adaptation_sha256')==adaptation['sha256']and consumer.get('workspace_loader_sha256')==loader['sha256'],'actual consumer approved adapter/loader identities')
   if candidate:need(consumer.get('model_candidate_review_sha256')==b['model_candidate_review']['sha256']and consumer.get('candidate_scope')==review['scope'],'actual consumer candidate scope')
   need(consumer.get('artifact_manifest_sha256')==b['artifact_manifest']['sha256']and started['binary_sha256']==frozen['common']['binary']['sha256'],'same actual artifact')
   ea=consumer.get('execution_admission',{})
   need(ea.get('execution_mode')==admission['mode']and ea.get('reviewed_budget_sha256')==admission['reviewed_budget_sha256']and ea.get('outer_cleanup_proof_required')is True,'actual consumer mode')
   if admission['mode']==mode.STAGE:need(ea.get('stage_budget_sha256')==admission['reviewed_budget_sha256'],'actual consumer stage budget domain')
   else:need(ea.get('stage_budget_sha256')is None,'legacy consumer cannot carry stage budget')
   need(ea.get('effective_limits')==cloud_budget.consumer_resource_limits(mode.consumer_limits(ea['original_limits'],admission,i),cloud_admission),'actual effective limits')
   parent_as=cloud_admission['consumer_address_space_bytes'];dut_as=cloud_admission['dut_address_space_bytes']
   expected_resource=dict(consumer_pre_fork_soft_bytes=parent_as,consumer_pre_fork_hard_bytes=dut_as,consumer_after_popen_hard_bytes=parent_as,dut_hard_address_space_bytes=dut_as,group_rss_is_sampled=True)
   need(consumer.get('resource_admission')==expected_resource and consumer['resource_admission'].get('group_rss_is_sampled') is True,'exact sampled group/resource admission')
   scope={mode.FULL:'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE',mode.CALIBRATION:'CALIBRATION_SAME_FULL_M128_STIMULUS',mode.STAGE:'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE'}[admission['mode']]
   need(ea.get('scope')==scope,'actual consumer scope')
   actual=evidence.verify(out,i,consumer['artifact_manifest_sha256'],consumer['runtime_bundle_sha256'],started['binary_sha256'],started['runtime_sha256'],record['outer'])
   need(actual==record,'recomputed actual record');records.append(actual)
   q=actual['qualification'];need(all(type(q[k])is list and len(q[k])<=64 for k in ('missing','failed','checked')),'bounded qualification')
   profiles.append(dict(profile=i,state=actual['state'],qualification=q,receipt_sha256=sha(rp)))
  q=acceptance.aggregate(records)
  need(numeric.get('actual_dut_reports')==records and numeric.get('qualification')==q and numeric.get('status')==q['status']and numeric.get('numerical_pass')is q['numerical_pass'],'actual numeric aggregate')
  need(flow.get('qualification')==q and flow.get('status')==q['status'],'actual flow aggregate')
  transport=mode.transport_exit(admission['mode'],q);need(type(flow.get('transport_exit_code'))is int and flow['transport_exit_code']==transport,'actual transport scope')
  result=dict(schema=unavailable['schema'],status='VERIFIED_REAGGREGATED',executor_identity=executor,builder_identity=builder,numerical_pass=q['numerical_pass'],final_rtl_executed=False,execution_mode=admission['mode'],transport_exit_code=transport,qualification=q,profiles=profiles,binding_sha256=binding_sha,execution_approval_sha256=b['execution_approval']['sha256'],cloud_budget_sha256=b['cloud_budget']['sha256'],source_pins_sha256=source_sha,builder_handoff_sha256=b['builder_handoff']['sha256'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],flow_receipt_sha256=sha(flow_path),numeric_receipt_sha256=sha(numeric_path))
  result.update(source_identity)
  if admission['mode']==mode.STAGE:
   progress_path=D/'summary_progress.py';need(b['pins'].get(str(progress_path))==sha(progress_path),'stage progress helper source pin')
   progress=load('stage_post_cleanup_progress',progress_path).project(job,builder,D/'numeric')
   targets=read(checked(b['stage_coverage_budget']))['profiles'];coverage=[]
   for row in progress['profiles']:
    last=row.get('last');observed=last.get('completions')if type(last)is dict else None;target=targets[str(row['profile'])]['target_completed_commands']
    coverage.append(dict(profile=row['profile'],target_completed_commands=target,observed_completed_commands=observed,target_observed=observed>=target if type(observed)is int else None,scope='POST_CLEANUP_COMMAND_RETIREMENT_ONLY_NOT_NUMERICAL_PASS'))
   result.update(stage_budget_sha256=admission['reviewed_budget_sha256'],stage_coverage_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE',full_acceptance_mode=False,stage_coverage_observations=coverage)
  need(len(json.dumps(result).encode())<=65536,'bounded safe summary');return result
 except (ValueError,TypeError,KeyError,AttributeError,OSError,ImportError):return unavailable
