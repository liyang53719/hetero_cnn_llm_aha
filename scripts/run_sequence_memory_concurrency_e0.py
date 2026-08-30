#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.sequence_memory_concurrency import sequence_memory_concurrency_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/sequence_memory_concurrency_e0_result.json');a=p.parse_args()
r=sequence_memory_concurrency_report();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status']=='PASS' else 1)
