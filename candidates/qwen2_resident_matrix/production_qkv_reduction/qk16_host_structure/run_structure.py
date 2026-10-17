"""Bounded original HostBlockTop CHIRRTL only; no firtool/RTL/native simulation."""
import argparse,hashlib,json,os,shutil,signal,time
from pathlib import Path
import owned_compile
from class_source import source_file
from check_structure import check
from check_packed import check_packed
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def inventory(root,suffix=None):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and (suffix is None or p.suffix==suffix)}
def run(a):
 start=time.monotonic();stop=start+90
 need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'preexisting alarm')
 def timeout(sig,frame):raise TimeoutError('original total/stage deadline')
 old=signal.signal(signal.SIGALRM,timeout)
 signal.setitimer(signal.ITIMER_REAL,min(10,stop-time.monotonic()))
 try:return bounded_run(a,start,stop,timeout)
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
def bounded_run(a,start,stop,timeout):
 work_stop=stop-5
 need(a.execute,'explicit --execute required')
 need(not a.out.exists() and not a.out.is_symlink(),'fresh output required')
 pins=json.loads((HERE/'SOURCE_PINS.json').read_text());baseline=json.loads((HERE/'BASELINE_CLASS_PINS.json').read_text());deps=json.loads((HERE/'BASELINE_DEPENDENCY_PINS.json').read_text());jdk=json.loads((HERE/'JDK_PINS.json').read_text())
 root=a.source_root.resolve(strict=True);classes0=a.base_classes.resolve(strict=True);cache=a.cache.resolve(strict=True);java=a.java.resolve(strict=True);out=a.out.resolve()
 def preflight():
  need(inventory(root,'.scala')==baseline['source_sha256'],'92 source closure mismatch')
  need(len(pins)==93 and {k:v for k,v in pins.items() if not k.startswith('structure/')}==baseline['source_sha256'],'source manifest mismatch')
  need(sha(HERE/'source/ProductionQk16HostStructure.scala')==pins['structure/ProductionQk16HostStructure.scala'],'emitter source drift')
  need(inventory(classes0)==baseline['classes'] and len(baseline['classes'])==550,'production baseline class drift')
  need({n:source_file((classes0/n).read_bytes()) for n in baseline['classes']}==baseline['class_source_files'],'baseline SourceFile drift')
  for n,h in deps['jars'].items():need(sha(cache/n)==h,'jar drift '+n)
  need(len(deps['jars'])==87,'87 fixed jars required')
  need(sha(java)==jdk['java_sha256']==deps['java_sha256'],'java drift')
  need(sha(java.parent.parent/'release')==jdk['java_release_sha256']==deps['java_release_sha256'],'JDK release drift')
  need(sha(HERE/'strict_cleanup.py')==owned_compile.HELPER_SHA,'strict helper drift')
 old=signal.getsignal(signal.SIGALRM) # outer alarm already covers load/resolve/preflight
 try:
  preflight();out.mkdir(parents=True);src=out/'scala';shutil.copytree(root,src);(src/'structure').mkdir();shutil.copyfile(HERE/'source/ProductionQk16HostStructure.scala',src/'structure/ProductionQk16HostStructure.scala');need(inventory(src,'.scala')==pins,'copied source mismatch')
  classes=out/'classes';shutil.copytree(classes0,classes);need(inventory(classes)==baseline['classes'],'copied class mismatch')
  import zipfile
  for n in deps['jars']:
   with zipfile.ZipFile(cache/n) as z:
    names=set(z.namelist());need(not names&set(baseline['classes']),'production shadow in jar');need(not any('heteronpu/continuous/ProductionQk16HostStructure' in p for p in names),'emitter shadow in jar')
  cp=':'.join(str(cache/n) for n in sorted(deps['jars']));common=[str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1']
  plugin=cache/'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
  cmd=common+['-cp',cp,'scala.tools.nsc.Main','-classpath',str(classes)+':'+cp,'-Xplugin:'+str(plugin),'-language:reflectiveCalls','-d',str(classes),str(src/'structure/ProductionQk16HostStructure.scala')]
  receipt=dict(status='NOT_COMPLETED',scope='ORIGINAL_HOST_CHIRRTL_ONLY',total_budget_seconds=90,rtl=False,numerical=False,protocol_execution=False,capacity_tokens=1024,actual_job_m=None,stages=[])
  (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
 def stage(name,cmd,seconds):
  signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
  (out/(name+'_argv.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  with (out/(name+'.log')).open('wb') as log:
   signal.setitimer(signal.ITIMER_REAL,0) # owned executor takes over the same stop
   try:result=owned_compile.execute(cmd,cwd=out,log=log,cleanup_helper=HERE/'strict_cleanup.py',absolute_stop=stop,stage_stop=min(work_stop,time.monotonic()+seconds),cleanup_seconds=5)
   finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
  receipt['stages'].append(dict(name=name,**result))
  handler=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
  try:(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));signal.signal(signal.SIGALRM,handler)
  need(result['exit_code']==0 and result['error'] is None and result['cleanup_complete'],'stage failed '+name)
 def verify_classes():
  allclasses=inventory(classes);need({n:source_file((classes/n).read_bytes()) for n in baseline['classes']}==baseline['class_source_files'],'post baseline SourceFile drift');need(all(allclasses.get(n)==h for n,h in baseline['classes'].items()),'production class overwritten')
  added=set(allclasses)-set(baseline['classes']);need(added=={'heteronpu/continuous/ProductionQk16HostStructure.class','heteronpu/continuous/ProductionQk16HostStructure$.class','heteronpu/continuous/ProductionQk16HostStructure$delayedInit$body.class'},'expected exact App emitter three classes')
  need(all(source_file((classes/n).read_bytes())=='ProductionQk16HostStructure.scala' for n in added),'new class provenance')
  return allclasses
 stage('compile_emitter',cmd,20)
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
 try:receipt['classes']=verify_classes()
 finally:signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));signal.signal(signal.SIGALRM,old)
 stage('emit_chirrtl',common+['-cp',str(classes)+':'+cp,'heteronpu.continuous.ProductionQk16HostStructure',str(out/'structure')],60)
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
 try:
  log=(out/'emit_chirrtl.log').read_text();need(log.count('PRODUCTION_HOST_CHIRRTL_BEGIN')==1 and log.count('PRODUCTION_HOST_CHIRRTL_WRITTEN')==1,'emitter markers missing')
  receipt['structure']=check(out/'structure/HostBlockTop.fir');receipt['packed_structure']=check_packed(out/'structure/HostBlockTop.fir');preflight();verify_classes();need(inventory(src,'.scala')==pins,'source postflight mismatch')
  need(not any(f.suffix in ['.v','.sv','.cpp','.so'] for f in out.rglob('*')),'forbidden RTL/native output')
  receipt.update(status='PASS_PRODUCTION_CHIRRTL_STRUCTURE_ONLY',elapsed_seconds=time.monotonic()-start,source_count=93,reused_classes=550,compiled_source_count=1)
  temp=out/'receipt.pending.json';temp.write_text(json.dumps(receipt,indent=2)+'\n');need(time.monotonic()<stop,'absolute deadline');temp.replace(out/'receipt.json')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['source-root','base-classes','cache','java','out']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--execute',action='store_true');run(p.parse_args())
