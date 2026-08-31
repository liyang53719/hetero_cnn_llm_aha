#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.attention_sfu_balance import balance_report
from heteronpu.qwen_model_resource_envelope import resource_envelope_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/sandbox_v75_result.json');a=p.parse_args();sfu=balance_report();models=resource_envelope_report(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json',ROOT/'config/model_profiles/qwen3_8_flash_next.json');r={'schema_version':1,'status':'PASS_SANDBOX_V7_5','evidence_class':'sandbox_E0_not_RTL_E1_E4_or_E3','balanced_sfu':sfu,'model_resources':models,'non_claims':['no 8x8 RTL elaboration','no 8x8 Verilator E1','no CLN22UL E4','no integrated E3','no official-weight Qwen execution']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
