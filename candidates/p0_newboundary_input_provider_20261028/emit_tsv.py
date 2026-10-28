"""Emit P0 exact unchanged ABI metadata plus input-only identity affine views."""
import argparse,json,hashlib
import numpy as np
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(a):
 root=a.provider.resolve();out=a.output.resolve();out.mkdir(exist_ok=False);m=json.loads((root/'program/manifest.json').read_text());views=['AFFINE_BYTES_V1'];cfg=['HOST_COMPILED_INPUT_V2'];probes=[];alloc=[];sources={x['name']:x for x in json.loads((root/'source_manifest.json').read_text())['sources']}
 cfg.append('\t'.join(map(str,['launch',1,0,1]+[m[k] for k in ('commandBase','commandLimit','commands','descriptorBase','descriptorLimit','descriptors')])))
 for i,(base,limit,rd,wr) in enumerate([(m['base'],m['metadataLimit'],1,0),(m['metadataLimit'],m['scratchBase'],1,0),(m['scratchBase'],m['limit'],1,1),(0x2000000000,0x2080000000,1,1)]):cfg.append('\t'.join(map(str,['region',i,base,limit,rd,wr])))
 def ro(name,address,n,reserved,p):
  if p.stat().st_size!=n:raise ValueError('size')
  alloc.append((name,address,n,reserved,'ro'));views.append('\t'.join(map(str,['map',name,address,address,n,1,n,1,p,0,1,1,1,'identity',n,sha(p)])))
  b=p.read_bytes()
  offsets={0,1,63,n//2,max(0,n-65),n-1}
  if name in {'wq','wk','wv','wo','wg','wu','wd'}:
   N,K=sources[name]['source']['shape'];offsets.update({2*N-1,2*N})
  for offset in sorted(offsets):
   length=min(65,n-offset);expected=b[offset:offset+length]
   if name in sources and 'name' in sources[name]['source']:
    r=sources[name]['source'];raw=(a.payload/'qwen2_1p5b'/(r['name']+'.bin')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('independent raw pin')
    expected=bytearray()
    for ix in range(offset,offset+length):
     if name in {'wq','wk','wv','wo','wg','wu','wd'}:
      N,K=r['shape'];element=ix//2;source=(element%N)*K+element//N;expected.append(raw[2*source+ix%2])
     else:expected.append(0 if ix%4<2 else raw[(ix//4)*2+ix%4-2])
    if bytes(expected)!=b[offset:offset+length]:raise ValueError('raw to logical mapping mismatch')
   probes.append((address+offset,expected.hex()))
 for name,base,limit,file in [('commands','commandBase','commandLimit','host_commands.bin'),('descriptors','descriptorBase','descriptorLimit','host_descriptors.bin')]:ro(name,m[base],m[limit]-m[base],m[limit]-m[base],root/'program'/file)
 for name in m['allocations']:
  t=m['tensors'][name];n=t.get('storage_bytes',t['words']*4);reserved=t['words']*4
  if t['readonly']:ro(name,t['address'],n,reserved,root/'input_only'/(name+'.bin'))
  else:alloc.append((name,t['address'],n,reserved,'virtual' if t['virtual'] else 'rw'))
 # kv is the sole physical cache allocation; cache_k/cache_v remain observation subspans.
 for x in sorted(alloc,key=lambda x:x[1]):cfg.append('\t'.join(map(str,['allocation',*x])))
 for s in m['schedule']:
  for name in s['outputs']:
   t=m['tensors'][name]
   if not t['virtual']:cfg.append('\t'.join(map(str,['observe',s['pc'],name,t['address'],t['words']*4,7])))
 (out/'views.tsv').write_text('\n'.join(views)+'\n');cfg.append('views\t'+str(out/'views.tsv'));(out/'runtime.tsv').write_text('\n'.join(cfg)+'\n');(out/'PRIVATE_PROBES.tsv').write_text('\n'.join(str(x)+'\t'+h for x,h in probes)+'\n')
 (out/'MANIFEST.json').write_text(json.dumps({'status':'EMITTED_INPUT_ONLY_TRANSPORT_NOT_DUT','program_manifest_sha256':sha(root/'program/manifest.json'),'files':{n:sha(out/n) for n in ('runtime.tsv','views.tsv')},'private_probes_records':len(probes),'no_reference_outputs':True,'rw_preloaded':False},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);p.add_argument('--provider',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
