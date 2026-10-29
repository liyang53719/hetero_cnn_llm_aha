"""TEMP actual single-build orchestration, not yet admitted or integrated-tested.
Explicit pinned binding supplies real tools/provider filelists and independently
reviewed runtime-preparation/comparison entrypoints. Missing inputs fail before
hardware launch. No shell, default execution, implicit retry or self-learned pins.
"""
import argparse,hashlib,json,pathlib,os,sys,time,subprocess
D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D));import supervise_multiroot as supervise
from check_contract import validate_plan,PROFILES
from run_frontend_serial import run_frontend_serial

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
 plan=load(D/'PLAN.json');validate_plan(plan)
 frontend_only=b.get('mode')=='FRONTEND_ONLY'
 job_budget=b.get('job_budget_seconds',21000)
 need(type(job_budget) is int and 0<job_budget<=21000,'shared finite job budget')
 need(frontend_only or b.get('mode')=='FIVE_PROFILE_NUMERICAL_DIAGNOSTIC','explicit execution scope')
 # These must be provided by independently reviewed preparers, never constructed
 # by this execution driver from untrusted run output or an accepted PASS string.
 required=['repo','repo_sha','java','verilator','make','python','pins','canonical_manifest','canonical_manifest_sha256','provider_sources','idma_include_dirs','idma_defines','hierarchy','driver','driver_include','helper_sources','runtime_prepare_argv','runtime_bundle','runtime_compare_script','output','fixed_source_overlay','fixed_source_validator','materialized_roots','sv_identity_script']
 if frontend_only:required=[k for k in required if k not in ('runtime_prepare_argv','runtime_bundle','runtime_compare_script')]
 need(all(k in b for k in required),'missing concrete portable binding fields')
 repo=pathlib.Path(b['repo']).resolve();out=pathlib.Path(b['output']).resolve();need(not out.exists(),'fresh one-shot output')
 need(len(b['idma_include_dirs'])==8 and len(b['idma_defines'])==4,'exact lifted includes/defines')
 for p,h in b['pins'].items():pinned(p,h)
 pinned(b['canonical_manifest'],b['canonical_manifest_sha256'])
 need(b['canonical_manifest_sha256']=='90464ff45917c1b853c7d1b36e67dd5e43b5503b7fa0583704ee615c08919533','root-reviewed fixed canonical baseline only')
 canonical_rows=pathlib.Path(b['canonical_manifest']).read_text().splitlines()
 need('circuit\t0d3abf62329320472199bdc10b81db1df7610dac90caf37ebe6717f7d1ba9f1f' in canonical_rows,'fixed typed AST canonical identity')
 need('annotations_order_preserved\t084025556b70d6a0c7cf992667c40d899b0a897da0fb311c8ec2b253f5d3ca0f' in canonical_rows,'ordered annotation identity')
 for key in ['java','verilator','make','python','hierarchy','driver']+([] if frontend_only else ['runtime_compare_script']):
  need(b[key] in b['pins'],'required tool/source pin '+key)
 need(all(x in b['pins'] for x in b['provider_sources']+b['helper_sources']),'source closure pin')
 if not frontend_only:need(b['runtime_prepare_argv'][0]==b['python'] and len(b['runtime_prepare_argv'])>1 and b['runtime_prepare_argv'][1] in b['pins'],'audited Python preparation entry')
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
 if not frontend_only:need(b['pins'][b['runtime_compare_script']]=='75ea644248d6d41f8ca915c625649c60c6bae1c56360d33c8875563df6e67cef','V3 actual five-profile comparator')
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
 def disk_gate():
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
  need(total<=12_081_306_272,'owned data cap excluding safety reserve')
  import shutil
  need(shutil.disk_usage(out).free>=1_500_000_000,'preserve disk reserve; no automatic deletion')
 def stage(name,argv,seconds=600,rss=5,tree=2_000_000_000,accepted_exit_codes=(0,),env_override=None,extra_watch_roots=None,extra_pins=None):
  disk_gate()
  left=job_budget-(time.monotonic()-start);need(left>seconds+60,'shared 350min deadline reserve')
  caps=dict(jdk_aliases=b['jdk_aliases'],wall_seconds=seconds,cleanup_seconds=30,file_bytes=536870912,tree_bytes=tree,log_bytes=150_000_000,raw_log_bytes=1073741824,max_entries=100000,per_process_as_bytes=15*1024**3,per_process_cpu_seconds=seconds,rss_bytes=rss*1024**3,cpu_seconds=seconds,extra_watch_roots=[str(repo),str(out)]+b['materialized_roots']+(extra_watch_roots or []),min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  stage_env=dict(env);stage_env.update(env_override or {});stage_pins=dict(b['pins']);stage_pins.update(extra_pins or {})
  r=supervise.execute(argv,str(out/name),str(lock),caps,stage_env,stage_pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
  stages.append(dict(name=name,status=r['status'],native_exit=r['native_exit'],rss=r['observed_peak_rss'],elapsed=r['elapsed_seconds']));(out/'stage_exits.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(r['native_exit'] in accepted_exit_codes and not r['errors'] and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','stage failed/incomplete: '+name);disk_gate()
  return r
 def java(heap,classpath,main,args=()):return [b['java'],'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-cp',classpath,main,*args]
 try:
  stage('compile155',java('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.']+source_paths),300,3)
  basecp=str(out/'compile155')+':'+cp
  stage('original_high',java('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'),600,6)
  stage('helper_compile',java('2g',cp,'scala.tools.nsc.Main',['-classpath',basecp,'-Xplugin:'+plugin,'-d','.']+b['helper_sources']),300,3)
  helpercp=str(out/'helper_compile')+':'+basecp
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
  if frontend_only:
   (out/'FRONTEND_ONLY_RESULT.json').write_text(json.dumps({'status':'PASS_FRONTEND_CODEGEN_ONLY_NO_BINARY_NO_NUMERICS','sv_sha256':sha(host),'source_manifest_sha256':sha(manifest),'driver_sha256':sha(b['driver']),'scope':'CHISEL_TEST_SIMULATION_BACKEND_PREPARATION_NOT_FINAL_RTL_REPLAY','frontend_receipt_sha256':sha(frontend_receipt)},indent=2)+'\n')
   return
  stage('cpp_build',[b['make'],'-C',str(obj),'-f','VHostBlockTopV4.mk','-j1'],3600,8)
  binary=obj/'VHostBlockTopV4';bh=sha(binary);sh=sha(host)
  # Preparation alone owns weights/references; binary invocation gets no oracle.
  stage('prepare_five',b['runtime_prepare_argv'],3600,5,5_000_000_000)
  need(pathlib.Path(b['runtime_bundle']).resolve().is_relative_to(out),'job-local runtime bundle')
  bundle=load(b['runtime_bundle']);need([r['id'] for r in bundle['profiles']]==list(range(5)),'five real profile bindings')
  def pin_record(p):
   p=pathlib.Path(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
  # Actual successful make receipt is retained alongside identities; not an
  # invented pre-build provenance JSON. Final-dump driver is separately pinned.
  receipt=out/'build_receipt.json'
  receipt.write_text(json.dumps(dict(config_only=False,software_arithmetic_substitution=False,
    binary_sha256=bh,sv_sha256=sh,source_manifest_sha256=sha(manifest),driver_sha256=sha(b['driver']),
    compile_process_receipt=pin_record(out/'cpp_build/RESULT.json'),frontend_process_receipt=pin_record(frontend_receipt),
    recipe_binding_sha256=a.binding_sha256),indent=2)+'\n')
  common={k:pin_record(v) for k,v in dict(binary=binary,sv=host,source_manifest=manifest,driver=b['driver'],build_receipt=receipt).items()}
  for r in bundle['profiles']:
   for k in ['runtime','views','reference_result','provider_receipt']:
    need(pathlib.Path(r[k]['path']).resolve().is_relative_to(out),'job-local data binding '+k)
  limits=bundle['limits'];remaining=int(job_budget-(time.monotonic()-start)-120)
  need(remaining>0 and limits['wall_seconds']*5+120<=remaining,'all five per-profile watchdogs must fit remaining shared job budget')
  full=dict(schema='FIVE_PROFILE_EXTERNAL_DUT_V1',layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,
    moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',common=common,profiles=bundle['profiles'],limits=limits)
  binding=out/'FIVE_PROFILE_BINDING.json';binding.write_text(json.dumps(full,indent=2)+'\n')
  # Concrete sibling entry owns five actual DUT launches and all-final-state
  # comparisons. Never launch the binary a second time here.
  combined=out/'five_profile_results'
  stage('run_compare_five',[b['python'],'-B',b['runtime_compare_script'],'--binding',str(binding),'--output',str(combined)],
        remaining,5,2_000_000_000,accepted_exit_codes=(2,))
  measured=load(combined/'RESULT.json')
  need(measured['status']=='INCOMPLETE' and measured['numeric_acceptance']=='NO_NEW_TOLERANCE_STRICT_BITWISE_DIAGNOSTICS_ONLY','no implicit tolerance or PASS upgrade')
  results=measured['profiles'];need([r['profile'] for r in results]==list(range(5)),'all five observations retained')
  (out/'profile_results.json').write_text(json.dumps(measured,indent=2)+'\n')
  # Preserve intentional exit2: strict byte diagnostics are not approved numerical PASS.
  raise SystemExit(2)
 finally:
  (out/'summary.json').write_text(json.dumps({'scope':'CHISEL_SIMULATION_BACKEND_NOT_FINAL_RTL','status':'INCOMPLETE','completed_profiles':len(results),'stage_count':len(stages)},indent=2)+'\n')
 # No upload: schema validation remains separate and fails closed until reviewed.
if __name__=='__main__':main()
