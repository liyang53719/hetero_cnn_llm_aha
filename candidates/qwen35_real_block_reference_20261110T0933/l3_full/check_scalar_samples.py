from check_samples import *
from run_full import h
tr=np.fromfile(ROOT/'round_20261110T0833/l3_full_host_torch210_payload/trig.bin',dtype='<u2').reshape(128,64);qn=load('qn',(128,8,256));checks=[]
for row,head,i in [(0,0,0),(127,7,31)]:
 b=ex.Budget(100);a=int(qn[row,head,i])<<16;o=int(qn[row,head,i+32])<<16;c=int(tr[row,i])<<16;s=int(tr[row,i+32])<<16
 ec=ex.bf16_rne(ex.mul(a,c,b))<<16;os=ex.bf16_rne(ex.mul(o,s,b))<<16
 val=ex.bf16_rne(ex.add(ec,os^0x80000000,b))
 if val!=int(qr[row,head,i]):raise ValueError('rope mismatch')
 checks.append('rope '+str((row,head,i)))
masked=rd('masked_score',(128,8,128));ee=np.fromfile(local/'exp.bin',dtype='<f4').reshape(128,8,128)
for row,head in [(0,0),(127,7)]:
 b=ex.Budget(10000);mx=max(masked[row,head].astype('<u4')<<16,key=lambda x:ex.fraction(int(x)));total=0;exps=[]
 for key in range(128):
  d=ex.add(int(masked[row,head,key])<<16,int(mx)^0x80000000,b)
  if key>row and d!=0xff7f0000:raise ValueError('sentinel mismatch')
  e=sig.exp_negative(d)
  if e!=int(ee[row,head,key:key+1].view('<u4')[0]):raise ValueError('exp mismatch')
  total=ex.add(total,e,b);exps.append(e)
 for key,e in enumerate(exps):
  y=sig.bf16(sig.divide(e,total))
  if y!=int(prob[row,head,key]):raise ValueError('softmax mismatch')
 checks.append('full softmax row '+str((row,head)))
(R/'SCALAR_SAMPLES.json').write_text(json.dumps({'status':'PASS_SELECTED_BITS_ONLY','checks':checks},indent=2));print(checks)
