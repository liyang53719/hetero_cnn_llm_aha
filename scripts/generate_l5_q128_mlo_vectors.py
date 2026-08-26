#!/usr/bin/env python3
import argparse,hashlib,json,math,struct
from pathlib import Path
import numpy as np
T=128;H=1536;HEADS=12;D=128
HASH={'q':'1e259f274616e3137dd1762d1cfeb8dc005ada8d40a1bb80fce716c55e7b4c6f','k':'499da9e0b835ab6de33c2870b9e0b28b8b1206943a8d863dcd2b6d5586eeebc1','v':'5c3169a425c823d6e60d1a7f77d4ea7ea14436ec291199cac290f49ce2f01078'}
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def val(s):return np.float32(struct.unpack('<f',struct.pack('<I',int(s,16)))[0])
def add(a,b):return np.float32(np.float32(a)+np.float32(b))
def mul(a,b):return np.float32(np.float32(a)*np.float32(b))
def red16(x):
 x=np.array(x,dtype=np.float32)
 while len(x)>1:x=np.array([add(x[i],x[i+1])for i in range(0,len(x),2)],dtype=np.float32)
 return x[0]
def dot(a,b):
 s=np.float32(0)
 for c in range(8):s=add(s,red16([mul(a[c*16+i],b[c*16+i])for i in range(16)]))
 return mul(s,np.float32(struct.unpack('<f',struct.pack('<I',0x3db504f3))[0]))
def exp2p(x):
 x=np.float32(x)
 if x < -16:return np.float32(0)
 if x >= 0:return np.float32(1)
 i=max(0,min(255,math.floor(float(x)*16)+256));x0=np.float32(i/16-16);x1=np.float32(x0+np.float32(1/16));y0=np.float32(np.exp2(x0));y1=np.float32(np.exp2(x1));m=np.float32((np.float64(y1)-np.float64(y0))/(1/16));b=np.float32(np.float64(y0)-np.float64(m)*np.float64(x0));return add(mul(m,x),b)
def recip(x):
 w=bits(x);e=(w>>23)&255;fr=w&0x7fffff;n=np.float32(struct.unpack('<f',struct.pack('<I',(127<<23)|fr))[0]);i=fr>>19;x0=1+i/16;x1=x0+1/16;m=np.float32(((1/x1)-(1/x0))/(1/16));b=np.float32(1/x0-float(m)*x0);y=add(mul(m,n),b);y=mul(y,add(np.float32(2),-mul(n,y)));return mul(y,np.float32(struct.unpack('<f',struct.pack('<I',(254-e)<<23))[0]))
def load(path,name):
 if hashlib.sha256(path.read_bytes()).hexdigest()!=HASH[name]:raise SystemExit(f'Q128_MLO_HASH_FAIL {name}')
 return np.array([val(s)for s in path.read_text().splitlines()],dtype=np.float32).reshape(T,H)
def write(p,x):p.write_text('\n'.join(f'{bits(v):08x}'for v in x.flat)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rope-dir',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 q=load(a.rope_dir/'q_rope.memh','q');k=load(a.rope_dir/'k_gqa.memh','k');v=load(a.rope_dir/'v_gqa.memh','v');mout=np.empty((T,HEADS),np.float32);lout=np.empty((T,HEADS),np.float32);oout=np.empty((T,H),np.float32);att=np.empty((T,H),np.float32);maxerr=0.;log2e=np.float32(1.4426950408889634)
 for qt in range(T):
  for h in range(HEADS):
   sl=slice(h*D,(h+1)*D);m=l=None;o=None;tm=-math.inf;tl=0.;to=np.zeros(D,np.float64)
   for kt in range(qt+1):
    s=dot(q[qt,sl],k[kt,sl]);sf=float(s)
    if kt==0:m=s;l=np.float32(1);o=v[kt,sl].copy()
    else:
     mn=s if s>m else m;alpha=exp2p(mul(add(m,-mn),log2e));beta=exp2p(mul(add(s,-mn),log2e));l=add(mul(l,alpha),beta);o=np.array([add(mul(o[i],alpha),mul(v[kt,sl][i],beta))for i in range(D)],np.float32);m=mn
    tmn=max(tm,sf);ta=0. if tm==-math.inf else math.exp(tm-tmn);tb=math.exp(sf-tmn);tl=tl*ta+tb;to=to*ta+v[kt,sl].astype(np.float64)*tb;tm=tmn
   inv=recip(l);norm=np.array([mul(x,inv)for x in o],np.float32);truth=to/tl;maxerr=max(maxerr,float(np.max(np.abs(norm.astype(np.float64)-truth))));mout[qt,h]=m;lout[qt,h]=l;oout[qt,sl]=o;att[qt,sl]=norm
 nodes={'m':mout,'l':lout,'o':oout,'attention':att}
 for n,x in nodes.items():write(a.out/f'{n}.memh',x)
 man={'input_sha256':HASH,'causal_updates':99072,'reciprocals':1536,'normalization_chunks':12288,'score_matrix_materialized':False,'max_attention_error':maxerr,'threshold':0.002,'pass':maxerr<=.002,'node_sha256':{n:hashlib.sha256((a.out/f'{n}.memh').read_bytes()).hexdigest()for n in nodes}}
 (a.out/'manifest.json').write_text(json.dumps(man,indent=2)+'\n');
 if not man['pass']:raise SystemExit(f'Q128_MLO_ERROR {maxerr}')
 print(f"L5_Q128_MLO_VECTORS_PASS updates=99072 score_matrix=false max_error={maxerr:.9g} attention_sha256={man['node_sha256']['attention']}")
if __name__=='__main__':main()
