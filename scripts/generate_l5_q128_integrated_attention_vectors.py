#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from heteronpu.attention_e2_vectors import Q_HEADS,KV_HEADS,HEAD_DIM,attention_e2_pack_report,blocked_causal_row,controller_task_count,deterministic_qkv,float32_to_bf16_bits,summary_merge_rows
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--sequence',type=int,default=128);p.add_argument('--seed',type=lambda x:int(x,0),default=0xA77E);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
q,k,v=deterministic_qkv(a.sequence,a.seed);expected=np.empty((Q_HEADS,a.sequence,HEAD_DIM),np.float32)
for head in range(Q_HEADS):
 for row in range(a.sequence):expected[head,row],_=blocked_causal_row(q,k,v,head,row)
tile_m=np.empty(16,np.float32);tile_l=np.empty(16,np.float32);tile_o=np.empty((16,HEAD_DIM),np.float32)
for row in range(16):
 scores=np.asarray(k[0,:32]@q[0,row]/np.float32(np.sqrt(HEAD_DIM)),dtype=np.float32);scores[row+1:]=np.float32(-np.inf)
 tile_m[row]=np.max(scores);weights=np.exp(np.asarray(scores-tile_m[row],dtype=np.float32)).astype(np.float32);weights[row+1:]=0
 tile_l[row]=np.sum(weights,dtype=np.float32);tile_o[row]=np.asarray(weights@v[0,:32],dtype=np.float32)
def write(path,array,width):
 flat=np.asarray(array).reshape(-1);path.write_text(''.join(f'{int(x):0{width}x}\n' for x in flat));return hashlib.sha256(path.read_bytes()).hexdigest()
hashes={'q':write(a.out/'q_bf16.memh',float32_to_bf16_bits(q),4),'k':write(a.out/'k_bf16.memh',float32_to_bf16_bits(k),4),'v':write(a.out/'v_bf16.memh',float32_to_bf16_bits(v),4),'expected':write(a.out/'expected_fp32.memh',expected.view(np.uint32),8),'tile_m':write(a.out/'tile_m_fp32.memh',tile_m.view(np.uint32),8),'tile_l':write(a.out/'tile_l_fp32.memh',tile_l.view(np.uint32),8),'tile_o':write(a.out/'tile_o_fp32.memh',tile_o.view(np.uint32),8)}
pack=attention_e2_pack_report(a.seed);manifest={'schema_version':1,'status':'PASS','sequence':a.sequence,'q_heads':Q_HEADS,'kv_heads':KV_HEADS,'head_dim':HEAD_DIM,'rows':a.sequence*Q_HEADS,'controller_tasks':controller_task_count(a.sequence),'summary_merge_rows':summary_merge_rows(a.sequence),'pack_aggregate_sha256':pack['aggregate_sha256'],'hashes':hashes};(a.out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');print(json.dumps(manifest,indent=2,sort_keys=True))
