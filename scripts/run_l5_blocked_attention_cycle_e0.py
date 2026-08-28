#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.blocked_attention_cycle import sweep_reports
out=ROOT/'reports/execution/l5_blocked_attention_cycle_e0_result.json';result=sweep_reports()
assert result['status']=='PASS';assert result['frozen_checks']['q1024_summary_merges']==43008;assert result['frozen_checks']['all_score_DDR_materialization_zero'] is True;assert result['cases']['384']['serialized_cycles']<=1500000
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','q128_cycles':result['cases']['128']['serialized_cycles'],'q384_cycles':result['cases']['384']['serialized_cycles'],'q1024_cycles':result['cases']['1024']['serialized_cycles'],'q1024_merges':43008},indent=2,sort_keys=True))
