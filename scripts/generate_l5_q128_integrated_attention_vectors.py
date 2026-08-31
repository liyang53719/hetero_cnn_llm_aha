#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from heteronpu.attention_e2_vectors import Q_HEADS,KV_HEADS,HEAD_DIM,attention_e2_pack_report,blocked_causal_row,deterministic_qkv,float32_to_bf16_bits
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=lambda x:int(x,0),default=0xA77E);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
q,k,v=deterministic_qkv(128,a.seed);expected=np.empty((Q_HEADS,128,HEAD_DIM),np.float32)
for head in range(Q_HEADS):
 for row in range(128):expected[head,row],_=blocked_causal_row(q,k,v,head,row)
def write(path,array,width):
 flat=np.asarray(array).reshape(-1);path.write_text(''.join(f'{int(x):0{width}x}\n' for x in flat));return hashlib.sha256(path.read_bytes()).hexdigest()
hashes={'q':write(a.out/'q_bf16.memh',float32_to_bf16_bits(q),4),'k':write(a.out/'k_bf16.memh',float32_to_bf16_bits(k),4),'v':write(a.out/'v_bf16.memh',float32_to_bf16_bits(v),4),'expected':write(a.out/'expected_fp32.memh',expected.view(np.uint32),8)}
pack=attention_e2_pack_report(a.seed);manifest={'schema_version':1,'status':'PASS','sequence':128,'q_heads':Q_HEADS,'kv_heads':KV_HEADS,'head_dim':HEAD_DIM,'rows':128*Q_HEADS,'controller_tasks':240,'summary_merge_rows':0,'pack_aggregate_sha256':pack['aggregate_sha256'],'hashes':hashes};(a.out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');print(json.dumps(manifest,indent=2,sort_keys=True))
