"""Bind verified trained FP32 tensors to existing 21-op Host input layout.
No DUT inputs are synthesized from intermediate references. Does NOT execute
hardware or qualify a unified five-profile RTL. Data outputs must stay local.
"""
from pathlib import Path
import argparse,hashlib,json,importlib.util,numpy as np
MAPPING={'wq':'self_attn.q_proj.weight','wk':'self_attn.k_proj.weight','wv':'self_attn.v_proj.weight','wo':'self_attn.o_proj.weight','wg':'mlp.gate_proj.weight','wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight','gamma0':'input_layernorm.weight','gamma1':'post_attention_layernorm.weight','bq':'self_attn.q_proj.bias','bk':'self_attn.k_proj.bias','bv':'self_attn.v_proj.bias','x':'input.tokens_0_127'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def transpose_words(raw,shape):
 if len(shape)!=2 or len(raw)!=shape[0]*shape[1]*4:raise ValueError('matrix geometry/bytes')
 return np.frombuffer(raw,dtype='<u4').reshape(shape).T.copy().tobytes()
def prepare(payload,summary,packer,shape_header,out):
 j=json.loads(summary.read_text());specs={x['name']:x for x in j['tensors']}
 if j['tokens']!=128 or j['revision']!='ba1cf1846d7df0a0591d6c00649f57e798519da8':raise ValueError('input revision/token mismatch')
 for name in MAPPING.values():
  p=payload/(name+'.f32le');t=specs[name]
  if p.stat().st_size!=t['bytes'] or sha(p)!=t['sha256']:raise ValueError('unverified payload '+name)
 # Import original descriptor encoder without modifying it.
 spec=importlib.util.spec_from_file_location('original_owner_packer',packer);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 shape={k:int(v) for k,v in m.re.findall(r'constexpr int (\w+)=(\d+);',shape_header.read_text())}
 if {k:shape[k] for k in ('H','F','HEADS','KVHEADS','HD')}!={'H':1536,'F':8960,'HEADS':12,'KVHEADS':2,'HD':128}:raise ValueError('not complete Qwen2 geometry')
 manifest=m.pack(shape,128,out)
 records=[]
 for target,source in MAPPING.items():
  t=specs[source];raw=(payload/(source+'.f32le')).read_bytes()
  data=transpose_words(raw,t['shape']) if target.startswith('w') else raw
  tensor=manifest['tensors'][target]
  if len(data)!=tensor['words']*4:raise ValueError('Host allocation differs: '+target)
  f=out/(target+'.f32le');f.write_bytes(data)
  if target.startswith('w') and transpose_words(data,list(reversed(t['shape'])))!=raw:raise ValueError('transpose not reversible')
  records.append(dict(name=target,source=source,address=tensor['address'],bytes=len(data),sha256=sha(f),transpose=target.startswith('w')))
 manifest['scope'].update(synthetic_weights=False,trained_input_bytes_bound=True,hardware_executed=False)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 result=dict(status='PASS_INPUT_BINDING_ONLY',tokens=128,revision=j['revision'],layers=1,weights_real=True,fp32_storage=True,shape=shape,records=records,packer_sha256=sha(packer),host_commands_sha256=sha(out/'host_commands.bin'),host_descriptors_sha256=sha(out/'host_descriptors.bin'),hardware_executed=False,python_forward_executed=False,unified_hardware_verified=False)
 (out/'REAL_INPUT_BINDING.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ('payload','summary','packer','shape-header','output'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();print(json.dumps(prepare(a.payload,a.summary,a.packer,a.shape_header,a.output),indent=2))
