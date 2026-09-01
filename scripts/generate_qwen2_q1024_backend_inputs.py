#!/usr/bin/env python3
import hashlib,json,multiprocessing as mp,sys
from pathlib import Path
import numpy as np,torch
from safetensors import safe_open
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from generate_l5_q128_qkv_batch_vectors import add,bf16_value,mul,reduce16,rsqrt_algorithm
MODEL=ROOT/'work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors';TOKENS=ROOT/'work/results/llama_cpp_qwen2_baseline/tokens.txt';OUT=ROOT/'work/results/qwen2_q1024_backend_inputs';OUT.mkdir(parents=True,exist_ok=True)
def refined(item):
 idx,x=item;total=np.float32(0)
 for ch in range(96):total=add(total,reduce16([mul(v,v)for v in x[ch*16:(ch+1)*16]]))
 me=add(mul(total,np.float32(1/1536)),np.float32(1e-6));first=rsqrt_algorithm(me);inv=mul(first,add(np.float32(1.5),-mul(np.float32(.5),mul(me,mul(first,first)))))
 vals=np.asarray([bf16_value(mul(bf16_value(mul(x[i],inv)),NW[i]))for i in range(1536)],np.float32);bits=(vals.view(np.uint32)>>16).astype(np.uint16);return idx,bits
ids=np.asarray([int(x)for x in TOKENS.read_text().splitlines()],np.int32);assert ids.size==1024 and hashlib.sha256(ids.tobytes()).hexdigest()=='e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628'
with safe_open(MODEL,framework='pt',device='cpu')as f:
 emb=f.get_tensor('model.embed_tokens.weight')[torch.tensor(ids,dtype=torch.long)].float().numpy();NW=f.get_tensor('model.layers.0.input_layernorm.weight').float().numpy()
 for kind in('q','k','v'):
  f.get_tensor(f'model.layers.0.self_attn.{kind}_proj.weight').contiguous().view(torch.uint16).numpy().tofile(OUT/f'{kind}_weight_bf16.bin');f.get_tensor(f'model.layers.0.self_attn.{kind}_proj.bias').float().numpy().astype(np.float32).tofile(OUT/f'{kind}_bias_fp32.bin')
with mp.get_context('fork').Pool(8)as pool:rows=pool.map(refined,list(enumerate(emb)))
norm=np.empty((1024,1536),np.uint16)
for i,row in rows:norm[i]=row
norm.tofile(OUT/'norm_bf16.bin');ids.tofile(OUT/'tokens_i32.bin');manifest=[json.loads(x)for x in(ROOT/'reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl').read_text().splitlines()[:9]];assert [x['operation']for x in manifest]==['l0.input_norm','l0.q','l0.q_bias','l0.q_rope','l0.k','l0.k_bias','l0.k_rope','l0.v','l0.v_bias'];(OUT/'first9_commands.bin').write_bytes(b''.join(int(x['word'],16).to_bytes(16,'little')for x in manifest));print('QWEN2_Q1024_BACKEND_INPUTS_PASS rows=1024 hidden=1536 norm_values=1572864 token_hash=e4151c23e259 commands=9')
