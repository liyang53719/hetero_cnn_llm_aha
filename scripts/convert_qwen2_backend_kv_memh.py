#!/usr/bin/env python3
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'work/results/qwen2_q1024_exact_backend';OUT=ROOT/'work/results/qwen2_q1024_exact_backend';
def pack(path,vals):path.write_text(''.join(f'{sum(int(v)<<(16*i)for i,v in enumerate(vals[j:j+32])):0128x}\n'for j in range(0,len(vals),32)))
k=np.fromfile(SRC/'k_rope.bin',np.uint16);v=np.fromfile(SRC/'v_bias.bin',np.uint16);assert k.size==v.size==1024*256;pack(OUT/'k_rope.memh',k);pack(OUT/'v_bias.memh',v);print('QWEN2_BACKEND_KV_MEMH_PASS K_beats=8192 V_beats=8192')
