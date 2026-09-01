#!/usr/bin/env python3
from pathlib import Path
import json,torch
from safetensors import safe_open
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/results/qwen2_kv_projection_vectors';OUT.mkdir(parents=True,exist_ok=True)
e=json.load(open(ROOT/'work/results/l5_qwen2_four_layer_reference/cross_vectors/expected.json'));norm=torch.tensor([int(v,16)for v in e['rms_bf16_bits'][:1536]],dtype=torch.uint16).view(torch.bfloat16)
def pack(vals,bits=16):return ''.join(f'{sum(int(v)<<(bits*i)for i,v in enumerate(vals[j:j+512//bits])):0128x}\n'for j in range(0,len(vals),512//bits))
summary={}
with safe_open(ROOT/'work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors',framework='pt',device='cpu') as f:
 for kind in ('k','v'):
  w=f.get_tensor(f'model.layers.0.self_attn.{kind}_proj.weight').contiguous();b=f.get_tensor(f'model.layers.0.self_attn.{kind}_proj.bias').contiguous();wb=w.view(torch.uint16);bb=b.view(torch.uint16)
  raw=torch.nn.functional.linear(norm,w,None).contiguous();biased=(raw.float()+b.float()).to(torch.bfloat16).contiguous();rawb=raw.view(torch.uint16);biasedb=biased.view(torch.uint16)
  (OUT/f'{kind}_weight_all_tiles.memh').write_text(pack([wb[t*32+c,k]for t in range(8)for k in range(1536)for c in range(32)]));(OUT/f'{kind}_raw_expected_beats.memh').write_text(pack(rawb));(OUT/f'{kind}_bias_fp32_beats.memh').write_text(pack(b.float().view(torch.uint32),32));(OUT/f'{kind}_biased_expected_beats.memh').write_text(pack(biasedb));
  summary[kind]={'columns':256,'tiles':8,'rows':1536,'row_bytes':64,'src_stride':512,'raw_equals_biased':bool(torch.equal(raw,biased)),'token0_rope_identity':kind=='k'}
(OUT/'result.json').write_text(json.dumps({'schema_version':1,'status':'PASS_EXACT_KV_VECTORS','model_revision':'ba1cf1846d7df0a0591d6c00649f57e798519da8','projections':summary},indent=2,sort_keys=True)+'\n');print(json.dumps(summary,sort_keys=True))
