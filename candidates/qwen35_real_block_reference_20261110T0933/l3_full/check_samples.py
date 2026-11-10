from run_full import ROOT,R,D,load
import sys,importlib.util,json,numpy as np
sys.path.insert(0,str(ROOT/'round_20261110T0833/legacy_python'));import legacy_reference as ex
p=ROOT/'hetero_recovery_20261014T2131/chisel/continuous_prefill/scripts/attention_sigmoid_reference.py';s=importlib.util.spec_from_file_location('sig',p);sig=importlib.util.module_from_spec(s);s.loader.exec_module(sig)
local=R/'local';rd=lambda n,sh:np.fromfile(local/(n+'.bin'),dtype='<u2').reshape(sh)
qr=rd('qr',(128,8,256));kr=rd('kr',(128,2,256));scores=rd('scaled_qk',(128,8,128));prob=rd('prob',(128,8,128));v=load('v',(128,2,256));ctx=rd('context',(128,8,256));gated=rd('gated_context',(128,8,256));q=load('q',(128,8,512));checks=[]
for row,head,key in [(0,0,0),(127,7,127)]:
 b=ex.Budget(2000);acc=0
 for k in range(256):acc=ex.bf16_fma(int(qr[row,head,k])<<16,int(kr[key,head//4,k])<<16,acc,b)
 val=ex.bf16_rne(ex.mul(ex.bf16_rne(acc)<<16,0x3d800000,b))
 if val!=int(scores[row,head,key]):raise ValueError('QK mismatch')
 checks.append('QK fullK256 '+str((row,head,key)))
for row,head,col in [(0,0,0),(127,7,255)]:
 b=ex.Budget(2000);acc=0
 for k in range(128):acc=ex.bf16_fma(int(prob[row,head,k])<<16,int(v[k,head//4,col])<<16,acc,b)
 if ex.bf16_rne(acc)!=int(ctx[row,head,col]):raise ValueError('PV mismatch')
 result=sig.lane(int(q[row,head,256+col]),int(ctx[row,head,col]))
 # lane returns output plus trace dictionary.
 expected=result[0] if isinstance(result,tuple) else result
 if isinstance(expected,dict):expected=expected['output']
 if expected!=int(gated[row,head,col]):raise ValueError(('gate mismatch',expected,int(gated[row,head,col])))
 checks.append('PV fullK128 and exact sigmoid '+str((row,head,col)))
print(checks);(R/'SAMPLES.json').write_text(json.dumps({'status':'PASS_SELECTED_BITS_ONLY','checks':checks},indent=2))
