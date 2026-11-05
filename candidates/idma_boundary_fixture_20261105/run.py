"""Isolated boundary fixture qualification only. No Host, engine/native or IR export."""
import contextlib,gzip,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,sys,time,urllib.request,zipfile
P=pathlib.Path;D=P(__file__).resolve().parent;REPO=D.parent.parent
REL='candidates/idma_boundary_fixture_20261105';NONCE='ci_launch/idma_boundary_fixture_20261105_relative_target_once.json'
CAT='candidates/gdn32_first_model_execution_20261104/GDN32_FULL_SOURCE_PINS.json'
CAT_SHA='ad2d4dcaddb213c85fd15adc65f7da5bd74a0d7c3e6c5922c725aa41bdc967cb'
BASE='28fb6150e04bb2f738c854509008e6264dfa9ed6';BASE_TREE='4cea7d5fd06fe873c4503fee180c0f0d04999fe5';TREE=12_081_306_272;RESERVE=8<<30
boundary_identity={}
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

def reject_fixture_failure(text,label,comparator):
 # Caller must first obtain text through read_closed_log. This path always
 # fails, irrespective of exit status; diagnostic text is never a pass oracle.
 if text.startswith('BOUNDARY_GRAPH_FAILURE_V1'):
  try:failure=comparator.parse_failure(text,label)
  except (ValueError,TypeError):raise Stop('BOUNDARY_FAILURE_SCHEMA_REJECTED')
  boundary_identity['boundary_failure']=failure
  raise Stop('BOUNDARY_FIXTURE_REPORTED_FAILURE')

def stage_cpu_budget(name,seconds):
 return min(seconds,600)

def main():
 global phase,boundary_identity
 boundary_identity={}
 phase='identity';need(os.environ.get('GITHUB_REPOSITORY')=='liyang53719/hetero_cnn_llm_aha' and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1')
 launch=git('rev-parse','HEAD');need(launch==os.environ.get('GITHUB_SHA'));source=git('rev-parse','HEAD^');need(git('rev-parse',BASE+'^{tree}')==BASE_TREE and git('rev-parse',source+'^')==BASE)
 need(git('diff','--name-only','HEAD^','HEAD')==NONCE and not git('status','--porcelain'))
 nonce=load(REPO/NONCE,4096);need(nonce=={'schema':'ONE_IDMA_BOUNDARY_FIXTURE_ONLY_V1','source_commit':source,'base_commit':BASE,'attempts':1,'numerical_execution':False,'native_execution':False,'artifact_upload':False,'full_host_execution':False})
 own=load(D/'SOURCE_PINS.json')
 expected_files={'.github/workflows/idma-boundary-fixture-once.yml',*[REL+'/'+p for p in ('run.py','prepare_jars.py','compare_boundary_results.py','modulecache/SymbolTable.scala','modulecache/BoundedCycleWitness.scala','scala/IdmaSplitLayout.scala','scala/IdmaFieldSplitTransform.scala','scala/IdmaPackedBoundarySplit.scala','scala/BoundarySplitStructuralFixture.scala')]}
 need(set(own)=={'schema','files','publication_delta'} and own['schema']=='IDMA_BOUNDARY_FIXTURE_SOURCE_PINS_V1')
 need(len(own['files'])==len(expected_files) and {r['path']for r in own['files']}==expected_files)
 pins=pins_for(own['files'],REPO);pins[str(D/'SOURCE_PINS.json')]=sha(D/'SOURCE_PINS.json')
 changed=set(git('diff','--name-only',BASE,source).splitlines())
 expected_delta={'.github/workflows/idma-boundary-fixture-once.yml',REL+'/run.py',REL+'/scala/BoundarySplitStructuralFixture.scala',REL+'/SOURCE_PINS.json'}
 need(len(own['publication_delta'])==len(expected_delta) and changed==set(own['publication_delta'])==expected_delta)
 catalog=regular(REPO/CAT);need(sha(catalog)==CAT_SHA);doc=load(catalog);need(doc['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1'and len(doc['files'])==1211);pins.update(pins_for(doc['files'],REPO));pins[str(catalog)]=CAT_SHA
 phase='admission';remote_exclusive(launch);admission();work=P(os.environ['RUNNER_TEMP'])/'idma-boundary-fixture';need(work.is_absolute()and not work.exists()and all(not p.is_symlink()for p in(work,*work.parents)));work.mkdir()
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
  reports.append(project(name,r));print(json.dumps({'schema':'IDMA_BOUNDARY_FIXTURE_PROGRESS_V1',**reports[-1],'numerical_pass':False}),flush=True)
  if name in ('boundary_official','boundary_cached'):return work/name,r # Parse only after independent cleanup/log-finalization gates.
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
 def jvm(heap,classpath,main,args=()):return [java,'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-XX:-HeapDumpOnOutOfMemoryError','-XX:ErrorFile=/dev/null','-cp',classpath,main,*args]
 # Compile a narrowly patched official SymbolTable and one common fixture.
 # No JVM simulation engine or native library is constructed by either.
 patch_source=regular(D/'modulecache/SymbolTable.scala');fixture_source=regular(D/'scala/BoundarySplitStructuralFixture.scala')
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
 helpers=sorted(str(p)for p in (D/'scala').glob('*.scala'));need(len(helpers)==4)
 fixtureclasses=stage('compile_boundary_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-d','.',*helpers]),180,3)
 for p in fixtureclasses.rglob('*.class'):pins[str(p)]=sha(p)
 need(not (fixtureclasses/'treadle2/executable/SymbolTable.class').exists() and not (fixtureclasses/'treadle2/executable/SymbolTable$.class').exists())
 compare_spec=importlib.util.spec_from_file_location('strict_boundary_compare',D/'compare_boundary_results.py');comparator=importlib.util.module_from_spec(compare_spec);compare_spec.loader.exec_module(comparator)
 boundary_identity={'boundary_status':'PENDING','official_symbol_table':official_pins,'patched_symbol_table':cached_pins,'fixture_source_sha256':sha(fixture_source),'boundary_transform_source_sha256':sha(D/'scala/IdmaPackedBoundarySplit.scala'),'interpreter_bookkeeping_modified':True}
 results=[]
 for label,expected,location,classpath in [('official',official_pins,official_jar,str(fixtureclasses)+':'+cp),('cached',cached_pins,str(patchclasses),str(patchclasses)+':'+str(fixtureclasses)+':'+cp)]:
  folder,receipt=stage('boundary_'+label,jvm('1g',classpath,'chiseltest.simulator.BoundarySplitStructuralFixture',[label,expected['class_sha256'],expected['companion_sha256'],location]),120,2)
  text=read_closed_log(folder/'frontend.log.gz',receipt)
  need(receipt.get('worker_started')is True,'BOUNDARY_PROCESS_NOT_STARTED')
  reject_fixture_failure(text,label,comparator)
  need(receipt.get('status')=='PASS_PROCESS_ONLY' and receipt.get('worker_started')is True,'BOUNDARY_PROCESS_FAILED')
  process={'exit':receipt.get('native_exit'),'errors':receipt.get('errors'),'cleanup_complete':(receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','log_finalized':(receipt.get('log_capture')or{}).get('gzip_finalized')is True}
  results.append((text,process))
 result=comparator.compare(results[0][0],results[1][0],official_pins,cached_pins,results[0][1],results[1][1])
 boundary_identity.update(boundary_status=result['status'])
 need(shutil.disk_usage(work).free>=RESERVE)
 for path,digest in pins.items():need(sha(path)==digest)
 return {'schema':'IDMA_BOUNDARY_FIXTURE_ONLY_V1',**result,**boundary_identity,'final_reserve_preserved':True,'owned_process_cleanup_complete':all(r['cleanup_complete']for r in reports),'private_job_files_exported':False,'source_commit':source,'launch_commit':launch,'catalog_sha256':CAT_SHA,'jdk_inventory_sha256':sha(work/'jdk_inventory.json'),'helper_manifest_sha256':sha(D/'SOURCE_PINS.json'),'dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False,'full_host_accepted':False,'stages':reports}
if __name__=='__main__':
 phase='startup';ok=False
 try:result=main();ok=result['status']=='PASS_ISOLATED_BOUNDARY_FIXTURE_ONLY'
 except BaseException as error:result={'schema':'IDMA_BOUNDARY_FIXTURE_ONLY_V1',**boundary_identity,'status':'FAIL_OR_INCOMPLETE','stage':phase,'reason':error.code if isinstance(error,Stop)else'UNCLASSIFIED_FAILURE','dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False,'full_host_accepted':False}
 encoded=json.dumps(result,separators=(',',':'));need(len(encoded)<=16384);print(encoded,flush=True)
 sys.exit(0 if ok else 2)
