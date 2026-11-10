"""Pure byte/layout adapter. Never imports a forward/reference or initializes scratch."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ROPE_SOURCE='46b126cb45e57ae6f13ef7f981ec209f1beb3354b26b39b771be7c091f301f8c'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def adapt(payload,out,rope):
 j=json.loads((payload/'manifest.json').read_text()); pins=json.loads((payload/'REAL_INPUT_BINDING.json').read_text())
 assert (j['tokens'],j['commands'],j['descriptors'])==(128,21,215)
 assert j['shape']=={'H':1536,'F':8960,'HEADS':12,'KVHEADS':2,'HD':128,'MAX_TOKENS':1024}
 assert pins['fp32_storage'] and pins['weights_real']
 files={}
 for r in pins['records']:
  p=payload/(r['name']+'.f32le'); assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
  assert j['tensors'][r['name']]['readonly'] and r['address']==j['tensors'][r['name']]['address']
  files[r['name']]=p.resolve()
 source=ROOT/'round_20261110T0733/qwen2_execution/host_real_inputs.cpp'
 assert sha(source)==ROPE_SOURCE
 assert rope.stat().st_size==2*1024*64*4 and sha(rope)=="9c59ecfe381ffd75e939cfda67423997454145376fff21991af06d98b8d06b7e", "original RoPE input bytes mismatch"
 files['rope']=rope.resolve()
 for n,key in [('commands','host_commands'),('descriptors','host_descriptors')]:
  p=payload/(key+'.bin'); assert sha(p)==pins[key+'_sha256'];files[n]=p.resolve()
 out.mkdir(parents=True,exist_ok=False)
 alloc=[('commands',j['commandBase'],j['commandLimit']-j['commandBase'],'ro'),('descriptors',j['descriptorBase'],j['descriptorLimit']-j['descriptorBase'],'ro')]
 for n in j['allocations']:
  t=j['tensors'][n];alloc.append((n,t['address'],t['words']*4,'virtual' if t['virtual'] else 'ro' if t['readonly'] else 'rw'))
 assert len({n for n,a,b,m in alloc})==len(alloc)
 for (_,a,b,_),(_,c,_,_) in zip(sorted(alloc,key=lambda x:x[1]),sorted(alloc,key=lambda x:x[1])[1:]):assert a+b<=c
 views=['AFFINE_BYTES_V1'];lines=['HOST_COMPILED_INPUT_V2','\t'.join(map(str,['launch',1,0,1,j['commandBase'],j['commandLimit'],21,j['descriptorBase'],j['descriptorLimit'],215]))]
 lines+=['\t'.join(map(str,['region',0,j['base'],j['scratchBase'],1,0])),'\t'.join(map(str,['region',1,j['scratchBase'],j['limit'],1,1])),'region\t2\t0\t0\t0\t0','region\t3\t0\t0\t0\t0']
 verified=[]
 for n,a,b,mode in alloc:
  assert a%64==0 and b%64==0
  lines.append('\t'.join(map(str,['allocation',n,a,b,b,mode])))
  if mode=='ro':
   p=files[n]; assert p.stat().st_size==b, (n,p.stat().st_size,b)
   h=sha(p);views.append('\t'.join(map(str,['map',n,a,a,b,1,b,1,p,0,1,1,1,'identity',b,h])))
   verified.append(dict(name=n,bytes=b,sha256=h))
 lines.append('views\t'+str((out/'views.tsv').resolve()))
 for s in j['schedule']:
  for n in s['outputs']:
   t=j['tensors'][n];assert not t['readonly'] and not t['virtual'];lines.append('\t'.join(map(str,['observe',s['pc'],n,t['address'],t['words']*4,7])))
 (out/'views.tsv').write_text('\n'.join(views)+'\n');(out/'host.tsv').write_text('\n'.join(lines)+'\n')
 result=dict(status='PASS_FORMAT_AND_SOURCE_HASH_ONLY',hardware_executed=False,tokens=128,commands=21,descriptors=215,readonly=verified,rope_original_source_sha256=ROPE_SOURCE,manifest_sha256=sha(payload/'manifest.json'),allocations=len(alloc),reference_preloads=0)
 (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rope',type=Path,required=True);a=p.parse_args();print(json.dumps(adapt(a.payload,a.output,a.rope)))
