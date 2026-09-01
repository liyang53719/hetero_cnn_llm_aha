#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
REV='ba1cf1846d7df0a0591d6c00649f57e798519da8';MODEL_SHA='302e327795994403cb1e3cb6a3345c76b246b894d14078c936b570c83a4e9057'
PHASES=('input_norm','qkv_projection','attention','post_attention_norm','mlp_gate_up','mlp_down')
def file_sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def bits(t):return [f'{int(v):04x}'for v in t.detach().contiguous().view(torch.uint16).cpu().tolist()]
def sample(v,idx):return v[0,-1,idx].contiguous()
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sequence',type=int,default=1024);a=p.parse_args()
 if file_sha(a.model/'model.safetensors')!=MODEL_SHA:raise SystemExit('model hash')
 torch.manual_seed(0);torch.set_num_threads(8);torch.set_num_interop_threads(1);tok=AutoTokenizer.from_pretrained(a.model,local_files_only=True);base=tok.encode('Qwen2 hardware payload checkpoints: deterministic continuous prefill. ',add_special_tokens=False);ids=(base*((a.sequence+len(base)-1)//len(base)))[:a.sequence];input_ids=torch.tensor([ids],dtype=torch.long)
 model=AutoModelForCausalLM.from_pretrained(a.model,dtype=torch.bfloat16,attn_implementation='eager',local_files_only=True);model.eval();records=[];cache={};handles=[]
 def indices(width,layer,salt,count=64):return [((i*97)+(layer*131)+salt)%width for i in range(count)]
 def add(layer,phase,tensor,width,values,idx):
  b=bits(sample(values,idx));records.append({'layer':layer,'phase':phase,'tensor':tensor,'shape':[1,a.sequence,width],'dtype':'bfloat16','stride':'contiguous_last_token_sample','sample_indices':idx,'sample_bf16_bits':b,'sample_sha256':hashlib.sha256(bytes.fromhex(''.join(b))).hexdigest(),'continuity_group':layer//4})
 for li,layer in enumerate(model.model.layers):
  handles.append(layer.input_layernorm.register_forward_hook(lambda _m,_i,o,li=li:add(li,'input_norm','norm_out',1536,o,indices(1536,li,11))))
  handles.append(layer.self_attn.q_proj.register_forward_hook(lambda _m,_i,o,li=li:cache.__setitem__((li,'q'),o.detach())))
  handles.append(layer.self_attn.k_proj.register_forward_hook(lambda _m,_i,o,li=li:cache.__setitem__((li,'k'),o.detach())))
  handles.append(layer.self_attn.v_proj.register_forward_hook(lambda _m,_i,o,li=li:cache.__setitem__((li,'v'),o.detach())))
  def attn_hook(_m,_i,o,li=li):
   q,k,v=cache.pop((li,'q')),cache.pop((li,'k')),cache.pop((li,'v'));qi=indices(1536,li,17,32);ki=indices(256,li,23,16);vi=indices(256,li,29,16);vals=torch.cat((sample(q,qi),sample(k,ki),sample(v,vi)));b=bits(vals);records.append({'layer':li,'phase':'qkv_projection','tensor':'qkv_out','shape':[1,a.sequence,2048],'dtype':'bfloat16','stride':'q32_k16_v16_last_token_sample','sample_indices':{'q':qi,'k':ki,'v':vi},'sample_bf16_bits':b,'sample_sha256':hashlib.sha256(bytes.fromhex(''.join(b))).hexdigest(),'continuity_group':li//4});ao=o[0]if isinstance(o,tuple)else o;add(li,'attention','attention_out',1536,ao,indices(1536,li,31))
  handles.append(layer.self_attn.register_forward_hook(attn_hook))
  handles.append(layer.post_attention_layernorm.register_forward_hook(lambda _m,_i,o,li=li:add(li,'post_attention_norm','post_norm_out',1536,o,indices(1536,li,37))))
  handles.append(layer.mlp.gate_proj.register_forward_hook(lambda _m,_i,o,li=li:cache.__setitem__((li,'gate'),o.detach())))
  handles.append(layer.mlp.up_proj.register_forward_hook(lambda _m,_i,o,li=li:cache.__setitem__((li,'up'),o.detach())))
  def layer_hook(_m,_i,o,li=li,layer=layer):
   gate,up=cache.pop((li,'gate')),cache.pop((li,'up'));idx=indices(8960,li,41);fused=layer.mlp.act_fn(sample(gate,idx))*sample(up,idx);b=bits(fused);records.append({'layer':li,'phase':'mlp_gate_up','tensor':'gate_up_out','shape':[1,a.sequence,8960],'dtype':'bfloat16','stride':'last_token_sample','sample_indices':idx,'sample_bf16_bits':b,'sample_sha256':hashlib.sha256(bytes.fromhex(''.join(b))).hexdigest(),'continuity_group':li//4});hidden=o[0]if isinstance(o,tuple)else o;add(li,'mlp_down','block_out',1536,hidden,indices(1536,li,43))
  handles.append(layer.register_forward_hook(layer_hook))
 start=time.monotonic()
 with torch.inference_mode():model(input_ids=input_ids,use_cache=False,return_dict=True,logits_to_keep=1)
 elapsed=time.monotonic()-start
 for h in handles:h.remove()
 records.sort(key=lambda x:(x['layer'],PHASES.index(x['phase'])));errors=[]
 if len(records)!=168:errors.append('checkpoint_count')
 for layer in range(28):
  if [r['phase']for r in records if r['layer']==layer]!=list(PHASES):errors.append(f'phase_order:{layer}')
 aggregate=hashlib.sha256(''.join(r['sample_sha256']for r in records).encode()).hexdigest();result={'schema_version':1,'status':'PASS_168_OFFICIAL_CHECKPOINTS'if not errors else'FAIL','evidence_class':'exact_revision_official_weight_reference_checkpoints_not_RTL','model':'Qwen/Qwen2-1.5B-Instruct','revision':REV,'model_safetensors_sha256':MODEL_SHA,'sequence':a.sequence,'layers':28,'phases_per_layer':6,'checkpoint_count':len(records),'sample_values':sum(len(r['sample_bf16_bits'])for r in records),'continuity_groups':list(range(7)),'input_token_sha256':hashlib.sha256(input_ids.numpy().tobytes()).hexdigest(),'records':records,'aggregate_sha256':aggregate,'elapsed_seconds':elapsed,'errors':errors,'non_claim':'reference checkpoint capture is not continuous RTL payload evidence'};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':result['status'],'checkpoints':len(records),'samples':result['sample_values'],'sha256':aggregate,'elapsed_seconds':elapsed},sort_keys=True));raise SystemExit(0 if not errors else 1)
if __name__=='__main__':main()
