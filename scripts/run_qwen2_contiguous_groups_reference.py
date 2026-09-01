#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from transformers.masking_utils import create_causal_mask
REV='ba1cf1846d7df0a0591d6c00649f57e798519da8';MODEL_SHA='302e327795994403cb1e3cb6a3345c76b246b894d14078c936b570c83a4e9057'
def file_sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def tsha(t):return hashlib.sha256(t.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sequence',type=int,default=1024);a=p.parse_args()
 if file_sha(a.model/'model.safetensors')!=MODEL_SHA:raise SystemExit('model hash')
 torch.manual_seed(0);torch.set_num_threads(8);torch.set_num_interop_threads(1);tok=AutoTokenizer.from_pretrained(a.model,local_files_only=True);base=tok.encode('Qwen2 hardware payload checkpoints: deterministic continuous prefill. ',add_special_tokens=False);ids=(base*((a.sequence+len(base)-1)//len(base)))[:a.sequence];input_ids=torch.tensor([ids],dtype=torch.long);model=AutoModelForCausalLM.from_pretrained(a.model,dtype=torch.bfloat16,attn_implementation='eager',local_files_only=True);model.eval();core=model.model
 with torch.inference_mode():
  hidden=core.embed_tokens(input_ids);cache_position=torch.arange(a.sequence);position_ids=cache_position.unsqueeze(0);mask=create_causal_mask(config=core.config,input_embeds=hidden,attention_mask=None,cache_position=cache_position,past_key_values=None,position_ids=position_ids);position_embeddings=core.rotary_emb(hidden,position_ids);starts=[];ends=[];begin=time.monotonic()
  for li,layer in enumerate(core.layers):
   if li%4==0:starts.append(hidden.detach().clone())
   hidden=layer(hidden,attention_mask=mask,use_cache=False,cache_position=cache_position,position_embeddings=position_embeddings)
   if li%4==3:ends.append(hidden.detach().clone())
  baseline_seconds=time.monotonic()-begin;groups=[]
  for group in range(7):
   h=starts[group].clone();start_hash=tsha(h);begin=time.monotonic()
   for li in range(group*4,group*4+4):h=core.layers[li](h,attention_mask=mask,use_cache=False,cache_position=cache_position,position_embeddings=position_embeddings)
   elapsed=time.monotonic()-begin;end_hash=tsha(h);expected_hash=tsha(ends[group]);groups.append({'group':group,'layers':[group*4,group*4+3],'start_hidden_sha256':start_hash,'output_sha256':end_hash,'expected_sha256':expected_hash,'bit_exact':bool(torch.equal(h,ends[group])),'reference_hidden_injections_inside_group':0,'elapsed_seconds':elapsed})
 final=core.norm(hidden);result={'schema_version':1,'status':'PASS_7_CONTIGUOUS_REFERENCE_GROUPS'if all(x['bit_exact']for x in groups)else'FAIL','evidence_class':'exact_revision_reference_continuity_not_RTL_payload','model':'Qwen/Qwen2-1.5B-Instruct','revision':REV,'model_safetensors_sha256':MODEL_SHA,'sequence':a.sequence,'groups':groups,'group_count':7,'layers_covered':28,'reference_hidden_injections_inside_groups':0,'baseline_unormalized_final_sha256':tsha(hidden),'final_rmsnorm_sha256':tsha(final),'baseline_seconds':baseline_seconds,'non_claim':'PyTorch continuity proves checkpoint grouping but not RTL payload datapath execution'};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':result['status'],'groups':7,'layers':28,'all_bit_exact':all(x['bit_exact']for x in groups),'final_sha256':result['final_rmsnorm_sha256']},sort_keys=True));raise SystemExit(0 if result['status'].startswith('PASS')else 1)
if __name__=='__main__':main()
