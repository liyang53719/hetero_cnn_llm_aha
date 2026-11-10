"""Bounded source compilation + CHIRRTL elaboration, NEVER numerical simulation."""
import argparse,pathlib,json,hashlib,subprocess,os
r=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--jar-dir',type=pathlib.Path,action='append',required=True);a=p.parse_args()
alljars=[f for d in a.jar_dir for f in d.rglob('*.jar')];used=[]
for pin in json.loads((r/'DEPENDENCIES.json').read_text()):
 f=next((f for f in alljars if f.name==pin['name'] and hashlib.sha256(f.read_bytes()).hexdigest()==pin['sha256']),None)
 if f is None:raise RuntimeError('missing pinned dependency '+pin['name'])
 if not f.name.endswith('-sources.jar'):used.append(f)
for pin in json.loads((r/'SOURCE_PINS.json').read_text()):assert hashlib.sha256((r/'upstream'/pin['name']).read_bytes()).hexdigest()==pin['sha256']
cp=os.pathsep.join(map(str,used));plugin=next(f for f in used if f.name.startswith('chisel-plugin_'))
(r/'build').mkdir(exist_ok=True);(r/'results').mkdir(exist_ok=True)
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx2400m']
steps=[('compile',java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(plugin),'-d',str(r/'build')]+list(map(str,sorted((r/'upstream').glob('*.scala'))+[r/'DerivedCheck.scala',r/'EmitConvRaw.scala']))),('elaboration',java+['-cp',str(r/'build')+os.pathsep+cp,'EmitConvRaw'])]
for label,cmd in steps:
 result=subprocess.run(cmd,cwd=r,capture_output=True,text=True,timeout=90)
 (r/'results'/f'{label}.log').write_text(result.stdout+result.stderr)
 (r/'results'/f'{label}.json').write_text(json.dumps({'exit':result.returncode,'scope':'compilation/CHIRRTL only; no numerical simulation'}))
 print(label,result.returncode);result.check_returncode()
