#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.qwen_model_resource_envelope import resource_envelope_report
p=argparse.ArgumentParser();p.add_argument('--q35',type=Path,default=ROOT/'config/model_profiles/qwen3_5_35b_a3b.json');p.add_argument('--q38',type=Path,default=ROOT/'config/model_profiles/qwen3_8_flash_next.json');p.add_argument('--output',type=Path,default=ROOT/'reports/execution/qwen_model_resource_envelope_result.json');a=p.parse_args();r=resource_envelope_report(a.q35,a.q38);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
