#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.revision7_contract import approval_report
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path,default=ROOT/'reports/execution/l5_revision7_sandbox_approval.json');p.add_argument('--operations',type=int,default=100000);a=p.parse_args()
r=approval_report(a.root,a.root/'config/l5_revision7_policy.json',a.root/'dc/synth_l5_bf16_context_lane_rev7.tcl',operations=a.operations)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status']=='PASS' else 1)
