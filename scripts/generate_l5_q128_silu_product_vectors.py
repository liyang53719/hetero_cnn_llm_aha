#!/usr/bin/env python3
import argparse,hashlib,json,math,struct
from pathlib import Path
import numpy as np
WORKLOADS={
 128:(8,1146880,'6a2d13e4f49bd9705a6aa004c531333080503f62bd0f2c195a505b154a7b987d','4852e5bcb1af0d90bcf743341dcd16495d7505f93458fb1b1e0d701b08b6e28b'),
 384:(24,3440640,'59f1899fbd871ed2f30c618649bd7b406deec3e03d91c110298ed9f83b397527','3a4b0dbaa9cce3be612239521afc91500500c841ab5db0b59dd4baecf8e52ed9')}
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def val(s):return np.float32(struct.unpack('<f',struct.pack('<I',int(s,16)))[0])
def add(a,b):return np.float32(np.float32(a)+np.float32(b))
def mul(a,b):return np.float32(np.float32(a)*np.float32(b))
def exp2p(x):
 x=np.float32(x)
 if x < -16:return np.float32(0)
 if x >= 0:return np.float32(1)
 i=max(0,min(255,math.floor(float(x)*16)+256));x0=np.float32(i/16-16);x1=np.float32(x0+np.float32(1/16));y0=np.float32(np.exp2(x0));y1=np.float32(np.exp2(x1));m=np.float32((np.float64(y1)-np.float64(y0))/(1/16));b=np.float32(np.float64(y0)-np.float64(m)*np.float64(x0));return add(mul(m,x),b)
def recip(x):
 w=bits(x);e=(w>>23)&255;fr=w&0x7fffff;n=np.float32(struct.unpack('<f',struct.pack('<I',(127<<23)|fr))[0]);i=fr>>19;x0=1+i/16;x1=x0+1/16;m=np.float32(((1/x1)-(1/x0))/(1/16));b=np.float32(1/x0-float(m)*x0);y=add(mul(m,n),b);y=mul(y,add(np.float32(2),-mul(n,y)));return mul(y,np.float32(struct.unpack('<f',struct.pack('<I',(254-e)<<23))[0]))
def silu(x):
 e=exp2p(mul(np.float32(-abs(float(x))),np.float32(1.4426950408889634)));base=mul(x,recip(add(np.float32(1),e)));return mul(base,e)if x<0 else base
def load(base,name,expected,batches):
 h=hashlib.sha256();vals=[]
 for b in range(batches):p=base/f'batch{b}/{name}.memh';data=p.read_bytes();h.update(data);vals.extend(val(s)for s in data.decode().splitlines())
 if h.hexdigest()!=expected:raise SystemExit(f'Q128_SILU_HASH_FAIL {name}')
 return np.array(vals,np.float32)
def write(p,x):p.write_text('\n'.join(f'{bits(v):08x}'for v in x)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--workload',type=int,choices=WORKLOADS,default=128);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);batches,n,gh,uh=WORKLOADS[a.workload];g=load(a.base,'gate',gh,batches);u=load(a.base,'up',uh,batches)
 if len(g)!=n or len(u)!=n:raise SystemExit(f'Q{a.workload}_SILU_LENGTH_FAIL')
 s=np.array([silu(x)for x in g],np.float32);p=np.array([mul(s[i],u[i])for i in range(n)],np.float32);true=g.astype(np.float64)/(1+np.exp(-g.astype(np.float64)));err=float(np.max(np.abs(s.astype(np.float64)-true)));write(a.out/'gate.memh',g);write(a.out/'up.memh',u);write(a.out/'silu.memh',s);write(a.out/'product.memh',p);chunks=n//16;m={'workload':a.workload,'inputs':{'gate':gh,'up':uh},'lanes':n,'product_chunks':chunks,'max_error':err,'threshold':.002,'pass':err<=.002,'silu_sha256':hashlib.sha256((a.out/'silu.memh').read_bytes()).hexdigest(),'product_sha256':hashlib.sha256((a.out/'product.memh').read_bytes()).hexdigest()};(a.out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(f"L5_Q_PREFILL_SILU_PRODUCT_VECTORS_PASS workload={a.workload} lanes={n} chunks={chunks} max_error={err:.9g} product_sha256={m['product_sha256']}")
if __name__=='__main__':main()
