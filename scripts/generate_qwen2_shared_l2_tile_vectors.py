#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'work/results/l5_qwen2_four_layer_reference/cross_vectors';OUT=ROOT/'work/results/qwen2_shared_l2_tile_payload';OUT.mkdir(parents=True,exist_ok=True)
def lines(p):return [int(x,16)for x in p.read_text().splitlines()]
def bf(x):return ((x+0x7fff+((x>>16)&1))>>16)&0xffff
def pack(vals,bits):return ''.join(f'{sum(v<<(bits*i)for i,v in enumerate(vals[j:j+512//bits])):0128x}\n'for j in range(0,len(vals),512//bits))
x=lines(SRC/'rms_x_fp32.memh')[:1536];w=lines(SRC/'rms_weight_fp32.memh')[:1536];mw=lines(SRC/'matrix_weights_bf16.memh');e=__import__('json').load(open(SRC/'expected.json'))
manifest=[__import__('json').loads(x)for x in (ROOT/'reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl').read_text().splitlines()[:2]]
(OUT/'commands.memh').write_text(''.join(x['word'].removeprefix('0x')+'\n'for x in manifest))
(OUT/'hidden_beats.memh').write_text(pack([bf(v)for v in x],16));(OUT/'rms_weight_beats.memh').write_text(pack(w,32));
(OUT/'q_weight_beats.memh').write_text(pack([mw[k*160+c]for k in range(1536)for c in range(32)],16));
(OUT/'norm_expected_beats.memh').write_text(pack([int(v,16)for v in e['rms_bf16_bits'][:1536]],16));
(OUT/'q_expected_beat.memh').write_text(pack([int(v,16)for v in e['matrix_bf16_bits'][:32]],16));print('QWEN2_SHARED_L2_TILE_VECTORS_PASS hidden_beats=48 rms_weight_beats=96 q_weight_beats=1536 norm_expected_beats=48 q_expected_beats=1')
