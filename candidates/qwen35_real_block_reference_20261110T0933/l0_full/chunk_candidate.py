"""Independent ordered chunk64 equations. Separate FP32 mul/add, never GEMM.
Finite scalar underflow/overflow fail closed; no transport/hardware claim.
"""
import numpy as np, struct
class FatalArithmetic(RuntimeError):
 def __init__(self,detail):super().__init__(str(detail));self.detail=detail
class Arithmetic:
 def __init__(self):self.phase='start';self.operations=0
 def op(self,a,b,kind):
  a,b=np.broadcast_arrays(np.asarray(a,dtype=np.float32),np.asarray(b,dtype=np.float32));self.operations+=a.size
  if not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('nonfinite operand')
  exact=a.astype(np.float64)*b.astype(np.float64) if kind=='mul' else a.astype(np.float64)+b.astype(np.float64)
  with np.errstate(under='ignore',over='ignore'):out=exact.astype(np.float32)
  tiny=(np.abs(out)<np.finfo(np.float32).tiny)&(out.astype(np.float64)!=exact)
  bad=tiny|~np.isfinite(out)
  if bad.any():
   idx=tuple(np.argwhere(bad)[0]); word=lambda x:f'{struct.unpack("<I",struct.pack("<f",float(x)))[0]:08x}'
   raise FatalArithmetic(dict(phase=self.phase,operation=kind,index=[int(i) for i in idx],a=word(a[idx]),b=word(b[idx]),result=word(out[idx]),flag='underflow_inexact' if tiny[idx] else 'overflow',operations=self.operations))
  return out
 def add(self,a,b):return self.op(a,b,'add')
 def mul(self,a,b):return self.op(a,b,'mul')
 def sub(self,a,b):return self.add(a,-np.asarray(b,dtype=np.float32))
 def mm(self,a,b):
  out=np.zeros((a.shape[0],b.shape[1]),np.float32)
  for k in range(a.shape[1]):out=self.add(out,self.mul(a[:,k,None],b[None,k,:]))
  return out
 def solve(self,u,rhs):
  out=np.zeros_like(rhs)
  for r in range(len(rhs)):
   acc=np.zeros(rhs.shape[1],np.float32)
   for j in range(r):acc=self.add(acc,self.mul(u[r,j],out[j]))
   out[r]=self.sub(rhs[r],acc)
  return out
 def exp(self,x):
  x=np.asarray(x,np.float32)
  if np.any(x>0):raise ValueError('positive log decay')
  a=np.abs(x);active=a<80;safe=np.where(active,a,0).astype(np.float32)
  scaled=self.mul(safe,np.array(0x3fb8aa3b,dtype=np.uint32).view(np.float32));k=np.trunc(scaled).astype(np.int32);f=self.sub(scaled,k.astype(np.float32))
  # Exactly same pinned coefficient words as original scalar_core.
  c=np.array([0x3f800000,0xbf317218,0x3e75fdf0,0xbd635847,0x3c1d955b,0xbaaec3ff,0x39218489,0xb77fe5fe],dtype=np.uint32).view(np.float32)
  y=np.full(x.shape,c[7],np.float32)
  for i in range(6,-1,-1):y=self.add(self.mul(y,f),c[i])
  scale=((127-k).astype(np.uint32)<<23).view(np.float32)
  return np.where(active,self.mul(y,scale),np.float32(0))
 def chunk(self,q,k,v,g,b,state):
  self.phase='1_cumulative';cum=[];acc=np.float32(0)
  for x in g:acc=self.add(acc,x);cum.append(acc)
  cum=np.array(cum,np.float32);e=self.exp(cum);remain=self.exp(self.sub(cum[-1],cum));decay=self.exp(cum[-1])
  self.phase='2_derived';kb=self.mul(k,b[:,None]);vb=self.mul(v,b[:,None]);kbg=self.mul(kb,e[:,None]);qg=self.mul(q,e[:,None]);ke=self.mul(k,remain[:,None])
  delta=self.sub(cum[:,None],cum[None,:]);mask=np.tril(np.ones((len(q),len(q)),bool));pair=np.where(mask,self.exp(np.where(mask,delta,0)),np.float32(0))
  self.phase='5_ut';ut=self.mul(self.mm(kb,k.T),pair)
  self.phase='6_intra';intra=self.mul(self.mm(q,k.T),pair)
  self.phase='7_solvev';sv=self.solve(ut,vb)
  self.phase='8_solvek';sk=self.solve(ut,kbg)
  self.phase='9_pred';pred=self.mm(sk,state)
  self.phase='10_vnew';vn=self.sub(sv,pred)
  self.phase='11_inter';inter=self.mm(qg,state)
  self.phase='12_local';local=self.mm(intra,vn)
  self.phase='13_out';out=self.add(inter,local)
  self.phase='14_update';update=self.mm(ke.T,vn)
  self.phase='15_decay';decayed=self.mul(state,decay)
  self.phase='16_state';return out,self.add(decayed,update)
