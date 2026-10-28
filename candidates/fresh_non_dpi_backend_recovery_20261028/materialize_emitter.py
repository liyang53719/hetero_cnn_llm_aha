#!/usr/bin/env python3
"""Rebind only verified input paths; fresh output, no compile/run/download or learned hash."""
from pathlib import Path
import argparse,hashlib,json
P=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--original-high',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
inputs=[('ORIGINAL_HIGH',a.original_high,98842098,'391774e80482befb9004f78ffb3cbbc6497f2a392e9729e97e648071026bd267'),('ANNOTATIONS',a.annotations,1353384,'e40aecae9e15a890acd6eacabd6974d9470434cc83b40c847a0d50096b2bdeee')]
for role,f,n,h in inputs:need(f.is_file() and not f.is_symlink() and f.stat().st_size==n and sha(f)==h,'required exact reviewed input '+role)
manifest=json.loads((P/'SOURCE_PINS.json').read_text());source=P/'source/FreshHostHighSimulationEmitter.scala';entry=next(x for x in manifest['files'] if x['path']=='source/FreshHostHighSimulationEmitter.scala')
need(source.stat().st_size==entry['public_bytes'] and sha(source)==entry['public_sha256'],'template identity')
text=source.read_text()
for role,f,_,_ in inputs:
 token='REQUIRES_VERIFIED_'+role;need(text.count(token)==1,'one explicit path token '+role)
 # JSON string escaping also yields a valid Scala string for these filesystem paths.
 s=str(f.resolve());need(not any(ord(c)<32 or ord(c)>126 for c in s),'ASCII path without controls')
 text=text.replace('"'+token+'"',json.dumps(s))
need(not a.output.exists() and not a.output.is_symlink(),'fresh output directory');a.output.mkdir()
out=a.output/'FreshHostHighSimulationEmitter.scala';out.write_text(text)
(a.output/'REBIND_RECEIPT.json').write_text(json.dumps({'scope':'INPUT_PATH_REBIND_ONLY_NOT_COMPILED','sha256':sha(out),'bytes':out.stat().st_size,'matches_historical_compiled_source_bytes':sha(out)==entry['compiled_original_sha256'],'limitations':'Different local paths change source bytes. A fresh compilation/emission receipt is required; no inherited PASS.'},indent=2)+'\n')
