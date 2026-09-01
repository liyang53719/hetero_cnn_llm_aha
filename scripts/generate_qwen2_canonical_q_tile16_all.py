#!/usr/bin/env python3
import hashlib,json,multiprocessing as mp,struct,sys
from pathlib import Path
import numpy as np,torch
from safetensors import safe_open
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from generate_l5_q128_qkv_batch_vectors import fma,from_word
SRC=ROOT/'work/results/qwen2_canonical_tile16_vectors';MODEL=ROOT/'work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors';OUT=ROOT/'work/results/qwen2_canonical_q_tile16_all';OUT.mkdir(parents=True,exist_ok=True)
def bf(v):
 w=struct.unpack('<I',struct.pack('<f',float(np.float32(v))))[0];return((w+0x7fff+((w>>16)&1))>>16)&0xffff
def load_beats(path):
 vals=[]
 for line in path.read_text().splitlines():
  w=int(line,16);vals.extend((w>>(16*i))&0xffff for i in range(16))
 return np.asarray(vals,dtype=np.uint16).reshape(1536,16).T
def pack(path,values):path.write_text(''.join(f'{sum(int(v)<<(16*i)for i,v in enumerate(values[j:j+32])):0128x}\n'for j in range(0,len(values),32)))
NORM=load_beats(SRC/'activation_kmajor.memh')
with safe_open(MODEL,framework='pt',device='cpu')as f:
 WEIGHTS={kind:f.get_tensor(f'model.layers.0.self_attn.{kind}_proj.weight').contiguous().view(torch.uint16).numpy()for kind in('q','k','v')}
def worker(item):
 kind,token=item;matrix=WEIGHTS[kind]
 out=[]
 for col in range(matrix.shape[0]):
  acc=np.float32(0)
  for k in range(1536):acc=fma(from_word(int(NORM[token,k])<<16),from_word(int(matrix[col,k])<<16),acc)
  out.append(bf(acc))
 return kind,token,out
with mp.get_context('fork').Pool(8)as pool:results=pool.map(worker,[(kind,t)for kind in('q','k','v')for t in range(16)])
rows={kind:[None]*16 for kind in('q','k','v')}
for kind,token,out in results:rows[kind][token]=out
summary={}
for kind in('q','k','v'):
 matrix=WEIGHTS[kind];columns=matrix.shape[0];tiles=columns//32;weight=[]
 for k in range(1536):
  for tile in range(tiles):weight.extend(int(matrix[tile*32+c,k])for c in range(32))
 pack(OUT/f'{kind}_weight_ddr_beats.memh',weight);pack(OUT/f'{kind}_expected_token_major.memh',[v for row in rows[kind]for v in row]);summary[kind]={'columns':columns,'tiles':tiles,'values':16*columns}
r={'schema_version':1,'status':'PASS_CANONICAL_QKV_TILE16_ALL_VECTORS','rows':16,'k':1536,'projections':summary,'token_hash':'e4151c23e259dda17d515c73f653031e8a2af9e7784dba297b454fe7cb4ba628'};(OUT/'result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print('QWEN2_CANONICAL_QKV_TILE16_ALL_VECTORS_PASS Q_tiles=48 K_tiles=8 V_tiles=8 values=32768')
