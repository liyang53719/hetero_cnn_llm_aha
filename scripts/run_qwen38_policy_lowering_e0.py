#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.policy_lowering import qwen38_policy_lowering_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/qwen38_policy_lowering_e0_result.json');a=p.parse_args()
r=qwen38_policy_lowering_report();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status']=='PASS' else 1)
