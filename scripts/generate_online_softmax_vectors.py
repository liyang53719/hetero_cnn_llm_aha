#!/usr/bin/env python3
import argparse,json,math,random,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def exp2p(x):
 x=np.float32(x)
 if x< -16:return np.float32(0)
 if x>=0:return np.float32(1)
 idx=max(0,min(255,math.floor(float(x)*16)+256));x0=np.float32(-16+idx/16);x1=np.float32(x0+np.float32(1/16));y0=np.float32(np.exp2(x0));y1=np.float32(np.exp2(x1));m=np.float32((np.float64(y1)-np.float64(y0))/(1/16));b=np.float32(np.float64(y0)-np.float64(m)*np.float64(x0));return np.float32(np.float32(m*x)+b)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();r=random.Random(0x50f74a);lines=[];maxerr=0.
 for seq in range(100):
  scores=[];values=[];m=l=None;o=None
  for t in range(100):
   score=np.float32((t/13 if t%17==0 else -t/9 if t%19==0 else r.uniform(-12,8))+seq%3);v=np.array([r.uniform(-2,2) for _ in range(4)],dtype=np.float32);scores.append(float(score));values.append(v.astype(np.float64));clear=t==0
   if clear:m=score;l=np.float32(1);o=v.copy()
   else:
    mn=np.float32(max(float(m),float(score)));am=exp2p(np.float32(np.float32(m-mn)*np.float32(1.4426950408889634)));be=exp2p(np.float32(np.float32(score-mn)*np.float32(1.4426950408889634)))
    l=np.float32(np.float32(l*am)+be);o=np.array([np.float32(np.float32(o[i]*am)+np.float32(v[i]*be)) for i in range(4)],dtype=np.float32);m=mn
   rec=int(clear);rec|=bits(score)<<1
   for i in range(4):rec|=bits(v[i])<<(33+32*i)
   rec|=bits(m)<<161;rec|=bits(l)<<193
   for i in range(4):rec|=bits(o[i])<<(225+32*i)
   lines.append(f'{rec:089x}')
  s=np.array(scores);w=np.exp(s-np.max(s));ref=np.sum(np.array(values)*w[:,None],axis=0)/np.sum(w);got=o.astype(np.float64)/float(l);maxerr=max(maxerr,float(np.max(np.abs(got-ref))))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');q={'sequences':100,'tokens_per_sequence':100,'lanes':4,'max_normalized_output_absolute_error':maxerr,'threshold':0.002,'threshold_pass':maxerr<=0.002};a.manifest.write_text(json.dumps(q,indent=2)+'\n');
 if not q['threshold_pass']:raise SystemExit(f'ONLINE_SOFTMAX_VECTOR_FAIL {q}')
 print(f'ONLINE_SOFTMAX_VECTORS_PASS tokens={len(lines)} max_abs={maxerr:.9g}')
if __name__=='__main__':main()
