#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from heteronpu.attention_e2_vectors import attention_e2_pack_report
from heteronpu.silu_edge_and_stall import combined_report
from heteronpu.quant_tail_scheduler import tail_report
from heteronpu.state_adversarial_vectors import adversarial_report
from heteronpu.e3_minimum_matrix import minimum_e3_matrix
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--quant-cases',type=int,default=2048);p.add_argument('--transactions',type=int,default=5000);a=p.parse_args()
r={'schema_version':1,'status':'PASS','evidence_class':'sandbox_v70_E0_not_local_E1_E2_E3_E4','attention_e2_pack':attention_e2_pack_report(),'silu_edge_and_stall':combined_report(),'quant_tail':tail_report(a.quant_cases),'state_adversarial':adversarial_report(a.transactions),'e3_minimum_matrix':minimum_e3_matrix(),'remaining_local_gates':['full_Attention_RTL_E2','measured_SiLU_lane_selection','integrated_iDMA_DDR_E3','quant_frontend_RTL_E1_and_llama_parity','state_transaction_RTL_E1','post_route_PVT_SAIF']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'attention_sha':r['attention_e2_pack']['aggregate_sha256'],'silu_vectors':r['silu_edge_and_stall']['special_vectors']['vectors'],'quant_cases':r['quant_tail']['cases'],'state_transactions':r['state_adversarial']['transactions'],'e3_cases':r['e3_minimum_matrix']['case_count']},indent=2))
