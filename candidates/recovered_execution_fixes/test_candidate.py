from pathlib import Path
import sys,json,importlib.util,tempfile,hashlib
import os
HERE=Path(os.environ['FIXTURE_WORK'])
sys.path.insert(0,str(HERE/'provider_candidate'))
from memory_provider import MemoryProvider,MemoryAccessError
spec=importlib.util.spec_from_file_location('native_payloads',HERE/'provider_candidate/qwen2/payloads.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
m=json.loads((HERE/'native_candidate/manifest.json').read_text());old=json.loads((HERE.parent/'programs/profile0/manifest.json').read_text());weights={'wq','wk','wv','wo','wg','wu','wd'}
class Pattern:
 def __init__(self,n):self.size=n
 def read(self,o,n):assert 0<=o<=o+n<=self.size;return bytes((i%251 for i in range(o,o+n)))
readers={}
for name,t in m['tensors'].items():
 if t['readonly']:readers[name]=Pattern(t.get('storage_bytes',t['words']*4))
 if name not in weights:assert t==old['tensors'][name]
p=MemoryProvider(m,readers,rw_alias_groups=[('kv','cache_k','cache_v')]);checks=0
for name in weights:
 t=m['tensors'][name];a=t['address'];n=t['storage_bytes'];assert n==old['tensors'][name]['words']*2
 for o in [0,1,63,n-65,n-1]:
  k=min(65,n-o);assert p.read(a+o,k)==readers[name].read(o,k);checks+=1
 try:p.read(a+n,1)
 except MemoryAccessError:checks+=1
 else:raise AssertionError('old upperweightguard readable')
for name,t in m['tensors'].items():
 if not t['readonly'] and not t.get('virtual'):
  try:p.read(t['address'],1)
  except MemoryAccessError:checks+=1
  else:raise AssertionError('RW preloaded')
with tempfile.TemporaryDirectory() as d:
 q=Path(d)/'sample.bin';raw=bytes(range(128));q.write_bytes(raw);rd=mod.Reader(q,len(raw),False)
 try:
  for o in range(128):
   n=min(9,128-o);assert rd.read(o,n)==raw[o:o+n];checks+=1
 finally:rd.close()
print(json.dumps({'scope':'SYNTHETIC_TRANSPORT_AND_METADATA_ONLY','checks':checks,'real_source_readers_built':False,'numeric_pass':False}))
