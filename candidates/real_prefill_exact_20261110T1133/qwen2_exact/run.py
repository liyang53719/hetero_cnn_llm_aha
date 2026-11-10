"""Actual M128 Qwen2 QK/PV ordered FMA and QK scalar nodes; no hardware."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import resource
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
from pathlib import Path
import sys,json,hashlib,time,ctypes
import numpy as np
O=Path(__file__).parent;R=O.parents[1];P=R/'round_20261110T0833/numpy_fma_candidate';sys.path.insert(0,str(P));from candidate import bf16_words
pins={}
for x in json.loads((P/'full_m128/RESULT.json').read_text())['progress']:
 if x.get('stage') and x['status']=='CANDIDATE_REFERENCE_STAGE_ONLY':
  for i,h in enumerate(x['sha256']):pins[x['buffer']+('.'+str(i) if len(x['sha256'])>1 else '')]=h
verified={};counts={};samples=[]
def check_environment():
 libm=ctypes.CDLL('libm.so.6');libm.fegetround.restype=ctypes.c_int
 if libm.fegetround()!=0:raise ValueError('IEEE RNE required')
 tiny=np.array([1],dtype='<u4').view('<f4')
 if int((tiny+tiny).view('<u4')[0])!=2 or int((tiny*np.float32(1)).view('<u4')[0])!=1:raise ValueError('gradual underflow required; FTZ/DAZ unsupported')
check_environment()

def load(name,shape):
 p=P/'full_m128'/(name+'.local.f32');h=hashlib.sha256(p.read_bytes()).hexdigest()
 if h!=pins[name]:raise ValueError('pin '+name)
 verified[name]=h;return np.fromfile(p,dtype='<u4').reshape(shape)
def two(a,b):
 s=a+b;bb=s-a;return s,(a-(s-bb))+(b-bb)
def round_flags(s,e,valid,stage):
 with np.errstate(over='ignore',under='ignore'):out=s.astype(np.float32)
 nx=(out.astype(np.float64)!=s)|(e!=0);uf=nx&(np.abs(out)<np.float32(2**-126));ov=~np.isfinite(out)
 v=np.broadcast_to(valid,out.shape);c=counts.setdefault(stage,dict(steps=0,flags={},residuals=0));c['steps']+=int(np.count_nonzero(v));c['residuals']+=int(np.count_nonzero((e!=0)&v))
 flags=nx.astype(np.uint8)|(uf.astype(np.uint8)<<1)|(ov.astype(np.uint8)<<2)
 for f,n in zip(*np.unique(flags[v],return_counts=True)):c['flags'][str(int(f))]=c['flags'].get(str(int(f)),0)+int(n)
 if np.any(ov&v):raise ValueError('overflow '+stage)
 return out

def main():
 libm=ctypes.CDLL('libm.so.6');libm.fegetround.restype=ctypes.c_int
 if libm.fegetround()!=0:raise ValueError('RNE required')
 q=bf16_words(load('q',(128,12,128))).view('<f4').astype(np.float64);k=bf16_words(load('k',(128,2,128))).view('<f4').astype(np.float64)
 mask=np.arange(128)[None,:,None]>=np.arange(128)[None,None,:];acc=np.zeros((12,128,128,16),np.float32)
 for d in range(0,128,16):
  a=q[:,:,d:d+16].transpose(1,0,2)[:,:,None,:];b=k[:,np.arange(12)//6,d:d+16].transpose(1,0,2)[:,None,:,:]
  s,e=two(a*b,acc.astype(np.float64));acc=round_flags(s,e,mask[...,None],'qk_fma')
 total=np.zeros((12,128,128),np.float32)
 for lane in range(16):
  s,e=two(total.astype(np.float64),acc[:,:,:,lane].astype(np.float64));total=round_flags(s,e,mask,'qk_fold_add')
 scale=np.array([0x3db504f3],dtype='<u4').view('<f4')[0];scores=round_flags(total.astype(np.float64)*float(scale),0,mask,'qk_scale_mul');scores=np.where(mask,scores,np.float32(0))
 if not np.array_equal(scores.view('<u4'),load('scores',(12,128,128))):raise ValueError('QK full output mismatch')
 prob=bf16_words(load('prob',(12,128,128))).view('<f4').astype(np.float64);v=bf16_words(load('kv.1',(128,2,128))).view('<f4').astype(np.float64);out=np.zeros((12,128,128),np.float32)
 for key in range(128):
  active=np.arange(128)[None,:,None]>=key;s,e=two(prob[:,:,key,None]*v[key,np.arange(12)//6,None,:],out.astype(np.float64));new=round_flags(s,e,active,'pv_fma');out=np.where(active,new,out)
 if not np.array_equal(out.transpose(1,0,2).reshape(128,1536).view('<u4'),load('att',(128,1536))):raise ValueError('PV full output mismatch')
 if libm.fegetround()!=0:raise ValueError('RNE changed')
 check_environment()
 result=dict(status='PASS_FULL_QK_PV_M128_VALUE_AND_FINITE_FMA_FLAGS_REFERENCE_ONLY',tokens=128,heads=12,kvheads=2,head_dim=128,counts=counts,verified_inputs=verified,scope='QK16-lane folding, separate scale, causal PV increasing keys; no input BF16-conversion flags, no softmax/RMS/SILU/fullblock/hardware qualification',hardware=False)
 (O/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':
 start=time.monotonic();(O/'IDENTITY.json').write_text(json.dumps(dict(pid=os.getpid(),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),start_ticks=Path('/proc/self/stat').read_text().split()[21],budget_s=600,address_space=2*1024**3)))
 main();print('seconds',time.monotonic()-start)
