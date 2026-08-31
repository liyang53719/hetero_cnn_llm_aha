#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/v69_source_contract_result.json');a=p.parse_args()
required={'rtl/attention/blocked_attention_stream_controller.sv':['SCORE_FIFO_DEPTH=2','PROB_FIFO_DEPTH=2','summary_merge_rows_o','matrix_cmd_kind_o'],'rtl/sfu/bf16_silu_mul_lut_lane.sv':['bf16_silu_lut_128.svh','HeteroFP32AddPipeBit1','HeteroFP32MulPipeBit1','META_FIFO_DEPTH'],'rtl/sfu/bf16_silu_mul_lut_array.sv':['LANES=1','LANES==2'],'tb/tb_blocked_attention_stream_controller.sv':['run_case(1024)','expected_merges'],'tb/tb_bf16_silu_mul_lut_array.sv':['VECTORS=%s','TB_PASS LANES=%0d']};errors=[];observed={}
for rel,needles in required.items():
 path=ROOT/rel
 if not path.is_file():errors.append(f'missing:{rel}');continue
 data=path.read_bytes();text=data.decode();observed[rel]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 for needle in needles:
  if needle not in text:errors.append(f'missing_contract:{rel}:{needle}')
 if rel.endswith('.sv'):
  stripped=re.sub(r'/\*.*?\*/','',text,flags=re.S);stripped=re.sub(r'//.*','',stripped)
  if len(re.findall(r'\bmodule\b',stripped))!=len(re.findall(r'\bendmodule\b',stripped)):errors.append(f'module_count:{rel}')
for path in (ROOT/'scripts').glob('run_l5_*'):
 if path.suffix=='.sh':
  text=path.read_text()
  for forbidden in ('set_multicycle_path','set_false_path -from [get_ports clk','CLOCK_PERIOD_NS=2'):
   if forbidden in text:errors.append(f'forbidden:{path.name}:{forbidden}')
result={'schema_version':1,'status':'PASS' if not errors else 'FAIL','evidence_class':'source_static_not_elaboration','observed':observed,'errors':errors,'remaining_local_gates':['Verilator_elaboration_and_E1','CLN22UL_1GHz_DC','full_Attention_numerical_E2','SiLU_1_vs_2_lane_PPA_and_producer_stall']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True));raise SystemExit(bool(errors))
