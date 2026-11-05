"""One source-only structural job. No engine/native, weights, references or IR export."""
import contextlib,gzip,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,sys,time,urllib.request,zipfile
P=pathlib.Path;D=P(__file__).resolve().parent;REPO=D.parent.parent
REL='candidates/chisel_structural_graph_20261104';NONCE='ci_launch/chisel_structural_graph_20261105_cycle_witness_fresh_once.json'
CAT='candidates/gdn32_first_model_execution_20261104/GDN32_FULL_SOURCE_PINS.json'
CAT_SHA='ad2d4dcaddb213c85fd15adc65f7da5bd74a0d7c3e6c5922c725aa41bdc967cb'
BASE='364f38c8a6300595281b9cc15202ff4276a0e936';TREE=12_081_306_272;RESERVE=8<<30
from witness_record import parse_record as parse_witness_record
graph_identity={}
differential_identity={}
class Stop(Exception):
 def __init__(self,code='GUARD_REJECTED'):self.code=code;super().__init__(code)
def need(x,code='GUARD_REJECTED'):
 if not x:raise Stop(code)
def jdk_location_allowed(path):
 return str(path) in ('/usr/lib/jvm/temurin-21-jdk-amd64','/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/21.0.13-9/x64')
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p):
 p=P(p);need(p.is_absolute() and p==p.resolve() and p.is_file() and all(not q.is_symlink()for q in(p,*p.parents)));return p
def git(*a):return subprocess.check_output(['git','-C',str(REPO),*a],text=True,stderr=subprocess.DEVNULL,timeout=20).strip()
def load(p,cap=2<<20):
 p=regular(p);need(0<p.stat().st_size<=cap);return json.loads(p.read_text())
def pins_for(rows,root):
 out={}
 for r in rows:
  rel=P(r['path']);need(not rel.is_absolute() and '..'not in rel.parts);p=regular(root/rel)
  need(type(r['bytes'])is int and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'] and str(p)not in out);out[str(p)]=r['sha256']
 return out
def admission():
 mem=int(next(x.split()[1]for x in P('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:')))*1024
 need(mem>=13<<30 and shutil.disk_usage(REPO).free>=TREE+RESERVE)
def remote_exclusive(launch,wait_seconds=90):
 token=os.environ.get('GITHUB_TOKEN');need(bool(token))
 base='https://api.github.com/repos/liyang53719/hetero_cnn_llm_aha'
 def get(path):
  req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
  with urllib.request.urlopen(req,timeout=20)as f:data=f.read(1_048_577)
  need(len(data)<=1_048_576);return json.loads(data)
 deadline=time.monotonic()+wait_seconds
 while True:
  need(get('/git/ref/heads/main')['object']['sha']==launch)
  busy=False
  for status in ('in_progress','queued','waiting','pending','requested'):
   x=get('/actions/runs?status='+status+'&per_page=100');need(x['total_count']<=100)
   busy=busy or any(str(r['id'])!=os.environ['GITHUB_RUN_ID'] for r in x['workflow_runs'])
  if not busy:return
  need(time.monotonic()<deadline);time.sleep(3)

def project(stage,r):
 return {'stage':stage,'status':'COMPLETE' if r.get('status')=='PASS_PROCESS_ONLY' else 'INCOMPLETE','elapsed_seconds':r.get('elapsed_seconds'),'peak_rss':r.get('observed_peak_rss'),'cpu_seconds':r.get('observed_cpu_seconds'),'cleanup_complete':r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'}
# Proposal only: fixed-schema diagnostics, never an alternate success oracle.
PHASES=('admission','read','parse','roundtrip','split','official_lower','lower_checks','get_firrtl_ast','set_implicit_output_info','prepare_ast','prepared_checks','symbol_table','summary_hash')
PHASE_RE='(?:'+'|'.join(PHASES)+')'
METRIC_RE=re.compile(r'GRAPH_PHASE_V1 seq=([0-9]+) kind=(BEGIN|END|SAMPLE|CYCLE_SEEN) phase=('+PHASE_RE+r') wallMs=([0-9]+) cpuMs=([0-9]+) heapUsed=([0-9]+) heapMax=([0-9]+) gcMillis=([0-9]+) gcCount=([0-9]+) cycleSeen=([01])')
PASS_RE=re.compile(r'PASS_DECLARED_CONE_TOPOLOGY_ONLY highSha=([0-9a-f]{64}) annotationsSha=([0-9a-f]{64}) preparedSha=([0-9a-f]{64}) symbols=([0-9]+) leafBindings=17 nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false suppressedDiagnosticBytes=([0-9]+) cycleSeen=([01])')
FAIL_RE=re.compile(r'FAIL_STRUCTURAL_GRAPH_ONLY stage=('+PHASE_RE+r') exceptionClassSha=([0-9a-f]{64}) nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false suppressedDiagnosticBytes=([0-9]+) cycleSeen=([01])')
def parse_graph_text(text,receipt,high_sha,annotations_sha):
 need(type(text)is str and len(text.encode('ascii'))<=32768,'GRAPH_LOG_LIMIT')
 need(not text or text.endswith('\n'),'GRAPH_LOG_TRUNCATED_LINE')
 lines=text.splitlines();need(len(lines)<=98,'GRAPH_RECORD_LIMIT')
 rows=[];final=None;active=None;next_phase=0;last=None;last_phase=None;cycle_event_seen=False;witness=None
 for line in lines:
  need(final is None,'GRAPH_LOG_TRAILING_OR_LONG')
  if line.startswith('GRAPH_CYCLE_WITNESS '):
   need(witness is None and active=='symbol_table' and not cycle_event_seen,'GRAPH_WITNESS_ORDER')
   try:witness=parse_witness_record(line[len('GRAPH_CYCLE_WITNESS '):])
   except (ValueError,TypeError,KeyError):raise Stop('GRAPH_WITNESS_SCHEMA')
   continue
  need(len(line)<=1024,'GRAPH_LOG_TRAILING_OR_LONG')
  m=METRIC_RE.fullmatch(line)
  if m:
   seq=int(m[1]);kind=m[2];phase=m[3];values=list(map(int,m.groups()[3:]))
   wall,cpu,used,maximum,gc_ms,gc_count,cycle=values
   need(seq==len(rows)+1 and seq<=96 and all(0<=v<1<<63 for v in values),'GRAPH_METRIC_RANGE')
   need(used<=maximum and 0<maximum<=15<<30 and wall<=2400000 and cpu<=2400000,'GRAPH_METRIC_RANGE')
   if last:
    need(all(values[i]>=last[i]for i in (0,1,4,5,6)) and maximum==last[3],'GRAPH_METRIC_REGRESSION')
   if kind=='BEGIN':
    need(active is None and next_phase<len(PHASES) and phase==PHASES[next_phase],'GRAPH_PHASE_ORDER');active=phase
   else:
    need(active==phase,'GRAPH_PHASE_ORDER')
    if kind=='CYCLE_SEEN':
     need(phase=='symbol_table' and cycle==1 and not cycle_event_seen,'GRAPH_CYCLE_EVENT_INVALID');cycle_event_seen=True
    if kind=='END':active=None;next_phase+=1
   last_phase=phase;last=values
   rows.append(dict(seq=seq,kind=kind,phase=phase,wall_ms=wall,cpu_ms=cpu,heap_used=used,heap_max=maximum,gc_ms=gc_ms,gc_count=gc_count,cycle_seen=bool(cycle)))
   continue
  a=PASS_RE.fullmatch(line);b=FAIL_RE.fullmatch(line)
  need(a is not None or b is not None,'GRAPH_LOG_NOT_WHITELISTED')
  if a:
   need(active is None and next_phase==len(PHASES) and witness is None,'GRAPH_SUCCESS_INCOMPLETE_PHASES')
   need(a[1]==high_sha and a[2]==annotations_sha and a[6]=='0' and (not last or last[6]==0),'GRAPH_SUCCESS_IDENTITY_OR_CYCLE')
   need(int(a[4])>0 and int(a[4])<1<<63 and int(a[5])<=8<<20,'GRAPH_FINAL_RANGE')
   final=dict(kind='success',prepared_sha256=a[3],symbol_count=int(a[4]))
  else:
   need(b[1]==(last_phase or 'admission'),'GRAPH_FAILURE_PHASE_MISMATCH')
   need(int(b[3])<=8<<20 and int(b[4])>=(last[6]if last else 0),'GRAPH_FINAL_RANGE')
   final=dict(kind='failure',phase=b[1],exception_class_sha256=b[2],cycle_seen=b[4]=='1')
 clean=receipt.get('status')=='PASS_PROCESS_ONLY' and receipt.get('native_exit')==0 and receipt.get('errors')==[] and receipt.get('worker_started')is True
 if final and final['kind']=='success':need(clean,'GRAPH_FALSE_SUCCESS_RECEIPT')
 # Keep at most last sample/marker per phase in exported JSON, not the full log.
 latest={r['phase']:r for r in rows}
 out=dict(status='INCOMPLETE_STRUCTURAL_GRAPH_ONLY',last_phase=last_phase,metric_records=len(rows),phase_metrics=list(latest.values()),cycle_seen=bool(last and last[6]))
 if final and final['kind']=='success':out.update(status='STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES',prepared_sha256=final['prepared_sha256'],symbol_count=final['symbol_count'],leaf_bindings=17)
 elif final:out.update(status='FAILED_STRUCTURAL_GRAPH_ONLY',phase=final['phase'],exception_class_sha256=final['exception_class_sha256'],cycle_seen=final['cycle_seen'])
 if witness is not None:
  need(final is not None and final['kind']=='failure' and final['cycle_seen'],'GRAPH_WITNESS_WITHOUT_CYCLE_FAILURE')
  out['cycle_witness']=witness
 return out

def read_closed_log(path,receipt):
 need((receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','GRAPH_CLEANUP_UNPROVEN')
 barrier=receipt.get('reader_join_barrier')or{};cap=receipt.get('log_capture')or{}
 need(barrier.get('complete')is True and barrier.get('alive')is False and barrier.get('reader_finally_done')is True,'GRAPH_READER_UNCLOSED')
 need(cap.get('pipe_eof_observed')is True and cap.get('gzip_finalized')is True and cap.get('capture_cap_hit')is False,'GRAPH_LOG_UNFINALIZED')
 path=regular(path);need(path.stat().st_size<=65536,'GRAPH_COMPRESSED_LOG_LIMIT')
 need(cap.get('compressed_bytes')==path.stat().st_size and cap.get('compressed_sha256')==sha(path),'GRAPH_COMPRESSED_LOG_IDENTITY')
 with gzip.open(path,'rb')as f:raw=f.read(32769)
 need(len(raw)<=32768 and cap.get('raw_bytes')==len(raw) and cap.get('raw_sha256')==hashlib.sha256(raw).hexdigest(),'GRAPH_RAW_LOG_IDENTITY')
 try:text=raw.decode('ascii')
 except UnicodeError:raise Stop('GRAPH_LOG_ENCODING')
 return text

def read_graph_diagnostics(path,receipt,high_sha,annotations_sha):
 return parse_graph_text(read_closed_log(path,receipt),receipt,high_sha,annotations_sha)

def stage_cpu_budget(name,seconds):
 # One explicit graph continuation, not a general stage cap relaxation.
 if name=='graph':
  need(seconds==1500,'GRAPH_WALL_CONTRACT');return 1200
 return min(seconds,600)

def main():
 global phase,graph_identity,differential_identity
 graph_identity={};differential_identity={}
 phase='identity';need(os.environ.get('GITHUB_REPOSITORY')=='liyang53719/hetero_cnn_llm_aha' and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1')
 launch=git('rev-parse','HEAD');need(launch==os.environ.get('GITHUB_SHA'));source=git('rev-parse','HEAD^');need(git('merge-base',BASE,source)==BASE)
 need(git('diff','--name-only','HEAD^','HEAD')==NONCE and not git('status','--porcelain'))
 nonce=load(REPO/NONCE,4096);need(nonce=={'schema':'ONE_STRUCTURAL_GRAPH_ONLY_V1','source_commit':source,'base_commit':BASE,'attempts':1,'numerical_execution':False,'native_execution':False,'artifact_upload':False})
 own=load(D/'SOURCE_PINS.json');pins=pins_for(own['files'],REPO);pins[str(D/'SOURCE_PINS.json')]=sha(D/'SOURCE_PINS.json')
 changed=set(git('diff','--name-only',BASE,source).splitlines());need(changed==set(own['publication_delta']) and changed=={'candidates/chisel_structural_graph_20261104/SOURCE_PINS.json', 'candidates/chisel_structural_graph_20261104/run.py', '.github/workflows/chisel-structural-graph-once.yml'})
 catalog=regular(REPO/CAT);need(sha(catalog)==CAT_SHA);doc=load(catalog);need(doc['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1'and len(doc['files'])==1211);pins.update(pins_for(doc['files'],REPO));pins[str(catalog)]=CAT_SHA
 phase='admission';remote_exclusive(launch);admission();work=P(os.environ['RUNNER_TEMP'])/'chisel-structural-graph';need(work.is_absolute()and not work.exists()and all(not p.is_symlink()for p in(work,*work.parents)));work.mkdir()
 contract={'schema':'BOUNDED_FRESH_HOST_V1','run_id':int(os.environ['GITHUB_RUN_ID']),'source_commit':source,'launch_commit':launch};contractPath=work/'fresh-host.json';contractPath.write_text(json.dumps(contract));pins[str(contractPath)]=sha(contractPath)
 material=REPO/'candidates/ci_frontend_materialization_r2_20261029';sys.path.insert(0,str(material));import fresh_host
 fresh_host.reject_injection(os.environ);fresh_host.validate_contract(contract)
 supdir=REPO/'candidates/ci_frontend_pipeline_r2_20261029';sys.path.insert(0,str(supdir));import supervise_multiroot as supervisor
 started=time.monotonic();reports=[];aliases=[]
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','GITHUB_RUN_ID':os.environ['GITHUB_RUN_ID'],'GITHUB_SHA':launch,'GITHUB_RUN_ATTEMPT':'1','ImageVersion':os.environ.get('ImageVersion',''),'ImageOS':os.environ.get('ImageOS','')}
 py=str(P('/usr/bin/python3').resolve());pins[py]=sha(py)
 def stage(name,args,seconds,rss):
  global phase
  phase=name
  if args and args[0].endswith('/bin/java'):args=[args[0],'-Djava.io.tmpdir='+str(work/name/'tmp'),*args[1:]]
  remote_exclusive(launch);need(time.monotonic()-started+seconds+90<2400)
  cap=dict(wall_seconds=seconds,cleanup_seconds=30,cpu_seconds=stage_cpu_budget(name,seconds),per_process_cpu_seconds=stage_cpu_budget(name,seconds),rss_bytes=rss<<30,per_process_as_bytes=15<<30,file_bytes=536870912,tree_bytes=3<<30,watch_tree_bytes=TREE,max_entries=150000,log_bytes=16<<20,raw_log_bytes=32<<20,min_free_disk_bytes=RESERVE,extra_watch_roots=[str(REPO),str(work)],jdk_aliases=aliases)
  stage_env=dict(env)
  if name=='jdk_inventory':stage_env['JAVA_TOOL_OPTIONS']='-Djava.io.tmpdir='+str(work/name/'tmp')+' -XX:-UsePerfData -XX:-HeapDumpOnOutOfMemoryError -XX:ErrorFile=/dev/null'
  with open(os.devnull,'w')as muted,contextlib.redirect_stdout(muted),contextlib.redirect_stderr(muted):
   r=supervisor.execute(args,str(work/name),str(work/'owner.lock'),cap,stage_env,dict(pins),resource_gate={'min_available_memory':13<<30,'min_disk_free':TREE+RESERVE})
  reports.append(project(name,r));print(json.dumps({'schema':'STRUCTURAL_GRAPH_PROGRESS_V1',**reports[-1],'numerical_pass':False}),flush=True)
  if name in ('graph','diff_official','diff_cached','witness_fixture'):return work/name,r # Parse only after independent cleanup/log-finalization gates.
  need(r.get('native_exit')in ((0,1)if name=='jdk_inventory'else(0,)) and not r.get('errors') and reports[-1]['cleanup_complete'])
  return work/name
 phase='jdk_location'
 need(bool(os.environ.get('JAVA_HOME_21_X64')),'JDK_ENVIRONMENT_MISSING')
 rawhome=P(os.environ['JAVA_HOME_21_X64']);need(rawhome.is_absolute(),'JDK_HOME_NOT_ABSOLUTE');need(rawhome.is_dir(),'JDK_HOME_MISSING');home=rawhome.resolve(strict=True);need(jdk_location_allowed(home),'JDK_HOME_LOCATION_REJECTED')
 inv=stage('jdk_inventory',[py,str(material/'inventory_runner_jdk.py'),'--java-home',str(home),'--output',str(work/'jdk_inventory.json'),'--fresh-host-contract',str(contractPath),'--fresh-host-contract-sha256',sha(contractPath)],300,1)
 jdk=load(work/'jdk_inventory.json',4<<20)
 if jdk.get('status')=='FAIL_JDK_INVENTORY':
  code=jdk.get('failure_code');allowed={'JDK_UNKNOWN_EXTERNAL_ALIAS','JDK_EXTERNAL_TARGET_NOT_BOUNDED_REGULAR','JDK_RELEASE_IDENTITY_MISMATCH','JDK_ARCH_MISMATCH','RUNNER_IMAGE_MISMATCH','JDK_PROBE_LOG_CAP','JDK_RUNTIME_IDENTITY_MISMATCH','JDK_TREE_BUDGET','JDK_PROBE_TIMEOUT','JDK_PROBE_NONZERO','JDK_FILESYSTEM_ERROR','JDK_UNCLASSIFIED_FAILURE'}
  need(code in allowed);raise Stop(code)
 need(jdk.get('status')=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION','JDK_INVENTORY_SCHEMA_REJECTED')
 for row in jdk['files']:
  p=home/row['path']
  if 'symlink'in row:
   aliases.append({'path':str(p),'link':row['symlink'],'target':row['resolved_target']})
   if 'external_dependency'in row:
    dep=row['external_dependency'];pins[dep['resolved_target']]=dep['sha256']
  else:pins[str(p)]=row['sha256']
 java=str(home/'bin/java');need(java in pins)
 phase='jars';stage('jars',[py,str(D/'prepare_jars.py'),str(REPO)],300,1)
 original=REPO/'candidates/fresh_original_top_recovery_20261028';m=load(original/'SOURCE_AND_TOOLCHAIN_PINS.json');jars=[];plugin=None
 for row in m['jars']:
  p=regular(original/'cache'/row['maven_path']);need(sha(p)==row['sha256']);pins[str(p)]=row['sha256']
  if row['role']=='plugin':plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin is not None);cp=':'.join(jars)
 gatepath=REPO/'candidates/gdn32_first_model162_producer_20261104/candidate_generation_gate.py';spec=importlib.util.spec_from_file_location('reviewed_graph_inputs',gatepath);gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 selection=gate.selected_inputs(REPO,gate.MODEL162_SOURCE);sources=gate.checked_paths(REPO,selection['overlay'],m,selection['contract']);need(len(sources)==162)
 def jvm(heap,classpath,main,args=()):return [java,'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-XX:-HeapDumpOnOutOfMemoryError','-XX:ErrorFile=/dev/null','-cp',classpath,main,*args]
 # Compile a narrowly patched official SymbolTable and one common fixture.
 # No JVM simulation engine or native library is constructed by either.
 patch_source=regular(D/'modulecache/SymbolTable.scala');fixture_source=regular(D/'modulecache/StructuralDifferential.scala')
 need(sha(patch_source)=='363cfcbc9df17d340580b2308551a83877ab91637c42bda3a6351e2b9fd22fc3')
 witness_source=regular(D/'modulecache/BoundedCycleWitness.scala')
 official_jars=[p for p in jars if P(p).name=='chiseltest_2.13-6.0.0.jar'];need(len(official_jars)==1)
 official_jar=official_jars[0]
 with zipfile.ZipFile(official_jar)as z:
  official_pins={'source_sha256':'9d8cf72aa1efb8c7ebd3e174da99e509bd7d44aec60a1c391b0dfc6f7b453bab','class_sha256':hashlib.sha256(z.read('treadle2/executable/SymbolTable.class')).hexdigest(),'companion_sha256':hashlib.sha256(z.read('treadle2/executable/SymbolTable$.class')).hexdigest()}
 patchclasses=stage('compile_modulecache',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-d','.',str(patch_source),str(witness_source)]),90,3)
 for p in patchclasses.rglob('*.class'):pins[str(p)]=sha(p)
 cached_pins={'source_sha256':sha(patch_source),'class_sha256':sha(regular(patchclasses/'treadle2/executable/SymbolTable.class')),'companion_sha256':sha(regular(patchclasses/'treadle2/executable/SymbolTable$.class'))}
 need(cached_pins['companion_sha256']!=official_pins['companion_sha256'])
 fixtureclasses=stage('compile_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-d','.',str(fixture_source)]),90,3)
 for p in fixtureclasses.rglob('*.class'):pins[str(p)]=sha(p)
 need(not (fixtureclasses/'treadle2/executable/SymbolTable.class').exists() and not (fixtureclasses/'treadle2/executable/SymbolTable$.class').exists())
 compare_spec=importlib.util.spec_from_file_location('strict_fixture_compare',D/'compare_fixture_results.py');comparator=importlib.util.module_from_spec(compare_spec);compare_spec.loader.exec_module(comparator)
 differential_identity={'differential_status':'PENDING','official_symbol_table':official_pins,'patched_symbol_table':cached_pins,'fixture_source_sha256':sha(fixture_source),'interpreter_bookkeeping_modified':True}
 results=[]
 for label,expected,location,classpath in [('official',official_pins,official_jar,str(fixtureclasses)+':'+cp),('cached',cached_pins,str(patchclasses),str(patchclasses)+':'+str(fixtureclasses)+':'+cp)]:
  folder,receipt=stage('diff_'+label,jvm('1g',classpath,'treadle2.executable.StructuralDifferential',[label,expected['source_sha256'],expected['class_sha256'],expected['companion_sha256'],location]),45,2)
  text=read_closed_log(folder/'frontend.log.gz',receipt)
  need(receipt.get('status')=='PASS_PROCESS_ONLY' and receipt.get('worker_started')is True,'DIFFERENTIAL_PROCESS_FAILED')
  # These booleans are derived from the actual closed-log checks above, not a synthetic receipt.
  process={'exit':receipt.get('native_exit'),'errors':receipt.get('errors'),'cleanup_complete':(receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','log_finalized':(receipt.get('log_capture')or{}).get('gzip_finalized')is True}
  results.append((text,process))
 differential=comparator.compare(results[0][0],results[1][0],official_pins,cached_pins,results[0][1],results[1][1])
 differential_identity.update(differential_status=differential['status'],differential_cases=differential['cases'])
 # Qualify the exact witness implementation before any large original graph.
 witness_fixture=regular(D/'modulecache/CycleWitnessFixture.scala')
 witnessclasses=stage('compile_witness_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',str(patchclasses)+':'+cp,'-d','.',str(witness_fixture)]),90,3)
 for p in witnessclasses.rglob('*.class'):pins[str(p)]=sha(p)
 wf,wr=stage('witness_fixture',jvm('1g',str(patchclasses)+':'+str(witnessclasses)+':'+cp,'treadle2.executable.CycleWitnessFixture'),45,2)
 wt=read_closed_log(wf/'frontend.log.gz',wr)
 cases=('self_loop','multi_loop','acyclic','reachable_other_cycle','node_cap','edge_cap','output_cap','time_cap','reverse_edge','invalid_role','name_cap','lazy_edges','callback_error','malformed_record','record_disclosure','exception_noninterference')
 expected=''.join('CYCLE_FIXTURE_V1 case='+c+' outcome=PASS\n'for c in cases)+'CYCLE_FIXTURE_FINAL_V1 cases=16 status=PASS\n'
 need(wt==expected and wr.get('status')=='PASS_PROCESS_ONLY' and wr.get('native_exit')==0 and not wr.get('errors'),'WITNESS_FIXTURE_FAILED')
 differential_identity.update(witness_fixture_status='PASS_16_SMALL_CASES_ONLY',witness_source_sha256=sha(witness_source),witness_fixture_source_sha256=sha(witness_fixture))
 # The live 2400-second gate remains authoritative before every later stage.
 classes=stage('compile_original',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.',*sources]),300,3)
 for p in classes.rglob('*.class'):pins[str(p)]=sha(p)
 basecp=str(classes)+':'+cp
 helpers=sorted(str(p)for p in (D/'scala').glob('*.scala'));need(len(helpers)==5)
 hclasses=stage('compile_graph',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',str(patchclasses)+':'+basecp,'-d','.',*helpers]),300,3)
 for p in hclasses.rglob('*.class'):pins[str(p)]=sha(p)
 highdir=stage('original_high',jvm('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'),600,6)/'host-diagnostic'
 high=regular(highdir/'original-high.fir');ann=regular(highdir/'high-annotations.json');ext=regular(highdir/'high-extmodules.fir')
 need(high.stat().st_size<=512<<20 and ann.stat().st_size<=16<<20 and ext.stat().st_size<=1<<20)
 # Separate inventory emitted by the unchanged original diagnostic is cross-bound
 # to the complete freshly generated high by the structural helper's own parser.
 blocks=re.split(r'(?m)(?=^extmodule )',ext.read_text());matches=[b for b in blocks if b.startswith('extmodule idma_backend_rw_axi_flat_wrap :')];need(len(matches)==1)
 need(matches[0].endswith('\n'));exttext=matches[0][:-1];extsha='85b299b3b237b70a8450315f887a2f8aad53bd86c95fb8d9a2ff943173cb4193';need(hashlib.sha256(exttext.encode()).hexdigest()==extsha)
 for p in (high,ann,ext):pins[str(p)]=sha(p)
 highsha=sha(high);annsha=sha(ann)
 identity={'high_sha256':highsha,'high_bytes':high.stat().st_size,'annotations_sha256':annsha,'annotations_bytes':ann.stat().st_size}
 graph_identity=dict(identity)
 graphdir,graphreceipt=stage('graph',jvm('4g',str(patchclasses)+':'+str(hclasses)+':'+basecp,'chiseltest.simulator.OriginalHostStructuralGraph',[str(high),highsha,str(ann),annsha,extsha]),1500,6)
 # Budget failures may yield useful diagnostics ONLY after closed/finalized log
 # and complete process cleanup. Never promote markers to numerical/graph PASS.
 try:diagnostics=read_graph_diagnostics(graphdir/'frontend.log.gz',graphreceipt,highsha,annsha)
 except BaseException as error:
  diagnostics={'status':'FAIL_OR_INCOMPLETE','reason':error.code if isinstance(error,Stop)else'GRAPH_DIAGNOSTIC_REJECTED'}
 need(shutil.disk_usage(work).free>=RESERVE)
 if diagnostics['status']=='STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES':
  for path,digest in pins.items():need(sha(path)==digest)
 return {'schema':'STRUCTURAL_GRAPH_ONLY_V1',**diagnostics,**identity,**differential_identity,'final_reserve_preserved':True,'owned_process_cleanup_complete':all(r['cleanup_complete']for r in reports),'private_job_files_exported':False,'source_commit':source,'launch_commit':launch,'catalog_sha256':CAT_SHA,'jdk_inventory_sha256':sha(work/'jdk_inventory.json'),'helper_manifest_sha256':sha(D/'SOURCE_PINS.json'),'expected_leaf_bindings':17,'dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False,'stages':reports}
if __name__=='__main__':
 phase='startup';ok=False
 try:result=main();ok=result['status']=='STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES'
 except BaseException as error:result={'schema':'STRUCTURAL_GRAPH_ONLY_V1',**graph_identity,**differential_identity,'status':'FAIL_OR_INCOMPLETE','stage':phase,'reason':error.code if isinstance(error,Stop)else'UNCLASSIFIED_FAILURE','dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False}
 encoded=json.dumps(result,separators=(',',':'));need(len(encoded)<=16384);print(encoded,flush=True)
 sys.exit(0 if ok else 2)
