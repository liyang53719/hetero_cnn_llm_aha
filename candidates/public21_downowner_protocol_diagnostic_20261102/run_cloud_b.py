"""One source-rebuilt protocol diagnostic. Never uploads artifacts or numerical PASS."""
import argparse, hashlib, json, math, os, pathlib, re, shutil, subprocess, sys, time
P=pathlib.Path
C=P(__file__).resolve().parent
WHOLE=7200
TREE=12081306272
STATE={'phase':'IDENTITY','last_completed_stage':None}
SCALA_SOURCES=['Public21DownOwnerProtocolHarness.scala','Public21DownOwnerCrossWindowProtocolOnlySpec.scala','DirectJnaAdapter.scala','DirectBContextFactory.scala','Public21DownOwnerDirectDriver.scala','Public21DownOwnerEmitOnly.scala']
PHASES={'jdk','compile_tools','jars','verilator_tools','fresh_host','compile','emit','ports','verilate','make','protocol'}
MAIN=[('compile',300,3),('emit',600,6),('ports',120,2),('verilate',900,6),('make',1800,6),('protocol',600,6)]
def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p,cap=16<<20):
 p=P(p);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=cap,'bounded JSON');return json.loads(p.read_text())
def save(p,o):
 with P(p).open('x') as f:json.dump(o,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def strict(r):
 return r.get('native_exit')==0 and r.get('errors')==[] and (r.get('cleanup_proof') or {}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and (r.get('log_capture') or {}).get('pipe_eof_observed') is True and (r.get('log_capture') or {}).get('gzip_finalized') is True
ERRORS={'ValueError: sampled observed aggregate RSS cap':'RSS_CAP','ValueError: sampled observed aggregate CPU cap':'CPU_CAP','ValueError: wall cap':'WALL_CAP','ValueError: locked memory gate':'MEMORY_GATE','ValueError: locked disk gate':'DISK_GATE','ValueError: file cap':'FILE_CAP','ValueError: sampled stage output tree cap':'TREE_CAP','ValueError: sampled aggregate writable-root cap':'WATCH_TREE_CAP','ValueError: sampled disk reserve':'DISK_RESERVE','InterruptedError: signal 14':'WALL_SIGNAL'}
def diagnostic(name,r,receipt,return_path=None):
 def num(x):return x if type(x) in (int,float) and math.isfinite(x) and abs(x)<2**53 else None
 e=r.get('errors');need(type(e)is list,'supervisor error list')
 d={'schema':'PUBLIC21_DOWNOWNER_PROTOCOL_DIAGNOSTIC_V1','stage':name,'receipt_sha256':sha(receipt) if receipt.is_file() and not receipt.is_symlink() else None,'receipt_available':receipt.is_file() and not receipt.is_symlink(),'supervisor_return_sha256':sha(return_path) if return_path is not None and return_path.is_file() else None,'native_exit':num(r.get('native_exit')),'error_count':len(e),'error_codes':sorted(set(ERRORS.get(x,'UNCLASSIFIED_SUPERVISOR_ERROR') for x in e)),'elapsed_seconds':num(r.get('elapsed_seconds')),'sampled_peak_rss_bytes':num(r.get('observed_peak_rss')),'observed_cpu_seconds':num(r.get('observed_cpu_seconds')),'strict_stage_success':strict(r),'cleanup_complete':(r.get('cleanup_proof') or {}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','pipe_eof':(r.get('log_capture') or {}).get('pipe_eof_observed') is True,'gzip_finalized':(r.get('log_capture') or {}).get('gzip_finalized') is True,'numerical_pass':False,'production_fault_reproduced':False}
 raw=json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False);need(len(raw.encode())<8192,'finite summary');print('PUBLIC21_B_STAGE '+raw,flush=True);return d

def main():
 a=argparse.ArgumentParser()
 for n in ('repo','work','identity','job-start'):a.add_argument('--'+n,type=P,required=True)
 v=a.parse_args();R=v.repo.resolve(strict=True);W=v.work.absolute();I=load(v.identity,4096);start=load(v.job_start,4096)
 need(set(I)=={'schema','run_id','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha','scope'} and I['schema']=='PUBLIC21_DOWNOWNER_PROTOCOL_JOB_IDENTITY_V1','identity schema')
 need(I['scope']=='PROTOCOL_ONLY_MOCK_MATRIX_VECTOR_DDR_NO_NUMERICAL_PASS_NO_ARTIFACT_TRANSFER','identity scope')
 need(type(I['run_id'])is int and str(I['run_id'])==os.environ['GITHUB_RUN_ID'] and os.environ['GITHUB_RUN_ATTEMPT']=='1' and I['launch_commit']==os.environ['GITHUB_SHA'],'actual first run')
 need(all(type(I[k])is str and re.fullmatch('[0-9a-f]{40}',I[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')),'commit pins')
 need(I['launch_manifest_path']=='ci_launch/public21_downowner_protocol_driveorderfix_20261102_once.json' and I['source_commit']!=I['launch_commit'],'launch boundary')
 need(start.get('schema')=='PUBLIC21_DOWNOWNER_PROTOCOL_JOB_START_V1' and start.get('run_id')==I['run_id'] and start.get('launch_commit')==I['launch_commit'] and start.get('job_budget_seconds')==WHOLE,'original clock binding')
 t=start.get('started_monotonic');need(type(t)in(int,float) and math.isfinite(t) and 0<=time.monotonic()-t<WHOLE,'original monotonic clock')
 event=load(os.environ['GITHUB_EVENT_PATH'],2<<20);need(event.get('before')==I['source_commit'] and event.get('after')==I['launch_commit'] and event.get('ref')=='refs/heads/main','actual source parent')
 need(subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True,stderr=subprocess.PIPE,timeout=20).strip()==I['source_commit'],'exact source checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
 need(C.is_relative_to(R) and not W.exists() and not W.is_symlink(),'fresh owned work')
 K=R/'candidates/model_candidate_build_20261101';D=R/'candidates/ci_frontend_materialization_r2_20261029'
 sys.path[:0]=[str(K),str(D),str(C)]
 W.mkdir();save(W/'IDENTITY.json',I);STATE['phase']='SOURCE_CLOSURE'
 contract=dict(schema='BOUNDED_FRESH_HOST_V1',run_id=I['run_id'],source_commit=I['source_commit'],launch_commit=I['launch_commit']);save(W/'FRESH_HOST_CONTRACT.json',contract)
 original=R/'candidates/fresh_original_top_recovery_20261028'
 # The diagnostic owns a separately pinned, fixed source/helper inventory.
 local=load(C/'DIAGNOSTIC_SOURCE_PINS.json');need(local.get('schema')=='PUBLIC21_B_SOURCE_PINS_V1','source manifest schema')
 need(local['supervisor_directory']=='candidates/ci_frontend_pipeline_r2_20261029' and local['compile_inventory']=='candidates/ci_frontend_pipeline_r2_20261029/inventory_compile_tools.py','fixed original supervision/tool inventory')
 pins={}
 def pin(p,expected=None):
  p=P(p);need(p.is_file() and not p.is_symlink(),'regular input');h=sha(p);need(expected is None or h==expected,'exact input bytes');pins[str(p.resolve())]=h;return str(p.resolve())
 pin(C/'DIAGNOSTIC_SOURCE_PINS.json')
 for rel,h in local['files'].items():
  need(type(rel)is str and not P(rel).is_absolute() and '..' not in P(rel).parts,'source relative path');pin(R/rel,h)
 need(local['scala_sources']==SCALA_SOURCES,'exact six fixture source roles')
 required=[C/n for n in [*SCALA_SOURCES,'run_cloud_b.py','diagnostics.py','prepare_direct_driver.py','prepare_protocol_input.py','P0_PROTOCOL_INPUT.json','EXPECTED_PORTS.json','BUDGET_CONTRACT.json']]
 required += [D/n for n in ['inventory_runner_jdk.py','fresh_host.py','materialize_verilator.py','VERILATOR_MANIFEST.json']]
 required += [K/n for n in ['restore_model_inputs.py','candidate_generation_gate.py','GENERATION_CONTRACT.json','MODEL_SOURCE_OVERLAY.json']]
 required += [R/local['compile_inventory'],R/local['supervisor_directory']/'supervise_multiroot.py',R/local['supervisor_directory']/'strict_cleanup.py',R/local['supervisor_directory']/'lossless_log.py',original/'SOURCE_AND_TOOLCHAIN_PINS.json']
 for required_path in required:need(str(required_path.resolve()) in pins and sha(required_path)==pins[str(required_path.resolve())],'required runtime source role pinned')
 import fresh_host
 fresh_host.reject_injection(os.environ)
 from candidate_generation_gate import load_contract,checked_paths,GENERATION_CONTRACT_SHA256
 generation=load_contract(K/'GENERATION_CONTRACT.json',GENERATION_CONTRACT_SHA256)
 m=load(original/'SOURCE_AND_TOOLCHAIN_PINS.json');sources=checked_paths(R,K/'MODEL_SOURCE_OVERLAY.json',m,generation);need(len(sources)==159,'actual 159 source closure')
 S=R/local['supervisor_directory'];need(S.is_relative_to(R),'supervisor fixed source')
 sys.path.insert(0,str(S));import supervise_multiroot as supervisor
 for p in sources:pin(p)
 py=pin(P('/usr/bin/python3').resolve());java_home=P(os.environ['JAVA_HOME_21_X64']).resolve();java=pin(java_home/'bin/java')
 pin(v.identity);pin(v.job_start);pin(W/'FRESH_HOST_CONTRACT.json')
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','MAKEFLAGS':'-j1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
 for k in ('GITHUB_RUN_ID','GITHUB_SHA','GITHUB_RUN_ATTEMPT','ImageVersion','ImageOS','JAVA_HOME_21_X64'):
  if k in os.environ:env[k]=os.environ[k]
 rows=[];aliases=[];runtime_aliases={};prep=time.monotonic()
 def stage(name,argv,wall,rss,remaining,preparing=False,stageenv=None):
  need(name in PHASES,'fixed stage');STATE['phase']=name
  for path,target in runtime_aliases.items():need(str(P(path).resolve(strict=True))==target,'runtime alias drift')
  need(time.monotonic()-t+wall+30+remaining+60<WHOLE,'whole reservation before stage')
  if preparing:need(time.monotonic()-prep+wall+30<=1800,'shared preparation budget')
  caps=dict(wall_seconds=wall,cleanup_seconds=30,per_process_cpu_seconds=wall,cpu_seconds=wall,rss_bytes=rss<<30,per_process_as_bytes=15<<30,file_bytes=512<<20,tree_bytes=2000000000,watch_tree_bytes=TREE,extra_watch_roots=[str(W),str(R)],max_entries=100000,log_bytes=16<<20,raw_log_bytes=32<<20,min_free_disk_bytes=1500000000,jdk_aliases=aliases)
  e=dict(env);e.update(stageenv or {})
  q=supervisor.execute(argv,str(W/name),str(W/'owner.lock'),caps,e,dict(pins),resource_gate={'min_available_memory':(rss+1)<<30,'min_disk_free':1500000000})
  return_path=W/(name+'_SUPERVISOR_RETURN.json')
  try:save(return_path,q)
  except OSError:return_path=None
  rows.append(diagnostic(name,q,W/name/'RESULT.json',return_path));save(W/(name+'_SAFE.json'),rows[-1])
  from diagnostics import project
  projection=project(W/name/'frontend.log.gz',q,[P(x).name for x in sources]+[P(x).name for x in local['scala_sources']]);save(W/(name+'_CLOSED_LOG_SAFE.json'),projection);print('PUBLIC21_B_CLOSED_LOG '+json.dumps(projection,sort_keys=True,separators=(',',':')),flush=True)
  need(strict(q),'stage failed: '+name);STATE['last_completed_stage']=name
  for p in (W/name).rglob('*'):
   if p.is_file() and not p.is_symlink() and p.suffix in ('.class','.json'):pin(p)
  return q
 # Prep budget includes all its subprocess cleanup; no network credentials or model data.
 tail=sum(x[1]+30 for x in MAIN)
 freshargs=['--fresh-host-contract',str(W/'FRESH_HOST_CONTRACT.json'),'--fresh-host-contract-sha256',sha(W/'FRESH_HOST_CONTRACT.json')]
 stage('jdk',[py,'-B',str(D/'inventory_runner_jdk.py'),'--java-home',str(java_home),'--output',str(W/'jdk.json'),*freshargs],180,1,tail,True)
 j=load(W/'jdk.json');need(j['status']=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION' and j['old_pass_transfer']is False,'fresh JDK inventory')
 for row in j['files']:
  p=java_home/row['path']
  if 'symlink' in row:
   need(p.is_symlink() and os.readlink(p)==row['symlink'] and str(p.resolve(strict=True))==row['resolved_target'],'JDK alias identity');aliases.append(dict(path=str(p),link=row['symlink'],target=row['resolved_target']))
   if 'external_dependency' in row:pin(row['resolved_target'],row['external_dependency']['sha256'])
  else:need(p.stat().st_size==row['bytes'],'JDK length');pin(p,row['sha256'])
 stage('compile_tools',[py,'-B',str(R/local['compile_inventory']),'--output',str(W/'compile-tools.json')],180,1,tail,True)
 tools=load(W/'compile-tools.json');fresh_host.validate_compile_inventory(tools)
 for p,h in tools['pins'].items():pin(p,h)
 runtime_aliases.update(tools['aliases'])
 stage('jars',[py,'-B',str(K/'restore_model_inputs.py'),'--download-jars','--status-json',str(W/'JAR_STATUS.json')],600,1,tail,True)
 jars=[];plugin=None
 for row in m['jars']:
  p=original/'cache'/row['maven_path'];pin(p,row['sha256'])
  if row['role']=='plugin':plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin,'107 ordered tool records')
 stage('verilator_tools',[py,'-B',str(D/'materialize_verilator.py'),'--output',str(W/'tools'),'--execute-reviewed-acquisition'],300,1,tail,True)
 stage('fresh_host',[py,'-B',str(D/'fresh_host.py'),'--contract',str(W/'FRESH_HOST_CONTRACT.json'),'--contract-sha256',sha(W/'FRESH_HOST_CONTRACT.json'),'--java-home',str(java_home),'--verilator-root',str(W/'tools'),'--output',str(W/'host.json')],180,1,tail,True)
 host=load(W/'host.json');need(host['contract']==contract and host['old_pass_transfer']is False,'actual host domain')
 for p,h in host['pins'].items():pin(p,h)
 for p,target in host['aliases'].items():need(str(P(p).resolve(strict=True))==target,'host alias')
 runtime_aliases.update(host['aliases'])
 # Backend inventory and exact regular tool closure remain the original official pins.
 vm=load(D/'VERILATOR_MANIFEST.json')
 for row in vm['files']:
  if row['path'].startswith(('usr/bin/','usr/share/verilator/')):pin((W/'tools/verilator-package'/row['path']).resolve(strict=True),row['sha256'])
 cp=':'.join(jars)
 def jvm(heap,main,args=(),classes=False):return [java,'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-cp',(str(W/'compile')+':' if classes else '')+cp,main,*args]
 fixture=[str(C/n) for n in local['scala_sources']]
 stage('compile',jvm('2g','scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.',*sources,*fixture]),300,3,sum(x[1]+30 for x in MAIN[1:]))
 emitted=W/'emitted';emitted.mkdir();top='Public21DownOwnerProtocolHarness'
 stage('emit',jvm('4g','chiseltest.simulator.jna.Public21DownOwnerEmitOnly',[str(emitted)],True),600,6,sum(x[1]+30 for x in MAIN[2:]))
 for name in (top+'.lo.fir',top+'.sv',top+'-harness.cpp'):pin(emitted/name)
 mapped=W/'mapped'
 stage('ports',[py,'-B',str(C/'prepare_direct_driver.py'),'--low',str(emitted/(top+'.lo.fir')),'--sv',str(emitted/(top+'.sv')),'--harness',str(emitted/(top+'-harness.cpp')),'--spec',str(C/'Public21DownOwnerCrossWindowProtocolOnlySpec.scala'),'--expected-ports',str(C/'EXPECTED_PORTS.json'),'--output',str(mapped)],120,2,sum(x[1]+30 for x in MAIN[3:]))
 need((mapped/'Public21DownOwnerDirectDriver.scala').read_bytes()==(C/'Public21DownOwnerDirectDriver.scala').read_bytes(),'original driver body regenerated exactly')
 pin(mapped/'PORTS.json');pin(mapped/'Public21DownOwnerDirectDriver.scala')
 vlt=pin(W/'tools/verilator');envbin=pin(P('/usr/bin/env').resolve())
 # Same official chiseltest 6.0.0 Verilator/JNA flags as the independently
 # observed original backend; no new FIRRTL/HW optimization or initialization flags.
 cflags="-O1 -DVL_USER_STOP -DVL_USER_FATAL -DVL_USER_FINISH -DTOP_TYPE=V"+top+" -include V"+top+".h -fPIC -shared -I'"+str(java_home/'include')+"' -I'"+str(java_home/'include/linux')+"' -fvisibility=hidden"
 va=[vlt,'--cc','--exe',top+'-harness.cpp','--assert','--coverage-user','-Wno-fatal','-Wno-WIDTH','-Wno-STMTDLY','--top-module',top,'+define+TOP_TYPE=V'+top,'-CFLAGS',cflags,'-Mdir',str(emitted/'verilated'),'-LDFLAGS','-shared -dynamiclib -fvisibility=hidden',top+'.sv']
 stage('verilate',[envbin,'-C',str(emitted),*va],900,6,sum(x[1]+30 for x in MAIN[4:]),stageenv={'PATH':str(W/'tools')+':/usr/bin:/bin'})
 for f in (emitted/'verilated').rglob('*'):
  need(not f.is_symlink(),'generated backend symlink')
  if f.is_file():pin(f)
 stage('make',[pin(P('/usr/bin/make').resolve()),'-C',str(emitted/'verilated'),'-f','V'+top+'.mk','-j1','OPT_FAST=-O0','OPT_SLOW=-O0','OPT_GLOBAL=-O0','VK_PCH_I_FAST=','VK_PCH_I_SLOW='],1800,6,MAIN[-1][1]+30,stageenv={'PATH':str(W/'tools')+':/usr/bin:/bin'})
 library=emitted/'verilated'/('V'+top);pin(library)
 metadata=C/'P0_PROTOCOL_INPUT.json';pin(metadata)
 from prepare_protocol_input import verify
 verify(load(metadata), '4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163')
 args=[str(mapped/'PORTS.json'),sha(mapped/'PORTS.json'),str(library),sha(library),str(emitted)]
 stage('protocol',jvm('512m','heteronpu.continuous.Public21DownOwnerDirectMain',args,True),600,6,0,stageenv={'P0_CLOSED_PROGRAM_MANIFEST':str(metadata),'P0_CLOSED_PROGRAM_MANIFEST_SHA256':sha(metadata)})
 result={'schema':'PUBLIC21_B_FINAL_SAFE_SUMMARY_V1','identity':I,'stages':[{k:x[k] for k in ('stage','receipt_sha256','native_exit','strict_stage_success')} for x in rows],'protocol_driver_returned':True,'mock_matrix_vector_ddr':True,'real_banks':True,'numerical_pass':False,'full_block_pass':False,'actual_p0_fault_reproduced':False,'artifact_transfer':False,'elapsed_whole_seconds':time.monotonic()-t,'whole_budget_seconds':WHOLE}
 save(W/'FINAL_SAFE.json',result);raw=json.dumps(result,sort_keys=True,separators=(',',':'));need(len(raw.encode())<=8192,'final bounded summary');print('PUBLIC21_B_FINAL '+raw,flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  kind=type(e).__name__ if type(e).__name__ in {'ValueError','OSError','FileNotFoundError','TimeoutError','KeyError','TypeError','RuntimeError','CalledProcessError'} else 'UNCLASSIFIED'
  lines=[];tb=e.__traceback__
  while tb is not None:
   if tb.tb_frame.f_code.co_filename==__file__:lines=(lines+[tb.tb_lineno])[-8:]
   tb=tb.tb_next
  phase=STATE['phase'] if STATE['phase'] in PHASES|{'IDENTITY','SOURCE_CLOSURE'} else 'UNKNOWN'
  print(json.dumps({'schema':'PUBLIC21_B_PARENT_FAILURE_V1','exception_class':kind,'phase':phase,'last_completed_stage':STATE['last_completed_stage'] if STATE['last_completed_stage'] in PHASES else None,'runner_line_numbers':lines,'numerical_pass':False,'artifact_transfer':False}),flush=True)
  raise SystemExit(1)
