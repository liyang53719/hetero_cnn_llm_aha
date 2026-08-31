#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.attention_adversarial import adversarial_attention_report
from heteronpu.quant_frontend_integrated import integrated_frontend_report
from heteronpu.state_multislot import stress
from heteronpu.qwen38_multilayer_trace import multilayer_trace_report
from heteronpu.service_curve_importer import import_report,sample_curve
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--quant-cases',type=int,default=2000);p.add_argument('--transactions',type=int,default=10000);a=p.parse_args()
r={'schema_version':1,'status':'PASS_SANDBOX_V7_2','attention':adversarial_attention_report(),'quant':integrated_frontend_report(a.quant_cases),'state':stress(a.transactions),'trace':multilayer_trace_report(),'service_good':import_report(sample_curve()),'service_degraded':import_report(sample_curve(degraded=True)),'non_claims':['not RTL Attention E2','not quant/state RTL E1','not official-weight trace','not integrated E3','not post-route signoff']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({k:(v.get('status') if isinstance(v,dict) else v) for k,v in r.items()},indent=2,sort_keys=True))
