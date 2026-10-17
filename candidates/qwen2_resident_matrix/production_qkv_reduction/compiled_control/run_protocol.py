"""REVIEW CANDIDATE: explicit opt-in bounded CHIRRTL/Verilator control gate."""
import argparse,hashlib,json,os,re,shutil,signal,time
from pathlib import Path
import owned_compile
import native_tools
import incremental_classes
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def verify_tree(root,pins,suffix=None):
 actual={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and (suffix is None or p.suffix==suffix)}
 require(actual==pins,'exact input inventory/hash mismatch: '+str(root))
def structure(path):
 b=path.read_bytes();require(len(b)<=2*1024*1024,'CHIRRTL size >2MiB');s=b.decode()
 names=re.findall(r'^  module (\w+)\s*:',s,re.M)
 require(0<len(names)<=12,'module count')
 require(not re.search(r'^\s*(?:mem|cmem|smem|extmodule)\s',s,re.M),'memory or external module forbidden')
 require(not any(re.search(r'DenseDownOwner|DenseBanks|MatrixPipeline|SiluVector|HardFloat|RecFN',n) for n in names),'arithmetic/backend module forbidden')
 required={'ProductionQkvProtocolHarness','HostBlockCommands','Public21QkvReductionRouter','DenseBlockReductionCoordinator','DenseTileSumBridge','Record128Reader','TypedTensorReader'}
 require(set(names)==required,'unexpected instantiated hierarchy')
 return dict(bytes=len(b),sha256=sha(path),modules=names,memory_declarations=0,external_modules=0,arithmetic=False)
def run(a):
 start=time.monotonic();stop=start+250;work_stop=stop-10
 require(a.execute,'no execution without explicit --execute')
 require(not a.out.exists() and not a.out.is_symlink(),'fresh output required')
 root=a.source_root.resolve(strict=True);cache=a.cache.resolve(strict=True);java=a.java.resolve(strict=True);out=a.out.resolve()
 pins=json.loads((HERE/'SOURCE_CLOSURE.json').read_text());deps=json.loads((HERE/'dependency-lock.json').read_text());jdk=json.loads((HERE/'JDK_PINS.json').read_text());fixtures=json.loads((HERE/'FIXTURE_PINS.json').read_text())
 require(len(deps['jars'])==106 and len(deps['removed'])==6 and len(deps['added'])==25,'exact interpreter lock required')
 def preflight():
  native_tools.preflight(a.tools.resolve(strict=True))
  incremental_classes.verify_baseline(a.base_classes.resolve(strict=True),pins['production'])
  incremental_classes.verify_dependency_transition(deps,jdk)
  verify_tree(root,pins['production'],'.scala');verify_tree(HERE/'source',{k.removeprefix('source/'):v for k,v in pins['harness'].items()},'.scala')
  verify_tree(HERE/'fixtures',fixtures)
  for n,h in deps['jars'].items():require(sha(cache/n)==h,'dependency drift '+n)
  require(sha(java)==jdk['java_sha256'] and sha(java.parent.parent/'release')==jdk['java_release_sha256'],'JDK drift')
  require(sha(HERE/'strict_cleanup.py')==owned_compile.HELPER_SHA,'cleanup helper drift')
 def timeout(sig,frame):raise TimeoutError('original total/stage deadline')
 require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing alarm')
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,min(10,work_stop-time.monotonic()))
 try:
  preflight();out.mkdir(parents=True,exist_ok=False);src=out/'scala';shutil.copytree(root,src)
  for n in pins['harness']:
   target=src/'protocol_test'/Path(n).name;target.parent.mkdir(exist_ok=True);shutil.copyfile(HERE/n,target)
  copied_pins={**pins['production'],**{'protocol_test/'+Path(n).name:h for n,h in pins['harness'].items()}}
  verify_tree(src,copied_pins,'.scala')
  classes=out/'classes';incremental_classes.copy_baseline(a.base_classes.resolve(strict=True),classes)
  cp=':'.join(str(cache/n) for n in sorted(deps['jars']))
  plugin=cache/'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
  common=[str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1']
  incremental_classes.check_no_shadow(cache,deps['jars'])
  compile_cmd=common+['-cp',cp,'scala.tools.nsc.Main','-classpath',str(classes)+':'+cp,'-Xplugin:'+str(plugin),'-language:reflectiveCalls','-d',str(classes)]+[str(p) for p in sorted((src/'protocol_test').glob('*.scala'))]
  require(len(list(src.rglob('*.scala')))==94,'exact 94-source closure')
  receipt=dict(status='NOT_COMPLETED',scope='HOST_ROUTER_COORDINATOR_COMPILED_CONTROL_WITH_SCRIPTED_SERVICES',production_kernel=False,arithmetic=False,rtl=True,total_budget_seconds=250,stages=[])
  (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 def stage(name,cmd,seconds,startup=None):
  stage_stop=min(time.monotonic()+seconds,work_stop);logpath=out/(name+'.log')
  (out/(name+'_argv.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  with logpath.open('wb') as log:
   result=owned_compile.execute(cmd,cwd=out,log=log,cleanup_helper=HERE/'strict_cleanup.py',absolute_stop=stop,stage_stop=stage_stop,progress_log=logpath,startup_seconds=startup)
  receipt['stages'].append(dict(name=name,**result))
  saved_handler=signal.signal(signal.SIGALRM,timeout)
  signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
  try:(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,saved_handler)
  require(result['exit_code']==0 and result['cleanup_complete'] and result['error'] is None,'stage failed '+name)
 native_tools.activate(a.tools.resolve(strict=True),out)
 stage('compile',compile_cmd,60)
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
 try:receipt['incremental_compile']=incremental_classes.verify_final(classes)
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 runtime_cp=str(classes)+':'+cp
 stage('structure',common+['-cp',runtime_cp,'heteronpu.continuous.ProductionQkvProtocolElaborate',str(out/'structure')],20)
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
 try:receipt['structure']=structure(out/'structure/protocol.fir');preflight()
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 # Fixture identity comes from this separately reviewed pin file, not gate claims.
 previous={k:os.environ.get(k) for k in ('HETERO_PUBLIC21_FIXTURE_ROOT','HETERO_PUBLIC21_GATE_SHA256')}
 os.environ['HETERO_PUBLIC21_FIXTURE_ROOT']=str(HERE/'fixtures');os.environ['HETERO_PUBLIC21_GATE_SHA256']=fixtures['gate.json']
 try:
  stage('compiled_control',common+['-cp',runtime_cp,'org.scalatest.tools.Runner','-o','-s','heteronpu.continuous.ProductionQkvProtocolSpec','-z','retire bounded scripted services and late faults'],150,startup=120)
 finally:
  for k,v in previous.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
 try:
  log=(out/'compiled_control.log').read_text();require(re.findall(r'Total number of tests run:\s*(\d+)',log)==['1'],'exactly one selected test')
  require(log.count('QKV_PROTOCOL_SIM_READY')==1 and log.count('QKV_PROTOCOL_CASE_PASS')==1 and 'All tests passed' in log,'callback/pass missing')
  require(log.count('PUBLIC21_REDUCTION_DISPATCH_CONTROL_PASS')==1 and log.count('PUBLIC21_REDUCTION_DISPATCH_REJECT_PASS')==7,'all selected scenario markers required')
  require(not re.search(r'\*\*\* (?:FAILED|CANCELED|ABORTED)|Tests:.*(?:failed|canceled|ignored|pending) [1-9]',log),'test failure')
  require(any(p.suffix in ('.v','.sv') for p in out.rglob('*')),'expected control RTL missing')
  preflight();native_tools.validate_audit(out/'native_argv.jsonl');incremental_classes.verify_final(classes);verify_tree(src,copied_pins,'.scala');receipt.update(status='PASS_CONTROL_ONLY',elapsed_seconds=time.monotonic()-start,source_count=94,fixture_sha256=fixtures)
  temp=out/'receipt.pending.json';temp.write_text(json.dumps(receipt,indent=2)+'\n');require(time.monotonic()<stop,'absolute deadline');temp.replace(out/'receipt.json')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','cache','java','out','tools','base-classes'):p.add_argument('--'+n,required=True,type=Path)
 p.add_argument('--execute',action='store_true');run(p.parse_args())
