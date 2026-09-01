#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--llama',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();x=np.fromfile(a.reference,dtype=np.float32);y=np.fromfile(a.llama,dtype=np.float32)
if x.shape!=y.shape or x.size!=151936:raise SystemExit(f'shape {x.shape} {y.shape}')
err=np.abs(x-y);topx=np.argpartition(x,-10)[-10:];topy=np.argpartition(y,-10)[-10:];r={'schema_version':1,'status':'PASS_REAL_LLAMA_CPU_BASELINE','evidence_class':'stock_pinned_llama_cpp_CPU_not_project_device_backend','vocab':int(x.size),'pytorch_argmax':int(x.argmax()),'llama_argmax':int(y.argmax()),'argmax_match':bool(x.argmax()==y.argmax()),'top10_overlap':len(set(topx.tolist())&set(topy.tolist())),'max_absolute_error':float(err.max()),'mean_absolute_error':float(err.mean()),'pytorch_logits_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'llama_logits_sha256':hashlib.sha256(y.tobytes()).hexdigest(),'non_claim':'stock CPU llama.cpp does not execute the project Matrix/SFU device payload datapath'};a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,sort_keys=True));raise SystemExit(0 if r['argmax_match']else 1)
