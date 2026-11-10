from pathlib import Path
import json,hashlib,sys,numpy as np
from exact import value,rounded
R=Path(__file__).parent;ROOT=R.parents[1];D=ROOT/'round_20261110T0933/dense_real_reference';P=ROOT/'round_20261110T0833/profile1_real_host_payload'
meta=json.loads((D/'RESULT.json').read_text())[0];qpin=next(x['sha256'] for x in meta['stages'] if x['name']=='qkv');wmeta=next(x for x in json.loads((P/'BINDING.json').read_text())['segments'] if x['name']=='conv_weight')
def load(p,pin,shape):
 b=p.read_bytes()
 if hashlib.sha256(b).hexdigest()!=pin:raise ValueError('pin')
 return np.frombuffer(b,'<u2').reshape(shape)
q=load(D/'profile1_local/qkv.bin',qpin,(128,6144));w=load(P/wmeta['file'],wmeta['sha256'],(6144,4));hist=np.zeros((6144,4),'<u2');count=0;examples=[]
for token,row in enumerate(q):
 for tap in range(4):
  a=(row if tap==3 else hist[:,tap+1]).astype('<u4')<<16;b=w[:,tap].astype('<u4')<<16;p=a.view('<f4').astype(np.float64)*b.view('<f4').astype(np.float64);out=p.astype(np.float32);uf=(np.abs(out)<np.float32(2**-126))&(out.astype(np.float64)!=p)
  for j in np.flatnonzero(uf):
   u,f=rounded(value(a[j])*value(b[j]),bool((int(a[j])^int(b[j]))>>31))
   if f!=3 or u!=int(out.view('<u4')[j]):raise ValueError('exact tiny-inexact mismatch')
   if len(examples)<4:examples.append(dict(token=token,tap=tap,channel=int(j),a=f'{a[j]:08x}',b=f'{b[j]:08x}',result=f'{u:08x}',flags=f,opcode='MulIeeeRne',original_policy='gradual_allowed'))
   count+=1
 hist[:,:3]=hist[:,1:].copy();hist[:,3]=row
result=dict(status='PASS_ALL_ACTUAL_CONV_TAP_UNDERFLOWS_EXACT',count=count,examples=examples,scope='Original MulIeeeRne allowed UF; not a policy change, not a hardware run');(R/'TAP_UF_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
