"""One source-only structural job. No engine/native, weights, references or IR export."""
import contextlib,gzip,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,sys,time,urllib.request
P=pathlib.Path;D=P(__file__).resolve().parent;REPO=D.parent.parent
REL='candidates/chisel_structural_graph_20261104';NONCE='ci_launch/chisel_structural_graph_20261104_jdkfix_once.json'
CAT='candidates/gdn32_first_model_execution_20261104/GDN32_FULL_SOURCE_PINS.json'
CAT_SHA='ad2d4dcaddb213c85fd15adc65f7da5bd74a0d7c3e6c5922c725aa41bdc967cb'
BASE='f8197a3f7b5b288bcbac02987f7e55b5016851d0';TREE=12_081_306_272;RESERVE=8<<30
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
def main():
 global phase
 phase='identity';need(os.environ.get('GITHUB_REPOSITORY')=='liyang53719/hetero_cnn_llm_aha' and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1')
 launch=git('rev-parse','HEAD');need(launch==os.environ.get('GITHUB_SHA'));source=git('rev-parse','HEAD^');need(git('merge-base',BASE,source)==BASE)
 need(git('diff','--name-only','HEAD^','HEAD')==NONCE and not git('status','--porcelain'))
 nonce=load(REPO/NONCE,4096);need(nonce=={'schema':'ONE_STRUCTURAL_GRAPH_ONLY_V1','source_commit':source,'base_commit':BASE,'attempts':1,'numerical_execution':False,'native_execution':False,'artifact_upload':False})
 own=load(D/'SOURCE_PINS.json');pins=pins_for(own['files'],REPO);pins[str(D/'SOURCE_PINS.json')]=sha(D/'SOURCE_PINS.json')
 changed=set(git('diff','--name-only',BASE,source).splitlines());need(changed==set(own['publication_delta']) and changed=={REL+'/run.py',REL+'/SOURCE_PINS.json','.github/workflows/chisel-structural-graph-once.yml'})
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
  cap=dict(wall_seconds=seconds,cleanup_seconds=30,cpu_seconds=min(seconds,600),per_process_cpu_seconds=min(seconds,600),rss_bytes=rss<<30,per_process_as_bytes=15<<30,file_bytes=536870912,tree_bytes=3<<30,watch_tree_bytes=TREE,max_entries=150000,log_bytes=16<<20,raw_log_bytes=32<<20,min_free_disk_bytes=RESERVE,extra_watch_roots=[str(REPO),str(work)],jdk_aliases=aliases)
  stage_env=dict(env)
  if name=='jdk_inventory':stage_env['JAVA_TOOL_OPTIONS']='-Djava.io.tmpdir='+str(work/name/'tmp')+' -XX:-UsePerfData -XX:-HeapDumpOnOutOfMemoryError -XX:ErrorFile=/dev/null'
  with open(os.devnull,'w')as muted,contextlib.redirect_stdout(muted),contextlib.redirect_stderr(muted):
   r=supervisor.execute(args,str(work/name),str(work/'owner.lock'),cap,stage_env,dict(pins),resource_gate={'min_available_memory':13<<30,'min_disk_free':TREE+RESERVE})
  reports.append(project(name,r));print(json.dumps({'schema':'STRUCTURAL_GRAPH_PROGRESS_V1',**reports[-1],'numerical_pass':False}),flush=True)
  need(r.get('native_exit')in ((0,2)if name=='graph'else(0,1)if name=='jdk_inventory'else(0,)) and not r.get('errors') and reports[-1]['cleanup_complete'])
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
 classes=stage('compile_original',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.',*sources]),300,3)
 for p in classes.rglob('*.class'):pins[str(p)]=sha(p)
 basecp=str(classes)+':'+cp
 helpers=sorted(str(p)for p in (D/'scala').glob('*.scala'));need(len(helpers)==4)
 hclasses=stage('compile_graph',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',basecp,'-d','.',*helpers]),300,3)
 for p in hclasses.rglob('*.class'):pins[str(p)]=sha(p)
 highdir=stage('original_high',jvm('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'),600,6)/'host-diagnostic'
 high=regular(highdir/'original-high.fir');ann=regular(highdir/'high-annotations.json');ext=regular(highdir/'high-extmodules.fir')
 need(high.stat().st_size<=512<<20 and ann.stat().st_size<=16<<20 and ext.stat().st_size<=1<<20)
 # Separate inventory emitted by the unchanged original diagnostic is cross-bound
 # to the complete freshly generated high by the structural helper's own parser.
 blocks=re.split(r'(?m)(?=^extmodule )',ext.read_text());matches=[b for b in blocks if b.startswith('extmodule idma_backend_rw_axi_flat_wrap :')];need(len(matches)==1)
 need(matches[0].endswith('\n'));exttext=matches[0][:-1];extsha='85b299b3b237b70a8450315f887a2f8aad53bd86c95fb8d9a2ff943173cb4193';need(hashlib.sha256(exttext.encode()).hexdigest()==extsha)
 for p in (high,ann,ext):pins[str(p)]=sha(p)
 graphdir=stage('graph',jvm('4g',str(hclasses)+':'+basecp,'chiseltest.simulator.OriginalHostStructuralGraph',[str(high),sha(high),str(ann),sha(ann),extsha]),900,6)
 # Only tightly whitelisted final structural summary may leave the owning job.
 
 with gzip.open(graphdir/'frontend.log.gz','rt')as f:text=f.read(16385)
 need(len(text)<=16384)
 failure=re.fullmatch(r'FAIL_STRUCTURAL_GRAPH_ONLY stage=(admission|read|parse|split|official_lower|official_prepare|symbol_table|summary) exceptionClassSha=([0-9a-f]{64}) nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false suppressedDiagnosticBytes=([0-9]+)\n?',text)
 if failure:
  need(shutil.disk_usage(work).free>=RESERVE)
  return {'schema':'STRUCTURAL_GRAPH_ONLY_V1','status':'FAILED_STRUCTURAL_GRAPH_ONLY','phase':failure[1],'exception_class_sha256':failure[2],'reason':'CYCLE_DETECTED'if failure[2]=='61d6a821192ba77eb86d930ac24a4ff0a6184ea1e7b02b0e7fe6c693af8b6c11'else'OTHER_STRUCTURAL_FAILURE','source_commit':source,'launch_commit':launch,'jdk_inventory_sha256':sha(work/'jdk_inventory.json'),'helper_manifest_sha256':sha(D/'SOURCE_PINS.json'),'dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False,'final_reserve_preserved':True,'owned_process_cleanup_complete':True,'private_job_files_exported':False,'stages':reports}
 match=re.fullmatch(r'PASS_DECLARED_CONE_TOPOLOGY_ONLY highSha=([0-9a-f]{64}) annotationsSha=([0-9a-f]{64}) preparedSha=([0-9a-f]{64}) symbols=([0-9]+) leafBindings=17 nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false suppressedDiagnosticBytes=([0-9]+)\n?',text)
 need(match is not None and match[1]==sha(high)and match[2]==sha(ann))
 need(shutil.disk_usage(work).free>=RESERVE)
 for path,digest in pins.items():need(sha(path)==digest)
 return {'schema':'STRUCTURAL_GRAPH_ONLY_V1','final_reserve_preserved':True,'owned_process_cleanup_complete':all(r['cleanup_complete']for r in reports),'private_job_files_exported':False,'status':'STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES','source_commit':source,'launch_commit':launch,'catalog_sha256':CAT_SHA,'jdk_inventory_sha256':sha(work/'jdk_inventory.json'),'helper_manifest_sha256':sha(D/'SOURCE_PINS.json'),'high_sha256':match[1],'annotations_sha256':match[2],'prepared_sha256':match[3],'symbol_count':int(match[4]),'leaf_bindings':17,'dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False,'stages':reports}
if __name__=='__main__':
 phase='startup';ok=False
 try:result=main();ok=result['status']=='STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES'
 except BaseException as error:result={'schema':'STRUCTURAL_GRAPH_ONLY_V1','status':'FAIL_OR_INCOMPLETE','stage':phase,'reason':error.code if isinstance(error,Stop)else'UNCLASSIFIED_FAILURE','dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False}
 encoded=json.dumps(result,separators=(',',':'));need(len(encoded)<=16384);print(encoded,flush=True)
 sys.exit(0 if ok else 2)
