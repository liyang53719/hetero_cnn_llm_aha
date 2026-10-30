"""TEMP actual single-build orchestration, not yet admitted or integrated-tested.
Explicit pinned binding supplies real tools/provider filelists and independently
reviewed runtime-preparation/comparison entrypoints. Missing inputs fail before
hardware launch. No shell, default execution, implicit retry or self-learned pins.
"""
import argparse,hashlib,json,pathlib,os,sys,time,subprocess
D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D));import supervise_multiroot as supervise
from check_contract import PROFILES
from run_frontend_serial import run_frontend_serial
from conditional_binary_producer import admit_build,prepare,run
from build_producer import CHILDREN
from pack_frozen_artifact import pack

def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def pinned(p,h):
 p=pathlib.Path(p).absolute();need(p.is_file() and not p.is_symlink() and sha(p)==h,'pin mismatch '+str(p));return p
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--binding',type=pathlib.Path,required=True);ap.add_argument('--binding-sha256',required=True);ap.add_argument('--execute-reviewed-once',action='store_true');a=ap.parse_args()
 b=load(pinned(a.binding,a.binding_sha256));need(b['schema']=='FRESH155_SINGLE_BINARY_M128_V1','schema')
 plan=load(D/'BUILD_PLAN.json')
 need(plan['schema']=='FIXED_SHARED_BUILD_ONLY_PLAN_V1' and plan['mode']=='BUILD_ONLY' and plan['matrix_mac']==4096 and plan['vector_lanes']==32 and plan['profiles']==PROFILES and plan['builds']==1 and plan['tokens']==128,'exact shared build plan')
 need(plan['numeric_execution'] is False and plan['cpp_compile_link'] is True and plan['timeout_seconds']==21000 and plan['owned_tree_cap_bytes']==12_081_306_272 and plan['min_free_reserve_bytes']==1_500_000_000,'explicit build-only resources')
 need(plan['artifact_file_whitelist']==['dut.bin','hardware.sv','driver.cpp','source_manifest.json','tool_manifest.json','build_receipt.json','frozen_artifact.json'] and plan['summary_cap_bytes']==65536,'exact artifact whitelist')
 job_budget=b.get('job_budget_seconds',21000)
 need(type(job_budget) is int and 0<job_budget<=21000,'shared finite job budget')
 need(b.get('mode')=='BUILD_ONLY','explicit build-only execution scope')
 # These must be provided by independently reviewed preparers, never constructed
 # by this execution driver from untrusted run output or an accepted PASS string.
 required=['repo','repo_sha','java','verilator','make','python','pins','canonical_manifest','canonical_manifest_sha256','provider_sources','idma_include_dirs','idma_defines','hierarchy','driver','driver_include','helper_sources','output','fixed_source_overlay','fixed_source_validator','materialized_roots','sv_identity_script']
 required += ['artifact_identity','compile_tools','compile_tool_manifest']
 need(all(k in b for k in required),'missing concrete portable binding fields')
 repo=pathlib.Path(b['repo']).resolve();out=pathlib.Path(b['output']).resolve();need(not out.exists(),'fresh one-shot output')
 need(len(b['idma_include_dirs'])==8 and len(b['idma_defines'])==4,'exact lifted includes/defines')
 for p,h in b['pins'].items():pinned(p,h)
 pinned(b['canonical_manifest'],b['canonical_manifest_sha256'])
 need(b['canonical_manifest_sha256']=='90464ff45917c1b853c7d1b36e67dd5e43b5503b7fa0583704ee615c08919533','root-reviewed fixed canonical baseline only')
 canonical_rows=pathlib.Path(b['canonical_manifest']).read_text().splitlines()
 need('circuit\t0d3abf62329320472199bdc10b81db1df7610dac90caf37ebe6717f7d1ba9f1f' in canonical_rows,'fixed typed AST canonical identity')
 need('annotations_order_preserved\t084025556b70d6a0c7cf992667c40d899b0a897da0fb311c8ec2b253f5d3ca0f' in canonical_rows,'ordered annotation identity')
 for key in ['java','verilator','make','python','hierarchy','driver']:
  need(b[key] in b['pins'],'required tool/source pin '+key)
 need(all(x in b['pins'] for x in b['provider_sources']+b['helper_sources']),'source closure pin')
 for name in ('conditional_binary_producer.py','conditional_admission.py','build_producer.py','HOST_PORTS.json','pack_frozen_artifact.py','driver_dependency_proof.py','p0_source_evidence.py'):
  need(str(D/name) in b['pins'],'build helper source pin '+name)
 need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==b['repo_sha'],'exact checked-out source commit')
 original=repo/'candidates/fresh_original_top_recovery_20261028';manifest=original/'SOURCE_AND_TOOLCHAIN_PINS.json';need(str(manifest) in b['pins'],'source manifest itself independently pinned');m=load(manifest);need(len(m['sources'])==155,'155 original sources')
 # NEW R2 recovery manifest is distinct from the original source/tool lock.
 # Never compile the stale old155 source list after the HostCommands fix.
 need(b['fixed_source_validator'] in b['pins'] and b['fixed_source_overlay'] in b['pins'],'fixed overlay/validator pin')
 need(b['pins'][b['fixed_source_overlay']]=='f8cb8f64819e7f2dd4f3778cc6066e18d062ec1102832f53ef6eabfbcace4b39','reviewed R2 overlay identity')
 need(b['pins'][b['fixed_source_validator']]=='86ed3e5319bcbdd0ea7a7a941f2eb12f72a12daf97e383e22f336cda01ef9ab9','reviewed fixed155 validator')
 import importlib.util
 spec=importlib.util.spec_from_file_location('reviewed_fixed_sources',b['fixed_source_validator']);validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
 source_paths=validator.checked_paths(repo,b['fixed_source_overlay'],m)
 manifest=pathlib.Path(b['fixed_source_overlay'])
 need(b['pins'][b['driver']]=='20df2692d41693491f0da03fa17f21886b9375ca599c83b5b75c0994841dc45e','V3 final-state driver')
 jars=[];plugin=None
 for x in m['jars']:
  p=original/'cache'/x['maven_path'];pinned(p,x['sha256'])
  if x['role']=='plugin':plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin,'exact ordered JAR/plugin closure')
 cp=':'.join(jars);need(b['canonical_manifest'] in b['pins'],'accepted manifest belongs to source pin closure')
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
  left=job_budget-(time.monotonic()-start);need(left>seconds+60,'shared 350min deadline reserve')
  caps=dict(jdk_aliases=b['jdk_aliases'],wall_seconds=seconds,cleanup_seconds=30,file_bytes=536870912,tree_bytes=tree,log_bytes=150_000_000,raw_log_bytes=1073741824,max_entries=100000,per_process_as_bytes=15*1024**3,per_process_cpu_seconds=seconds,rss_bytes=rss*1024**3,cpu_seconds=seconds,extra_watch_roots=[str(repo),str(out)]+b['materialized_roots']+(extra_watch_roots or []),min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  stage_env=dict(env);stage_env.update(env_override or {});stage_pins=dict(b['pins']);stage_pins.update(extra_pins or {})
  try:
   r=supervise.execute(argv,str(out/name),str(lock),caps,stage_env,stage_pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
  finally:
   for path,target in b.get('fresh_host_aliases',{}).items():need(str(pathlib.Path(path).resolve(strict=True))==target,'fresh runtime alias drift after stage')
  stages.append(dict(name=name,status=r['status'],native_exit=r['native_exit'],rss=r['observed_peak_rss'],elapsed=r['elapsed_seconds']));(out/'stage_exits.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(r['native_exit'] in accepted_exit_codes and not r['errors'] and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','stage failed/incomplete: '+name);disk_gate()
  return r
 def java(heap,classpath,main,args=()):return [b['java'],'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-cp',classpath,main,*args]
 try:
  stage('compile155',java('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.']+source_paths),300,3)
  basecp=str(out/'compile155')+':'+cp
  stage('helper_compile',java('2g',cp,'scala.tools.nsc.Main',['-classpath',basecp,'-Xplugin:'+plugin,'-d','.']+b['helper_sources']),300,3)
  helpercp=str(out/'helper_compile')+':'+basecp
  stage('original_high',java('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'),600,6)
  stage('canonical_micro',java('512m',helpercp,'chiseltest.simulator.CanonicalInfoMicroTest'),120,1)
  high=str(out/'original_high/host-diagnostic/original-high.fir');ann=str(out/'original_high/host-diagnostic/high-annotations.json')
  stage('canonical_full',java('2g',helpercp,'chiseltest.simulator.CanonicalHighGate',['candidate',high,ann,b['canonical_manifest'],b['canonical_manifest_sha256'],'canonical.tsv']),300,3)
  stage('transform_new_toolchain',java('2g',helpercp,'chiseltest.simulator.NewToolchainTransformGate',[high,'transform-new-toolchain.tsv']),300,3)
  stage('emit_host',java('4g',helpercp,'chiseltest.simulator.PortableHostHighSimulationEmitter',[high,ann,b['canonical_manifest'],b['canonical_manifest_sha256']]),900,6)
  stage('sv_identity',[b['python'],'-B',b['sv_identity_script'],'--sv',str(out/'emit_host/compiled-host/HostBlockTopV4.sv'),'--output','sv-identity.json'],180,1)
  stage('emit_fma',java('2g',helpercp,'chiseltest.simulator.EmitPhysicalFmaStageLibrary',['fma']),300,3)
  host=out/'emit_host/compiled-host/HostBlockTopV4.sv';fma=out/'emit_fma/fma/PhysicalFmaStageLibrary.sv'
  # The reused extractor compares duplicate shared HardFloat module BYTES first.
  extractor=D/'prepare_fma_subset.py';need(str(extractor) in b['pins'],'FMA extractor pinned')
  subset=out/'fma_subset.sv'
  stage('subset',[b['python'],'-B',str(extractor),'--host',str(host),'--host-sha256',sha(host),'--fma',str(fma),'--fma-sha256',sha(fma),'--out',str(subset)],120,2)
  obj=out/'frontend/obj'
  argv=[b['verilator'],*['+incdir+'+x for x in b['idma_include_dirs']],*['+define+'+x for x in b['idma_defines']],'--cc','--exe','--no-std','--relative-includes','--hierarchical','--build-jobs','1','--verilate-jobs','1','--threads','1','--top-module','HostBlockTopV4','--prefix','VHostBlockTopV4','--Mdir',str(obj),'-Wno-fatal',b['hierarchy'],*b['provider_sources'],str(host),str(subset),b['driver'],'-CFLAGS','-std=c++17 -I'+b['driver_include'],'-LDFLAGS','-lcrypto']
  run_frontend_serial(stage,argv,b['python'],b['verilator'],out)
  frontend_receipt=out/'frontend_native_VHostBlockTopV4/RESULT.json'
  # Fresh actual Host.mk/header is admitted against reviewed tool/source/ABI;
  # no inherited C++/binary/numerical PASS from the frontend-only R8 run.
  gate_files=[out/n/'RESULT.json' for n in ('compile155','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4')]
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
   artifact=pack(b,build_binding,built,host,manifest,out,disk_gate)
  except Exception as exc:
   import re
   message=str(exc);raw=message.encode();digest=hashlib.sha256(raw).hexdigest()
   if re.search(r'(?i)(github_pat_|gh[pousr]_|bearer\s|authorization|\b(?:password|secret|token)\s*[=:])',message):message='REDACTED_UNSAFE'
   else:message=re.sub(r'(?:[A-Za-z]:[\\/]|/)[^\s\'\"<>():,;]*',lambda m:'<path>/'+re.split(r'[/\\]',m[0])[-1],message)
   message=''.join(c if ord(c)>=32 else ' 'for c in message).encode()[:1024].decode('utf-8','ignore')
   (out/'BUILD_ADMISSION_FAILURE.json').write_text(json.dumps(dict(phase=phase,exception_class=type(exc).__name__,sanitized_error=dict(message=message,raw_message_sha256=digest,raw_message_bytes=len(raw),truncated=len(message.encode())<len(raw))),indent=2)+'\n')
   raise
  (out/'BUILD_ONLY_RESULT.json').write_text(json.dumps(dict(status='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS',artifact=artifact,scope='CHISEL_TEST_BACKEND_PREPARATION_NOT_FINAL_RTL_REPLAY'),indent=2)+'\n')
  return

 finally:
  (out/'summary.json').write_text(json.dumps({'scope':'CHISEL_SIMULATION_BACKEND_NOT_FINAL_RTL','status':'BUILD_ONLY_TERMINATION_NO_NUMERIC_CLAIM','completed_profiles':len(results),'stage_count':len(stages)},indent=2)+'\n')
 # No upload: schema validation remains separate and fails closed until reviewed.
if __name__=='__main__':main()
