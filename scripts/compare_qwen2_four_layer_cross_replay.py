#!/usr/bin/env python3
from __future__ import annotations
import argparse,ctypes,hashlib,json,math,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--expected',type=Path,required=True);p.add_argument('--rms',type=Path,required=True);p.add_argument('--matrix',type=Path,required=True);p.add_argument('--weights',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--threshold',type=float,default=.002);a=p.parse_args();e=json.loads(a.expected.read_text())
def f32(u):return struct.unpack('<f',struct.pack('<I',u))[0]
def bf16f(u):return f32(u<<16)
def bf16_rne(u):
 hi=u>>16;lo=u&0xffff
 if lo>0x8000 or(lo==0x8000 and hi&1):hi=(hi+1)&0xffff
 return hi
rms_bits=[int(x,16)for x in a.rms.read_text().split()];matrix_bits=[int(x,16)for x in a.matrix.read_text().split()];weights=[int(x,16)for x in a.weights.read_text().split()]
if len(rms_bits)!=7680 or len(matrix_bits)!=160 or len(weights)!=1536*160:raise SystemExit(f'counts rms={len(rms_bits)} matrix={len(matrix_bits)} weights={len(weights)}')
rms_values=[f32(x)for x in rms_bits];rms_errors=[abs(x-y)for x,y in zip(rms_values,e['rms_fp32_values'])];rms_bf=[bf16_rne(x)for x in rms_bits];model_rms=[int(x,16)for x in e['rms_bf16_bits']]
libm=ctypes.CDLL('libm.so.6');fmaf=libm.fmaf;fmaf.argtypes=[ctypes.c_float]*3;fmaf.restype=ctypes.c_float
gold=[]
for s in range(160):
 acc=ctypes.c_float(0.0)
 for k in range(1536):acc=ctypes.c_float(fmaf(ctypes.c_float(bf16f(rms_bf[(s//32)*1536+k])),ctypes.c_float(bf16f(weights[k*160+s])),acc))
 gold.append(acc.value)
matrix_values=[f32(x)for x in matrix_bits];matrix_errors=[abs(x-y)for x,y in zip(matrix_values,gold)];matrix_bf=[bf16_rne(x)for x in matrix_bits];model_matrix=[int(x,16)for x in e['matrix_bf16_bits']];ulp_rms=[abs(x-y)for x,y in zip(rms_bf,model_rms)];ulp_matrix=[abs(x-y)for x,y in zip(matrix_bf,model_matrix)]
finite=all(math.isfinite(x)for x in rms_values+matrix_values);status='PASS'if finite and max(rms_errors)<=a.threshold and max(matrix_errors)<=a.threshold and max(ulp_rms)<=1 and max(ulp_matrix)<=1 else'FAIL'
r={'schema_version':1,'status':status,'evidence_class':'official_weight_reference_anchored_cross_layer_RTL_E2','nodes':e['nodes'],'layers':4,'threshold':a.threshold,'rms':{'count':7680,'fp32_max_absolute_error':max(rms_errors),'bf16_model_bit_exact':sum(x==y for x,y in zip(rms_bf,model_rms)),'bf16_model_max_ulp':max(ulp_rms),'actual_sha256':hashlib.sha256(a.rms.read_bytes()).hexdigest()},'matrix':{'count':160,'operator_golden':'libm_fmaf_over_RTL_RMS_BF16_boundary','fp32_bit_exact':sum(struct.pack('<f',x)==struct.pack('<f',y)for x,y in zip(matrix_values,gold)),'fp32_max_absolute_error':max(matrix_errors),'bf16_model_bit_exact':sum(x==y for x,y in zip(matrix_bf,model_matrix)),'bf16_model_max_ulp':max(ulp_matrix),'actual_sha256':hashlib.sha256(a.matrix.read_bytes()).hexdigest()},'finite':finite,'backpressure':'deterministic_random_ready','boundary_policy':'0.002 applies to FP32 operator values; BF16 model boundary additionally requires <=1 ULP','non_claim':'reference hidden snapshots anchor each layer; this is not a full q1024 payload RTL run'}
a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':status,'rms':r['rms'],'matrix':r['matrix']},sort_keys=True));raise SystemExit(0 if status=='PASS'else 1)
