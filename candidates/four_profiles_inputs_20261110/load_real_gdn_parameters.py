"""Validated trained Conv4/RawPrep parameters for existing original owner fixture.
Does not supply Dense results, alter DUT, execute hardware, or claim full block.
"""
from pathlib import Path
import json,hashlib,numpy as np
PIN_SHA='80352cc5df45472a8867a4e1d346f60dc888e6f89ee191ec35457b484770d9c4'
def load(root,payload):
 root=Path(root);payload=Path(payload)
 raw=(root/'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=PIN_SHA:raise ValueError('immutable parameter pin mismatch')
 pin=json.loads(raw);specs={t['local_name']:t for t in pin['tensors']}
 arrays=[]
 for name,dtype,shape in [('linear_attn.conv1d.weight','<u2',(6144,1,4)),('linear_attn.A_log','<f4',(16,)),('linear_attn.dt_bias','<u2',(16,))]:
  t=specs[name];raw=(payload/(name+'.bin')).read_bytes()
  if len(raw)!=t['bytes'] or hashlib.sha256(raw).hexdigest()!=t['sha256'] or t['shape']!=list(shape):raise ValueError('parameter bytes/shape mismatch: '+name)
  arrays.append(np.frombuffer(raw,dtype=dtype).reshape(shape).copy())
 return arrays[0].reshape(6144,4),arrays[1],arrays[2]
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--payload',type=Path,required=True);a=p.parse_args()
 arrays=load(a.root,a.payload)
 print(json.dumps({'status':'PASS_PARAMETERS_BYTES_ONLY','parameters':[{'shape':list(x.shape),'dtype':str(x.dtype),'sha256':hashlib.sha256(x.tobytes()).hexdigest()} for x in arrays],'hardware_executed':False,'full_block_pass':False},indent=2))
