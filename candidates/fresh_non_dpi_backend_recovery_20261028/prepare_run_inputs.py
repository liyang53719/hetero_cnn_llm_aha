#!/usr/bin/env python3
"""Pin explicit already-rebuilt inputs for the exact bounded runner; no download or execution."""
import argparse,hashlib,json,os,shutil
from pathlib import Path
P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--baseline-classes',type=Path,required=True);p.add_argument('--classpath-file',type=Path,required=True);p.add_argument('--java-home',type=Path,required=True);p.add_argument('--rebound-emitter',type=Path,required=True);p.add_argument('--original-high',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
def need(v,m):
 if not v:raise ValueError(m)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def verified(p,r):need(p.is_file() and p.stat().st_size==r['bytes'] and digest(p)==r['sha256'],'input mismatch '+str(p))
tools=json.loads((P/'TOOLCHAIN_PINS.json').read_text());classes=json.loads((P/'HELPER_CLASS_PINS.json').read_text());base=a.baseline_classes.resolve()
need(sorted(str(p.relative_to(base)) for p in base.rglob('*.class'))==sorted(r['path'] for r in classes) and len(classes)==901,'all 901 exact baseline classes required')
files=[]
for r in classes:q=base/r['path'];verified(q,r);files.append(q)
jars=[Path(x).resolve() for x in a.classpath_file.read_text().strip().split(':')];need(len(jars)==len(tools['jars_in_order']),'complete ordered classpath')
for q,r in zip(jars,tools['jars_in_order']):verified(q,r);files.append(q)
java_home=a.java_home.resolve()
for r in tools['jdk_files']:q=java_home/r['path'];verified(q,r);files.append(q)
plugin=[q for q in jars if digest(q)==tools['plugin_sha256']];need(len(plugin)==1,'one exact Chisel plugin')
expected=[(a.original_high,98842098,'391774e80482befb9004f78ffb3cbbc6497f2a392e9729e97e648071026bd267'),(a.annotations,1353384,'e40aecae9e15a890acd6eacabd6974d9470434cc83b40c847a0d50096b2bdeee')]
for q,n,h in expected:need(not q.is_symlink(),'regular reviewed artifact');verified(q,{'bytes':n,'sha256':h});files.append(q.resolve())
# Verify the rebind is solely the two explicit paths, using the checked public template.
sm=json.loads((P/'SOURCE_PINS.json').read_text());sr={r['path']:r for r in sm['files']};template=P/'source/FreshHostHighSimulationEmitter.scala';verified(template,{'bytes':sr['source/FreshHostHighSimulationEmitter.scala']['public_bytes'],'sha256':sr['source/FreshHostHighSimulationEmitter.scala']['public_sha256']})
text=template.read_text()
for role,q in [('ORIGINAL_HIGH',a.original_high),('ANNOTATIONS',a.annotations)]:
 token='"REQUIRES_VERIFIED_'+role+'"';need(text.count(token)==1,'one template token');text=text.replace(token,json.dumps(str(q.resolve())))
need(a.rebound_emitter.read_text()==text,'only reviewed path substitutions allowed')
need(not a.output.exists() and not a.output.is_symlink(),'fresh output');a.output.mkdir();d=a.output.resolve();(d/'source').mkdir()
names=['FreshHostHighSimulationEmitter.scala','FreshHostDenseAccMemoryLowering.scala','FreshHostMatrixResultFifoMemoryLowering.scala'];sources=[]
for n in names:
 q=a.rebound_emitter if n==names[0] else P/'source'/n
 if n!=names[0]:verified(q,{'bytes':sr['source/'+n]['public_bytes'],'sha256':sr['source/'+n]['public_sha256']})
 dst=d/'source'/n;shutil.copyfile(q,dst);sources.append(dst);files.append(dst)
for n in ['run_once.py','run_fma_r2.py']:shutil.copyfile(P/n,d/n)
rows=[]
for q in sorted(set(files)):
 rows.append({'path':str(q),'resolved':str(q.resolve()),'symlink':os.readlink(q) if q.is_symlink() else None,'bytes':q.stat().st_size,'sha256':digest(q)})
pins={'status':'PREPARED_NOT_EXECUTED_FRESH_LOCAL_PATH_IDENTITY','baseline_classes':str(base),'baseline_count':901,'java':str(java_home/tools['java_relative']),'plugin':str(plugin[0]),'jars':list(map(str,jars)),'sources':list(map(str,sources)),'files':rows}
(d/'INPUT_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print(json.dumps({'status':'PREPARED_NOT_EXECUTED','pins':len(rows),'no_inherited_PASS':True}))
