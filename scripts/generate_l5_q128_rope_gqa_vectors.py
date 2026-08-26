#!/usr/bin/env python3
import argparse,hashlib,json,math,struct
from pathlib import Path
import numpy as np
H=1536;KV=256;D=128;THETA=1_000_000.0
ALL_HASHES={128:{'q':'90e5f377634d20a68bf411c4bc60cc874e228464e4483f8211ec685894559040','k':'59a0989dc8f85b01e8171d6d0a50c24a14c7d375332d90d77f0b08b650634f1f','v':'6f12dcc1104fb20781dee561bf06b5e72d9e5696b8d8fda29e3ce9f96cb3337f'},384:{'q':'a5d2e31e592db1f0ff65c8d36d6b4f14b96e0d7b6642818ca7e087c86882d88a','k':'69a7f29c52ee6d74a6ef975ced7559c09d0334d19a746515892d289d595ec4dd','v':'71db3e37fd43017994349e32fd9d653443db49db10b6b239543345a7fba6a158'},1024:{'q':'4e67c4cc15bf3a72ea1f49b773832f411ff6b7445352887b9c60fe5ef0728e0f','k':'7a1daa90c38a3d680827e1663984d7bb9b63ee2298a78226a94fe2c8014c85de','v':'1853b21c3f348d347cf42adb5a996964c546fa5f88f01954769f45d6d5f7829f'}}
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def val(s):return np.float32(struct.unpack('<f',struct.pack('<I',int(s,16)))[0])
def add(a,b):return np.float32(np.float32(a)+np.float32(b))
def mul(a,b):return np.float32(np.float32(a)*np.float32(b))
def load_batches(base,name,width,tokens,hashes):
 vals=[];h=hashlib.sha256()
 for b in range(tokens//16):
  p=base/f'batch{b}/{name}.memh';data=p.read_bytes();h.update(data);vals.extend(val(s)for s in data.decode().splitlines())
 if h.hexdigest()!=hashes[name]:raise SystemExit(f'PREFILL_ROPE_INPUT_HASH_FAIL {name} {h.hexdigest()}')
 return np.array(vals,dtype=np.float32).reshape(tokens,width)
def rope(x,heads,pos,coeff):
 y=x.copy()
 for h in range(heads):
  base=h*D
  for i in range(64):
   a=x[base+i];b=x[base+64+i];c=coeff[pos,2*i];s=coeff[pos,2*i+1]
   y[base+i]=add(mul(a,c),-mul(b,s));y[base+64+i]=add(mul(b,c),mul(a,s))
 return y
def expand(x):
 y=np.empty(H,dtype=np.float32)
 for qh in range(12):y[qh*D:(qh+1)*D]=x[(qh//6)*D:(qh//6+1)*D]
 return y
def write(p,x):p.write_text('\n'.join(f'{bits(v):08x}'for v in x.flat)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--qkv-dir',type=Path,required=True);ap.add_argument('--tokens',type=int,choices=(128,384,1024),default=128);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);hashes=ALL_HASHES[a.tokens]
 q=load_batches(a.qkv_dir,'q',H,a.tokens,hashes);k=load_batches(a.qkv_dir,'k',KV,a.tokens,hashes);v=load_batches(a.qkv_dir,'v',KV,a.tokens,hashes)
 coeff=np.empty((a.tokens,128),dtype=np.float32)
 for p in range(a.tokens):
  for i in range(64):
   angle=np.float32(p/(THETA**(2*i/D)));coeff[p,2*i]=np.float32(math.cos(float(angle)));coeff[p,2*i+1]=np.float32(math.sin(float(angle)))
 qr=np.array([rope(q[t],12,t,coeff)for t in range(a.tokens)]);kr=np.array([rope(k[t],2,t,coeff)for t in range(a.tokens)])
 kg=np.array([expand(kr[t])for t in range(a.tokens)]);vg=np.array([expand(v[t])for t in range(a.tokens)])
 nodes={'q_input':q,'k_input':k,'v_input':v,'coeff':coeff,'q_rope':qr,'k_rope':kr,'k_gqa':kg,'v_gqa':vg}
 for n,x in nodes.items():write(a.out/f'{n}.memh',x)
 m={'input_sha256':hashes,'positions':a.tokens,'q_rope_pairs':a.tokens*768,'k_rope_pairs':a.tokens*128,'gqa_inputs_each':a.tokens*16,'gqa_outputs_each':a.tokens*96,'node_sha256':{n:hashlib.sha256((a.out/f'{n}.memh').read_bytes()).hexdigest()for n in nodes}}
 (a.out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(f"L5_Q_PREFILL_ROPE_GQA_VECTORS_PASS workload={a.tokens} pairs={a.tokens*896} q_sha256={m['node_sha256']['q_rope']}")
if __name__=='__main__':main()
