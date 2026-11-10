"""Execute pinned official TextRotaryEmbedding default methods on Torch CPU default.
No Transformers replacement: extracts only the three pinned arithmetic methods;
default rope needs no dynamic update. Records this restricted execution scope.
"""
from pathlib import Path
import ast,types,hashlib,json,argparse,os
import torch,numpy as np
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if torch.__version__!='2.10.0+cpu' or os.environ.get('ATEN_CPU_CAPABILITY')!='default':raise ValueError('wrong runtime')
r=a.root/'config/upstream/qwen3_5_0p8b';source=(r/'modeling_qwen3_5.py').read_bytes();cfgraw=(r/'config.json').read_bytes()
if hashlib.sha256(source).hexdigest()!='aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18':raise ValueError('official source pin drift')
if hashlib.sha256(cfgraw).hexdigest()!='b90b86f35c8e6925ef74ee04d0e758f0a845c83a42089ad82bbaa948de9b4204':raise ValueError('config pin drift')
cfg=json.loads(cfgraw)['text_config'];config=types.SimpleNamespace(**cfg)
if config.rope_parameters['rope_type']!='default':raise ValueError('default-only extraction')
klass=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Qwen3_5TextRotaryEmbedding')
names=['compute_default_rope_parameters','forward','recomposition_frequencies'];nodes=[]
for n in klass.body:
 if isinstance(n,ast.FunctionDef) and n.name in names:
  n.decorator_list=[];n.returns=None
  for arg in ast.walk(n):
   if isinstance(arg,ast.arg):arg.annotation=None
  nodes.append(n)
ns={'torch':torch};exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'pinned_official_rotary_methods','exec'),ns)
torch.set_num_threads(1);inv,scale=ns['compute_default_rope_parameters'](config)
self=types.SimpleNamespace(inv_freq=inv,attention_scaling=scale,mrope_section=config.rope_parameters['mrope_section']);self.recomposition_frequencies=types.MethodType(ns['recomposition_frequencies'],self)
positions=torch.arange(128).reshape(1,1,128);x=torch.empty((1,128,1024),dtype=torch.bfloat16)
cos,sin=ns['forward'](self,x,positions)
if not torch.equal(cos[...,:32],cos[...,32:]) or not torch.equal(sin[...,:32],sin[...,32:]):raise ValueError('unexpected recomposition')
trig=torch.cat((cos[0,:,:32],sin[0,:,:32]),dim=-1).contiguous().view(torch.uint16).numpy().astype('<u2');data=trig.tobytes();a.output.write_bytes(data)
old=np.frombuffer(a.candidate.read_bytes(),dtype='<u2').reshape(128,64);bad=np.argwhere(old!=trig)
summary={'status':'PASS_OFFICIAL_METHODS_TORCH210_DEFAULT_TRIG_CAPTURE_ONLY','torch':torch.__version__,'cpu_capability':torch.backends.cpu.get_cpu_capability(),'numpy':np.__version__,'source_sha256':hashlib.sha256(source).hexdigest(),'config_sha256':hashlib.sha256(cfgraw).hexdigest(),'shape':[128,64],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'numpy_candidate_mismatches':len(bad),'first_mismatch':bad[0].tolist() if len(bad) else None,'scope':'three pinned default-RoPE methods; not full official model or Host execution','hardware_executed':False}
print(json.dumps(summary,indent=2))
