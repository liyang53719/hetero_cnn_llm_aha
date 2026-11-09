import pathlib,json,hashlib,subprocess,os,resource,time
R=pathlib.Path(__file__).resolve().parent;W=R.parent
pins=json.loads((R/'DEPENDENCIES.json').read_text());pins+=json.loads((W/'tail_identity_1934/DEPENDENCIES.json').read_text())
unique={p['name']:p for p in pins}; paths=[]
alljars=list(W.glob('host93_*/**/*.jar'))
for n,p in unique.items():
 candidates=list((W/'tail_identity_1934/runtime').glob(n))+[f for f in alljars if f.name==n]
 f=next((f for f in candidates if hashlib.sha256(f.read_bytes()).hexdigest()==p['sha256']),None)
 if f is None:
  print("MISSING_LOCAL",n,flush=True);continue
 if not n.endswith('-sources.jar'):paths.append(str(f))
for p in json.loads((R/'SOURCE_PINS.json').read_text()):assert hashlib.sha256((R/'upstream'/p['name']).read_bytes()).hexdigest()==p['sha256'],p
(R/'RESOLVED_DEPENDENCIES.json').write_text(json.dumps(list(unique.values()),indent=2))
cp=os.pathsep.join(paths);plugin=next(x for x in paths if '/chisel-plugin_' in x)
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx1200m']
commands=[('compile',java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-d',str(R/'build')]+[str(p) for p in sorted((R/'upstream').glob('*.scala'))]+[str(R/'Fixture.scala'),str(R/'LoadPrepCheck.scala')]),('simulation',java+['-cp',str(R/'build')+os.pathsep+cp,'LoadPrepCheck'])]
def limit():resource.setrlimit(resource.RLIMIT_CPU,(160,165))
for label,cmd in commands:
 t=time.monotonic()
 with (R/'results'/f'{label}.log').open('w') as f:
  p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=R,timeout=200,preexec_fn=limit)
 result={'stage':label,'exit':p.returncode,'seconds':time.monotonic()-t};(R/'results'/f'{label}.json').write_text(json.dumps(result,indent=2));print(result,flush=True)
 if p.returncode:break
