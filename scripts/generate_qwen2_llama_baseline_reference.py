#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np,torch
from transformers import AutoModelForCausalLM,AutoTokenizer
MODEL_SHA='302e327795994403cb1e3cb6a3345c76b246b894d14078c936b570c83a4e9057';REV='ba1cf1846d7df0a0591d6c00649f57e798519da8'
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);torch.manual_seed(0);torch.set_num_threads(8);torch.set_num_interop_threads(1);tok=AutoTokenizer.from_pretrained(a.model,local_files_only=True);base=tok.encode('Qwen2 hardware payload checkpoints: deterministic continuous prefill. ',add_special_tokens=False);ids=(base*((1024+len(base)-1)//len(base)))[:1024];(a.out/'tokens.txt').write_text(''.join(f'{x}\n'for x in ids));model=AutoModelForCausalLM.from_pretrained(a.model,dtype=torch.bfloat16,attn_implementation='eager',local_files_only=True);model.eval()
 with torch.inference_mode():logits=model(input_ids=torch.tensor([ids]),use_cache=False,return_dict=True,logits_to_keep=1).logits[0,-1].float().cpu().numpy().astype(np.float32)
 logits.tofile(a.out/'pytorch_logits.bin');r={'schema_version':1,'status':'PASS_PYTORCH_Q1024_REFERENCE','model':'Qwen/Qwen2-1.5B-Instruct','revision':REV,'model_safetensors_sha256':MODEL_SHA,'tokens':1024,'layers':28,'vocab':int(logits.size),'argmax':int(logits.argmax()),'tokens_sha256':hashlib.sha256(np.asarray(ids,dtype=np.int32).tobytes()).hexdigest(),'logits_sha256':hashlib.sha256(logits.tobytes()).hexdigest()};(a.out/'pytorch_result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
