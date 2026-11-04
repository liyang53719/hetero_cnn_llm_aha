"""Explicit same-job P0 host diagnostic bridge, not FULL/cloud admission.
Source-only integration pending independent review and producer source closure.
No launcher runs at import. Caller supplies owning controller pins, never a review
manufactured from candidate output. All payloads remain inside the owning job.
"""
import contextlib,hashlib,importlib.util,json,os,pathlib,re,sys,time
P=pathlib.Path;HERE=P(__file__).resolve().parent
MODE='SAME_JOB_P0_M128_HOST_DIAGNOSTIC'
SCOPE=MODE+'_NOT_FULL_ACCEPTANCE'
SCHEMA='SAME_JOB_P0_M128_HOST_DIAGNOSTIC_BINDING_V1'
CONTEXT='ADMITTED_SAME_JOB_P0_HOST_DIAGNOSTIC_V1'
DRIVER_SHA='e4b23d01ee81a738220512eb24d63b4e323723f686c8af340ad64849a00b5887'
HARDWARE_SOURCE='prefill-supply-overlap-v1'
SOURCE_CONTRACT_SHA='634ecd3e0187844b7f97ef7ca9b0d38fdd274960bccc210a2419923164e05c24'
RELATION_SHA='0eb2261d28b1afd49692c40b578659a101a5fd5014655be18ededdc144110ddf'
GENERATION_SHA='d6b8f476cb4f586ff47a44d4f2155891f15e3bac99f56e45039c459093feaabb'
OVERLAY_SHA='a43e536bc0d0af808429f0730e4ad5fd6f949f4b4e1deb8194c1518eeacb521b'
RELATION_REL='candidates/prefill_host_diagnostic_20261103/SOURCE_RELATION.json'
CALIBRATION='BOUNDED_CALIBRATION';FULL='FULL_BLOCK_ACCEPTANCE';STAGE='STAGE_COVERAGE_DIAGNOSTIC';FIRST_FAULT='P0_FIRST_FAULT_DIAGNOSTIC'
PROGRAM_SHA='4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163'
FORBIDDEN=('cloud_binding','builder_handoff','executor_adaptation','model_candidate_review','finite_long_policy','first_fault_diagnostic','full_block_budget','stage_coverage_budget')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(row,cap=2<<20):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact independently supplied pin')
 p=P(row['path']);need(p.is_absolute()and p==p.resolve()and all(not x.is_symlink()for x in(p,*p.parents))and p.is_file(),'canonical regular pinned file')
 need(type(row['bytes'])is int and 0<=row['bytes']<=cap and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'actual bounded pinned bytes');return p
def load(row,cap=2<<20):return json.loads(pin(row,cap).read_text())
def filepin(p):
 p=P(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def module(path,pins,name):
 path=P(path);need(pins.get(str(path))==sha(path),'owning controller exact module pin '+name)
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
CANDIDATE_IMPORTS=('first_fault_policy','finite_watchdog_policy','host_profile_policy','first_fault_probe','terminal_finite_probe','first_fault_compilation','candidate_generation_gate','model_source_evidence')
@contextlib.contextmanager
def candidate_imports(repo,pins):
 root=P(repo)/'candidates/model_candidate_build_20261101';expected={name:root/(name+'.py')for name in CANDIDATE_IMPORTS}
 previous={name:sys.modules.get(name)for name in expected}
 for name,path in expected.items():
  need(path==path.resolve()and path.is_file()and all(not q.is_symlink()for q in(path,*path.parents))and pins.get(str(path))==sha(path),'fixed same-builder dependency '+name)
  old=previous[name]
  need(old is None or (getattr(old,'__file__',None)is not None and P(old.__file__).resolve()==path),'cached candidate module belongs to another source '+name)
 try:
  for name,path in expected.items():
   spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
  yield
 finally:
  for name,old in previous.items():
   if old is None:sys.modules.pop(name,None)
   else:sys.modules[name]=old

def verify_candidate_payload(root,identity,manifest_sha,repo,pins):
 with candidate_imports(repo,pins):
  pack=module(P(repo)/'candidates/model_candidate_build_20261101/pack_model_candidate.py',pins,'samejob_actual_candidate_pack')
  return pack.verify_candidate_seven(root,identity,manifest_sha)

def is_mode(value):return value==MODE
def forbidden(value):
 need(all(value.get(k)is None for k in FORBIDDEN),'same-job diagnostic cannot borrow cloud/FULL/readonly/finite authority')
def admit_controller(b):
 need(b.get('execution_mode')==MODE,'explicit separate host diagnostic mode');forbidden(b)
 need(b['profiles']==list(range(5))and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'same full five-profile hardware definition')
 d=b['host_diagnostic'];need(type(d)is dict and set(d)=={'scope','profiles','hardware_source','driver_sha256','source_contract','generation_contract','source_overlay','source_catalog','runner','wall_seconds','max_active_cycles','bootstrap_seconds'},'exact diagnostic contract fields')
 need(d['scope']==SCOPE and d['profiles']==[0]and d['hardware_source']==HARDWARE_SOURCE and d['driver_sha256']==DRIVER_SHA,'independent new P0 source scope')
 relation=b['host_profile_driver'];need(relation==dict(path=str(P(b['repo'])/RELATION_REL),sha256=RELATION_SHA),'explicit isolated host source relation')
 relation_path=P(relation['path']);pin(dict(relation,bytes=relation_path.stat().st_size),65536)
 need(d['generation_contract']['sha256']==GENERATION_SHA and d['source_overlay']['sha256']==OVERLAY_SHA,'same physical supply159 source domain')
 need(d['source_contract']['sha256']==SOURCE_CONTRACT_SHA and P(d['source_contract']['path']).name=='MODEL_P0_PREFILL_HOST_PROFILE_SOURCE_CONTRACT.json','separate fixed host source contract')
 need(d['wall_seconds']==14400 and d['max_active_cycles']==3000000,'fixed long diagnostic upper bounds, no short fallback')
 for k,hi in [('wall_seconds',14400),('max_active_cycles',1000000000),('bootstrap_seconds',1800)]:need(type(d[k])is int and 0<d[k]<=hi,'finite diagnostic '+k)
 need(d['bootstrap_seconds']<=b['budgets']['build']<=7200,'setup inside original build reservation')
 for k in ('source_contract','generation_contract','source_overlay','source_catalog','runner'):pin(d[k],4<<20)
 need(d['source_contract']['path']==str(P(b['repo'])/'candidates/gdn32_full_model_execution_20261104/numeric'/P(d['source_contract']['path']).name),'fixed local source contract role')
 return dict(mode=MODE,profile_seconds={'0':d['wall_seconds']},max_active_cycles=d['max_active_cycles'],diagnostic_profiles=[0],reviewed_budget_sha256=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest(),numerical_pass=False)
def reservations(b,admission):
 q=b['budgets'];need(admission['mode']==MODE and set(admission['profile_seconds'])=={'0'},'P0-only diagnostic upper window')
 for k in ('archives','weights','install','owner_bind','reference','provider','build','parent'):need(type(q[k])is int and q[k]>0,'finite phase budget')
 need(q['archives']<=1800 and q['weights']<=7200 and q['install']<=1800 and q['owner_bind']<=1800 and q['reference']<=1800 and q['build']==7200,'original per-stage caps inside aggregate envelope')
 # Continuous shared preparation meter clamps actual stages. Do not sum all
 # maxima, and do not mistake the static upper window for a frozen runtime lease.
 return 3600,9900,300+7200+3600+9000+900


def load_binding(args):
 path=getattr(args,'samejob_diagnostic_binding',None);expected=getattr(args,'samejob_diagnostic_binding_sha256',None)
 need(path is not None and expected is not None,'paired explicit same-job diagnostic invocation')
 row=dict(path=str(path),bytes=P(path).stat().st_size,sha256=expected);b=load(row)
 need(b['schema']==SCHEMA and b['execution_mode']==MODE and b['profile']==0,'actual P0 diagnostic invocation');forbidden(b)
 for key in ('cloud_binding','builder_handoff','executor_identity','full_block_budget','stage_coverage_budget'):
  need(getattr(args,key,None)is None and getattr(args,key+'_sha256',None)is None,'no other CLI authority')
 controller=load(b['controller_binding']);admission=admit_controller(controller)
 need(b['host_diagnostic']==controller['host_diagnostic']and b['host_profile_driver']==controller['host_profile_driver']and b['identity']==controller['artifact_identity']and b['repo']==controller['repo']and b['job_root']==controller['job_root']and b['job_started_monotonic']==controller['job_started_monotonic'],'same original controller/source/clock')
 need(b['pins']==dict(controller['pins'],**{b['controller_binding']['path']:b['controller_binding']['sha256']}),'exact controller closure plus controller binding')
 need(str(b['identity']['run_id'])==os.environ.get('GITHUB_RUN_ID')and b['identity']['launch_commit']==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','same first owning CI job')
 need(args.profile==0 and b['identity']['run_id']==args.expected_run_id and b['identity']['source_commit']==args.expected_source_commit and b['identity']['launch_commit']==args.expected_launch_commit,'same expected owner identity')
 need(b['artifact_manifest']['path']==str(args.artifact_manifest)and b['artifact_manifest']['sha256']==args.artifact_manifest_sha256 and b['build_result']['path']==str(args.local_build_result)and b['build_result']['sha256']==args.local_build_result_sha256,'same actual build and artifact invocation')
 need(P(b['controller_binding']['path'])==P(b['job_root']).parent/(P(b['job_root']).name+'-BINDING.json')and P(path).is_relative_to(P(b['job_root'])),'exact original sibling controller binding and job-local diagnostic binding')
 need(0<=time.monotonic()-b['job_started_monotonic']<21000,'same workflow clock not restarted')
 need(b['pins'].get(str(P(__file__).resolve()))==sha(__file__),'actual diagnostic bridge source pin')
 window_row=b.get('frozen_window')
 if window_row is not None:
  window=load(window_row,65536);need(P(window_row['path']).is_relative_to(P(b['job_root'])),'local one-shot window')
  need(window['schema']=='REAL_FULLTOP_P0_M128_LONG_HOST_DIAGNOSTIC_V1'and window['job_started_monotonic']==b['job_started_monotonic'],'same original frozen clock')
  wall=validate_window(window,b['job_started_monotonic'],time.monotonic())
  admission=dict(admission,profile_seconds={'0':wall},frozen_window=window_row,dut_deadline_monotonic=window['dut_deadline_monotonic'])
 return b,row,admission

def validate_window(window,job_started,now):
 import math
 frozen=window['frozen_at_monotonic'];elapsed=frozen-job_started;wall=window['dut_wall_seconds']
 need(all(type(x)in(int,float)and math.isfinite(x)for x in(frozen,job_started,now))and 0<=elapsed and frozen<=now,'finite actual freeze time')
 need(type(wall)is int and wall==min(14400,math.floor(21000-elapsed-900))and wall>=9000,'exact one-shot long diagnostic window')
 need(window['max_active_cycles']==3000000 and window['dut_deadline_monotonic']==frozen+wall and window['job_deadline_monotonic']==job_started+21000 and window['tail_deadline_monotonic']==min(job_started+21000,frozen+wall+900),'exact runtime cycle/deadline caps')
 need(window['extends_existing_lease']is False and window['restart_allowed']is False and window['full_block_acceptance']is False,'window cannot grant continuation/full acceptance')
 return wall

def remaining_limits(limits,admission,now):
 import math
 need(admission['mode']==MODE and 'frozen_window'in admission,'execute requires real one-shot window')
 remaining=math.floor(admission['dut_deadline_monotonic']-now)
 need(remaining>=9000,'INSUFFICIENT_LONG_DIAGNOSTIC_WINDOW_AFTER_PREFLIGHT_NO_DUT_START')
 r=dict(limits);r['wall_seconds']=min(r['wall_seconds'],remaining);r['cpu_seconds']=min(r['cpu_seconds'],r['wall_seconds']);r.update(diagnostic_scope=SCOPE,diagnostic_deadline_monotonic=admission['dut_deadline_monotonic'],diagnostic_window_sha256=admission['frozen_window']['sha256']);return r

def cap_before_popen(limits,now):
 import math
 if 'diagnostic_deadline_monotonic'not in limits:return None
 need(limits.get('diagnostic_scope')==SCOPE and re.fullmatch('[0-9a-f]{64}',limits.get('diagnostic_window_sha256',''))is not None,'explicit diagnostic deadline domain')
 deadline=limits['diagnostic_deadline_monotonic'];need(type(deadline)in(int,float)and math.isfinite(deadline)and type(now)in(int,float)and math.isfinite(now),'finite absolute launch deadline')
 remaining=math.floor(deadline-now);need(remaining>=9000,'INSUFFICIENT_LONG_DIAGNOSTIC_WINDOW_AT_POPEN_NO_DUT_START')
 limits['wall_seconds']=min(limits['wall_seconds'],remaining);limits['cpu_seconds']=min(limits['cpu_seconds'],limits['wall_seconds'])
 return dict(scope=SCOPE,window_sha256=limits['diagnostic_window_sha256'],popen_before_monotonic=now,absolute_deadline_monotonic=deadline,wall_seconds=limits['wall_seconds'],cpu_seconds=limits['cpu_seconds'],max_active_cycles=limits['max_active_cycles'])

def verify_build(args,frozen):
 b,row,admission=load_binding(args);artifact=pin(b['artifact_manifest'],65536);resultpath=pin(b['build_result'],65536);result=json.loads(resultpath.read_text())
 need(resultpath==P(b['job_root'])/'build/frontend/BUILD_ONLY_RESULT.json'and artifact==resultpath.parent/'frozen_artifact/frozen_artifact.json','same live build tree, never imported artifact')
 need(result['status']=='UNREVIEWED_MODEL_BUILD'and result['scope']=='MODEL_CANDIDATE_BYTES_REQUIRE_EXTERNAL_REVIEW_BEFORE_NUMERICS','preserve actual candidate build status, not a fabricated review')
 need(result['artifact']['manifest']==b['artifact_manifest']and frozen==json.loads(artifact.read_text())and frozen['artifact_identity']==b['identity'],'producer exact artifact and owner')
 need(frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'and frozen['profiles']==list(range(5))and frozen['common']['driver']['sha256']==DRIVER_SHA,'new mapper artifact with complete same hardware definition')
 compilation=verify_candidate_payload(artifact.parent,b['identity'],b['artifact_manifest']['sha256'],b['repo'],b['pins'])
 need(compilation['files']==7 and compilation['numerical_pass']is False and compilation['final_rtl_replay']is False,'compilation proof is not execution authority')
 return dict(status='SAME_JOB_CANDIDATE_COMPILATION_CONSISTENT_NOT_NUMERIC_ACCEPTANCE',scope=SCOPE,build_result_sha256=b['build_result']['sha256'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],controller_binding_sha256=b['controller_binding']['sha256'],diagnostic_binding=row,compilation=compilation,artifact_uploaded=False,downloaded_artifact_id=None,remote_api_verified=False,numerical_pass=False)

def source_context(args,frozen):
 b,row,admission=load_binding(args);proof=verify_build(args,frozen);d=b['host_diagnostic'];root=P(b['artifact_manifest']['path']).parent
 source_row=frozen['common']['source_manifest'];source=load(dict(source_row,path=str(root/source_row['path'])),16<<20)
 policy=module(P(b['repo'])/'candidates/model_candidate_build_20261101/host_profile_policy.py',b['pins'],'samejob_profiled_source_policy')
 need(policy.artifact_policy(source,DRIVER_SHA)is not None,'actual isolated mapper dependency/source relation')
 closure=source['model_candidate_observation']['source_closure'];need(closure['generation_contract_sha256']==d['generation_contract']['sha256']and closure['source_overlay']['sha256']==d['source_overlay']['sha256']and closure['source_pins_sha256']==d['source_catalog']['sha256']and closure['source_count']==159,'actual new fullTop generation/overlay/catalog domain')
 need(source['driver_sha256']==DRIVER_SHA and 'readonly_probe'not in source and 'finite_watchdog_driver'not in source,'no old readonly/finite evidence')
 need(source['generation_input_pins'].get(b['host_profile_driver']['path'])==RELATION_SHA,'actual isolated host source relation was a generation input')
 for key in ('generation_contract','source_overlay','source_contract'):
  need(source['generation_input_pins'].get(d[key]['path'])==d[key]['sha256'],'actual new generation source input '+key)
 contract=load(d['source_contract']);need(contract['schema']=='MODEL_CANDIDATE_P0_OBSERVATION_CONTRACT_V1','existing full original source role contract')
 evidence=source['model_source_evidence'];need(evidence['contract']['sha256']==d['source_contract']['sha256']and evidence['contract']['path']==d['source_contract']['path'],'actual contract bytes and origin remain unchanged')
 checker=HERE/'candidate_observation_contract.py';need(b['pins'].get(str(checker))==sha(checker),'actual candidate observation implementation')
 context=dict(schema=CONTEXT,candidate_scope=SCOPE,diagnostic_binding=row,controller_binding=b['controller_binding'],artifact_manifest=b['artifact_manifest'],source_manifest_sha256=source_row['sha256'],model_source_contract=d['source_contract'],builder_identity=b['identity'],repo=b['repo'],current_source_pins_pin=d['source_catalog'],candidate_observation_checker=filepin(checker),builder_source_commit=b['identity']['source_commit'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],anchors={},local_build_proof=proof)
 m=module(checker,b['pins'],'samejob_candidate_observation');context['anchors']=m.relocation_records(source,b['repo'],b['pins'],load(d['source_catalog'],4<<20),context)
 need(all(x['origin_path']==x['local']['path']for x in context['anchors'].values()),'same job source paths, no cross-job relocation')
 return context

def admitted_context(context):
 need(type(context)is dict and context.get('schema')==CONTEXT and context.get('candidate_scope')==SCOPE,'separate same-job diagnostic context')
 b=load(context['diagnostic_binding']);controller=load(b['controller_binding']);admit_controller(controller)
 need(b['schema']==SCHEMA and b['host_diagnostic']==controller['host_diagnostic']and b['host_profile_driver']==controller['host_profile_driver']and b['identity']==context['builder_identity']and b['artifact_manifest']==context['artifact_manifest']and context['controller_binding']==b['controller_binding'],'context exact actual owning binding')
 need(context['model_source_contract']==b['host_diagnostic']['source_contract']and context['current_source_pins_pin']==b['host_diagnostic']['source_catalog'],'context actual source domain');return b

def validate_runtime_cycles(limits,admission,driver_sha,artifact_sha):
 need(admission['mode']==MODE and driver_sha==DRIVER_SHA and limits['max_active_cycles']==1000000000,'original full program bound with new exact driver')
 need(type(admission['max_active_cycles'])is int and 0<admission['max_active_cycles']<=limits['max_active_cycles'],'finite diagnostic cycle cap only')
def consumer_limits(limits,admission,profile):
 need(profile==0 and admission['mode']==MODE,'diagnostic P0 only');r=dict(limits);r['wall_seconds']=min(limits['wall_seconds'],admission['profile_seconds']['0']);r['cpu_seconds']=min(limits['cpu_seconds'],r['wall_seconds']);r['max_active_cycles']=admission['max_active_cycles'];return r
def finite_long(admission):return False
