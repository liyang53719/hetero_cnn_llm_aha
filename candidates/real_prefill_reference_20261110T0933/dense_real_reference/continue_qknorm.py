"""C2 QKnorm value-path candidate, original admission range checked.
No claim of arithmetic flags or hardware pass; no inverse approximation.
"""
from run import R,ROOT,sha
from original_prep_reference import fp,bf16,add,mul,div
import numpy as np,json

def c2(x,w):
 for a in (x,w):
  e=(a>>7)&255
  if np.any(((a&32767)!=0)&((e<95)|(e>158))):raise ValueError('original QKnorm range admission')
 x=fp(x);w=fp(w);parts=np.zeros(x.shape[:-1]+(32,),dtype='<f4')
 for t in range(8):
  ids=np.array([32*t+8*(i%4)+i//4 for i in range(32)])
  parts=add(parts,mul(x[...,ids],x[...,ids]))
 lanes=parts[...,np.arange(8)*4].copy()
 for r in (1,2,3):lanes=add(lanes,parts[...,np.arange(8)*4+r])
 total=np.zeros(x.shape[:-1]+(1,),dtype='<f4')
 for i in range(8):total=add(total,lanes[...,i:i+1])
 inv=div(np.float32(1),np.sqrt(add(mul(total,np.float32(1/256)),np.float32(1e-6)),dtype=np.float32))
 return bf16(mul(mul(x,inv),add(np.float32(1),w)))
if __name__=='__main__':
 p=ROOT/'round_20261110T0833/l3_full_host_torch210_payload';local=R/'profile2_local';stages=[]
 for name,heads in [('q',8),('k',2)]:
  try:
   x=np.fromfile(local/(name+'.bin'),dtype='<u2').reshape(128,heads,-1)
   if name=='q':
    gate=x[...,256:].copy();(local/'qgate.bin').write_bytes(gate.tobytes());x=x[...,:256]
   w=np.fromfile(p/(name+'_gamma.bin'),dtype='<u2').reshape(256)
   y=c2(x,w);(local/(name+'n.bin')).write_bytes(y.tobytes())
   stages.append(dict(name=name+'n',status='CANDIDATE_C2_VALUE_PATH',shape=list(y.shape),sha256=sha(y.tobytes())))
  except Exception as e:stages.append(dict(name=name+'n',status='FAIL_CANDIDATE',error=repr(e)))
 (R/'QKNORM_RESULT.json').write_text(json.dumps(dict(stages=stages,flags='NOT_QUALIFIED',hardware=False),indent=2))
 print(stages)
