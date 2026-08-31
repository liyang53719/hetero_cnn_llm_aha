#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from heteronpu.silu_edge_and_stall import combined_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=combined_report();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'special_vectors':r['special_vectors']['vectors'],'stall_scenarios':r['stall_envelope']['scenarios']},indent=2))
