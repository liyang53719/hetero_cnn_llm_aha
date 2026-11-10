"""Bind full profile1 M128 original Host program to trained L0 inputs.
Only readonly source allocations are initialized. No normalized/projection/Conv
or reference intermediate is accepted. Does not execute or qualify hardware.
"""
from pathlib import Path
import json,hashlib,argparse,numpy as np
import emit_cold128_programs as program
PINS={'emit_cold128_programs.py':'ef33463e26a09d7e49e8e583612cb32d4c390379e73cc05c5ba1fe426568989e','attention_moe_policies.py':'7f5dca906595ff8f3c8b9df69966c844ffd855b8b56de3b831b8f5411917cb57','layer0_payload_pin.json':'80352cc5df45472a8867a4e1d346f60dc888e6f89ee191ec35457b484770d9c4'}
MAP={'input_gamma':'input_layernorm.weight','post_gamma':'post_attention_layernorm.weight','qkv_weight':'linear_attn.in_proj_qkv.weight','z_weight':'linear_attn.in_proj_z.weight','conv_weight':'linear_attn.conv1d.weight','a_log':'linear_attn.A_log','dt_bias':'linear_attn.dt_bias','gated_gamma':'linear_attn.norm.weight','o_weight':'linear_attn.out_proj.weight','gate_weight':'mlp.gate_proj.weight','up_weight':'mlp.up_proj.weight','down_weight':'mlp.down_proj.weight'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def transpose(raw,shape):
 if len(shape)!=2 or len(raw)!=np.prod(shape)*2:raise ValueError('BF16 matrix geometry')
 return np.frombuffer(raw,dtype='<u2').reshape(shape).T.copy().tobytes()
def ab(a,b):
 if len(a)!=16*1024*2 or len(b)!=len(a):raise ValueError('AB geometry')
 # Runtime RawPrep reads first16 A then16 B, per token.
 return np.concatenate([np.frombuffer(a,dtype='<u2').reshape(16,1024),np.frombuffer(b,dtype='<u2').reshape(16,1024)],axis=0).T.copy().tobytes()
def bind(payload,input_file,out):
 here=Path(__file__).parent
 for name,digest in PINS.items():
  if sha(here/name)!=digest:raise ValueError('source pin mismatch '+name)
 pin=json.loads((here/'layer0_payload_pin.json').read_text());specs={t['local_name']:t for t in pin['tensors']}
 raws={}
 for name,t in specs.items():
  f=payload/(name+'.bin')
  if f.stat().st_size!=t['bytes'] or sha(f)!=t['sha256']:raise ValueError('trained payload mismatch '+name)
  raws[name]=f.read_bytes()
 x=input_file.read_bytes()
 if len(x)!=128*1024*2:raise ValueError('input must be raw BF16 M128 H1024')
 if np.any((np.frombuffer(x,dtype='<u2')&0x7f80)==0x7f80):raise ValueError('nonfinite input')
 builder,_=program.common(1);cb,db,m=builder.finish()
 if m['launch']['profileId']!=1 or m['tokens']!=128:raise ValueError('runtime shape')
 bound={'input':x,'ab_weight':ab(raws['linear_attn.in_proj_a.weight'],raws['linear_attn.in_proj_b.weight'])}
 for target,source in MAP.items():
  data=raws[source]
  if target.endswith('_weight') and target!='conv_weight':data=transpose(data,specs[source]['shape'])
  bound[target]=data
 for name in ['history_in','state_in']:bound[name]=bytes(m['tensors'][name]['bytes'])
 readonly={n for n,t in m['tensors'].items() if t['readonly']}
 if set(bound)!=readonly:raise ValueError('source coverage differs '+str(set(bound)^readonly))
 for name,data in bound.items():
  if len(data)!=m['tensors'][name]['bytes']:raise ValueError('allocation size differs '+name)
 out.mkdir(parents=True,exist_ok=False);(out/'commands.bin').write_bytes(cb);(out/'descriptors.bin').write_bytes(db)
 segments=[]
 for name,data in bound.items():
  f=out/(name+'.bin');f.write_bytes(data);t=m['tensors'][name]
  segments.append(dict(name=name,file=f.name,address=t['address'],bytes=len(data),sha256=sha(f),dtype=t['dtype'],dims=t['dims'],source='caller_hidden_input' if name=='input' else 'cold_zero_state' if name in ('history_in','state_in') else 'pinned_trained_parameter'))
 m.update(status='PASS_READONLY_BINDING_ONLY_NOT_HARDWARE',weights_materialized=True,segments=segments,input_sha256=sha(input_file),model_revision=pin['revision'],hardware_executed=False,full_block_pass=False,full4096_hardware_proven=False)
 m['sha256']={'commands':sha(out/'commands.bin'),'descriptors':sha(out/'descriptors.bin')}
 (out/'BINDING.json').write_text(json.dumps(m,indent=2)+'\n');return m
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ('payload','input','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();print(json.dumps(bind(a.payload,a.input,a.output),indent=2))
