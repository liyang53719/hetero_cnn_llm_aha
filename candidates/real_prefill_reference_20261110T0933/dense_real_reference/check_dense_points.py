from run import ROOT,R
import sys,json,numpy as np
sys.path.insert(0,str(ROOT/'round_20261110T0833/legacy_python'))
import legacy_reference as ex
result=[]
for profile,payload,name in [(1,'profile1_real_host_payload','qkv'),(1,'profile1_real_host_payload','ab'),(2,'l3_full_host_torch210_payload','q'),(2,'l3_full_host_torch210_payload','k')]:
 local=R/('profile'+str(profile)+'_local');x=np.fromfile(local/'input_norm.bin',dtype='<u2').reshape(128,1024)
 w=np.fromfile(ROOT/'round_20261110T0833'/payload/(name+'_weight.bin'),dtype='<u2').reshape(1024,-1)
 y=np.fromfile(local/(name+'.bin'),dtype='<u2').reshape(128,-1)
 for row,col in [(0,0),(127,w.shape[1]-1)]:
  acc=0;b=ex.Budget(1024)
  for k in range(1024):acc=ex.bf16_fma(int(x[row,k])<<16,int(w[k,col])<<16,acc,b)
  expected=ex.bf16_rne(acc);actual=int(y[row,col])
  if expected!=actual:raise RuntimeError('candidate mismatch')
  result.append(dict(profile=profile,stage=name,row=row,column=col,K=1024,expected_bf16=expected,actual_bf16=actual))
(R/'DENSE_EXACT_SAMPLES.json').write_text(json.dumps({'scope':'8 real output coordinates, full K1024 each; bits only, no flags or exhaustive qualification','points':result},indent=2))
print('PASS 8 real full-K1024 output coordinates against independent Fraction FMA and BF16 rounding')
