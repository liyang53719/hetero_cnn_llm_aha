#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--expected',type=Path,required=True);p.add_argument('--actual',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--threshold',type=float,default=0.002);a=p.parse_args()
e=json.loads(a.expected.read_text());bits=[int(x,16)for x in a.actual.read_text().split()];raw_values=[struct.unpack('>f',struct.pack('>I',x))[0]for x in bits]
def bf16_rne(u):
 hi=u>>16;lo=u&0xffff
 if lo>0x8000 or(lo==0x8000 and hi&1):hi=(hi+1)&0xffff
 return hi
values=[struct.unpack('>f',struct.pack('>I',bf16_rne(x)<<16))[0]for x in bits]
if len(values)!=160 or len(e['values'])!=160:raise SystemExit(f'sample count actual={len(values)} expected={len(e["values"])}')
errors=[abs(x-y)for x,y in zip(values,e['values'])];raw_errors=[abs(x-y)for x,y in zip(raw_values,e['values'])];finite=all(math.isfinite(x)for x in values);mx=max(errors);mi=errors.index(mx);rtl_argmax=e['indices'][max(range(160),key=lambda i:values[i])]
r={'schema_version':1,'status':'PASS'if finite and mx<=a.threshold else'FAIL','evidence_class':'official_weight_sampled_Revision8B_B_RTL_E2','tensor_boundary':'FP32 accumulator to BF16 RNE output','samples':160,'contexts':5,'array_steps':7680,'threshold':a.threshold,'max_absolute_error':mx,'raw_fp32_accumulator_max_difference_from_bf16_reference':max(raw_errors),'bit_exact_samples':sum(x==0 for x in errors),'max_error_sample':mi,'max_error_vocab_index':e['indices'][mi],'reference_argmax_token':e['argmax_token'],'sampled_rtl_argmax_token':rtl_argmax,'finite':finite,'actual_fp32_bits':[f'{x:08x}'for x in bits],'actual_bf16_bits':[f'{bf16_rne(x):04x}'for x in bits]}
a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({k:r[k]for k in('status','samples','max_absolute_error','max_error_vocab_index','reference_argmax_token','sampled_rtl_argmax_token')},sort_keys=True));raise SystemExit(0 if r['status']=='PASS'else 1)
