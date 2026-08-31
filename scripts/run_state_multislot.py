#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.state_multislot import stress
p=argparse.ArgumentParser();p.add_argument('--transactions',type=int,default=10000);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=stress(a.transactions);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
