#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.quant_frontend_integrated import integrated_frontend_report
p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=2000);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=integrated_frontend_report(a.cases);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
