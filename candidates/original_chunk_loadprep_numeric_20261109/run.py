"""Offline, bounded original-Chisel unit test. Supply local official pinned jars."""
import argparse,pathlib,json,hashlib,subprocess,os,resource,time,sys
R=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--jar-dir',type=pathlib.Path,action='append',required=True);p.add_argument('--verify-only',action='store_true');p.add_argument('--guarded32-only',action='store_true');a=p.parse_args()
alljars=[f for d in a.jar_dir for f in d.resolve().rglob('*.jar')]; used=[]; missing=[]
for pin in json.loads((R/'DEPENDENCIES.json').read_text()):
 f=next((f for f in alljars if f.name==pin['name'] and hashlib.sha256(f.read_bytes()).hexdigest()==pin['sha256']),None)
 if f is None:missing.append(pin['name']);continue
 if not f.name.endswith('-sources.jar'):used.append(dict(pin,path=str(f),bytes=f.stat().st_size))
for pin in json.loads((R/'SOURCE_PINS.json').read_text()):assert hashlib.sha256((R/'upstream'/pin['name']).read_bytes()).hexdigest()==pin['sha256']
assert hashlib.sha256((R/'scalar_core.py').read_bytes()).hexdigest()==json.loads((R/'ORACLE_PINS.json').read_text())['scalar_core.py']
(R/'results').mkdir(exist_ok=True);(R/'build').mkdir(exist_ok=True)
(R/'results/DEPENDENCY_RESOLUTION.json').write_text(json.dumps({'used':used,'absent':missing},indent=2)+'\n')
print('Verified local jars:',len(used),'Absent:',missing,flush=True)
if a.verify_only:sys.exit(0)
subprocess.run([sys.executable,str(R/'generate_fixture.py')],check=True)
cp=os.pathsep.join(x['path'] for x in used);plugin=next(x['path'] for x in used if x['name'].startswith('chisel-plugin_'))
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx1200m']
commands=[('compile',java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-d',str(R/'build')]+[str(f) for f in sorted((R/'upstream').glob('*.scala'))]+[str(R/'Fixture.scala'),str(R/'LoadPrepCheck.scala')]),('simulation',java+['-cp',str(R/'build')+os.pathsep+cp,'LoadPrepCheck']+(['--guarded32-only'] if a.guarded32_only else []))]
(R/'results/COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n')
files=list((R/'upstream').glob('*.scala'))+[R/'Fixture.scala',R/'LoadPrepCheck.scala']
(R/'results/EXECUTED_SOURCE_HASHES.json').write_text(json.dumps({str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2)+'\n')
def limit():resource.setrlimit(resource.RLIMIT_CPU,(160,165))
for label,cmd in commands:
 t=time.monotonic()
 with (R/'results'/f'{label}.log').open('w') as f:
  try:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=R,timeout=200,preexec_fn=limit).returncode
  except subprocess.TimeoutExpired:code='WALL_TIMEOUT'
 result={'stage':label,'exit':code,'seconds':time.monotonic()-t};(R/'results'/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)
 if code!=0:sys.exit(1)
