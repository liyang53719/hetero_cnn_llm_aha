#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from heteronpu.attention_e2_vectors import attention_e2_pack_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=lambda x:int(x,0),default=0xA77E);a=p.parse_args();r=attention_e2_pack_report(a.seed);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({k:r[k] for k in ('status','max_abs','max_relative_l2','aggregate_sha256')},indent=2))
