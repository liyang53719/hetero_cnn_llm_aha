"""One fresh, bounded copied-closure Scala class compile. Never runs an emitter."""
import argparse,json,os,shutil,signal,subprocess,time
from pathlib import Path
import prepare as p
PLUGIN='org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar'
def run(source_root,fragment_root,cache,java,output,cleanup_helper):
 source_root,fragment_root,cache,java,output=map(lambda x:Path(x).resolve(),(source_root,fragment_root,cache,java,output))
 if output.exists() or output.is_symlink():raise ValueError('fresh compile output required')
 pins,_=p.load();deps=json.loads((p.HERE/'compile_pins.json').read_text())
 def preflight():
  for n,h in deps['jars'].items():
   if p.sha((cache/n).read_bytes())!=h:raise ValueError('dependency drift: '+n)
  if p.sha(java.read_bytes())!=deps['java_sha256']:raise ValueError('Java binary drift')
  if p.sha((java.parent.parent/'release').read_bytes())!=deps['java_release_sha256']:raise ValueError('Java release drift')
  expected={**pins['inputs'],**pins['unchanged'],**deps['original_core']}
  actual={str(f.relative_to(source_root)):p.sha(f.read_bytes()) for f in source_root.rglob('*.scala')}
  if actual!=expected or len(actual)!=83:raise ValueError('exact 83-source closure required')
 preflight();output.mkdir(parents=True,exist_ok=False)
 overlay=output/'overlay';p.prepare(source_root,fragment_root,overlay)
 src=output/'scala';shutil.copytree(source_root,src)
 for f in overlay.rglob('*.scala'):shutil.copyfile(f,src/f.relative_to(overlay))
 actual={str(f.relative_to(src)):p.sha(f.read_bytes()) for f in src.rglob('*.scala')}
 expected={**pins['unchanged'],**pins['outputs'],**pins['fragment']}
 if actual!=expected:raise ValueError('copied source drift')
 classes=output/'classes';classes.mkdir();cp=':'.join(str(cache/n) for n in sorted(deps['jars']))
 argv=[str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(cache/PLUGIN),'-language:reflectiveCalls','-d',str(classes)]+[str(f) for f in sorted(src.rglob('*.scala'))]
 report=dict(scala_class_compile_pass=False,source_count=len(actual),source_sha256=actual,elaboration=False,rtl=False,numerical=False,protocol_validation=False)
 import owned_compile
 start=time.monotonic()
 try:
  with (output/'compiler.log').open('wb') as log:
   report.update(owned_compile.execute(argv,cwd=output,log=log,cleanup_helper=cleanup_helper))
  preflight();report['inputs_reverified']=True
  report['classes']={str(f.relative_to(classes)):p.sha(f.read_bytes()) for f in sorted(classes.rglob('*.class'))}
  report['class_count']=len(report['classes'])
  report['scala_class_compile_pass']=report['exit_code']==0 and report['cleanup_complete'] and report['error'] is None
 finally:
  report['elapsed_seconds']=time.monotonic()-start
  (output/'receipt.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ['source_sha256','classes']},indent=2))
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','fragment-root','cache','java','output','cleanup-helper'):ap.add_argument('--'+n,required=True,type=Path)
 a=ap.parse_args();run(a.source_root,a.fragment_root,a.cache,a.java,a.output,a.cleanup_helper)
