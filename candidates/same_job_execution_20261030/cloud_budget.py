"""Separately reviewed cloud lifecycle, independent of CI's 21000s envelope.
An independently operator-reviewed approval pin is mandatory; no default admission.
The pin must be provided by the trusted invoker, never derived from this file.
No JSON field authenticates its own author. Invocation records both external pins.
Per-phase original safety ceilings remain; full numerical acceptance is elsewhere.
"""
import hashlib,json,pathlib,re,math,platform,sys,importlib.util
P=pathlib.Path;D=P(__file__).resolve().parent
IDS=set(map(str,range(5)))
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(v,limit):
 need(type(v)is dict and set(v)=={'path','bytes','sha256'},'exact cloud evidence pin');p=P(v['path'])
 need(p.is_absolute()and p==p.resolve()and p.is_file()and all(not q.is_symlink()for q in(p,*p.parents)),'canonical cloud evidence')
 need(type(v['bytes'])is int and 0<v['bytes']<=limit and p.stat().st_size==v['bytes']and isinstance(v['sha256'],str)and re.fullmatch('[0-9a-f]{64}',v['sha256'])and sha(p)==v['sha256'],'bounded pinned cloud evidence')
 return p

MODEL_SCHEMA='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
MODEL_SCOPE='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'
FIRST_FAULT='P0_FIRST_FAULT_DIAGNOSTIC'
FIRST_FAULT_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1'
FIRST_FAULT_SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
def model_candidate_inputs(b):
 frozen=json.loads(pin(b['artifact_manifest'],65536).read_text())
 first_fault=b.get('execution_mode')==FIRST_FAULT
 need(first_fault==(frozen.get('schema')==FIRST_FAULT_SCHEMA),'first fault artifact requires exact explicit diagnostic mode')
 candidate=frozen.get('schema')in(MODEL_SCHEMA,FIRST_FAULT_SCHEMA)
 if candidate:
  need(frozen.get('status')=='UNREVIEWED_MODEL_BUILD','immutable unreviewed model artifact')
  need(b.get('model_candidate_review')is not None,'MODEL_CANDIDATE_REVIEW_REQUIRED')
  review=json.loads(pin(b['model_candidate_review'],2<<20).read_text())
  need(first_fault==(review.get('schema')=='MODEL_CANDIDATE_FIRST_FAULT_REVIEW_V1'),'first fault review requires exact explicit diagnostic mode')
 else:need('model_candidate_review'not in b,'model review cannot relabel legacy artifact')
 return candidate

def admit(b):
 need(b.get('execution_context')=='CLOUD_EXECUTOR_V1','explicit cloud executor context')
 need(b.get('execution_approval') is not None,'OPERATOR_APPROVED_EXECUTION_INPUT_REQUIRED')
 candidate=model_candidate_inputs(b)
 stage=b.get('execution_mode')=='STAGE_COVERAGE_DIAGNOSTIC'
 first_fault=b.get('execution_mode')==FIRST_FAULT
 need(not first_fault or (b.get('full_block_budget')is None and 'stage_coverage_budget'not in b),'first fault excludes full/stage budgets')
 need(not stage or candidate,'stage diagnostic requires model candidate')
 need(stage or 'stage_coverage_budget'not in b,'stage budget forbidden in legacy mode')
 need('p0_provider_reuse'not in b or ((stage or first_fault) and candidate),'P0 provider reuse requires stage candidate')
 reference_reuse='reference_data_reuse'in b
 need(not reference_reuse or ((stage or first_fault) and candidate),'reference data reuse requires stage candidate')
 need(reference_reuse or 'aggregate_tree_cap_bytes'not in b,'tree cap requires reference data reuse')
 adaptation_fields={'executor_adaptation','workspace_loader'}
 adapted=bool(adaptation_fields & set(b))
 need(not adapted or adaptation_fields<=set(b),'paired executor adaptation and workspace loader required')
 optional_fields=({'retained_materials'}if 'retained_materials'in b else set())|({'model_candidate_review'}if candidate else set())
 extra_fields=(adaptation_fields if adapted else set())|optional_fields|({'stage_coverage_budget'}if stage else set())|({'p0_provider_reuse'}if 'p0_provider_reuse'in b else set())|({'reference_data_reuse'}if reference_reuse else set())
 approval_extra={k+'_sha256'for k in extra_fields}
 approval_path=pin(b['execution_approval'],65536);approval=json.loads(approval_path.read_text())
 need(set(approval)=={'schema','approved','authority','purpose','source_commit','budget_sha256','artifact_manifest_sha256','execution_id','host_identity_sha256','review_evidence'}|approval_extra,'exact independent execution approval')
 need(approval['schema']=='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1'and approval['approved']is True and approval['authority']=='USER_AUTHORIZED_OPERATOR_REVIEW','independent review scope')
 need(approval['source_commit']==b['identity']['source_commit']and approval['execution_id']==b['identity']['execution_id']and approval['host_identity_sha256']==b['identity']['host_identity_sha256'],'approved exact execution/source/host')
 need(approval['artifact_manifest_sha256']==b['artifact_manifest']['sha256'],'approved actual build artifact')
 pin(approval['review_evidence'],2<<20)
 if extra_fields:
  for k in extra_fields:
   pin(b[k],2<<20);need(approval[k+'_sha256']==b[k]['sha256'],'approved exact '+k)
 p=pin(b['cloud_budget'],65536);need(b['cloud_budget']['sha256']==approval['budget_sha256'],'externally approved exact cloud budget')
 d=json.loads(p.read_text())
 need(set(d)=={'schema','ready','source_commit','host_identity','artifact_manifest_sha256','basis','job_budget_seconds','budgets','dut_rss_bytes','dut_address_space_bytes','numeric_reserved_increment_bytes','execution_mode','full_block_budget','reserved_other_owner_bytes','consumer_address_space_bytes','resource_scope','stage_resources','runtime_mode','archive_mode','runtime_reuse_manifest'}|extra_fields|({'aggregate_tree_cap_bytes'}if reference_reuse else set()),'exact cloud lifecycle admission')
 if extra_fields:
  for k in extra_fields:need(d[k]==b[k],'reviewed adaptation input '+k)
 if reference_reuse:
  need(type(d['aggregate_tree_cap_bytes'])is int and d['aggregate_tree_cap_bytes']==12037043872,'exact reduced reference reuse aggregate tree cap')
  need('aggregate_tree_cap_bytes'not in b or (type(b['aggregate_tree_cap_bytes'])is int and b['aggregate_tree_cap_bytes']==d['aggregate_tree_cap_bytes']),'binding exact reduced aggregate tree cap')
 need(d['schema']=='FIVE_M128_CLOUD_LIFECYCLE_BUDGET_V1'and d['ready']is True,'cloud admission ready')
 need(d['source_commit']==b['identity']['source_commit'],'same frozen cloud source')
 host=pin(d['host_identity'],65536);host_observation(json.loads(host.read_text()),b['identity']);need(d['host_identity']['sha256']==b['identity']['host_identity_sha256'],'exact independently reviewed actual host identity')
 need(d['artifact_manifest_sha256']==b['artifact_manifest']['sha256'],'actual received binary manifest admission')
 need(set(d['basis'])=={'resource_audit','independent_review'},'actual resource audit and independent review')
 for v in d['basis'].values():pin(v,2<<20)
 if first_fault:
  need(d['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME' and d['archive_mode']=='READ_EXISTING_PINNED_ARCHIVES','first fault requires original pinned runtime/archive import')
 if reference_reuse:
  need(d['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME' and d['archive_mode']=='READ_EXISTING_PINNED_ARCHIVES','reference reuse requires original pinned runtime and archive import')
 if d['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME':
  need(d['archive_mode']=='READ_EXISTING_PINNED_ARCHIVES','reuse runtime requires exact existing archive revalidation')
  pin(d['runtime_reuse_manifest'],65536)
 else:
  need(d['runtime_mode']=='FRESH_ORIGINAL_RUNTIME_INSTALL'and d['archive_mode']=='DOWNLOAD_ORIGINAL_ARCHIVES'and d['runtime_reuse_manifest']is None,'explicit fresh or readonly reuse runtime mode')
 q=d['budgets'];caps={'archives':1800,'weights':7200,'install':1800,'owner_bind':1800,'reference':1800,'provider':180,'parent':600}
 need(type(q)is dict and set(q)==set(caps)|{'calibration_seconds'},'cloud no build phase/reservation')
 need(all(type(q[k])is int and 0<q[k]<=v for k,v in caps.items()),'original phase ceilings retained')
 need(type(q['calibration_seconds'])is dict and set(q['calibration_seconds'])==IDS and all(type(v)is int and 0<v<=300 for v in q['calibration_seconds'].values()),'only explicit up-to300s calibration windows')
 need(d['execution_mode']in('BOUNDED_CALIBRATION','FULL_BLOCK_ACCEPTANCE','STAGE_COVERAGE_DIAGNOSTIC',FIRST_FAULT)and approval['purpose']==d['execution_mode'],'explicit approved cloud execution mode')
 need(stage==(d['execution_mode']=='STAGE_COVERAGE_DIAGNOSTIC'),'binding stage mode equals approved budget')
 need(first_fault==(d['execution_mode']==FIRST_FAULT),'binding first fault mode equals approved budget')
 if d['execution_mode']in('BOUNDED_CALIBRATION','STAGE_COVERAGE_DIAGNOSTIC',FIRST_FAULT):
  need(d['full_block_budget']is None and d['resource_scope']==('CURRENT_HOST_P0_FIRST_FAULT_DIAGNOSTIC'if first_fault else 'CURRENT_HOST_STAGE_COVERAGE_DIAGNOSTIC'if stage else 'CURRENT_HOST_BOUNDED_RESOURCE_DIAGNOSTIC'),'explicit calibration diagnostic scope')
  need(type(d['dut_rss_bytes'])is int and type(d['dut_address_space_bytes'])is int and 0<d['dut_rss_bytes']<=2684354560 and 0<d['dut_address_space_bytes']<=2684354560,'current host diagnostic2.5GiB envelope, not original8/12GiB')
 else:
  need(d['resource_scope']=='FULL_BLOCK_MEASURED_RESOURCE_PLAN','full measured resource scope')
  pin(d['full_block_budget'],65536) # existing execution_mode.admit independently requires approved full evidence
 need(type(d['job_budget_seconds'])is int and 0<d['job_budget_seconds']<=2**31-1,'reviewed finite cloud deadline, no CI default')
 need(type(d['dut_rss_bytes'])is int and 0<d['dut_rss_bytes']<=8<<30,'no expanded original DUT RSS ceiling')
 need(type(d['consumer_address_space_bytes'])is int and d['consumer_address_space_bytes']==512<<20,'reviewed consumer512MiB envelope')
 need(type(d['dut_address_space_bytes'])is int and 0<d['dut_address_space_bytes']<=12<<30,'no expanded original DUT address space')
 need(type(d['numeric_reserved_increment_bytes'])is int and 0<d['numeric_reserved_increment_bytes']<=512<<20,'original numeric increment ceiling')
 roles=d['stage_resources'];need(type(roles)is dict and set(roles)=={'install','reference'},'explicit installation/reference resource roles')
 for role in roles:
  values=roles[role];need(type(values)is dict and set(values)=={'rss_bytes','as_bytes'}and all(type(v)is int and v>0 for v in values.values()),'exact finite role resource limits')
  rss_cap=2684354560 if d['execution_mode']in('BOUNDED_CALIBRATION','STAGE_COVERAGE_DIAGNOSTIC',FIRST_FAULT)else 3<<30
  as_cap=2684354560 if d['execution_mode']in('BOUNDED_CALIBRATION','STAGE_COVERAGE_DIAGNOSTIC',FIRST_FAULT)else (4<<30 if role=='install'else 8<<30)
  need(values['rss_bytes']<=rss_cap and values['as_bytes']<=as_cap,'no expanded role resource ceiling')
 need(type(d['reserved_other_owner_bytes'])is int and d['reserved_other_owner_bytes']==5<<30,'preserve unknown owner5GiB reservation')
 result={k:d[k]for k in('runtime_mode','archive_mode','runtime_reuse_manifest','stage_resources','consumer_address_space_bytes','reserved_other_owner_bytes','job_budget_seconds','budgets','dut_rss_bytes','dut_address_space_bytes','numeric_reserved_increment_bytes','execution_mode','full_block_budget')}
 if extra_fields:result.update({k:d[k]for k in extra_fields})
 if reference_reuse:result['aggregate_tree_cap_bytes']=d['aggregate_tree_cap_bytes']
 if candidate:
  path=D/'numeric/candidate_admission.py';need(b['pins'].get(str(path))==sha(path),'model candidate admission source pin')
  spec=importlib.util.spec_from_file_location('budget_model_candidate_admission',path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
  reviewed=helper.verify(b['model_candidate_review'],b)
  need(reviewed['scope']==(FIRST_FAULT_SCOPE if first_fault else MODEL_SCOPE) and reviewed['artifact_manifest_sha256']==b['artifact_manifest']['sha256'],'exact model candidate evaluation scope/artifact')
 if stage:
  path=D/'execution_mode.py';need(b['pins'].get(str(path))==sha(path),'stage mode verifier source pin')
  spec=importlib.util.spec_from_file_location('cloud_stage_mode',path);mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)
  mode.stage_admission(b) # pure: never recursively calls cloud admission
 if first_fault:
  path=D/'execution_mode.py';need(b['pins'].get(str(path))==sha(path),'first fault mode verifier source pin')
  spec=importlib.util.spec_from_file_location('cloud_first_fault_mode',path);mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)
  admitted=mode.first_fault_admission(b) # pure authority check, no recursive cloud admission
  result['diagnostic_profiles']=admitted['diagnostic_profiles']
 return result


def host_observation(d,identity):
 need(type(d)is dict and set(d)=={'schema','boot_id','architecture','python_version','avx512f','physical_memtotal_bytes','observed_memavailable_bytes','observed_monotonic'},'exact host observation schema')
 need(d['schema']=='CLOUD_EXECUTOR_HOST_OBSERVATION_V1'and d['boot_id']==identity['boot_id'],'actual executor boot identity')
 need(d['architecture']=='x86_64'and d['python_version']==[3,12]and all(type(v)is int for v in d['python_version'])and d['avx512f']is True,'original runtime host capability, not numerical qualification')
 need(all(type(d[k])is int and d[k]>0 for k in('physical_memtotal_bytes','observed_memavailable_bytes'))and d['observed_memavailable_bytes']<=d['physical_memtotal_bytes'],'memory observation bounded')
 need(type(d['observed_monotonic'])in(int,float)and math.isfinite(d['observed_monotonic'])and 0<=d['observed_monotonic']<=identity['started_monotonic'],'host observation on same boot before admission')
 return d

def verify_host(host_pin,identity):
 d=host_observation(json.loads(pin(host_pin,65536).read_text()),identity)
 need(P('/proc/sys/kernel/random/boot_id').read_text().strip()==d['boot_id'],'current host boot not prior runner')
 need(platform.machine()==d['architecture']and list(sys.version_info[:2])==d['python_version'],'current host interpreter ABI')
 need('avx512f'in P('/proc/cpuinfo').read_text().split(),'actual original P0 AVX512 gate')
 fields={x.split(':')[0]:int(x.split()[1])*1024 for x in P('/proc/meminfo').read_text().splitlines()if x.startswith('MemTotal:')}
 need(fields['MemTotal']==d['physical_memtotal_bytes'],'same observed host physical memory')
 return d # No old MemAvailable is used as live admission; stage lock samples again.


def consumer_resource_limits(effective,admitted):
 result=dict(effective);value=admitted['dut_address_space_bytes']
 need(type(value)is int and admitted['consumer_address_space_bytes']<=value<=result['address_space_bytes'],'no expanded original DUT address space')
 result['address_space_bytes']=value
 return result
