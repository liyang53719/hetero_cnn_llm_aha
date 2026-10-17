"""Pinned 91-source class compilation only; no emitter is executed."""
import argparse,hashlib,json,signal,time,shutil
from pathlib import Path
import owned_compile
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(output,source_root,cache,java,preflight_only=False):
 start=time.monotonic();stop=start+88;work_stop=stop-8
 output=output.resolve()
 deps=json.loads((HERE/'dependency_pins.json').read_text());pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
 source_root=source_root.resolve(strict=True);cache=cache.resolve(strict=True);java=java.resolve(strict=True)
 report=dict(scala_class_compile_pass=False,elaboration=False,rtl=False,numerical=False,protocol_validation=False,source_count=len(pins),source_sha256=pins,absolute_budget_seconds=88)
 def checktime():
  if time.monotonic()>=work_stop:raise TimeoutError('absolute work deadline')
 def preflight():
  checktime()
  for n,h in deps['jars'].items():
   if sha(cache/n)!=h:raise ValueError('jar drift: '+n)
   checktime()
  if sha(java)!=deps['java_sha256'] or sha(java.parent.parent/'release')!=deps['java_release_sha256']:raise ValueError('JDK drift')
  actual={str(p.relative_to(source_root)):sha(p) for p in (source_root).rglob('*.scala')}
  if actual!=pins or len(actual)!=91:raise ValueError('source closure drift')
  if sha(HERE/'strict_cleanup.py')!=owned_compile.HELPER_SHA:raise ValueError('helper drift')
  checktime()
 if output.exists() or output.is_symlink():raise ValueError('fresh output required')
 def alarm(signum,frame):raise TimeoutError('absolute preflight deadline')
 if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('preexisting alarm')
 old=signal.signal(signal.SIGALRM,alarm)
 signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
 try:
  preflight()
  if preflight_only:
   print(json.dumps(dict(preflight_pass=True,source_count=len(pins),jar_count=len(deps['jars']),compiler_started=False)));return
  output.mkdir(parents=True,exist_ok=False);src=output/'scala';shutil.copytree(source_root,src)
  if {str(p.relative_to(src)):sha(p) for p in src.rglob('*.scala')}!=pins:raise ValueError('copy drift')
  classes=output/'classes';classes.mkdir();checktime()
  cp=':'.join(str(cache/n) for n in sorted(deps['jars']))
  plugin=cache/'org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
  argv=[str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(plugin),'-language:reflectiveCalls','-d',str(classes)]+[str(src/n) for n in sorted(pins)]
  (output/'argv.json').write_text(json.dumps(argv,indent=2)+'\n')
  # Persistent fail-closed receipt survives interruption of post-run verification/publication.
  (output/'receipt.json').write_text(json.dumps({**report,'error':'NOT_COMPLETED'},indent=2,sort_keys=True)+'\n')
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 with (output/'compiler.log').open('wb') as log:report.update(owned_compile.execute(argv,cwd=output,log=log,cleanup_helper=HERE/'strict_cleanup.py',absolute_stop=stop))
 def postcheck():
  if time.monotonic()>=stop:raise TimeoutError('absolute post-run deadline')
 postcheck()
 old=signal.signal(signal.SIGALRM,alarm)
 signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()))
 try:
  report['inputs_reverified']=True
  for n,h in pins.items():
   if sha(source_root/n)!=h or sha(src/n)!=h:raise ValueError('post-run source drift: '+n)
   postcheck()
  for n,h in deps['jars'].items():
   if sha(cache/n)!=h:raise ValueError('post-run dependency drift: '+n)
   postcheck()
  if sha(java)!=deps['java_sha256'] or sha(java.parent.parent/'release')!=deps['java_release_sha256']:raise ValueError('post-run JDK drift')
  report['classes']={}
  for p in classes.rglob('*.class'):
   report['classes'][str(p.relative_to(classes))]=sha(p);postcheck()
  report['class_count']=len(report['classes'])
  report['scala_class_compile_pass']=report['exit_code']==0 and report['cleanup_complete'] and report['error'] is None and report['inputs_reverified']
  report['elapsed_seconds']=time.monotonic()-start
  temp=output/'receipt.pending.json'
  temp.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');postcheck()
  temp.replace(output/'receipt.json')
  print(json.dumps({k:v for k,v in report.items() if k not in ('classes','source_sha256')},indent=2))
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--source-root',required=True,type=Path);p.add_argument('--cache',required=True,type=Path);p.add_argument('--java',required=True,type=Path);p.add_argument('--preflight-only',action='store_true');a=p.parse_args();run(a.output,a.source_root,a.cache,a.java,a.preflight_only)
