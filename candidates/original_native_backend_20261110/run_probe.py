import pathlib,json,hashlib,subprocess,os,resource,time
import argparse
r=pathlib.Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--jar-dir',type=pathlib.Path,action='append',required=True);parser.add_argument('--runtime-dir',type=pathlib.Path,default=r/'runtime');args=parser.parse_args()
local=[f for d in args.jar_dir for f in d.resolve().rglob('*.jar')];used=[]
for pin in json.loads((r/'DEPENDENCIES.json').read_text()):
 f=next((f for f in local if f.name==pin['name'] and hashlib.sha256(f.read_bytes()).hexdigest()==pin['sha256']),None)
 assert f is not None,pin['name'];used.append(dict(pin,path=str(f)))
for p in json.loads((r/'SOURCE_PINS.json').read_text()):assert hashlib.sha256((r/'upstream'/p['name']).read_bytes()).hexdigest()==p['sha256']
(r/'build').mkdir(exist_ok=True);(r/'results').mkdir(exist_ok=True)
cp=os.pathsep.join(p['path'] for p in used);plugin=next(p['path'] for p in used if p['name'].startswith('chisel-plugin'))
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx1200m']
commands=[('compile',java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-d',str(r/'build')]+[str(f) for f in sorted((r/'upstream').glob('*.scala'))]+[str(r/'NativeAluProbe.scala')]),('native',java+['-cp',str(r/'build')+os.pathsep+cp,'NativeAluProbe'])]
env=os.environ.copy();env['PATH']=str(args.runtime_dir.resolve())+os.pathsep+env['PATH']
(r/'results/COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n')
(r/'results/RESOLVED_DEPENDENCIES.json').write_text(json.dumps(used,indent=2)+'\n')
def limit():resource.setrlimit(resource.RLIMIT_CPU,(60,65))
for label,cmd in commands:
 start=time.monotonic();old=resource.getrusage(resource.RUSAGE_CHILDREN)
 with (r/'results'/f'{label}.log').open('w') as f:
  try:code=subprocess.run(cmd,cwd=r,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=90,preexec_fn=limit).returncode
  except subprocess.TimeoutExpired:code='WALL_TIMEOUT'
 end=resource.getrusage(resource.RUSAGE_CHILDREN);o={'phase':label,'exit':code,'wall_seconds':time.monotonic()-start,'cpu_seconds':end.ru_utime+end.ru_stime-old.ru_utime-old.ru_stime,'max_rss_kib':end.ru_maxrss};(r/'results'/f'{label}.json').write_text(json.dumps(o,indent=2)+'\n');print(o,flush=True)
 if code!=0:break
