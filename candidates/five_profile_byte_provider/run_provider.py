"""Explicit full byte-stream reproduction; can read GB inputs. Not run by unit tests."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys
from parent_inputs import path_for_sha
from memory_provider import MemoryProvider,MemoryAccessError
HERE=Path(__file__).resolve().parent
def load_reader(name):
 spec=importlib.util.spec_from_file_location('provider_'+name,HERE/name/'payloads.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m
def metadata_from_manifest(m):
 l=m.get('launch',m);out=[]
 for name,tag,stem in [('command_bytes','commands','command'),('descriptor_bytes','descriptors','descriptor')]:
  filename=('host_' if 'launch' not in m else '')+tag+'.bin';digest=m['sha256'].get(filename,m['sha256'].get(tag));data=path_for_sha(digest).read_bytes();size=l[stem+'Limit']-l[stem+'Base']
  if not(l[tag]*16<=len(data)<=size):raise MemoryAccessError('metadata size')
  out.append((name,l[stem+'Base'],data+bytes(size-len(data))))
 return out
def one(profile):
 pins=json.loads((HERE/'PROGRAM_PINS.json').read_text())['profiles'];r=pins[profile]['files']['manifest.json'];mp=path_for_sha(r['sha256'],r['bytes']);m=json.loads(mp.read_text())
 mod=load_reader('qwen2' if profile==0 else 'qwen08' if profile<3 else 'qwen35');readers,report=mod.build_readers(mp)
 extra=[];aliases=[]
 if 'launch' in m:
  region=m['launch']['regions'][3];extra=[('dense_transport_scratch',region['base'],region['limit']-region['base'])]
 if profile==0:
  t=m['tensors'];kv,k,v=(t[n] for n in ('kv','cache_k','cache_v'))
  if not(kv['dims']==[2,128,256] and k['dims']==v['dims']==[128,256] and kv['address']==k['address'] and v['address']==k['address']+128*256*4 and kv['words']==2*k['words']==2*v['words']):raise ValueError('exact Qwen2 KV alias geometry required')
  aliases=[('kv','cache_k','cache_v')]
 p=MemoryProvider(m,readers,metadata_from_manifest(m),extra,aliases);checks=0
 try:
  for start,end,name,ro,reader in p.regions:
   if ro:
    for off in sorted({0,min(1,end-start),min(63,end-start),max(0,end-start-65),max(0,end-start-1)}):
     n=min(65,end-start-off)
     if p.read(start+off,n)!=reader.read(off,n):raise ValueError('transport mismatch')
     checks+=1
   else:
    try:p.read(start,1)
    except MemoryAccessError:checks+=1
    else:raise ValueError('RW preloaded')
    n=min(65,end-start);data=bytes((i*17+profile)%256 for i in range(n));p.write(start,data)
    if p.read(start,n)!=data:raise ValueError('temporary test write mismatch')
    checks+=1
  logical=p.stream_ro_hashes();expected=json.loads((HERE/'LOGICAL_HASHES.json').read_text())['profiles'][profile]['logical_ro']
  if logical!=expected:raise ValueError('recorded exact stream hashes differ')
 finally:
  for r in readers.values():
   if hasattr(r,'close'):r.close()
 return dict(profile=profile,status='BYTE_PROVIDER_ONLY_NOT_DUT',logical_ro=logical,transport_checks=checks,numeric_pass=False,test_writes_exported=False,timing_model=False)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--profiles',type=int,nargs='+',choices=range(5),default=list(range(5)));a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 for i in a.profiles:(a.out/f'profile{i}_hashes.json').write_text(json.dumps(one(i),indent=2)+'\n')
