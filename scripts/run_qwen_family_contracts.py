#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.qwen_family_contracts import family_contract_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/qwen_family_contracts_result.json');a=p.parse_args();r=family_contract_report(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json',ROOT/'config/model_profiles/qwen3_8_flash_next.json');a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
