"""Offline bounded compile/native phase2; supervise only our own process groups."""
import argparse,pathlib,json,hashlib,subprocess,os,resource,time,sys,signal
R=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--jar-dir',type=pathlib.Path,action='append',required=True);p.add_argument('--verilator-dir',type=pathlib.Path,required=True);p.add_argument('--cycles',type=int,default=150000);p.add_argument('--wall-seconds',type=int,default=240);a=p.parse_args()
alljars=[f for d in a.jar_dir for f in d.resolve().rglob('*.jar')];used=[];missing=[]
for pin in json.loads((R/'DEPENDENCIES.json').read_text()):
 f=next((f for f in alljars if f.name==pin['name'] and hashlib.sha256(f.read_bytes()).hexdigest()==pin['sha256']),None)
 if f is None:missing.append(pin['name']);continue
 if not f.name.endswith('-sources.jar'):used.append(dict(pin,path=str(f)))
for pin in json.loads((R/'SOURCE_PINS.json').read_text()):assert hashlib.sha256((R/'upstream'/pin['name']).read_bytes()).hexdigest()==pin['sha256']
assert hashlib.sha256((R/'scalar_core.py').read_bytes()).hexdigest()==json.loads((R/'ORACLE_PINS.json').read_text())['scalar_core.py']
(R/'results').mkdir(exist_ok=True);(R/'build').mkdir(exist_ok=True)
(R/'results/DEPENDENCY_RESOLUTION.json').write_text(json.dumps({'used':used,'absent':missing},indent=2)+'\n')
subprocess.run([sys.executable,str(R/'generate_fixture.py')],check=True)
cp=os.pathsep.join(x['path'] for x in used);plugin=next(x['path'] for x in used if x['name'].startswith('chisel-plugin_'))
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx2400m']
files=sorted((R/'upstream').glob('*.scala'))+[R/'DerivedCheck.scala']
commands=[('compile',java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-d',str(R/'build')]+list(map(str,files))),('simulation',java+['-cp',str(R/'build')+os.pathsep+cp,'DerivedCheck','--verilator','--cycles='+str(a.cycles)])]
(R/'results/COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n')
(R/'results/EXECUTED_SOURCE_HASHES.json').write_text(json.dumps({str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files+[R/'run.py',R/'generate_fixture.py',R/'scalar_core.py']},indent=2)+'\n')
env=os.environ.copy();env['PATH']=str(a.verilator_dir.resolve())+os.pathsep+env['PATH']
def limit():resource.setrlimit(resource.RLIMIT_CPU,(210,215))
for label,cmd in commands:
 t=time.monotonic();wall=90 if label=='compile' else a.wall_seconds
 with (R/'results'/f'{label}.log').open('w') as f:
  proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=R,env=env,start_new_session=True,preexec_fn=limit)
  identity={'pid':proc.pid,'pgid':proc.pid,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'starttime_ticks':pathlib.Path(f'/proc/{proc.pid}/stat').read_text().split()[21]}
  (R/'results'/f'{label}_identity.json').write_text(json.dumps(identity,indent=2)+'\n')
  timedout=False
  try:code=proc.wait(timeout=wall)
  except subprocess.TimeoutExpired:
   timedout=True;os.killpg(proc.pid,signal.SIGKILL);proc.wait();code='WALL_TIMEOUT_GROUP_KILLED'
 result=dict(stage=label,exit=code,seconds=time.monotonic()-t,timeout=timedout,terminal_returncode=proc.returncode,identity=identity)
 (R/'results'/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)
 if code!=0:sys.exit(1)
