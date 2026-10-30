"""One isolated old/new full155 SV-only reconstruction. No frontend/native build."""
import argparse,json,os,pathlib,platform,shutil,subprocess,sys,time
from contract import *

def main():
 execution_start=time.monotonic();parent_start=execution_start;ap=argparse.ArgumentParser()
 for n in ('repo','identity','job-start','work'):ap.add_argument('--'+n,type=pathlib.Path,required=True)
 ap.add_argument('--execute-reviewed-once',action='store_true');a=ap.parse_args()
 R=a.repo.resolve();W=a.work;P=R/'candidates/ci_frontend_pipeline_r2_20261029';M=R/'candidates/ci_frontend_materialization_r2_20261029';O=R/'candidates/fresh_original_top_recovery_20261028'
 need(a.execute_reviewed_once and W.is_absolute() and not W.exists() and not any(p.is_symlink()for p in (W,*W.parents)),'explicit fresh owned work root')
 identity=validate_identity(read(a.identity,4096));clock=read(a.job_start,4096)
 need(clock['schema']=='SAME_JOB_START_V1' and clock['job_budget_seconds']==WHOLE and clock['run_id']==identity['run_id'] and clock['launch_commit']==identity['launch_commit'],'first-step wholejob clock binding')
 origin=clock['started_monotonic'];need(type(origin)in(int,float) and 0<=time.monotonic()-origin<WHOLE,'original monotonic clock')
 need(os.environ['GITHUB_RUN_ATTEMPT']=='1' and os.environ['GITHUB_RUN_ID']==str(identity['run_id']) and os.environ['GITHUB_SHA']==identity['launch_commit'],'actual attempt/run identity')
 event=read(pathlib.Path(os.environ['GITHUB_EVENT_PATH']),2<<20);need(event.get('before')==identity['source_commit'] and event.get('after')==identity['launch_commit'] and event.get('ref')=='refs/heads/main','exact source-to-launch event')
 need(subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True,timeout=15).strip()==identity['source_commit'],'exact checked out source');subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True,timeout=30)
 need(D.is_relative_to(R),'executing reviewed source entry');pins=closure(R)
 need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64','original Python/architecture')
 sys.path.insert(0,str(M));import fresh_host
 fresh_host.reject_injection(os.environ)
 available=int(next(l for l in pathlib.Path('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:')).split()[1])*1024
 need(available>=7<<30,'fresh host6GiB stage plus1GiB reserve')
 need(shutil.disk_usage(W.parent).free>=12_081_306_272+(8<<30),'aggregate disk plus8GiB initial reserve')
 need(time.monotonic()-parent_start<=300 and time.monotonic()-origin+EXECUTION+600<WHOLE,'initial bounded validation and execution reservation')
 W.mkdir();write(W/'IDENTITY.json',identity,4096)
 fresh=dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k]for k in ('run_id','source_commit','launch_commit')});fresh_host.validate_contract(fresh,identity);write(W/'HOST_CONTRACT.json',fresh,4096)
 pins[str(W/'HOST_CONTRACT.json')]=sha(W/'HOST_CONTRACT.json')
 sys.path.insert(0,str(P));import supervise_multiroot as supervise
 py=str(pathlib.Path('/usr/bin/python3').resolve());java=(pathlib.Path(os.environ['JAVA_HOME_21_X64'])/'bin/java').resolve(strict=True)
 pins[py]=sha(py);pins[str(java)]=sha(java)
 env={k:os.environ[k]for k in ('ImageVersion','ImageOS','GITHUB_RUN_ID','GITHUB_SHA','GITHUB_RUN_ATTEMPT')};env.update(TMPDIR=str(W),PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 stages=[];aliases={};jdk_aliases=[]
 def check_aliases():
  for path,target in aliases.items():need(str(pathlib.Path(path).resolve(strict=True))==target,'runtime alias drift')
  supervise.verify_aliases(jdk_aliases)
 def stage(name,argv):
  index=len(stages);need(index<len(STAGES) and name==STAGES[index][0],'exact no-repeat phase ordering')
  _,wall,rss=STAGES[index];check_aliases()
  # Original phase caps remain unchanged, future phases and cleanup reserved.
  remaining=sum(w+30 for _,w,_ in STAGES[index:])
  need(time.monotonic()-origin+remaining+600<WHOLE,'same whole-job future phase/export reserve')
  need(time.monotonic()-execution_start+wall+30<EXECUTION,'execution envelope includes cleanup')
  caps=dict(jdk_aliases=jdk_aliases,wall_seconds=wall,cleanup_seconds=30,file_bytes=536870912,tree_bytes=12_081_306_272,log_bytes=(16_777_216 if name in ('jdk','jars') else 150_000_000),raw_log_bytes=(33_554_432 if name in ('jdk','jars') else 1073741824),max_entries=100000,per_process_as_bytes=(4 if name in ('jdk','jars') else 15)*1024**3,per_process_cpu_seconds=wall,rss_bytes=rss*1024**3,cpu_seconds=wall,extra_watch_roots=[str(R),str(W)],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  try:r=supervise.execute(argv,str(W/name),str(W/'exclusive.lock'),caps,env,dict(pins),resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
  finally:check_aliases()
  row=dict(name=name,native_exit=r.get('native_exit'),elapsed_seconds=r.get('elapsed_seconds'),observed_peak_rss=r.get('observed_peak_rss'),strict_complete=completed(r),error_count=len(r.get('errors')or []),result_sha256=sha(W/name/'RESULT.json'))
  stages.append(row);(W/'STAGES.json').write_text(json.dumps(stages,sort_keys=True,indent=2)+'\n')
  need(row['strict_complete'],'stage failed or incomplete: '+name);need(time.monotonic()-origin<WHOLE and time.monotonic()-execution_start<EXECUTION,'end-stage deadline')
 def java_cmd(heap,cp,main,args=()):return [str(java),'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-cp',cp,main,*args]
 stage('jdk',[py,'-B',str(D/'runtime_inventory.py'),'--repo',str(R),'--java-home',str(java.parent.parent),'--contract',str(W/'HOST_CONTRACT.json'),'--contract-sha256',sha(W/'HOST_CONTRACT.json'),'--output',str(W/'jdk-runtime.json')])
 parent_start=time.monotonic();runtime=read(W/'jdk-runtime.json');need(runtime['schema']=='SV_ONLY_JDK_PYTHON_IDENTITY_V1' and runtime['contract']==fresh and runtime['old_pass_transfer']is False,'runtime identity receipt')
 for p,h in runtime['pins'].items():need(sha(p)==h,'fresh runtime drift');pins[p]=h
 aliases=runtime['aliases'];jdk_aliases=runtime['jdk_aliases'];check_aliases();pins[str(W/'jdk-runtime.json')]=sha(W/'jdk-runtime.json')
 need(time.monotonic()-parent_start<=300,'bounded runtime binding')
 stage('jars',[py,'-B',str(O/'restore_inputs.py'),'--download-jars'])
 parent_start=time.monotonic();original=read(O/'SOURCE_AND_TOOLCHAIN_PINS.json');jars=[];plugin=None
 for row in original['jars']:
  p=O/'cache'/row['maven_path'];need(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'full Maven closure');pins[str(p)]=row['sha256']
  if row['role']=='plugin':need(plugin is None,'unique plugin');plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin,'106 jars plus original plugin');cp=':'.join(jars)
 sources={side:source_paths(R,side,original)for side in ('old','new')}
 canonical={'old':M/'fixed-canonical-baseline.tsv','new':R/'candidates/observer_ir_only_20261030/evidence/run41114764250/observed-canonical.tsv'}
 backend=R/'candidates/fresh_non_dpi_backend_recovery_20261028/source'
 helpers={side:[(D/'old_helpers'/n if side=='old' else P/n)for n in ('CanonicalHighGate.scala','PortableHostHighSimulationEmitter.scala')]+[P/n for n in ('PortableHostDenseAccMemoryLowering.scala','PortableHostMatrixResultFifoMemoryLowering.scala')]+[backend/n for n in ('RetainedBackendCircuitGate.scala','RetainedEndpointPortContract.scala','RetainedServicePhaseObserver.scala')]for side in ('old','new')}
 for side in ('old','new'):
  need(sha(canonical[side])==CANONICAL[side],'old/new canonical hard pin')
  need(all(str(p)in pins for p in helpers[side]+[canonical[side]]),'helper/canonical in source closure')
 need(time.monotonic()-parent_start<=300,'bounded source/JAR binding');sv_inputs={};scan_inputs={}
 for side in ('old','new'):
  stage(side+'_compile155',java_cmd('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.']+sources[side]))
  basecp=str(W/(side+'_compile155'))+':'+cp
  stage(side+'_helper_compile',java_cmd('2g',cp,'scala.tools.nsc.Main',['-classpath',basecp,'-Xplugin:'+plugin,'-d','.']+list(map(str,helpers[side]))))
  helpercp=str(W/(side+'_helper_compile'))+':'+basecp
  stage(side+'_original_ir',java_cmd('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'))
  high=W/(side+'_original_ir')/'host-diagnostic/original-high.fir';ann=high.with_name('high-annotations.json')
  for p in (high,ann):pins[str(p)]=sha(p)
  stage(side+'_canonical',java_cmd('2g',helpercp,'chiseltest.simulator.CanonicalHighGate',['candidate',str(high),str(ann),str(canonical[side]),CANONICAL[side],'canonical.tsv']))
  generated=W/(side+'_canonical')/'canonical.tsv';need(sha(generated)==CANONICAL[side],'actual typed canonical exact');pins[str(generated)]=sha(generated)
  stage(side+'_emit_sv',java_cmd('4g',helpercp,'chiseltest.simulator.PortableHostHighSimulationEmitter',[str(high),str(ann),str(canonical[side]),CANONICAL[side]]))
  sv=W/(side+'_emit_sv')/'compiled-host/HostBlockTopV4.sv';pins[str(sv)]=sha(sv);sv_inputs[side]=sv
  stage(side+'_svscan',[py,'-B',str(P/'frontend_observation_metadata.py'),'--observe-sv',str(sv),'--materialization',str(M),'--output','sv-identity.json'])
  scan=W/(side+'_svscan')/'sv-identity.json';x=read(scan,512<<10);need(x['normalized_sha256']==NORMALIZED[side] and x['raw_sha256']==sha(sv) and x['bytes']==sv.stat().st_size,'whole normalized old/new hard lock and actual raw binding');pins[str(scan)]=sha(scan);pins[str(scan.parent/'RESULT.json')]=sha(scan.parent/'RESULT.json');scan_inputs[side]=scan
 # Exact projection CLI supplied by independent implementation; no synthetic mode.
 stage('projection',[py,'-B',str(D/'sv_difference_projection.py'),'--old-sv',str(sv_inputs['old']),'--new-sv',str(sv_inputs['new']),'--old-metadata',str(scan_inputs['old']),'--new-metadata',str(scan_inputs['new']),'--materialization',str(M),'--output','proof.json'])
 for p in [*sv_inputs.values(),*scan_inputs.values(),*[p.parent/'RESULT.json'for p in scan_inputs.values()]]:need(sha(p)==pins[str(p)],'projection input drift')
 need(len(stages)==15 and all(x['strict_complete']for x in stages),'all15 owned terminal receipts')
 # Raw paths and classes remain local; export rereads and independently projects proof.
 write(W/'COMPLETE.json',dict(schema='SV_ONLY_RECONSTRUCTION_COMPLETE_V1',identity=identity,source_pins_sha256=sha(D/'SOURCE_PINS.json'),runtime_inventory_sha256=sha(W/'jdk-runtime.json'),proof_sha256=sha(W/'projection/proof.json'),canonical_sha256=CANONICAL,normalized_sha256=NORMALIZED,sv_inputs={k:dict(sha256=sha(p),bytes=p.stat().st_size)for k,p in sv_inputs.items()},stage_count=15,numerical_pass=False,sv_repin_authorized=False),65536)
if __name__=='__main__':main()
