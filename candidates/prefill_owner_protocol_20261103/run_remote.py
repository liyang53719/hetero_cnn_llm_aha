"""One fresh hosted VM: exact source regeneration, serial build, eight protocol cases.
No model weights, runtime reference, full Top elaboration or MAC numerical claim.
"""
import argparse,gzip,hashlib,json,os,pathlib,re,resource,shutil,struct,subprocess,sys,time
P=pathlib.Path;HERE=P(__file__).resolve().parent
ROOT=P('/workspace/scratch/f28987e955ed');D=ROOT/'prefill_supply_overlap_candidate_20261103T1130';A=D/'next_protocol_resource_analysis';N=A/'native_protocol';W=D/'remote_ci';IR=A/'owner_chirrtl_r1/run/design/TransposedDenseDownOwner.fir';SV=A/'owner_lowering_r1/run/TransposedDenseDownOwner.sv';OBJ=N/'translation_r2/run/obj';V=ROOT/'verilator_dependency_recovery_20261030T0534/tools/verilator-package/usr';VR=V/'share/verilator';VB=V/'bin/verilator_bin'
START=time.monotonic();START_CPU=time.process_time();BASE_USAGE=resource.getrusage(resource.RUSAGE_CHILDREN);OBSERVED_CPU=0.;CPU=0.;PINS={};PHASES=[];ENV={};JOB_START=None;EXPORT_OWNED=False

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):
 with P(p).open('x')as f:json.dump(x,f,indent=2);f.write('\n')
def load(n):return json.loads((HERE/n).read_text())
def pin(p,h=None):
 p=P(p).resolve(strict=True);actual=sha(p);need(h is None or actual==h,'input hash '+str(p));PINS[str(p)]=actual

def light_guard():
 need(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024<=64<<20,'wrapper RSS64MiB')
 if JOB_START is not None:need(time.monotonic()<min(JOB_START+4500,START+3480)-30,'wrapper remaining time');need(global_cpu()<=2400,'whole wrapper CPU')
def verify():
 for i,(p,h)in enumerate(PINS.items()):
  need(sha(p)==h,'input drift '+p)
  if i%32==0:light_guard()
 light_guard()
 if(W/'HOST_TOOLS.json').exists():
  for r in json.loads((W/'HOST_TOOLS.json').read_text())['aliases']:need(str(P(r['requested']).resolve(strict=True))==r['resolved'],'host alias drift')

def global_cpu():
 u=resource.getrusage(resource.RUSAGE_CHILDREN);waited=u.ru_utime+u.ru_stime-BASE_USAGE.ru_utime-BASE_USAGE.ru_stime
 return max(OBSERVED_CPU,waited)+time.process_time()-START_CPU

def freegate():
 mem=int(next(l.split()[1]for l in P('/proc/meminfo').read_text().splitlines()if l.startswith('MemAvailable:')))*1024
 free=shutil.disk_usage(ROOT).free;need(mem>=8<<30 and free>=10<<30,'fresh remote memory/disk gate')
 return dict(MemAvailable=mem,disk_free=free)

def postcheck():
 need(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024<=64<<20,'supervisor/post RSS64MiB')
 need(time.monotonic()<min(JOB_START+4500,START+3480)-30,'whole job/step time reserve');need(global_cpu()<=2400,'whole CPU including wrapper')
 total=0
 for i,p in enumerate(ROOT.rglob('*')):
  if i%32==0:light_guard()
  if p.is_symlink():continue # Official package documentation aliases are not emitted products.
  if p.is_file():total+=p.stat().st_size;need(p.stat().st_size<=128<<20,'single output128MiB')
 need(total<=2<<30 and shutil.disk_usage(ROOT).free>=8<<30,'whole output2GiB/disk8GiB')
 return total

def phase(name,argv,run,rss,cpu,wall,percpu=None,pins=None):
 global CPU,OBSERVED_CPU
 verify();light_guard();need(global_cpu()+cpu<=2400 and time.monotonic()+wall+60<min(JOB_START+4500,START+3480),'remaining whole resource budget');gate=freegate();run.parent.mkdir(parents=True,exist_ok=True)
 before_bytes=postcheck();stage_limits={'acquire':256,'host_inventory':8,'compile159':128,'emit':128,'firtool':128,'ports':2,'translate':128,'build52':512,'protocol8':16};stage_bytes=stage_limits[name]<<20;watch_cap=min(2<<30,before_bytes+stage_bytes)
 caps=dict(wall_seconds=wall,cleanup_seconds=30,per_process_cpu_seconds=percpu or cpu,cpu_seconds=cpu,combined_cpu_seconds=cpu,rss_bytes=rss<<20,per_process_as_bytes=8<<30,file_bytes=128<<20,log_bytes=4<<20,raw_log_bytes=(4<<20)-65536,tree_bytes=stage_bytes,watch_tree_bytes=watch_cap,extra_watch_roots=[str(ROOT)],max_entries=20000,min_free_disk_bytes=8<<30,min_available_memory_bytes=2<<30,supervisor_rss_bytes=64<<20,jdk_aliases=[],forbid_descendants=False)
 before=resource.getrusage(resource.RUSAGE_CHILDREN);r=supervise_multiroot.execute(list(map(str,argv)),str(run),str(W/'owner.lock'),caps,ENV,dict(PINS,**(pins or{})),resource_gate={'min_available_memory':8<<30,'min_disk_free':10<<30});after=resource.getrusage(resource.RUSAGE_CHILDREN)
 waited=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime);charged=max(waited,r['observed_cpu_seconds'])+r['supervisor_cpu_seconds'];OBSERVED_CPU+=r['observed_cpu_seconds'];CPU=global_cpu()
 rec=dict(phase=name,result_sha256=sha(run/'RESULT.json'),waited_children_CPU=waited,observed_CPU_lower_bound=r['observed_cpu_seconds'],charged_CPU=charged,cumulative_CPU=CPU,resource_gate=gate,scope='sampled tree resources with terminal waited CPU reconciliation, not cgroup containment')
 rec.update(bytes_before=before_bytes,new_output_limit_bytes=stage_bytes,aggregate_watch_cap_bytes=watch_cap)
 save(W/'export'/(name+'_accounting.json'),rec);PHASES.append(rec)
 # Export the bounded original process evidence before any success assertion.
 for source,suffix in [('RESULT.json','_result.json'),('frontend.log.gz','.log.gz')]:
  src=run/source
  if src.is_file():
   need(src.stat().st_size<=4<<20,'bounded failure evidence export');shutil.copyfile(src,W/'export'/(name+suffix))
 need(postcheck()-before_bytes<=stage_bytes,'phase complete output including exported evidence')
 need(charged<=cpu and CPU<=2400,'CPU cap');need(r['status']=='PASS_PROCESS_ONLY'and r['native_exit']==0 and not r['errors'],'phase failed '+name)
 need(r['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and not r['observed_remaining'],'cleanup '+name)
 need(r['log_capture']['pipe_eof_observed']and r['log_capture']['gzip_finalized']and not r['log_capture']['capture_cap_hit'],'EOF/log closure '+name)
 postcheck();verify();return r

def bounded_probe(argv,label):
 p=W/'export'/(label+'.txt')
 def limits():
  resource.setrlimit(resource.RLIMIT_FSIZE,(1<<20,1<<20));resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_AS,(256<<20,256<<20))
 with p.open('xb')as f:subprocess.run(list(map(str,argv)),stdout=f,stderr=subprocess.STDOUT,check=True,timeout=10,preexec_fn=limits)
 need(p.stat().st_size<=1<<20,'bounded ELF tool output');light_guard();return p.read_text()

def main(repo):
 global ENV,JOB_START,EXPORT_OWNED
 need(os.environ.get('GITHUB_ACTIONS')=='true'and os.environ.get('GITHUB_REPOSITORY')=='liyang53719/hetero_cnn_llm_aha'and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','only explicitly launched fresh hosted job')
 # Retain even identity, Git, or resource preflight failures before any child phase.
 need(ROOT.is_dir()and not list(ROOT.iterdir()),'new independent VM root must be empty');W.mkdir(parents=True);(W/'export').mkdir();EXPORT_OWNED=True
 ident=json.loads((P(os.environ['RUNNER_TEMP'])/'owner-protocol-identity.json').read_text());clock=json.loads((P(os.environ['RUNNER_TEMP'])/'owner-protocol-clock.json').read_text());JOB_START=clock['started_monotonic']
 need(ident['run_id']==clock['run_id']==os.environ['GITHUB_RUN_ID']and ident['through']=='compile_and_protocol8'and ident['driver_sha256']==load('EXPECTED_GENERATED.json')['driver_sha256'],'exact run identity and preapproved bounded mode')
 # No threaded index preload or optional fsmonitor helper under the wrapper's bounded AS.
 # These flags change metadata-check scheduling, not the clean tracked-content predicate.
 git=['git','-c','core.preloadIndex=false','-c','index.threads=1','-c','core.fsmonitor=false','-C',str(repo)]
 head=subprocess.check_output([*git,'rev-parse','HEAD'],text=True,timeout=5).strip();need(head==ident['source_commit'],'reviewed source checkout');subprocess.run([*git,'diff','--quiet','HEAD','--'],check=True,timeout=5)
 save(W/'export'/'START.json',dict(identity=ident,clock=clock,gate=freegate(),scope='ACTUAL_OWNER_PROTOCOL_ONLY_NOT_NUMERICAL'))
 for p in HERE.rglob('*'):
  if p.is_file():pin(p)
 ENV={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','JAVA_HOME_21_X64':os.environ['JAVA_HOME_21_X64'],'ImageOS':os.environ.get('ImageOS',''),'ImageVersion':os.environ.get('ImageVersion','')}
 for rel in ['candidates/prefill_supply_overlap_20261103/selected159.py','candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json','candidates/ci_frontend_materialization_r2_20261029/VERILATOR_MANIFEST.json']:pin(repo/rel)
 for n in ['EmitRealDownOwnerChirrtl.scala','owner_protocol.cpp','generate_ports.py']:
  dst=(A/n if n.endswith('.scala')else N/n);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(HERE/n,dst);pin(dst,sha(HERE/n))
 pin(N/'owner_protocol.cpp',load('EXPECTED_GENERATED.json')['driver_sha256'])
 selector=load('SELECTED159.json')['independent_selector'];pin(repo/selector['repo_path'],selector['sha256'])
 sys.path.insert(0,str(repo/'candidates/prefill_supply_overlap_20261103'));import selected159 as generation
 selection=generation.selected_inputs(repo,'prefill-supply-overlap-v1');original=json.loads((repo/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text());selected=generation.checked_paths(repo,selection['overlay'],original,selection['contract']);rows=load('SELECTED159.json')['files'];need(len(selected)==len(rows)==159,'actual selected159')
 paths=[]
 for p,r in zip(selected,rows):
  src=P(p);need(src==repo/r['repo_path']and src.stat().st_size==r['bytes']and sha(src)==r['sha256'],'source selection identity');dst=D/'integration_repo'/r['repo_path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);pin(dst,r['sha256']);paths.append(str(dst))
 save(W/'export'/'SELECTED159.json',load('SELECTED159.json'))
 phase('acquire',[sys.executable,'-B',HERE/'acquire_tools.py',HERE/'TOOLS.json',W/'acquire',repo],W/'acquire',128,120,300)
 tools=load('TOOLS.json');jars=[W/'acquire/cache'/(r['sha256']+'.jar')for r in tools['classpath']];plugin=W/'acquire/cache'/(tools['plugin']['sha256']+'.jar')
 for p,r in zip(jars,tools['classpath']):pin(p,r['sha256'])
 manifest=json.loads((repo/tools['verilator_manifest_repo_path']).read_text())
 for r in manifest['files']:
  if r['path'].startswith(('usr/bin/','usr/share/verilator/')):pin(V.parent/r['path'],r['sha256'])
 phase('host_inventory',[sys.executable,'-B',HERE/'collect_host_tools.py',W/'HOST_TOOLS.json'],W/'host_inventory',128,30,60)
 host=json.loads((W/'HOST_TOOLS.json').read_text());save(W/'export'/'HOST_TOOLS.json',host)
 for i,(p,h)in enumerate(host['pins'].items()):
  if i%32==0:light_guard()
  pin(p,h)
 java=host['java'];cxx=host['cxx'];cp=':'.join(map(str,jars));classes=W/'compile/classes'
 jvm=[java,'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xms32m','-Xmx1536m','-XX:ReservedCodeCacheSize=64m','-XX:CompressedClassSpaceSize=128m','-Xss4m']
 phase('compile159',[*jvm,'-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(plugin),'-Xplugin-require:chiselplugin','-d','classes',*paths,str(A/'EmitRealDownOwnerChirrtl.scala')],W/'compile',3072,420,600)
 classrows=[]
 for i,p in enumerate(sorted(classes.rglob('*.class'))):
  if i%32==0:light_guard()
  pin(p);classrows.append(dict(path=str(p.relative_to(classes)),bytes=p.stat().st_size,sha256=sha(p)))
 need(classrows and any(r['path'].endswith('EmitRealDownOwnerChirrtl$.class')for r in classrows),'new emitter class');save(W/'export'/'CLASSES.json',classrows)
 phase('emit',[*jvm[:5],'-Xmx512m','-Xss4m','-cp',str(classes)+':'+cp,'heteronpu.continuous.EmitRealDownOwnerChirrtl'],A/'owner_chirrtl_r1/run',1024,60,120)
 expect=load('EXPECTED_GENERATED.json');need(IR.stat().st_size==expect['CHIRRTL']['bytes'],'IR bytes');pin(IR,expect['CHIRRTL']['sha256'])
 ft=A/'owner_lowering_r1/tools/firtool';ft.parent.mkdir(parents=True);shutil.copyfile(W/'acquire/firtool',ft);ft.chmod(0o500);pin(ft,tools['firtool_binary_sha256']);need(not(ft.parent.parent/'lib').exists(),'firtool copied ORIGIN/../lib remains absent; pinned system resolution only')
 phase('firtool',[ft,'-format=fir',IR,'-o','TransposedDenseDownOwner.sv','-warn-on-unprocessed-annotations','-output-annotation-file','circt.anno.json','--preserve-values=all','-disable-all-randomization','--verbose-pass-executions','--mlir-disable-threading'],A/'owner_lowering_r1/run',768,180,300)
 need(SV.stat().st_size==expect['SV']['bytes'],'SV bytes');pin(SV,expect['SV']['sha256'])
 phase('ports',[sys.executable,'-B',N/'generate_ports.py'],W/'ports',64,10,30)
 pin(N/'ports_generated.hpp',expect['generated_header_sha256']);pin(N/'PORTS.json')
 ENV.update(VERILATOR_ROOT=str(VR),LD_LIBRARY_PATH='/lib/x86_64-linux-gnu')
 phase('translate',[VB,'--cc','--exe','--top-module','TransposedDenseDownOwner','--Mdir','obj','--threads','1','--output-split','10000','--output-split-cfuncs','1000','--assert','-Wno-fatal',SV,N/'owner_protocol.cpp'],N/'translation_r2/run',768,180,360)
 need({p.name for p in OBJ.iterdir()}=={r['name']for r in expect['generated_files']},'exact57 generated set')
 for r in expect['generated_files']:
  if r['name']in expect['byte_identical_required']:need((OBJ/r['name']).stat().st_size==r['bytes'],'generated size');pin(OBJ/r['name'],r['sha256'])
 dat=OBJ/'VTransposedDenseDownOwner__verFiles.dat';need(dat.stat().st_size<=64<<10,'bounded timestamp metadata64KiB');rows=[];command=None
 for line in dat.read_text().splitlines():
  if line.startswith('C '):need(command is None,'single C record');command=line
  elif line.startswith(('S ','T ')):
   m=re.fullmatch(r'([ST])\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"([^"]+)"',line);need(m,'timestamp metadata syntax');rows.append(dict(role=m[1],bytes=int(m[2]),path=m[8]))
  else:need(not line or line.startswith('#'),'unexpected metadata record')
 need(command==expect['timestamp_metadata_identity']['C_record']and rows==expect['timestamp_metadata_identity']['records'],'dat role/path/size/argv identity');pin(dat)
 phase('build52',[sys.executable,'-B',HERE/'compile_worker.py',OBJ,VR/'include',N/'owner_protocol.cpp',cxx,W/'objects'],W/'build',4096,1200,1800,240)
 recipes=json.loads((W/'objects/RECIPES.json').read_text());need(len(recipes['compile'])==52 and len({r['object']for r in recipes['compile']})==52,'52 fresh objects');deps=set();objects=[]
 for row in recipes['compile']:
  light_guard()
  obj=W/'objects'/row['object'];dep=obj.with_suffix('.d');need(obj.is_file()and dep.is_file()and dep.stat().st_size<1<<20,'object/dependency');data=obj.open('rb').read(20);need(data[:4]==b'\x7fELF'and data[4:6]==b'\x02\x01'and struct.unpack('<H',data[16:18])[0]==1,'ELF64 REL object')
  first=dep.read_text().replace('\\\n','').splitlines()[0];need(':'in first,'MD syntax')
  for i,name in enumerate(first.partition(':')[2].split()):
   if i%32==0:light_guard()
   p=P(name);p=p if p.is_absolute()else W/'build'/p;p=p.resolve(strict=True);need(str(p)in PINS,'unrecorded MD dependency '+str(p));deps.add(str(p))
  pin(obj);objects.append(dict(name=obj.name,bytes=obj.stat().st_size,sha256=sha(obj)))
 need(any(x.startswith('/usr/include/')for x in deps)and len(list((W/'objects').glob('*.o')))==52 and not list(W.rglob('*.gch')),'full system MD and no PCH')
 need(not list(W.rglob('*.gch')),'no PCH')
 elf=W/'objects/owner_protocol';data=elf.open('rb').read(20);need(data[:6]==b'\x7fELF\x02\x01'and struct.unpack('<H',data[18:20])[0]==62,'ELF x86_64');pin(elf)
 phdr=bounded_probe(['/usr/bin/readelf','-l',elf],'ELF_PROGRAM_HEADERS');interp=re.findall(r'Requesting program interpreter: ([^\]]+)\]',phdr);need(len(interp)==1 and str(P(interp[0]).resolve(strict=True))in PINS,'ELF PT_INTERP pinned')
 dynamic=bounded_probe(['/usr/bin/readelf','-d',elf],'ELF_DYNAMIC');need('(RPATH)'not in dynamic and '(RUNPATH)'not in dynamic,'unexpected ELF search path');needed=re.findall(r'\(NEEDED\).*?\[([^]]+)\]',dynamic)
 for name in needed:
  lib=next((d/name for d in [P('/lib/x86_64-linux-gnu'),P('/usr/lib/x86_64-linux-gnu')]if(d/name).is_file()),None);need(lib is not None and str(lib.resolve())in PINS,'new ELF unpinned library '+name)
 symbols=bounded_probe(['/usr/bin/nm','-C',elf],'ELF_SYMBOLS');need('VTransposedDenseDownOwner::eval_step()'in symbols and 'VTransposedDenseDownOwner::VTransposedDenseDownOwner('in symbols,'linked actual owner interface');verify()
 save(W/'export'/'BUILD.json',dict(objects=objects,ELF_sha256=sha(elf),ELF_bytes=elf.stat().st_size,actual_MD_dependencies=sorted(deps),generated_metadata_sha256=sha(dat),scope='New52TU link; no protocol run yet'))
 phase('protocol8',[elf],W/'model',1024,120,180,120)
 with gzip.open(W/'model/frontend.log.gz','rt')as f:log=f.read(4<<20)
 cases=re.findall(r'^CASE tag=(\d+) .* PASS_OWNER_PROTOCOL_ONLY$',log,re.M);need(cases==['1','2','3','4','11','12','13','14'],'exact8case markers')
 need(len(re.findall(r'^COUNTERS ',log,re.M))==8 and len(re.findall(r'^EVENT next_N_read_before_old_group_ACK ',log,re.M))>=2,'actual external counters/nextN events')
 terminal='PASS 8 owner protocol cases; synthetic Matrix payload, no DMA/TileSumBridge/arithmetic/full4096 qualification'
 need(log.splitlines().count(terminal)==1 and not re.search(r'^FAIL',log,re.M),'unique terminal protocol marker/no FAIL')
 counts=re.findall(r'^COUNTERS tag=(\d+) accepted_steps=(\d+) retired_results=(\d+) group_done=(\d+) returned_beats=(\d+) write_ACK_count=(\d+) write_ACK_bytes=(\d+)$',log,re.M)
 need(len(counts)==8,'exact counter grammar')
 for row,expected in zip(counts[:4],[(1,1280,10,2,2304,163840),(2,768,6,2,768,98304),(3,768,6,2,2560,98304),(4,128,1,1,1152,16384)]):
  tag,steps,retired,groups,returned,acks,bytes_=map(int,row);need((tag,steps,retired,groups,returned,bytes_)==expected and acks>0,'precise success counters')
 for row,tag in zip(counts[4:],[11,12,13,14]):
  got,steps,retired,groups,returned,acks,bytes_=map(int,row);need(got==tag and steps==retired==groups==acks==bytes_==0 and returned>1,'fault drain counters')
 verify();postcheck()
 save(W/'export'/'FINAL.json',dict(status='PASS_8_ACTUAL_OWNER_PROTOCOL_CASES_ONLY',source_commit=head,driver_sha256=sha(N/'owner_protocol.cpp'),SV_sha256=sha(SV),ELF_sha256=sha(elf),cumulative_CPU_seconds=global_cpu(),phases=PHASES,no_full4096_arithmetic=True,no_DMA=True,no_TileSumBridge=True,no_weight_or_reference_acquisition=True))

if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_AS,(256<<20,8<<30));resource.setrlimit(resource.RLIMIT_CORE,(0,0));p=argparse.ArgumentParser();p.add_argument('--execute-compile-and-protocol8',action='store_true');p.add_argument('--repo',type=P,required=True);args=p.parse_args();need(args.execute_compile_and_protocol8,'explicit reviewed whole route required');sys.path.insert(0,str(HERE/'supervisor'));import supervise_multiroot
 try:main(args.repo.resolve())
 except BaseException as e:
  if EXPORT_OWNED and(W/'export').is_dir():save(W/'export'/'FAILED.json',dict(status='FAIL_OR_INCOMPLETE',error=type(e).__name__+': '+str(e),phases=PHASES,cumulative_CPU_seconds=CPU,no_automatic_retry=True))
  raise
