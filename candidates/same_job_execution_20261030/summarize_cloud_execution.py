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
 return binding['source_pins']['sha256']

# Only fixed actual supervisor result locations; never glob arbitrary files.
STAGE_PATHS=tuple([(n,'runs/'+n+'/RESULT.json')for n in ('archives','weights',*('reference'+str(i)for i in range(5)))]+[(n,'materials/runs/'+n+'/RESULT.json')for n in ('qwen2','qwen35_08b','qwen35_35b','bind')]+[(n,'materials/numeric/runs/'+n+'/RESULT.json')for n in ('startup_abi','p0_p0_rope','p0_p0_provider','p0_p0_transport','p1_p12_provider','p2_p12_provider','p3_p34_provider','p4_p34_provider',*(f'p{i}_{phase}'for i in range(5)for phase in ('initialize','connect','dut')))])
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
  handoff=load('summary_cloud_handoff',D/'numeric/artifact_handoff.py')
  manifest=checked(b['artifact_manifest']);frozen=read(manifest);builder=handoff.builder_identity(b['artifact_identity'])
  need(builder==frozen['artifact_identity']and executor['source_commit']==builder['source_commit'],'separate same-source identities')
  hp=checked(b['builder_handoff']);handoff_result=handoff.verify(hp,b['builder_handoff']['sha256'],manifest,b['artifact_manifest']['sha256'],frozen,executor)
  need(handoff_result['source_pins_sha256']==source_sha,'builder reviewed source closure equals actual executor closure')
  cloud_budget=load('summary_cloud_budget',D/'cloud_budget.py');cloud_admission=cloud_budget.admit(b)
  mode=load('summary_cloud_mode',D/'execution_mode.py');admission=mode.admit(b)
  need(cloud_admission['execution_mode']==admission['mode']and cloud_admission['full_block_budget']==b.get('full_block_budget'),'approved cloud mode and full budget')
  flow_path=job/'FLOW_RESULT.json'
  if not flow_path.exists()and not flow_path.is_symlink():
   result=dict(schema=unavailable['schema'],status='INCOMPLETE_EXECUTION',numerical_pass=False,final_rtl_executed=False,profile_qualification='UNKNOWN_NOT_INFERRED_FROM_PARTIAL_STAGES',profiles_registered=list(range(5)),stages=partial_stages(job),binding_sha256=binding_sha,source_pins_sha256=source_sha,builder_handoff_sha256=b['builder_handoff']['sha256'],execution_approval_sha256=b['execution_approval']['sha256'],cloud_budget_sha256=b['cloud_budget']['sha256'])
   need(len(json.dumps(result).encode())<=65536,'bounded incomplete summary');return result
  flow=read(flow_path);root=job/'materials/numeric';numeric_path=root/'RESULT.json';numeric=read(numeric_path)
  for key,value in [('identity',executor),('execution_approval',b['execution_approval']),('artifact_identity',builder),('execution_binding',pin(bp)),('builder_handoff',b['builder_handoff']),('artifact_manifest',b['artifact_manifest']),('numeric_result',pin(numeric_path))]:need(flow.get(key)==value,'fixed flow binding '+key)
  need(flow.get('hardware_definitions')==1 and flow.get('profiles')==list(range(5)),'one fixed five profile hardware')
  need(flow.get('execution_mode')==admission['mode']and numeric.get('execution_mode')==admission['mode']and numeric.get('full_budget_sha256')==admission['reviewed_budget_sha256'],'mode budget binding')
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
   need(consumer.get('artifact_manifest_sha256')==b['artifact_manifest']['sha256']and started['binary_sha256']==frozen['common']['binary']['sha256'],'same actual artifact')
   ea=consumer.get('execution_admission',{})
   need(ea.get('execution_mode')==admission['mode']and ea.get('reviewed_budget_sha256')==admission['reviewed_budget_sha256']and ea.get('outer_cleanup_proof_required')is True,'actual consumer mode')
   need(ea.get('effective_limits')==cloud_budget.consumer_resource_limits(mode.consumer_limits(ea['original_limits'],admission,i),cloud_admission),'actual effective limits')
   parent_as=cloud_admission['consumer_address_space_bytes'];dut_as=cloud_admission['dut_address_space_bytes']
   expected_resource=dict(consumer_pre_fork_soft_bytes=parent_as,consumer_pre_fork_hard_bytes=dut_as,consumer_after_popen_hard_bytes=parent_as,dut_hard_address_space_bytes=dut_as,group_rss_is_sampled=True)
   need(consumer.get('resource_admission')==expected_resource and consumer['resource_admission'].get('group_rss_is_sampled') is True,'exact sampled group/resource admission')
   scope='FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'if admission['mode']==mode.FULL else'CALIBRATION_SAME_FULL_M128_STIMULUS'
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
  need(len(json.dumps(result).encode())<=65536,'bounded safe summary');return result
 except (ValueError,TypeError,KeyError,AttributeError,OSError,ImportError):return unavailable
