from pathlib import Path
import numpy as np,json,ctypes,ctypes.util,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;CAND=OUT/'stages';BASE=ROOT/'work/qwen2_block_recipe_m128_release_20261011';NATIVE=ROOT/'work/qwen2_layer0_model_gate_cold_m128_20261011/bf16/phase_0'
lib=ctypes.CDLL(ctypes.util.find_library('m'));lib.fmaf.argtypes=[ctypes.c_float]*3;lib.fmaf.restype=ctypes.c_float
fp=np.float32
def bf(x):
 u=int(np.float32(x).view('<u4'));return np.uint32((u+0x7fff+((u>>16)&1))&0xffff0000).view('<f4')
def direct_bf64(x):
 center=int(np.float32(x).view('<u4'))>>16
 choices=[(float(np.uint32(word<<16).view('<f4')),word) for word in (center-1,center,center+1)]
 v,word=min(choices,key=lambda item:(abs(item[0]-x),item[1]&1));return v

def accumulate(a,b,lanes=1,bias=fp(0),bias_at_start=False,partition='cyclic'):
 parts=[fp(0)]*lanes
 if bias_at_start:parts[0]=bias
 for j,(x,y) in enumerate(zip(a,b)):
  index=j%lanes if partition=='cyclic' else min(j*lanes//len(a),lanes-1)
  parts[index]=fp(lib.fmaf(float(x),float(y),float(parts[index])))
 total=fp(0)
 for value in parts:total=fp(total+value)
 if not bias_at_start:total=fp(total+bias)
 return total

def variations(a,b,bias):
 out=[]
 for partition in ('cyclic','contiguous'):
  for lanes in (1,2,4,16):
   if partition=='contiguous' and lanes==1:continue
   for first in (False,True):
    result=accumulate(a,b,lanes,bias,first,partition)
    out.append(dict(partition=partition,lanes=lanes,bias='initial_accumulator' if first else 'after_completed_reduction',fp32=float(result),bf16=float(bf(result))))
 return out
layout=json.loads((BASE/'generated/layout.json').read_text());regions={r['name']:r for r in layout['regions']};arena=np.memmap(BASE/'readonly_arena.f32le',mode='r',dtype='<f4')
def region(name,shape):
 r=regions[name];return arena[r['offset']//4:r['offset']//4+r['words']].reshape(shape)
wq=region('wq',(1536,1536));bq=region('bq',(1536,))
n0=np.fromfile(CAND/'candidate_n0.f32le',dtype='<f4').reshape(128,1536);nn0=np.fromfile(NATIVE/'native_n0.f32le',dtype='<f4').reshape(128,1536)
qr=np.fromfile(CAND/'candidate_qr.f32le',dtype='<f4').reshape(128,1536);nqr=np.fromfile(NATIVE/'native_qr.f32le',dtype='<f4').reshape(128,1536)
points=[(102,1215),(30,1343)]
points.extend(tuple(map(int,ix)) for ix in np.argwhere(qr[:16].view('<u4')!=nqr[:16].view('<u4'))[:5])
dense=[]
for t,col in points:
 a,b=n0[t],wq[:,col];bias=bq[col];exact=float(np.sum(a.astype(np.float64)*b.astype(np.float64))+float(bias));mid=(float(qr[t,col])+float(nqr[t,col]))/2
 dense.append(dict(token=t,column=col,bias=float(bias),input_bit_equal_native=bool(np.array_equal(a.view('<u4'),nn0[t].view('<u4'))),candidate=float(qr[t,col]),native=float(nqr[t,col]),fp64_diagnostic=exact,direct_bf16_of_fp64_diagnostic=direct_bf64(exact),candidate_native_midpoint=mid,distance_from_midpoint=exact-mid,variations=variations(a,b,bias)))
q=np.fromfile(CAND/'candidate_q.f32le',dtype='<f4').reshape(128,12,128);k=np.fromfile(CAND/'candidate_k.f32le',dtype='<f4').reshape(128,2,128)
nq=np.fromfile(NATIVE/'native_q.f32le',dtype='<f4').reshape(128,12,128);nk=np.fromfile(NATIVE/'native_k.f32le',dtype='<f4').reshape(128,2,128)
score=np.fromfile(CAND/'candidate_scores.f32le',dtype='<f4').reshape(12,128,128);ns=np.fromfile(NATIVE/'native_scores.f32le',dtype='<f4').reshape(12,128,128)
qk=[]
for h,t,key in [(6,70,75),(9,102,2),(1,106,75)]:
 cases={}
 for label,a,b in [('candidate_operands',q[t,h],k[key,h//6]),('native_operands',nq[t,h],nk[key,h//6])]:
  exact=float(np.sum(a.astype(np.float64)*b.astype(np.float64)))
  values=variations(a,b,fp(0))
  for value in values:value['scaled_bf16']=float(bf(fp(fp(value['bf16'])*fp(1/np.sqrt(128)))))
  cases[label]=dict(fp64_diagnostic=exact,direct_bf16_of_fp64_diagnostic=direct_bf64(exact),variations=values)
 qk.append(dict(head=h,query=t,key=key,masked_future=key>t,candidate_score=float(score[h,t,key]),native_score=float(ns[h,t,key]),q_differences=np.flatnonzero(q[t,h].view('<u4')!=nq[t,h].view('<u4')).tolist(),k_differences=np.flatnonzero(k[key,h//6].view('<u4')!=nk[key,h//6].view('<u4')).tolist(),cases=cases))
report=dict(scope='small-coordinate read-only reduction probes, no candidate/hardware arithmetic change',dense=dense,qk=qk,native_backend_proven=False,native_backend_evidence='Saved torch build reports MKL, MKL-DNN 3.7.1 and CPU capability AVX512; no profiler, executed-kernel trace or instruction disassembly from original full-shape run was captured. Bias initialization, fused-bias and instruction reduction remain hypotheses.',no_FP64_matrix_candidate=True)
(OUT/'REDUCTION_DIAGNOSTIC.json').write_text(json.dumps(report,indent=2)+'\n')
for item in dense:
 print('DENSE',item['token'],item['column'],'candidate/native',item['candidate'],item['native'],'bias',item['bias'],'exact',item['fp64_diagnostic'],'midpoint',item['candidate_native_midpoint'])
 print([(v['partition'],v['lanes'],v['bias'],v['fp32'],v['bf16']) for v in item['variations']])
for item in qk:
 print('QK',item['head'],item['query'],item['key'],'candidate/native',item['candidate_score'],item['native_score'],'diff',item['q_differences'],item['k_differences'])
 for label,case in item['cases'].items():print(label,case['fp64_diagnostic'],case['direct_bf16_of_fp64_diagnostic'],[(v['partition'],v['lanes'],v['scaled_bf16']) for v in case['variations'] if v['bias']=='after_completed_reduction'])
