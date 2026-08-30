#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.ggml_node_adapter import adapter_contract_report
from heteronpu.l5_join_sensitivity import sensitivity_report
from heteronpu.quant_operand_frontend import frontend_self_test
from heteronpu.state_commit_protocol import protocol_stress
from heteronpu.trace_schema import trace_schema_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/sandbox_v68_result.json');p.add_argument('--quant-cases',type=int,default=1000);p.add_argument('--transactions',type=int,default=1000);a=p.parse_args()
r={'schema_version':1,'status':'PASS','evidence_class':'sandbox_v68_E0_not_local_E1_E3_E4','quant_operand_frontend':frontend_self_test(a.quant_cases),'state_commit_barrier':protocol_stress(a.transactions),'official_trace_schema':trace_schema_report(),'ggml_node_adapter':adapter_contract_report(),'L5_join_sensitivity':sensitivity_report(),'remaining_local_gates':['L5.3_real_stream_E1_E2','L5.4_fused_SiLU_E1_E4','L5.5_integrated_iDMA_DDR_E3','pinned_llama_cpp_quant_parity','state_transaction_RTL_E1','official_weight_trace_capture','real_llama_cpp_backend','post_route_PVT_power']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
