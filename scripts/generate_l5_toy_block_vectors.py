#!/usr/bin/env python3
import argparse,ctypes,hashlib,json,math,random,struct
from pathlib import Path
import numpy as np
H=16;HEADS=4;D=4;MLP=32
libm=ctypes.CDLL('libm.so.6');fmaf=libm.fmaf;fmaf.argtypes=[ctypes.c_float]*3;fmaf.restype=ctypes.c_float
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def bf16_bits(x):
 u=bits(x);return ((u+0x7fff+((u>>16)&1))>>16)&0xffff
def bf16_value(x):return np.float32(f(bf16_bits(x)<<16))
def add(a,b):return np.float32(np.float32(a)+np.float32(b))
def mul(a,b):return np.float32(np.float32(a)*np.float32(b))
def fma(a,b,c):return np.float32(fmaf(ctypes.c_float(float(a)),ctypes.c_float(float(b)),ctypes.c_float(float(c))))
def gemv(x,w):
 xb=np.array([bf16_value(z) for z in x],dtype=np.float32);out=[]
 for j in range(w.shape[1]):
  acc=np.float32(0)
  for k in range(w.shape[0]):acc=fma(xb[k],np.float32(f(int(w[k,j])<<16)),acc)
  out.append(acc)
 return np.array(out,dtype=np.float32)
def rsqrt_alg(x):
 xb=bits(x);E=(xb>>23)&255;fr=xb&0x7fffff;e=E-127;odd=e&1;ee=e-1 if odd else e;norm=np.float32(f(((128 if odd else 127)<<23)|fr));idx=(odd<<4)|(fr>>19);lo,step=(1.,1/16)if not odd else(2.,1/8);x0=lo+(idx&15)*step;x1=x0+step;m=np.float32(((1/math.sqrt(x1))-(1/math.sqrt(x0)))/step);b=np.float32(1/math.sqrt(x0)-float(m)*x0);y=add(mul(m,norm),b);y2=mul(y,y);xy=mul(norm,y2);term=add(np.float32(1.5),-mul(np.float32(.5),xy));return mul(mul(y,term),np.float32(f((127-ee//2)<<23)))
def rmsnorm(x,w,eps=np.float32(1e-5)):
 q=np.array([mul(z,z) for z in x],dtype=np.float32)
 while len(q)>1:q=np.array([add(q[i],q[i+1])for i in range(0,len(q),2)],dtype=np.float32)
 inv=rsqrt_alg(add(mul(q[0],np.float32(1/16)),eps));return np.array([mul(mul(x[i],inv),w[i])for i in range(16)],dtype=np.float32)
def exp2p(x):
 x=np.float32(x)
 if x< -16:return np.float32(0)
 if x>=0:return np.float32(1)
 i=max(0,min(255,math.floor(float(x)*16)+256));x0=np.float32(i/16-16);x1=np.float32(x0+np.float32(1/16));y0=np.float32(np.exp2(x0));y1=np.float32(np.exp2(x1));m=np.float32((np.float64(y1)-np.float64(y0))/(1/16));b=np.float32(np.float64(y0)-np.float64(m)*np.float64(x0));return add(mul(m,x),b)
def recip(x):
 xb=bits(x);E=(xb>>23)&255;fr=xb&0x7fffff;norm=np.float32(f((127<<23)|fr));i=fr>>19;x0=1+i/16;x1=x0+1/16;m=np.float32(((1/x1)-(1/x0))/(1/16));b=np.float32(1/x0-float(m)*x0);y=add(mul(m,norm),b);return mul(mul(y,add(np.float32(2),-mul(norm,y))),np.float32(f((254-E)<<23)))
def silu(x):
 e=exp2p(mul(np.float32(-abs(float(x))),np.float32(1.4426950408889634)));base=mul(x,recip(add(np.float32(1),e)));return mul(base,e)if x<0 else base
def rope(x):
 out=x.copy()
 for p in range(0,H,2):
  angle=np.float32(.125*(p//2+1));c=np.float32(math.cos(float(angle)));s=np.float32(math.sin(float(angle)));e,o=x[p],x[p+1]
  out[p]=add(mul(e,c),-mul(o,s));out[p+1]=add(mul(e,s),mul(o,c))
 return out
def dot4(a,b):
 p=[mul(a[i],b[i])for i in range(4)];return mul(add(add(p[0],p[1]),add(p[2],p[3])),np.float32(.5))
def write_mem(path,values,width=32):path.write_text('\n'.join(f'{int(v):0{width//4}x}'for v in values)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);r=random.Random(0x10bf16b)
 def wm(rows,cols,scale=.25):return np.array([[bf16_bits(r.uniform(-scale,scale))for _ in range(cols)]for _ in range(rows)],dtype=np.uint16)
 x=np.array([bf16_value(r.uniform(-1,1))for _ in range(H)],dtype=np.float32);nw1=np.array([np.float32(r.uniform(.8,1.2))for _ in range(H)]);nw2=np.array([np.float32(r.uniform(.8,1.2))for _ in range(H)])
 weights={'wq':wm(H,H),'wk':wm(H,H),'wv':wm(H,H),'wo':wm(H,H),'wg':wm(H,MLP),'wu':wm(H,MLP),'wd':wm(MLP,H)}
 n1=rmsnorm(x,nw1);q=gemv(n1,weights['wq']);k=gemv(n1,weights['wk']);v=gemv(n1,weights['wv']);qr=rope(q);kr=rope(k)
 att=np.zeros(H,dtype=np.float32);scores=[]
 for h in range(HEADS):
  sl=slice(h*D,(h+1)*D);scores.append(dot4(qr[sl],kr[sl]));att[sl]=v[sl]
 op=gemv(att,weights['wo']);res1=np.array([add(x[i],op[i])for i in range(H)],dtype=np.float32);n2=rmsnorm(res1,nw2)
 gate=gemv(n2,weights['wg']);up=gemv(n2,weights['wu']);act=np.array([silu(z)for z in gate],dtype=np.float32);prod=np.array([mul(act[i],up[i])for i in range(MLP)],dtype=np.float32);down=gemv(prod,weights['wd']);final=np.array([add(res1[i],down[i])for i in range(H)],dtype=np.float32)
 nodes={'x':x,'norm1':n1,'q':q,'k':k,'v':v,'q_rope':qr,'k_rope':kr,'attention':att,'oproj':op,'residual1':res1,'norm2':n2,'gate':gate,'up':up,'silu':act,'gate_mul_up':prod,'down':down,'final':final,'scores':np.array(scores,dtype=np.float32)}
 for name,val in nodes.items():write_mem(a.out/f'{name}.memh',[bits(z)for z in val])
 rope_coeff=[]
 for pidx in range(8):
  angle=np.float32(.125*(pidx+1));rope_coeff.extend([bits(np.float32(math.cos(float(angle)))),bits(np.float32(math.sin(float(angle))))])
 write_mem(a.out/'rope_coeff.memh',rope_coeff)
 write_mem(a.out/'norm_weight1.memh',[bits(z)for z in nw1]);write_mem(a.out/'norm_weight2.memh',[bits(z)for z in nw2])
 offsets={};flat=[]
 for name,w in weights.items():offsets[name]={'offset':len(flat),'rows':w.shape[0],'cols':w.shape[1]};flat.extend(int(z)for z in w.flat)
 write_mem(a.out/'weights_bf16.memh',flat,16)
 manifest={'hidden':H,'heads':HEADS,'head_dim':D,'mlp':MLP,'weight_offsets':offsets,'node_sha256':{}}
 for name in nodes:
  manifest['node_sha256'][name]=hashlib.sha256((a.out/f'{name}.memh').read_bytes()).hexdigest()
 (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(f"L5_TOY_BLOCK_VECTORS_PASS nodes={len(nodes)} final_sha256={manifest['node_sha256']['final']}")
if __name__=='__main__':main()
