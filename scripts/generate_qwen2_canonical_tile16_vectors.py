#!/usr/bin/env python3
import hashlib
import struct
import sys
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from generate_l5_q128_qkv_batch_vectors import add,bf16_value,fma,from_word,mul,reduce16,rsqrt_algorithm
MODEL=ROOT/'work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors';TOKENS=ROOT/'work/results/llama_cpp_qwen2_baseline/tokens.txt';OUT=ROOT/'work/results/qwen2_canonical_tile16_vectors';OUT.mkdir(parents=True,exist_ok=True)
def bits(v):return struct.unpack('<I',struct.pack('<f',float(np.float32(v))))[0]
def bf(v):
 w=bits(v);return ((w+0x7fff+((w>>16)&1))>>16)&0xffff
def refined(x,w):
 total=np.float32(0)
 for ch in range(96):total=add(total,reduce16([mul(v,v)for v in x[ch*16:(ch+1)*16]]))
 me=add(mul(total,np.float32(1/1536)),np.float32(1e-6));first=rsqrt_algorithm(me);inv=mul(first,add(np.float32(1.5),-mul(np.float32(.5),mul(me,mul(first,first)))))
 return np.asarray([bf16_value(mul(bf16_value(mul(x[i],inv)),w[i]))for i in range(1536)],dtype=np.float32)
def pack(path,values,width=16):
 n=512//width;path.write_text(''.join(f'{sum(int(v)<<(width*i)for i,v in enumerate(values[j:j+n])):0128x}\n'for j in range(0,len(values),n)))
ids=np.asarray([int(x)for x in TOKENS.read_text().splitlines()],dtype=np.int32);assert hashlib.sha256(ids.tobytes()).hexdigest()=='e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628'
with safe_open(MODEL,framework='pt',device='cpu')as f:
 emb_tensor=f.get_tensor('model.embed_tokens.weight')[torch.tensor(ids[:16],dtype=torch.long)].contiguous();emb=emb_tensor.float().numpy();nw_tensor=f.get_tensor('model.layers.0.input_layernorm.weight').float().contiguous();nw=nw_tensor.numpy();qw=f.get_tensor('model.layers.0.self_attn.q_proj.weight')[:32].contiguous().view(torch.uint16).numpy()
norm=np.stack([refined(emb[t],nw)for t in range(16)]);norm_bits=np.asarray([[bf(v)for v in norm[t]]for t in range(16)],dtype=np.uint16);a=[]
for k in range(1536):a.extend(int(norm_bits[t,k])for t in range(16));a.extend([0]*16)
weights=[]
for k in range(1536):weights.extend(int(qw[c,k])for c in range(32))
expected=[]
for t in range(16):
 for c in range(32):
  acc=np.float32(0)
  for k in range(1536):acc=fma(from_word(int(norm_bits[t,k])<<16),from_word(int(qw[c,k])<<16),acc)
  expected.append(bf(acc))
pack(OUT/'hidden_token_major.memh',emb_tensor.view(torch.uint16).flatten().tolist());pack(OUT/'rms_weight_fp32.memh',nw_tensor.view(torch.uint32).flatten().tolist(),32);pack(OUT/'norm_token_major.memh',norm_bits.flatten().tolist());pack(OUT/'activation_kmajor.memh',a);pack(OUT/'q_weight_tile0.memh',weights);pack(OUT/'expected_rows.memh',expected)
print('QWEN2_CANONICAL_TILE16_VECTORS_PASS rows=16 columns=32 k=1536 values=512 token_hash=e4151c23e259')
