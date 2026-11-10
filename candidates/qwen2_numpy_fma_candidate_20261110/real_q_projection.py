"""Actual M128 full Q projection reference ONLY: exact RMS then candidate Dense.
Local output data not included in source delivery or Git.
"""
import sys,pathlib,json,hashlib,time,os
import numpy as np
p=pathlib.Path(__file__).resolve().parent;root=p.parents[1]
sys.path.insert(0,str(p.parent/'legacy_python'))
import operators as ops
from legacy_reference import Budget
from candidate import dense
payload=root/'round_20261110T0733/qwen2_host_payload';records=json.loads((payload/'REAL_INPUT_BINDING.json').read_text())['records'];pins={}
for name in ['x','gamma0','wq']:
 f=payload/(name+'.f32le');entry=next(x for x in records if x['name']==name);sha=hashlib.sha256(f.read_bytes()).hexdigest()
 if sha!=entry['sha256'] or f.stat().st_size!=entry['bytes']:raise ValueError('input pin '+name)
 pins[name]=sha
x=np.memmap(payload/'x.f32le',dtype='<u4',mode='r',shape=(128,1536));gamma=np.memmap(payload/'gamma0.f32le',dtype='<u4',mode='r',shape=(1536,));w=np.memmap(payload/'wq.f32le',dtype='<u4',mode='r',shape=(1536,1536))
(p/'RUN_IDENTITY.json').write_text(json.dumps(dict(pid=os.getpid(),boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),start_ticks=pathlib.Path('/proc/self/stat').read_text().split()[21],scope='bounded180s Python reference RMS+Dense only')))
t=time.monotonic();budget=Budget(2000000);norm=ops.rms(x,gamma,budget);rms_seconds=time.monotonic()-t
print('RMS_REFERENCE_COMPLETE',rms_seconds,flush=True)
t=time.monotonic();q=dense(norm,w);dense_seconds=time.monotonic()-t
# Spot-check full 1536-term columns against Fraction, not just truncated K.
from legacy_reference import dense as exact_dense
coords=[(0,0),(0,1535),(63,777),(127,1535)];checks=[]
for row,col in coords:
 exact=exact_dense(norm[row:row+1],w[:,col:col+1],Budget(1536))
 if int(exact[0,0])!=int(q[row,col]):raise ValueError('Fraction full-K disagreement')
 checks.append(dict(row=row,col=col,word=int(exact[0,0])))
norm.astype('<u4').tofile(p/'norm0.local.f32');q.astype('<u4').tofile(p/'q0.local.f32')
report=dict(status='EXECUTED_REFERENCE_ONLY',scope='actual M128 Legacy RMS + complete Q Dense, no bias/RoPE/rest of block, no Chisel or RTL',pins=pins,shape=dict(M=128,K=1536,N=1536),macs=128*1536*1536,rms_seconds=rms_seconds,dense_seconds=dense_seconds,rms_scalar_ops=2000000-budget.remaining,norm_sha256=hashlib.sha256(norm.astype('<u4').tobytes()).hexdigest(),q_sha256=hashlib.sha256(q.astype('<u4').tobytes()).hexdigest(),fraction_full_k_checks=checks,full_block_hardware_pass=0)
(p/'REAL_Q_RESULT.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
