"""Bind full profile2 M128 original Host program to trained L3 inputs.
Only readonly source allocations are initialized. No normalized/projection/Conv
or reference intermediate is accepted. Does not execute or qualify hardware.
"""
from pathlib import Path
import json,hashlib,argparse,numpy as np
import emit_cold128_programs as program
TRIG_PIN='1156df1551f166fe3f816547b6a15eac1c2ff994683138d5276d2f64c68aa9bb' # official pinned methods, Torch2.10 CPU DEFAULT capture
PINS={'emit_cold128_programs.py':'ef33463e26a09d7e49e8e583612cb32d4c390379e73cc05c5ba1fe426568989e','attention_moe_policies.py':'7f5dca906595ff8f3c8b9df69966c844ffd855b8b56de3b831b8f5411917cb57','layer3_payload_pin.json':'ab9735a92f3b3377737288621019bccd855a5696bd4d02b2d8257cbf24a5b0ac'}
MAP={'input_gamma':'input_layernorm.weight','post_gamma':'post_attention_layernorm.weight','q_weight':'self_attn.q_proj.weight','k_weight':'self_attn.k_proj.weight','v_weight':'self_attn.v_proj.weight','q_gamma':'self_attn.q_norm.weight','k_gamma':'self_attn.k_norm.weight','o_weight':'self_attn.o_proj.weight','gate_weight':'mlp.gate_proj.weight','up_weight':'mlp.up_proj.weight','down_weight':'mlp.down_proj.weight'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def transpose(raw,shape):
 if len(shape)!=2 or len(raw)!=np.prod(shape)*2:raise ValueError('BF16 matrix geometry')
 return np.frombuffer(raw,dtype='<u2').reshape(shape).T.copy().tobytes()
def bind(payload,input_file,trig_file,out):
 here=Path(__file__).parent
 for name,digest in PINS.items():
  if sha(here/name)!=digest:raise ValueError('source pin mismatch '+name)
 pin=json.loads((here/'layer3_payload_pin.json').read_text());specs={t['local_name']:t for t in pin['tensors']}
 raws={}
 for name,t in specs.items():
  f=payload/(name+'.bin')
  if f.stat().st_size!=t['bytes'] or sha(f)!=t['sha256']:raise ValueError('trained payload mismatch '+name)
  raws[name]=f.read_bytes()
 x=input_file.read_bytes()
 if len(x)!=128*1024*2:raise ValueError('input must be raw BF16 M128 H1024')
 if np.any((np.frombuffer(x,dtype='<u2')&0x7f80)==0x7f80):raise ValueError('nonfinite input')
 builder,_=program.common(2);cb,db,m=builder.finish()
 if m['launch']['profileId']!=2 or m['tokens']!=128:raise ValueError('runtime shape')
 trig=trig_file.read_bytes()
 if len(trig)!=128*64*2:raise ValueError('trig must be BF16 cos32/sin32 rows')
 if np.any((np.frombuffer(trig,dtype='<u2')&0x7f80)==0x7f80):raise ValueError('nonfinite trig')
 bound={'input':x,'trig':trig}
 for target,source in MAP.items():
  data=raws[source]
  if target.endswith('_weight') and target!='conv_weight':data=transpose(data,specs[source]['shape'])
  bound[target]=data
 readonly={n for n,t in m['tensors'].items() if t['readonly']}
 if set(bound)!=readonly:raise ValueError('source coverage differs '+str(set(bound)^readonly))
 for name,data in bound.items():
  if len(data)!=m['tensors'][name]['bytes']:raise ValueError('allocation size differs '+name)
 out.mkdir(parents=True,exist_ok=False);(out/'commands.bin').write_bytes(cb);(out/'descriptors.bin').write_bytes(db)
 segments=[]
 for name,data in bound.items():
  f=out/(name+'.bin');f.write_bytes(data);t=m['tensors'][name]
  segments.append(dict(name=name,file=f.name,address=t['address'],bytes=len(data),sha256=sha(f),dtype=t['dtype'],dims=t['dims'],source='caller_hidden_input' if name=='input' else ('official_torch210_default_trig_capture' if sha(trig_file)==TRIG_PIN else 'caller_trig_requires_reference_contract_validation') if name=='trig' else 'pinned_trained_parameter'))
 m.update(status='PASS_COMPLETE_READONLY_BINDING_NOT_HARDWARE' if sha(trig_file)==TRIG_PIN else 'TEMP_COMPLETE_READONLY_BINDING_TRIG_CONTRACT_UNVALIDATED',weights_materialized=True,segments=segments,input_sha256=sha(input_file),model_revision=pin['revision'],trig_sha256=sha(trig_file),trig_contract_validated=sha(trig_file)==TRIG_PIN,hardware_executed=False,full_block_pass=False,full4096_hardware_proven=False)
 m['sha256']={'commands':sha(out/'commands.bin'),'descriptors':sha(out/'descriptors.bin')}
 (out/'BINDING.json').write_text(json.dumps(m,indent=2)+'\n');return m
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ('payload','input','trig','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();print(json.dumps(bind(a.payload,a.input,a.trig,a.output),indent=2))
