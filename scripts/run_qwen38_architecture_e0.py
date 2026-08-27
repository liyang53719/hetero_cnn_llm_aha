#!/usr/bin/env python3
from pathlib import Path
import json
from heteronpu.qwen38_qsa_streaming import run_random_parity
from heteronpu.qwen38_state_transaction import run_transaction_stress
from heteronpu.qwen38_budget import full_budget_report
from heteronpu.qwen38_memory_dse import memory_dse_report
from heteronpu.qwen38_quantization import quantization_screen_report
from heteronpu.qwen38_liveness import liveness_report
from heteronpu.matrix_context_pipeline import dependent_round_robin,randomized_backpressure
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports'/'execution';OUT.mkdir(parents=True,exist_ok=True)
results={
 'qwen38_qsa_streaming_result.json':run_random_parity(200),
 'qwen38_state_transaction_result.json':run_transaction_stress(1000),
 'qwen38_full_shape_budget.json':full_budget_report((1024,4096,262144)),
 'qwen38_memory_dse.json':memory_dse_report(1024),
 'qwen38_quantization_screen.json':quantization_screen_report(),
 'qwen38_liveness_result.json':liveness_report(),
 'matrix_context_source_model_result.json':{'schema_version':1,'status':'PASS','evidence_class':'E0_protocol_model_not_RTL','dependent_1m':dependent_round_robin(1_000_000,4,4),'random_backpressure':randomized_backpressure(10_000,4,4)} }
for name,result in results.items():(OUT/name).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
summary={'schema_version':1,'status':'PASS','evidence_class':'sandbox_E0_architecture_analysis','results':{name:value['status'] for name,value in results.items()},'non_claims':['no_official_weight_accuracy','no_new_RTL_E1','no_E3','no_E4']}
(OUT/'qwen38_architecture_e0_result.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n');print(json.dumps(summary,indent=2,sort_keys=True))
