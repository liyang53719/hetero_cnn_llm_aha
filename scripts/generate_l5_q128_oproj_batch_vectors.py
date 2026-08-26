#!/usr/bin/env python3
import argparse,ctypes,hashlib,json,math,struct
from pathlib import Path
import numpy as np
T=128;B=16;H=1536
HASH={'attention':'b72c3a34951c84b29d20bd5be9ff58c1282cde5afe7cf9c4e800243ef2b60c76','inputs':'39917c9e6f887030091cb93e944b263f4966322f487d567a6c28881b615335e0','weights':'27c1f27c834a25a28ff32d3956e5fff028c1a565e46f9013cb11c91ce55ed6b3','norm_weight':'7785c762e20b178ddd03ae05f5b95d9edc81236f7d60015bd685738a142a5418'}
libm=ctypes.CDLL('libm.so.6');fmaf=libm.fmaf;fmaf.argtypes=[ctypes.c_float]*3;fmaf.restype=ctypes.c_float
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def word(w):return np.float32(struct.unpack('<f',struct.pack('<I',int(w)))[0])
def val(s):return word(int(s,16))
def bf(x):w=bits(x);return word((((w+0x7fff+((w>>16)&1))>>16)&0xffff)<<16)
def add(a,b):return np.float32(np.float32(a)+np.float32(b))
def mul(a,b):return np.float32(np.float32(a)*np.float32(b))
def fma(a,b,c):return np.float32(fmaf(ctypes.c_float(float(a)),ctypes.c_float(float(b)),ctypes.c_float(float(c))))
def red(x):
 x=np.array(x,np.float32)
 while len(x)>1:x=np.array([add(x[i],x[i+1])for i in range(0,len(x),2)],np.float32)
 return x[0]
def rsqrt(x):
 w=bits(x);e=(w>>23)&255;fr=w&0x7fffff;ue=e-127;odd=ue&1;ee=ue-1 if odd else ue;n=word(((128 if odd else 127)<<23)|fr);i=(odd<<4)|(fr>>19);lo,st=((1.,1/16)if not odd else(2.,1/8));x0=lo+(i&15)*st;x1=x0+st;m=np.float32(((1/math.sqrt(x1))-(1/math.sqrt(x0)))/st);b=np.float32(1/math.sqrt(x0)-float(m)*x0);y=add(mul(m,n),b);term=add(np.float32(1.5),-mul(np.float32(.5),mul(n,mul(y,y))));return mul(mul(y,term),word((127-ee//2)<<23))
def norm(x,w):
 s=np.float32(0)
 for c in range(96):s=add(s,red([mul(z,z)for z in x[c*16:(c+1)*16]]))
 inv=rsqrt(add(mul(s,np.float32(1/H)),np.float32(1e-6)));return np.array([mul(mul(x[i],inv),w[i])for i in range(H)],np.float32)
def write(p,x):p.write_text('\n'.join(f'{bits(v):08x}'for v in x.flat)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--attention',type=Path,required=True);ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--weights',type=Path,required=True);ap.add_argument('--norm-weight',type=Path,required=True);ap.add_argument('--batch-index',type=int,required=True,choices=range(8));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 for p,n in[(a.attention,'attention'),(a.inputs,'inputs'),(a.weights,'weights'),(a.norm_weight,'norm_weight')]:
  if hashlib.sha256(p.read_bytes()).hexdigest()!=HASH[n]:raise SystemExit(f'Q128_OPROJ_HASH_FAIL {n}')
 att=np.array([val(s)for s in a.attention.read_text().splitlines()],np.float32).reshape(T,H);inp=np.array([val(s)for s in a.inputs.read_text().splitlines()],np.float32).reshape(T,H);ww=np.array([int(s,16)for s in a.weights.read_text().splitlines()],np.uint16).reshape(H,H);nw=np.array([val(s)for s in a.norm_weight.read_text().splitlines()],np.float32);st=a.batch_index*B;x=att[st:st+B];orig=inp[st:st+B];xb=np.array([[bf(z)for z in row]for row in x],np.float32);op=np.empty((B,H),np.float32)
 for col in range(H):
  acc=[np.float32(0)for _ in range(B)]
  for r in range(H):
   w=word(int(ww[r,col])<<16)
   for t in range(B):acc[t]=fma(xb[t,r],w,acc[t])
  for t in range(B):op[t,col]=acc[t]
 res=np.array([[add(orig[t,i],op[t,i])for i in range(H)]for t in range(B)],np.float32);n2=np.array([norm(res[t],nw)for t in range(B)],np.float32);nodes={'attention':x,'current':orig,'oproj':op,'residual1':res,'norm2':n2}
 for n,z in nodes.items():write(a.out/f'{n}.memh',z)
 m={'batch_index':a.batch_index,'tokens':[st,st+15],'steps':73728,'residual_chunks':1536,'norm_operations':16,'node_sha256':{n:hashlib.sha256((a.out/f'{n}.memh').read_bytes()).hexdigest()for n in nodes}}
 (a.out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(f"L5_Q128_OPROJ_BATCH_VECTORS_PASS batch={a.batch_index} steps=73728 norm2_sha256={m['node_sha256']['norm2']}")
if __name__=='__main__':main()
