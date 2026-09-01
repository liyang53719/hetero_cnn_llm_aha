#!/usr/bin/env python3
from pathlib import Path
import json,torch
from safetensors import safe_open
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'work/results/l5_qwen2_four_layer_reference/cross_vectors';OUT=ROOT/'work/results/qwen2_shared_l2_tile_payload';OUT.mkdir(parents=True,exist_ok=True)
def lines(p):return [int(x,16)for x in p.read_text().splitlines()]
def bf(x):return ((x+0x7fff+((x>>16)&1))>>16)&0xffff
def pack(vals,bits):return ''.join(f'{sum(v<<(bits*i)for i,v in enumerate(vals[j:j+512//bits])):0128x}\n'for j in range(0,len(vals),512//bits))
x=lines(SRC/'rms_x_fp32.memh')[:1536];w=lines(SRC/'rms_weight_fp32.memh')[:1536];e=json.load(open(SRC/'expected.json'))
manifest=[json.loads(x)for x in (ROOT/'reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl').read_text().splitlines()[:2]]
(OUT/'commands.memh').write_text(''.join(x['word'].removeprefix('0x')+'\n'for x in manifest))
(OUT/'hidden_beats.memh').write_text(pack([bf(v)for v in x],16));(OUT/'rms_weight_beats.memh').write_text(pack(w,32));
with safe_open(ROOT/'work/models/qwen2_1p5b_instruct_ba1cf184/model.safetensors',framework='pt',device='cpu') as f:q_weight=f.get_tensor('model.layers.0.self_attn.q_proj.weight')[:32].contiguous()
q_bits=q_weight.view(torch.uint16);norm_bits=torch.tensor([int(v,16)for v in e['rms_bf16_bits'][:1536]],dtype=torch.uint16);norm=norm_bits.view(torch.bfloat16)
q_expected=torch.nn.functional.linear(norm,q_weight,None).contiguous().view(torch.uint16).tolist()
(OUT/'q_weight_beats.memh').write_text(pack([int(q_bits[c,k])for k in range(1536)for c in range(32)],16));
(OUT/'norm_expected_beats.memh').write_text(pack([int(v,16)for v in e['rms_bf16_bits'][:1536]],16));
(OUT/'q_expected_beat.memh').write_text(pack([int(v)for v in q_expected],16));print('QWEN2_SHARED_L2_TILE_VECTORS_PASS hidden_beats=48 rms_weight_beats=96 q_weight_beats=1536 norm_expected_beats=48 q_expected_beats=1 physical_q_columns=0_31')
