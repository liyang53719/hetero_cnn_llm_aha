#!/usr/bin/env python3
"""Execute the frozen Qwen2 first-four-layer reference and last-token LM head."""
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

REVISION='ba1cf1846d7df0a0591d6c00649f57e798519da8'
MODEL_SHA='302e327795994403cb1e3cb6a3345c76b246b894d14078c936b570c83a4e9057'
CONFIG_SHA='a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136'
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def tensor_sha(t):return hashlib.sha256(t.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--vectors',type=Path);p.add_argument('--sequence',type=int,default=1024);a=p.parse_args()
 if sha_file(a.model/'model.safetensors')!=MODEL_SHA:raise SystemExit('model hash mismatch')
 if sha_file(a.model/'config.json')!=CONFIG_SHA:raise SystemExit('config hash mismatch')
 torch.manual_seed(0);torch.set_num_threads(8);torch.set_num_interop_threads(1)
 tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
 base=tokenizer.encode('Qwen2 hardware reference trace: deterministic four-layer prefill. ',add_special_tokens=False)
 ids=(base*((a.sequence+len(base)-1)//len(base)))[:a.sequence]
 input_ids=torch.tensor([ids],dtype=torch.long)
 started=time.monotonic()
 model=AutoModelForCausalLM.from_pretrained(a.model,torch_dtype=torch.bfloat16,attn_implementation='eager',local_files_only=True)
 model.model.layers=torch.nn.ModuleList(list(model.model.layers[:4]));model.eval()
 load_seconds=time.monotonic()-started;run_started=time.monotonic()
 with torch.inference_mode():out=model(input_ids=input_ids,use_cache=False,output_hidden_states=True,return_dict=True,logits_to_keep=1)
 run_seconds=time.monotonic()-run_started
 hs=list(out.hidden_states);logits=out.logits
 argmax=int(logits[0,-1].argmax());sample_indices=[argmax]+[(i*941+17)%151936 for i in range(1,160)]
 if len(set(sample_indices))!=160:raise SystemExit('sample index collision')
 if a.vectors:
  a.vectors.mkdir(parents=True,exist_ok=True);hidden=hs[-1][0,-1].contiguous();weight=model.lm_head.weight[sample_indices].contiguous()
  (a.vectors/'hidden_bf16.memh').write_text(''.join(f'{int(v):04x}\n'for v in hidden.view(torch.uint16).cpu().tolist()))
  wb=weight.view(torch.uint16).cpu();(a.vectors/'weights_bf16.memh').write_text(''.join(f'{int(wb[s,k]):04x}\n'for k in range(1536)for s in range(160)))
  sampled=logits[0,-1,sample_indices].float().cpu();(a.vectors/'expected.json').write_text(json.dumps({'indices':sample_indices,'values':[float(v)for v in sampled],'argmax_token':argmax},indent=2)+'\n')
 result={'schema_version':1,'status':'PASS_REFERENCE','evidence_class':'official_weight_PyTorch_reference_not_RTL_E2','model':'Qwen/Qwen2-1.5B-Instruct','revision':REVISION,'sequence':a.sequence,'layers':4,'dtype':'bfloat16','attention':'eager_causal','input_token_sha256':tensor_sha(input_ids),'input_token_count':input_ids.numel(),'hidden_state_count':len(hs),'hidden_state_sha256':[tensor_sha(x)for x in hs],'final_hidden_sha256':tensor_sha(hs[-1]),'last_token_logits_shape':list(logits.shape),'last_token_logits_sha256':tensor_sha(logits),'argmax_token':argmax,'finite_logits':bool(torch.isfinite(logits.float()).all()),'sample_count':160,'sample_indices_sha256':hashlib.sha256(json.dumps(sample_indices,separators=(',',':')).encode()).hexdigest(),'model_safetensors_sha256':MODEL_SHA,'config_sha256':CONFIG_SHA,'load_seconds':load_seconds,'run_seconds':run_seconds,'torch_version':torch.__version__}
 if result['last_token_logits_shape']!=[1,1,151936]or not result['finite_logits']or len(hs)<5:raise SystemExit(f'reference shape failure:{result}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':result['status'],'sequence':a.sequence,'layers':4,'logits_sha256':result['last_token_logits_sha256'],'argmax_token':result['argmax_token'],'run_seconds':run_seconds},sort_keys=True))
if __name__=='__main__':main()
