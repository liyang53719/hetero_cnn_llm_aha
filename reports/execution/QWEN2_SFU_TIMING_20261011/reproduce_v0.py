#!/usr/bin/env python3
"""Bounded saved-v0 gate branch audit; no model rerun, RTL, or flag oracle."""
import argparse
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np

EXPECTED_RECEIPT='18021a757aef57c94bdbd34a17a899c76df194c0ff32706baa089eefd6a3db6e'
EXPECTED_GATE='288123c170c85a5b47d0d03a0f3c93ff7fdbe6c8014bdc820e910c82a870efb5'
EXPECTED_BYTES=4587520

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--repo',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();root=a.repo.resolve()
 receipt=root/'work/qwen2_block_recipe_m128_release_20261011/RESULT.json'
 gate=receipt.parent/'phase_10_gate_recipe.f32le'
 assert sha(receipt)==EXPECTED_RECEIPT and sha(gate)==EXPECTED_GATE and gate.stat().st_size==EXPECTED_BYTES
 r=json.loads(receipt.read_text());s=next(x for x in r['stages'] if x['name']=='gate')
 assert s['sha256']==EXPECTED_GATE and s['path']==gate.name
 mp=root/'scripts/qwen2_shared_sfu_schedule.py';spec=importlib.util.spec_from_file_location('sfu',mp);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 source_before=sha(mp);pins=m.verify_sources(root);binding=m.timing_binding(root)
 libc=ctypes.CDLL(None);libc.fegetround.restype=ctypes.c_int
 assert libc.fegetround()==0, 'Requires FE_TONEAREST (glibc/Linux value0)'
 v=np.fromfile(gate,dtype='<u4');av=v&0x7fffffff
 assert len(v)==128*8960 and np.all(av<0x42a00000)
 assert np.all(((av>>23)!=0)|((av&0x7fffff)==0)), 'Input must be normal or zero'
 x=av.view('<f4');N=len(v);g=N//16
 indices=np.unique(np.concatenate((np.linspace(0,N-1,64,dtype=np.int64),[np.argmin(av),np.argmax(av)])))
 registers=[dict(gate=int(v[i]),up=m.ONE) for i in indices]
 programs=[m.program(int(v[i])) for i in indices]
 comparisons=0;range_rows=[]
 def audit(name,z,pc):
  nonlocal comparisons
  bits=z.view('<u4');exp=(bits>>23)&255;frac=bits&0x7fffff
  assert np.all(exp!=255)
  assert np.all((exp!=0)|(frac==0)), 'No gradual-underflow/FTZ assumption is permitted'
  for j,idx in enumerate(indices):
   node=programs[j][pc];assert node['name']==name
   aa,bb,expected=m._evaluate(node,registers[j]);m._write(node,registers[j],expected)
   assert int(bits[idx])==expected,(name,int(idx),hex(int(bits[idx])),hex(expected))
   comparisons+=1
  range_rows.append(dict(node=name,minimum=float(np.min(z)),maximum=float(np.max(z)),normal_or_zero=True))
 t=time.monotonic()
 with np.errstate(all='raise'):
  scale=np.multiply(x,np.float32(m.f32_value(m.INV_LN2)),dtype=np.float32);audit('exp_scale',scale,0)
  k=scale.astype(np.uint32)
  assert np.all(k<=115)
  # RecFNToIN round_minMag of finite nonnegative scale, then exact INToRecFN.
  for j,idx in enumerate(indices):
   node=programs[j][1];aa,bb,expected=m._evaluate(node,registers[j]);m._write(node,registers[j],expected)
   assert int(k[idx])==expected;comparisons+=1
  frac=np.add(scale,-k.astype(np.float32),dtype=np.float32);audit('exp_fraction',frac,2)
  assert np.all((frac>=0)&(frac<1))
  h=np.full(N,m.f32_value(m.COEFFICIENTS[7]),dtype=np.float32);pc=3
  for i in range(6,-1,-1):
   product=np.multiply(h,frac,dtype=np.float32);audit('exp_mul_'+str(i),product,pc);pc+=1
   h=np.add(product,np.float32(m.f32_value(m.COEFFICIENTS[i])),dtype=np.float32);audit('exp_add_'+str(i),h,pc);pc+=1
  power=((np.uint32(127)-k)<<np.uint32(23)).view('<f4')
  e=np.multiply(h,power,dtype=np.float32);audit('exp_finish',e,17)
  den=np.add(np.float32(1),e,dtype=np.float32);audit('denominator',den,18)
 db=den.view('<u4');assert np.all((db>=0x3f800000)&(db<=0x40000000))
 d=np.where((db==0x3f800000)|(db==0x40000000),25,26).reshape(g,16)
 assert sha(mp)==source_before
 result=dict(schema_version=1,status='SOURCE_TIMING_BRANCH_AUDIT_OF_SAVED_V0_SOFTWARE_GATES',
  scope=dict(model_rerun=False,rtl=False,hardfloat_flags=False,numerical_acceptance=False,full_cycle_prediction=False),
  source_sha256={**pins,'scripts/qwen2_shared_sfu_schedule.py':source_before},source_timing_binding=binding,
  audit_script_sha256=sha(Path(__file__)),receipt=dict(path=str(receipt.relative_to(root)),sha256=EXPECTED_RECEIPT,status=r['status'],source_identity=r['source_identity']),
  gate=dict(path=str(gate.relative_to(root)),bytes=EXPECTED_BYTES,sha256=EXPECTED_GATE,elements=N,groups=g,all_nonsaturated=True,abs_min=float(np.min(x)),abs_max=float(np.max(x)),bf16_representable=bool(np.all(v&65535==0))),
  method='Explicit NumPy FP32 add/mul nodes, no fused expression; every intermediate is verified normal or zero; integer-RNE program checks every node at 64 evenly spaced indices plus min/max. Only exp7 and denominator are evaluated; no reciprocal or full SiLU output.',
  runtime=dict(python=platform.python_version(),numpy=np.__version__,fegetround=libc.fegetround(),rounding='FE_TONEAREST'),wall_seconds=time.monotonic()-t,
  checked_indices=[int(i) for i in indices],independent_node_checks=comparisons,intermediate_ranges=range_rows,
  denominator=dict(minimum=float(np.min(den)),maximum=float(np.max(den))),
  d25_lane_requests=int(np.sum(d==25)),d26_lane_requests=int(np.sum(d==26)),
  per_divider_service_cycles=[int(z) for z in np.sum(d,axis=0)],
  primitive_service_floor_cycles=int(np.max(np.sum(d,axis=0))),
  wrapper_d26_groups=int(np.sum(np.any(d==26,axis=1))),
  wrapper_arithmetic_edge_span=62*g+int(np.sum(np.any(d==26,axis=1)))-1,
  assumptions=['successful original flag policy','continuously ready arithmetic interface','resident operands; excludes load/store/ACK and owner control'],
  measured_full_block_cycles=None,predicted_full_block_cycles=None)
 a.out.parent.mkdir(parents=True,exist_ok=True)
 with a.out.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps({k:result[k] for k in ('status','independent_node_checks','d25_lane_requests','d26_lane_requests','primitive_service_floor_cycles','wrapper_d26_groups','wrapper_arithmetic_edge_span','wall_seconds')}))
if __name__=='__main__':main()
