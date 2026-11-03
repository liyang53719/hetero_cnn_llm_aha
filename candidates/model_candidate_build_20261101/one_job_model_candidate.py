"""TEMP actual single-build orchestration, not yet admitted or integrated-tested.
Explicit pinned binding supplies real tools/provider filelists and independently
reviewed runtime-preparation/comparison entrypoints. Missing inputs fail before
hardware launch. No shell, default execution, implicit retry or self-learned pins.
"""
import argparse,hashlib,json,pathlib,os,sys,time,subprocess
C=pathlib.Path(__file__).resolve().parent
D=C.parent/'ci_frontend_pipeline_r2_20261029'
sys.path.insert(0,str(D));sys.path.insert(0,str(C));import supervise_multiroot as supervise
from check_contract import PROFILES
from run_frontend_serial import run_frontend_serial
from candidate_binary_producer import admit_build,prepare,run
from candidate_build_producer import CHILDREN
from pack_model_candidate import pack
from candidate_generation_gate import require_generation_binding,checked_paths

def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def pinned(p,h):
 p=pathlib.Path(p).absolute();need(p.is_file() and not p.is_symlink() and sha(p)==h,'pin mismatch '+str(p));return p
# Safe finite projection only: never copy argv, raw errors, paths, compiler logs,
# process rows, source bodies or arbitrary report keys to Actions stdout.
BUILD_STAGE_NAMES=('compile_model_sources','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4','archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link')
BUILD_ERROR_CODES={
 'ValueError: wall cap':'WALL_CAP',
 'InterruptedError: signal 14':'MONITOR_SIGALRM',
 'ValueError: prelaunch work deadline':'PRELAUNCH_DEADLINE',
 'ValueError: sampled observed aggregate RSS cap':'SAMPLED_RSS_CAP',
 'ValueError: sampled observed aggregate CPU cap':'SAMPLED_CPU_CAP',
 'ValueError: locked memory gate':'PRELAUNCH_MEMORY_GATE',
 'ValueError: locked disk gate':'PRELAUNCH_DISK_GATE',
 'ValueError: entry cap':'ENTRY_CAP',
 'ValueError: file cap':'FILE_CAP',
 'ValueError: sampled aggregate writable-root cap':'AGGREGATE_TREE_CAP',
 'ValueError: sampled stage output tree cap':'STAGE_TREE_CAP',
 'ValueError: sampled disk reserve':'DISK_RESERVE',
 'ValueError: sampled log cap':'LOG_CAP',
 'ValueError: log reader failure':'LOG_READER_FAILURE',
 'ValueError: log EOF missing after cleanup':'LOG_EOF_MISSING',
 'RuntimeError: capture missing EOF; no full log claim':'LOG_EOF_MISSING',
 'ValueError: reader completion deadline':'READER_DEADLINE',
 'ValueError: reader join deadline':'READER_DEADLINE',
 'ValueError: post-cleanup deadline':'POST_CLEANUP_DEADLINE',
 'ValueError: proc enumeration cap':'PROC_ENUMERATION_CAP',
 'ValueError: observed process cap':'OBSERVED_PROCESS_CAP',
 'ValueError: tracked PID reused within owned set':'TRACKED_PID_REUSED',
 'ValueError: RSS telemetry 64MiB cap':'RSS_TELEMETRY_CAP',
 'ValueError: output link forbidden':'OUTPUT_LINK_FORBIDDEN',
 'ValueError: nonregular output':'NONREGULAR_OUTPUT',
 'ValueError: observed identities remain after group cleanup':'OBSERVED_IDENTITIES_REMAIN',
 'InterruptedError: signal 2':'MONITOR_SIGINT',
 'InterruptedError: signal 15':'MONITOR_SIGTERM',
}
def build_error_details(errors):
 # Deliberately no paths, arbitrary class names, raw messages, argv, or tracebacks.
 # A recorded class/errno is a symptom, not a process location or root cause.
 import re
 classes={'OSError','FileNotFoundError','ProcessLookupError','PermissionError','InterruptedError','TimeoutError','BlockingIOError','ChildProcessError','BrokenPipeError','IsADirectoryError','NotADirectoryError','FileExistsError','ConnectionError','ValueError','RuntimeError','TypeError','KeyError','IndexError','StopIteration','MemoryError','OverflowError','UnicodeDecodeError','SystemExit','KeyboardInterrupt','_Invalid','_Deadline','CleanupFailure'}
 os_classes={'OSError','FileNotFoundError','ProcessLookupError','PermissionError','InterruptedError','TimeoutError','BlockingIOError','ChildProcessError','BrokenPipeError','IsADirectoryError','NotADirectoryError','FileExistsError','ConnectionError'}
 rows=[]
 if type(errors)is not list:return rows
 for error in errors[:16]:
  row={'origin':'UNKNOWN','exception_class':'UNKNOWN','errno':None,'reason_code':'MALFORMED_ERROR'}
  if type(error)is str:
   row.update(origin='LOG_READER' if error.startswith('log_reader: ') else 'SUPERVISOR',reason_code=BUILD_ERROR_CODES.get(error,'UNCLASSIFIED_SUPERVISOR_ERROR'))
   prefix=error[:192]
   if row['origin']=='LOG_READER':prefix=prefix[len('log_reader: '):]
   name,separator,rest=prefix.partition(': ')
   if separator and name in classes:
    row['exception_class']=name
    matched=re.match(r'^\[Errno ([1-9][0-9]{0,3})\](?: |$)',rest) if name in os_classes else None
    if matched and int(matched.group(1))<=4095:row['errno']=int(matched.group(1))
  rows.append(row)
 return rows

def build_stage_diagnostic(name,report,receipt_path):
 import math
 def number(v):
  return v if type(v)in(int,float)and 0<=v<=2**53 and math.isfinite(v) else None
 def boolean(v):return v if type(v)is bool else None
 def obj(v):return v if type(v)is dict else {}
 r=obj(report);errors=r.get('errors');valid_errors=type(errors)is list
 categories=sorted({BUILD_ERROR_CODES.get(e,'UNCLASSIFIED_SUPERVISOR_ERROR') if type(e)is str else 'MALFORMED_ERROR' for e in errors[:256]}) if valid_errors else ['MALFORMED_ERROR_LIST']
 if valid_errors and len(errors)>256:categories.append('ERROR_LIST_TRUNCATED')
 caps=obj(r.get('caps'));cleanup=obj(r.get('cleanup_proof'));capture=obj(r.get('log_capture'))
 native=r.get('native_exit');native=native if type(native)is int and -128<=native<=255 else None
 receipt_sha=None
 try:
  if receipt_path.is_file()and not receipt_path.is_symlink():receipt_sha=sha(receipt_path)
 except OSError:pass
 result=dict(schema='BOUNDED_BUILD_STAGE_DIAGNOSTIC_V1',stage=name if name in BUILD_STAGE_NAMES else 'UNKNOWN_STAGE',receipt_sha256=receipt_sha,
  worker_started=boolean(r.get('worker_started')),native_exit=native,error_count=min(len(errors),2**31-1) if valid_errors else None,error_categories=categories,error_details=build_error_details(errors),error_details_truncated=valid_errors and len(errors)>16,
  elapsed_seconds=number(r.get('elapsed_seconds')),observed_cpu_seconds=number(r.get('observed_cpu_seconds')),observed_peak_rss=number(r.get('observed_peak_rss')),peak_tree_bytes=number(r.get('peak_tree_bytes')),peak_file_bytes=number(r.get('peak_file_bytes')),
  caps={k:number(caps.get(k)) for k in ('wall_seconds','cleanup_seconds','rss_bytes','cpu_seconds','per_process_as_bytes','per_process_cpu_seconds','file_bytes','tree_bytes','watch_tree_bytes','max_entries')},
  cleanup_complete=cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof_observed=boolean(capture.get('pipe_eof_observed')),gzip_finalized=boolean(capture.get('gzip_finalized')),
  numerical_pass=False,final_rtl_replay=False)
 # native nonzero with no supervisor error is NOT classified as compiler/OOM.
 raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)
 if len(raw.encode())>8192:raise ValueError('bounded diagnostic schema overflow')
 return raw

def post_build_failure_diagnostic(phase,exc):
 # Fixed bounded diagnostic only. Original exception still aborts the build.
 import re
 phases={'IDENTITY','SOURCE_PINS','OBSERVATION','STAGE_RECEIPTS','COMPILE_OUTPUTS','ENRICH','COPY','FINAL'}
 reasons={'SOURCE_PIN_SET','SOURCE_PIN_HASH_FORMAT','SOURCE_PIN_PATH','SOURCE_PIN_SIZE','SOURCE_PIN_HASH_MISMATCH','STAGE_VALIDATION_FAILED'}
 classes={'ValueError','TypeError','FileNotFoundError','PermissionError','OSError','JSONDecodeError','UnicodeDecodeError','OTHER'}
 def enum(v,allowed,fallback):return v if type(v)is str and v in allowed else fallback
 def integer(v,cap):return v if type(v)is int and 0<=v<=cap else None
 def digest(v):return v if type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None else None
 raw=getattr(exc,'model_pack_diagnostic',None)
 valid=type(raw)is dict and set(raw)=={'schema','phase','reason','exception_class','index','bytes','expected_sha256','actual_sha256'} and raw.get('schema')=='MODEL_PACK_FAILURE_V1'
 r=raw if valid else {}
 result=dict(schema='MODEL_POST_BUILD_FAILURE_DIAGNOSTIC_V1',phase=enum(phase,('admit_build','prepare','run','pack'),'UNKNOWN'),pack_phase=enum(r.get('phase'),phases,'UNKNOWN'),reason=enum(r.get('reason'),reasons,'UNCLASSIFIED'),exception_class=enum(r.get('exception_class'),classes,enum(type(exc).__name__,classes,'OTHER')),index=integer(r.get('index'),1000000),bytes=integer(r.get('bytes'),4<<30),expected_sha256=digest(r.get('expected_sha256')),actual_sha256=digest(r.get('actual_sha256')),numerical_pass=False,post_build_structure_accepted=False)
 need(len(json.dumps(result,sort_keys=True).encode())<=2048,'bounded post-build diagnostic')
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--binding',type=pathlib.Path,required=True);ap.add_argument('--binding-sha256',required=True);ap.add_argument('--execute-reviewed-once',action='store_true');a=ap.parse_args()
 b=load(pinned(a.binding,a.binding_sha256));need(b['schema']=='MODEL_CANDIDATE_BUILD_BINDING_V1','schema');generation=require_generation_binding(b)
 plan=load(D/'BUILD_PLAN.json')
 need(plan['schema']=='FIXED_SHARED_BUILD_ONLY_PLAN_V1' and plan['mode']=='BUILD_ONLY' and plan['matrix_mac']==4096 and plan['vector_lanes']==32 and plan['profiles']==PROFILES and plan['builds']==1 and plan['tokens']==128,'exact shared build plan')
 need(plan['numeric_execution'] is False and plan['cpp_compile_link'] is True and plan['timeout_seconds']==21000 and plan['owned_tree_cap_bytes']==12_081_306_272 and plan['min_free_reserve_bytes']==1_500_000_000,'explicit build-only resources')
 need(plan['artifact_file_whitelist']==['dut.bin','hardware.sv','driver.cpp','source_manifest.json','tool_manifest.json','build_receipt.json','frozen_artifact.json'] and plan['summary_cap_bytes']==65536,'exact artifact whitelist')
 job_budget=b.get('job_budget_seconds')
 need(type(job_budget) is int and 0<job_budget<=7200,'explicit remaining build-only budget including prep')
 need(b.get('mode')=='BUILD_ONLY','explicit build-only execution scope')
 # These must be provided by independently reviewed preparers, never constructed
 # by this execution driver from untrusted run output or an accepted PASS string.
 required=['repo','repo_sha','java','verilator','make','python','pins','generation_contract','generation_contract_sha256','unchanged_module_contract','host_port_contract','provider_sources','idma_include_dirs','idma_defines','hierarchy','driver','driver_include','helper_sources','output','fixed_source_overlay','fixed_source_validator','materialized_roots','sv_identity_script']
 required += ['artifact_identity','compile_tools','compile_tool_manifest']
 need(all(k in b for k in required),'missing concrete portable binding fields')
 repo=pathlib.Path(b['repo']).resolve();out=pathlib.Path(b['output']).resolve();need(not out.exists(),'fresh one-shot output')
 need(len(b['idma_include_dirs'])==8 and len(b['idma_defines'])==4,'exact lifted includes/defines')
 for p,h in b['pins'].items():pinned(p,h)
 # New HIGH identity is observed below, never used as an accepted baseline.
 for key in ['java','verilator','make','python','hierarchy','driver']:
  need(b[key] in b['pins'],'required tool/source pin '+key)
 need(all(x in b['pins'] for x in b['provider_sources']+b['helper_sources']),'source closure pin')
 need(all(str(p)in b['pins']for p in C.glob('*.py')),'complete candidate executable closure')
 for name in ('conditional_binary_producer.py','conditional_admission.py','build_producer.py','OBSERVER_HOST_PORTS_122.json','observer_baseline_gate.py','pack_frozen_artifact.py','driver_dependency_proof.py','p0_source_evidence.py'):
  need(str(D/name) in b['pins'],'build helper source pin '+name)
 need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==b['repo_sha'],'exact checked-out source commit')
 original=repo/'candidates/fresh_original_top_recovery_20261028';manifest=original/'SOURCE_AND_TOOLCHAIN_PINS.json';need(str(manifest) in b['pins'],'source manifest itself independently pinned');m=load(manifest);need(len(m['sources'])==155,'155 original sources')
 # NEW R2 recovery manifest is distinct from the original source/tool lock.
 # Never compile the stale old155 source list after the HostCommands fix.
 need(b['fixed_source_validator'] in b['pins'] and b['fixed_source_overlay'] in b['pins'],'fixed overlay/validator pin')
 source_paths=checked_paths(repo,b['fixed_source_overlay'],m,generation)
 manifest=pathlib.Path(b['fixed_source_overlay'])
 from first_fault_policy import binding_policy
 from finite_watchdog_policy import expected_driver_sha
 diagnostic=binding_policy(b)
 need(b['pins'][b['driver']]==expected_driver_sha(b),'fixed final-state driver')
 jars=[];plugin=None
 for x in m['jars']:
  p=original/'cache'/x['maven_path'];pinned(p,x['sha256'])
  if x['role']=='plugin':plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin,'exact ordered JAR/plugin closure')
 cp=':'.join(jars)
 if not a.execute_reviewed_once:print('TEMP_PREFLIGHT_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS');return
 out.mkdir();start=time.monotonic();stages=[];results=[];lock=out/'exclusive.lock'
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','MAKEFLAGS':'-j1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
 def disk_gate(additional_bytes=0):
  # Include dependency caches, checkout and runtime acquisition, not only outputs.
  roots=[out,repo]+[pathlib.Path(x).resolve() for x in b['materialized_roots']]
  need(all(p.is_absolute() for p in roots),'absolute owned disk roots')
  unique=[]
  for p in sorted(set(roots),key=lambda x:len(x.parts)):
   if not any(p.is_relative_to(parent) for parent in unique):unique.append(p)
  seen=set();total=0
  for root in unique:
   if not root.exists():continue
   for f in root.rglob('*'):
    if f.is_symlink():continue
    if f.is_file():
     st=f.stat();identity=(st.st_dev,st.st_ino)
     if identity not in seen:total+=st.st_size;seen.add(identity)
  need(total+additional_bytes<=12_081_306_272,'owned data cap excluding safety reserve')
  import shutil
  need(shutil.disk_usage(out).free>=1_500_000_000+additional_bytes,'preserve disk reserve; no automatic deletion')
 def stage(name,argv,seconds=600,rss=5,tree=2_000_000_000,accepted_exit_codes=(0,),env_override=None,extra_watch_roots=None,extra_pins=None):
  for path,target in b.get('fresh_host_aliases',{}).items():need(str(pathlib.Path(path).resolve(strict=True))==target,'fresh runtime alias drift')
  disk_gate()
  left=job_budget-(time.monotonic()-start);need(left>seconds+60,'remaining build-only deadline reserve')
  caps=dict(jdk_aliases=b['jdk_aliases'],wall_seconds=seconds,cleanup_seconds=30,file_bytes=536870912,tree_bytes=tree,log_bytes=150_000_000,raw_log_bytes=1073741824,max_entries=100000,per_process_as_bytes=15*1024**3,per_process_cpu_seconds=seconds,rss_bytes=rss*1024**3,cpu_seconds=seconds,extra_watch_roots=[str(repo),str(out)]+b['materialized_roots']+(extra_watch_roots or []),min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  stage_env=dict(env);stage_env.update(env_override or {});stage_pins=dict(b['pins']);stage_pins.update(extra_pins or {})
  try:
   r=supervise.execute(argv,str(out/name),str(lock),caps,stage_env,stage_pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
   print('BUILD_STAGE_DIAGNOSTIC '+build_stage_diagnostic(name,r,out/name/'RESULT.json'),flush=True)
   if name=='original_high':
    from original_ir_diagnostic import project as project_original_ir_diagnostic
    print('MODEL_ORIGINAL_IR_DIAGNOSTIC '+project_original_ir_diagnostic(out/name,r),flush=True)
   if name in ('canonical_full','transform_new_toolchain','emit_host'):
    from candidate_diagnostic import read_projection
    print('MODEL_CANDIDATE_DIAGNOSTIC '+read_projection(out/name/'MODEL_CANDIDATE_DIAGNOSTIC.json',name),flush=True)
  finally:
   for path,target in b.get('fresh_host_aliases',{}).items():need(str(pathlib.Path(path).resolve(strict=True))==target,'fresh runtime alias drift after stage')
  stages.append(dict(name=name,status=r['status'],native_exit=r['native_exit'],rss=r['observed_peak_rss'],elapsed=r['elapsed_seconds']));(out/'stage_exits.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(r['native_exit'] in accepted_exit_codes and not r['errors'] and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','stage failed/incomplete: '+name);disk_gate()
  return r
 def java(heap,classpath,main,args=()):return [b['java'],'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-cp',classpath,main,*args]
 try:
  stage('compile_model_sources',java('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.']+source_paths),300,3)
  basecp=str(out/'compile_model_sources')+':'+cp
  stage('helper_compile',java('2g',cp,'scala.tools.nsc.Main',['-classpath',basecp,'-Xplugin:'+plugin,'-d','.']+b['helper_sources']),300,3)
  helpercp=str(out/'helper_compile')+':'+basecp
  stage('original_high',java('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'),600,6)
  stage('canonical_micro',java('512m',helpercp,'chiseltest.simulator.CanonicalInfoMicroTest'),120,1)
  high=str(out/'original_high/host-diagnostic/original-high.fir');ann=str(out/'original_high/host-diagnostic/high-annotations.json')
  stage('canonical_full',java('2g',helpercp,'chiseltest.simulator.ModelCandidateHighDescriptorV1',[high,ann,'canonical.tsv','details.json','ordered-annotations.json']),300,3)
  canonical=out/'canonical_full/canonical.tsv'
  b['observed_canonical_sha256']=sha(canonical)
  b['observed_canonical']=str(canonical.resolve())
  b['pins'][str(canonical.resolve())]=sha(canonical)
  stage('transform_new_toolchain',java('2g',helpercp,'chiseltest.simulator.ModelCandidateTransformGateV1',[high,str(canonical),sha(canonical),'transform-preconditions.json']),300,3)
  stage('emit_host',java('4g',helpercp,'chiseltest.simulator.ModelCandidateHostSimulationEmitterV1',[high,ann,str(canonical),sha(canonical),b['unchanged_module_contract'],generation['unchanged_module_contract_sha256']]),900,6)
  stage('sv_identity',[b['python'],'-B',b['sv_identity_script'],'--sv',str(out/'emit_host/compiled-host/HostBlockTopV4.sv'),'--output','sv-identity.json'],180,1)
  stage('emit_fma',java('2g',helpercp,'chiseltest.simulator.EmitPhysicalFmaStageLibrary',['fma']),300,3)
  host=out/'emit_host/compiled-host/HostBlockTopV4.sv';fma=out/'emit_fma/fma/PhysicalFmaStageLibrary.sv'
  # The reused extractor compares duplicate shared HardFloat module BYTES first.
  extractor=D/'prepare_fma_subset.py';need(str(extractor) in b['pins'],'FMA extractor pinned')
  subset=out/'fma_subset.sv'
  stage('subset',[b['python'],'-B',str(extractor),'--host',str(host),'--host-sha256',sha(host),'--fma',str(fma),'--fma-sha256',sha(fma),'--out',str(subset)],120,2)
  obj=out/'frontend/obj'
  argv=[b['verilator'],*['+incdir+'+x for x in b['idma_include_dirs']],*['+define+'+x for x in b['idma_defines']],'--cc','--exe','--no-std','--relative-includes','--hierarchical','--build-jobs','1','--verilate-jobs','1','--threads','1','--top-module','HostBlockTopV4','--prefix','VHostBlockTopV4','--Mdir',str(obj),'-Wno-fatal',b['hierarchy'],*([str(repo/diagnostic['probe_config']['repo_path'])]+([str(repo/diagnostic['terminal_probe_config']['repo_path'])] if diagnostic.get('schema')=='FIRST_FAULT_DRIVER_CONTRACT_V2' else []) if diagnostic is not None else []),*b['provider_sources'],str(host),str(subset),b['driver'],'-CFLAGS','-std=c++17 -I'+b['driver_include'],'-LDFLAGS','-lcrypto']
  run_frontend_serial(stage,argv,b['python'],b['verilator'],out)
  if diagnostic is not None:
   # Pure bounded declaration/provenance work inside original whole-job envelope.
   # Never modifies SV or generated C++; all actual products enter prebuild pins.
   from first_fault_probe import generate
   disk_gate(256<<10)
   need(time.monotonic()-start<job_budget,'remaining original build budget before probe generation')
   evidence=out/'readonly-probe-evidence.json'
   generated=generate(repo/diagnostic['probe_schema']['repo_path'],repo/diagnostic['probe_config']['repo_path'],obj/'VHostBlockTopV4___024root.h',obj/'readonly_first_fault_access.hpp',evidence)
   b['readonly_probe_evidence']={'path':str(evidence),'bytes':evidence.stat().st_size,'sha256':sha(evidence)}
   b['pins'][str(evidence)]=sha(evidence)
   b['pins'][str(obj/'readonly_first_fault_access.hpp')]=generated['accessor']['sha256']
   b['pins'][str(obj/'VHostBlockTopV4___024root.h')]=generated['root_header']['sha256']
   if diagnostic['schema']=='FIRST_FAULT_DRIVER_CONTRACT_V2':
    from terminal_finite_probe import generate as generate_terminal
    disk_gate(8<<20)
    need(time.monotonic()-start<job_budget,'remaining original build budget before terminal generation')
    terminal_evidence=out/'terminal-probe-evidence.json'
    terminal_generated=generate_terminal(repo/diagnostic['terminal_probe_schema']['repo_path'],repo/diagnostic['terminal_probe_config']['repo_path'],obj/'VHostBlockTopV4___024root.h',obj/'readonly_terminal_finite_access.hpp',terminal_evidence)
    need(terminal_generated['root_header']==generated['root_header'],'same actual scalar/terminal header')
    b['terminal_probe_evidence']={'path':str(terminal_evidence),'bytes':terminal_evidence.stat().st_size,'sha256':sha(terminal_evidence)}
    b['pins'][str(terminal_evidence)]=sha(terminal_evidence)
    b['pins'][str(obj/'readonly_terminal_finite_access.hpp')]=terminal_generated['accessor']['sha256']
    need(time.monotonic()-start<job_budget,'remaining original build budget after terminal generation')
   disk_gate()
  frontend_receipt=out/'frontend_native_VHostBlockTopV4/RESULT.json'
  # Fresh actual Host.mk/header is admitted against reviewed tool/source/ABI;
  # no inherited C++/binary/numerical PASS from the frontend-only R8 run.
  gate_files=[out/n/'RESULT.json' for n in ('compile_model_sources','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4')]
  gate_files += [host,subset,out/'sv_identity/sv-identity.json',pathlib.Path(high),pathlib.Path(ann),out/'SERIAL_FRONTEND_RESULT.json']
  b.update(fma_subset=str(subset.resolve()),sv_identity_receipt=str((out/'sv_identity/sv-identity.json').resolve()),serial_frontend_receipt=str((out/'SERIAL_FRONTEND_RESULT.json').resolve()),initial_frontend_argv=argv)
  b['verified_gate_pins']={str(p.resolve()):sha(p) for p in gate_files}
  b['verilator_root']=str(pathlib.Path(b['verilator']).parent/'verilator-package/usr/share/verilator')
  b['shared_tree_cap']=12_081_306_272
  b['budgets']={name:dict(seconds=seconds,rss_gib=8,tree_bytes=2_000_000_000) for name,seconds in list(zip(['archive_'+n for n in CHILDREN],[600,1800,3600]))+[('host_archive',3600),('host_link',600)]}
  try:
   phase='admit_build'
   build_binding=admit_build(b,obj,host,frontend_receipt,out/'binary_admission')
   phase='prepare'
   prepared=prepare(build_binding)
   phase='run'
   built=run(build_binding,stage)
   phase='pack'
   from candidate_observation import collect_observation
   observation=collect_observation(b,out,host)
   artifact=pack(b,build_binding,built,host,manifest,out,disk_gate,observation)
  except Exception as exc:
   print("MODEL_POST_BUILD_DIAGNOSTIC "+json.dumps(post_build_failure_diagnostic(phase,exc),sort_keys=True),flush=True)
   import re
   message=str(exc);raw=message.encode();digest=hashlib.sha256(raw).hexdigest()
   if re.search(r'(?i)(github_pat_|gh[pousr]_|bearer\s|authorization|\b(?:password|secret|token)\s*[=:])',message):message='REDACTED_UNSAFE'
   else:message=re.sub(r'(?:[A-Za-z]:[\\/]|/)[^\s\'\"<>():,;]*',lambda m:'<path>/'+re.split(r'[/\\]',m[0])[-1],message)
   message=''.join(c if ord(c)>=32 else ' 'for c in message).encode()[:1024].decode('utf-8','ignore')
   (out/'BUILD_ADMISSION_FAILURE.json').write_text(json.dumps(dict(phase=phase,exception_class=type(exc).__name__,sanitized_error=dict(message=message,raw_message_sha256=digest,raw_message_bytes=len(raw),truncated=len(message.encode())<len(raw))),indent=2)+'\n')
   raise
  (out/'BUILD_ONLY_RESULT.json').write_text(json.dumps(dict(status='UNREVIEWED_MODEL_BUILD',artifact=artifact,scope='MODEL_CANDIDATE_BYTES_REQUIRE_EXTERNAL_REVIEW_BEFORE_NUMERICS'),indent=2)+'\n')
  return

 finally:
  (out/'summary.json').write_text(json.dumps({'scope':'CHISEL_SIMULATION_BACKEND_NOT_FINAL_RTL','status':'BUILD_ONLY_TERMINATION_NO_NUMERIC_CLAIM','completed_profiles':0,'stage_count':len(stages)},indent=2)+'\n')
 # No upload: schema validation remains separate and fails closed until reviewed.
if __name__=='__main__':main()
