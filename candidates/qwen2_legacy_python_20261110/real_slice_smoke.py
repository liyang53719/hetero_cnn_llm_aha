"""Bounded actual-input math exercise, NOT a model stage or hardware comparison."""
import pathlib,json,hashlib,time
import numpy as np
from legacy_reference import dense,Budget
p=pathlib.Path(__file__).resolve().parent;root=p.parents[1]
payload=root/'qwen2_host_payload'
records=json.loads((p.parent/'REAL_INPUT_BINDING.json').read_text())['records']
verified={}
for name in ['x','wq']:
 f=payload/(name+'.f32le');entry=next(x for x in records if x['name']==name)
 sha=hashlib.sha256(f.read_bytes()).hexdigest()
 if sha!=entry['sha256'] or f.stat().st_size!=entry['bytes']:raise ValueError('input identity mismatch: '+name)
 verified[name]=sha
x=np.memmap(payload/'x.f32le',dtype='<u4',mode='r',shape=(128,1536))
w=np.memmap(payload/'wq.f32le',dtype='<u4',mode='r',shape=(1536,1536))
t=time.monotonic();y=dense(x[:1,:16],w[:16,:16],Budget(256))
print(json.dumps({'status':'EXECUTED_BOUNDED_REFERENCE_ONLY','scope':'raw embedding and trained wq slice 1x16x16, NOT RMS output/full Q projection/complete block/hardware comparison','input_hashes':verified,'macs':256,'output_sha256':hashlib.sha256(y.astype('<u4').tobytes()).hexdigest(),'seconds':time.monotonic()-t},indent=2))
