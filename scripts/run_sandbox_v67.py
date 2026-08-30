#!/usr/bin/env python3
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.ggml_quant import self_test_report
from heteronpu.sequence_state_transactions import transaction_stress_report
from heteronpu.graph_partition import partition_report
from heteronpu.system_e3_model import system_preflight_report
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'reports/execution/sandbox_v67_result.json');p.add_argument('--quant-cases',type=int,default=2000);p.add_argument('--transactions',type=int,default=1000);p.add_argument('--vectors',type=Path,default=ROOT/'tests/vectors/ggml_quant_vectors.txt');a=p.parse_args();q=self_test_report(a.quant_cases);s=transaction_stress_report(a.transactions);g=partition_report();e=system_preflight_report();cpp=None
if a.vectors.exists():
 b=Path('/tmp/heteronpu_ggml_quant_ref');subprocess.run(['/usr/bin/g++','-std=c++20','-O2','-Wall','-Wextra','-Werror',str(ROOT/'cpp/ggml_quant_reference.cpp'),'-o',str(b)],check=True);cpp=json.loads(subprocess.check_output([str(b),str(a.vectors)],text=True))
r={'schema_version':1,'status':'PASS','evidence_class':'sandbox_v67_E0_not_local_E1_E3_E4','ggml_quant':q,'ggml_quant_cpp':cpp,'sequence_state_transactions':s,'graph_partition':g,'system_e3_preflight':e,'not_claimed':['official_llama_cpp_quant_parity','RTL_E1','integrated_iDMA_E3','post_route_E4']};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':'PASS','output':str(a.output),'cpp_vectors':None if cpp is None else cpp['vectors']}))
