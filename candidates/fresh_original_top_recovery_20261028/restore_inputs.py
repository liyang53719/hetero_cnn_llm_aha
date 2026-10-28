#!/usr/bin/env python3
"""Verify complete source closure; optionally fetch exact Maven artifacts. Never launches Java/EDA."""
import argparse,hashlib,json,pathlib,urllib.request,shlex
D=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--download-jars',action='store_true');p.add_argument('--java',default='java');a=p.parse_args()
m=json.loads((D/'SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
def verify(q,x):
 if not q.is_file() or q.stat().st_size!=x['bytes'] or hashlib.sha256(q.read_bytes()).hexdigest()!=x['sha256']:
  raise SystemExit('FAIL integrity: '+str(q))
for x in m['sources']:verify(D/x['path'],x)
paths=[];plugin=None
for x in m['jars']:
 q=D/'cache'/x['maven_path']
 if not q.exists() and a.download_jars:
  q.parent.mkdir(parents=True,exist_ok=True)
  with urllib.request.urlopen(x['url'],timeout=60) as f:data=f.read(64<<20)
  if len(data)!=x['bytes'] or hashlib.sha256(data).hexdigest()!=x['sha256']:
   raise SystemExit('FAIL download integrity: '+x['url'])
  q.write_bytes(data)
 if q.exists():verify(q,x)
 if x['role']=='plugin':plugin=str(q)
 else:paths.append(str(q))
cp=':'.join(paths)
cmd=[a.java,'-Xmx2g','-Xss4m','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-Xmaxerrs','500','-deprecation','-feature','-unchecked','-language:reflectiveCalls','-d',str(D/'rebuild-classes'),*[str(D/x['path']) for x in m['sources']]]
print('PASS source hashes only; dependency presence:',sum(pathlib.Path(x).exists() for x in paths),'/',len(paths))
print('REVIEW BEFORE EXECUTION; create fresh rebuild-classes; apply reviewed resource/process gates and pin Java runtime. Compiler invocation:')
print(shlex.join(cmd))
print('Then reviewed diagnostic main: chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5; same155sources/fixedTop. No simulation, no RTL/numeric PASS.')
