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
from frontend_observation_metadata import qualify_frontend, observe_sv
from build_producer import CHILDREN


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
 job_budget=b.get('job_budget_seconds',12000)
 need(type(job_budget) is int and job_budget==12000,'exact frontend qualification budget')
 need(b.get('whole_job_budget_seconds')==21000,'original whole job budget unchanged')
 need(b.get('mode')=='FRONTEND_ONLY','frontend qualification only')
 # These must be provided by independently reviewed preparers, never constructed
 # by this execution driver from untrusted run output or an accepted PASS string.
 required=['repo','repo_sha','java','verilator','make','python','pins','canonical_manifest','canonical_manifest_sha256','provider_sources','idma_include_dirs','idma_defines','hierarchy','driver','driver_include','helper_sources','output','fixed_source_overlay','fixed_source_validator','materialized_roots','sv_identity_script']
 required += ['artifact_identity','compile_tools','compile_tool_manifest','compile_tool_pins','job_started_monotonic']
 need(all(k in b for k in required),'missing concrete portable binding fields')
 repo=pathlib.Path(b['repo']).resolve();out=pathlib.Path(b['output']).resolve();need(not out.exists(),'fresh one-shot output')
 need(len(b['idma_include_dirs'])==8 and len(b['idma_defines'])==4,'exact lifted includes/defines')
 for p,h in b['pins'].items():pinned(p,h)
 pinned(b['canonical_manifest'],b['canonical_manifest_sha256'])
 need(b['canonical_manifest_sha256']=='00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c','root-reviewed fixed canonical baseline only')
 canonical_rows=pathlib.Path(b['canonical_manifest']).read_text().splitlines()
 need('circuit\t107bcbc0e17d430c2908666bdb750bcbc53b8b4caedc45ccbd9df612173ff872' in canonical_rows,'fixed typed AST canonical identity')
 need('annotations_order_preserved\t8dd84536415d0f97aad603d1e0b9fbdadf8cae58a04d4ae5328105c9a844af39' in canonical_rows,'ordered annotation identity')
 for key in ['java','verilator','make','python','hierarchy','driver']:
  need(b[key] in b['pins'],'required tool/source pin '+key)
 need(all(x in b['pins'] for x in b['provider_sources']+b['helper_sources']),'source closure pin')
 for name in ('conditional_binary_producer.py','conditional_admission.py','build_producer.py','HOST_PORTS.json','pack_frozen_artifact.py','driver_dependency_proof.py','p0_source_evidence.py','frontend_observation_metadata.py','frontend_qualify_only.py','OBSERVER_HOST_PORTS_122.json'):
  need(str(D/name) in b['pins'],'build helper source pin '+name)
 need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==b['repo_sha'],'exact checked-out source commit')
 original=repo/'candidates/fresh_original_top_recovery_20261028';manifest=original/'SOURCE_AND_TOOLCHAIN_PINS.json';need(str(manifest) in b['pins'],'source manifest itself independently pinned');m=load(manifest);need(len(m['sources'])==155,'155 original sources')
 # NEW R2 recovery manifest is distinct from the original source/tool lock.
 # Never compile the stale old155 source list after the HostCommands fix.
 need(b['fixed_source_validator'] in b['pins'] and b['fixed_source_overlay'] in b['pins'],'fixed overlay/validator pin')
 need(b['pins'][b['fixed_source_overlay']]=='9be7810a372572e87b40d86d0b30245140c31cd40cdd6cf2f9cacead459beda2','reviewed R2 overlay identity')
 need(b['pins'][b['fixed_source_validator']]=='ac480aaeb39ebae58ce310939e7ae9ed293ddc65e61303d8ef53841c8362bfcb','reviewed fixed155 validator')
 import importlib.util
 spec=importlib.util.spec_from_file_location('reviewed_fixed_sources',b['fixed_source_validator']);validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
 source_paths=validator.checked_paths(repo,b['fixed_source_overlay'],m)
 manifest=pathlib.Path(b['fixed_source_overlay'])
 need(b['pins'][b['driver']]=='f4f00dffd348e1822e7fcb5ac59602579d693d7a8d04e221cdd3f0255b56b04c','V3 final-state driver')
 jars=[];plugin=None
 for x in m['jars']:
  p=original/'cache'/x['maven_path'];pinned(p,x['sha256'])
  if x['role']=='plugin':plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin,'exact ordered JAR/plugin closure')
 cp=':'.join(jars);need(b['canonical_manifest'] in b['pins'],'accepted manifest belongs to source pin closure')
 if not a.execute_reviewed_once:print('TEMP_PREFLIGHT_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS');return
 need(type(b['job_started_monotonic']) in (int,float) and 0<b['job_started_monotonic']<=time.monotonic(),'original workflow monotonic start required')
 out.mkdir();start=time.monotonic();stages=[];results=[];lock=out/'exclusive.lock'
 def deadline():
  need(time.monotonic()-b['job_started_monotonic']<21000,'shared whole job21000 deadline')
  need(time.monotonic()-start<12000,'frontend qualification12000 deadline')
 deadline()
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
  deadline();left=min(job_budget-(time.monotonic()-start),21000-(time.monotonic()-b['job_started_monotonic']));need(left>seconds+60,'whole job and frontend stage reserve')
  caps=dict(jdk_aliases=b['jdk_aliases'],wall_seconds=seconds,cleanup_seconds=30,file_bytes=536870912,tree_bytes=tree,log_bytes=150_000_000,raw_log_bytes=1073741824,max_entries=100000,per_process_as_bytes=15*1024**3,per_process_cpu_seconds=seconds,rss_bytes=rss*1024**3,cpu_seconds=seconds,extra_watch_roots=[str(repo),str(out)]+b['materialized_roots']+(extra_watch_roots or []),min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  stage_env=dict(env);stage_env.update(env_override or {});stage_pins=dict(b['pins']);stage_pins.update(extra_pins or {})
  try:
   r=supervise.execute(argv,str(out/name),str(lock),caps,stage_env,stage_pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
  finally:
   for path,target in b.get('fresh_host_aliases',{}).items():need(str(pathlib.Path(path).resolve(strict=True))==target,'fresh runtime alias drift after stage')
  stages.append(dict(name=name,status=r['status'],native_exit=r['native_exit'],rss=r['observed_peak_rss'],elapsed=r['elapsed_seconds']));(out/'stage_exits.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(r['native_exit'] in accepted_exit_codes and not r['errors'] and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','stage failed/incomplete: '+name)
  need(r.get('log_capture',{}).get('pipe_eof_observed') is True and r.get('log_capture',{}).get('gzip_finalized') is True,'stage logs not finalized: '+name);disk_gate();deadline()
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
  stage('sv_identity',[b['python'],'-B',str(D/'frontend_observation_metadata.py'),'--observe-sv',str(out/'emit_host/compiled-host/HostBlockTopV4.sv'),'--materialization',str(pathlib.Path(b['sv_identity_script']).parent),'--output','sv-identity.json'],180,1)
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
  qualify_frontend(b,obj,host,frontend_receipt,out,stage,deadline)
  return

 finally:
  (out/'summary.json').write_text(json.dumps({'scope':'CHISEL_SIMULATION_BACKEND_NOT_FINAL_RTL','status':'FRONTEND_QUALIFICATION_TERMINATION_NO_NUMERIC_CLAIM','completed_profiles':len(results),'stage_count':len(stages)},indent=2)+'\n')
 # No upload: schema validation remains separate and fails closed until reviewed.
if __name__=='__main__':main()
