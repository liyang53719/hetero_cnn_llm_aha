#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from heteronpu.e3_minimum_matrix import minimum_e3_matrix
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=minimum_e3_matrix();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'cases':r['case_count'],'sha256':r['sha256']},indent=2))
