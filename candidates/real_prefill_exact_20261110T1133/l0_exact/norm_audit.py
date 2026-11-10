from pathlib import Path
import sys,json,hashlib,time,resource,collections
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
import numpy as np
from exact import value,rounded,sqrt,div
R=Path(__file__).resolve().parent;ROOT=R.parents[1];D=ROOT/'round_20261110T0933/dense_real_reference';L=ROOT/'round_20261110T0933/l3_full';P=ROOT/'round_20261110T0833/profile1_real_host_payload'

sys.path.insert(0,str(D));from original_prep_reference import fp,bf16,add,mul
hashes={};counts=collections.Counter();stages=[]
def h(raw):return hashlib.sha256(raw).hexdigest()
def load(p,shape,expected):
 raw=p.read_bytes()
 if h(raw)!=expected:raise ValueError('hash '+str(p))
 hashes[str(p.relative_to(ROOT))]=expected
 return np.frombuffer(raw,dtype='<u2').reshape(shape)
def audit(a,b,kind):
 a,b=np.broadcast_arrays(np.asarray(a,dtype='<f4'),np.asarray(b,dtype='<f4'));y=add(a,b) if kind=='add' else mul(a,b)
 for u,v,w in zip(a.view('<u4').flat,b.view('<u4').flat,y.view('<u4').flat):
  x=value(u)+value(v) if kind=='add' else value(u)*value(v)
  neg=(int(u)==0x80000000 and int(v)==0x80000000) if kind=='add' else bool((int(u)^int(v))>>31)
  actual,flags=rounded(x,neg)
  if int(w)!=actual:raise ValueError(('node mismatch',kind,hex(int(u)),hex(int(v)),hex(int(w)),hex(actual)))
  counts[kind+'_nodes']+=1;counts[kind+'_flag_'+str(flags)]+=1
 return y

def norm(name,x,w,expected,qk=False):
 start=time.monotonic();x=fp(x);w=fp(w);shape=x.shape;flat=x.reshape(-1,shape[-1]);m,width=flat.shape
 parts=np.zeros((m,32),dtype='<f4')
 for base in range(0,width,512):
  acc=np.zeros_like(parts)
  for term in range(min(16,width//32)):
   idx=base+term*32+np.array([8*(i%4)+i//4 for i in range(32)])
   acc=audit(acc,audit(flat[:,idx],flat[:,idx],'mul'),'add')
  parts=audit(parts,acc,'add')
 lanes=np.zeros((m,8),dtype='<f4')
 for residue in range(4):lanes=audit(lanes,parts[:,np.arange(8)*4+residue],'add')
 total=np.zeros((m,1),dtype='<f4')
 for lane in range(8):total=audit(total,lanes[:,lane:lane+1],'add')
 arg=audit(audit(total,np.float32(1/width),'mul'),np.float32(1e-6),'add')
 roots=np.empty_like(arg);inverse=np.empty_like(arg);flags=collections.Counter()
 for i,u in enumerate(arg.view('<u4').flat):
  a,f=sqrt(int(u));b,g=div(0x3f800000,a)
  roots.view('<u4').flat[i]=a;inverse.view('<u4').flat[i]=b
  flags['sqrt_'+str(f)]+=1;flags['div_'+str(g)]+=1
 if not np.array_equal(roots.view('<u4'),np.sqrt(arg,dtype=np.float32).view('<u4')):raise ValueError('sqrt candidate mismatch')
 if not np.array_equal(inverse.view('<u4'),(np.float32(1)/roots).view('<u4')):raise ValueError('div candidate mismatch')
 # Audit actual normalization and gamma application, preserving distinct operations.
 y=bf16(audit(audit(flat,inverse,'mul'),audit(np.float32(1),w,'add'),'mul')).reshape(shape)
 if not np.array_equal(y,expected):raise ValueError('saved output differs '+name)
 stages.append(dict(name=name,rows=m,width=width,sqrt_div_pairs=m,flags=dict(flags),argument_sha256=h(arg.tobytes()),inverse_sha256=h(inverse.tobytes()),output_sha256=h(y.tobytes()),seconds=time.monotonic()-start))
 (R/'PROGRESS.json').write_text(json.dumps(stages,indent=2))
