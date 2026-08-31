#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from heteronpu.quant_tail_scheduler import tail_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cases',type=int,default=2048);a=p.parse_args();r=tail_report(a.cases);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'cases':r['cases'],'max_dot':r['maximum_dot_difference']},indent=2))
