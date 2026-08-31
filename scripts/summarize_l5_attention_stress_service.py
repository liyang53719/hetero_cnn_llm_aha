#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
log=ROOT/'work/results/l5_blocked_attention_controller_e1/tb.log';text=log.read_text()
pattern=re.compile(r'CASE_PASS seed=([0-9a-f]+) seq=(128|384|1024) tasks=(\d+) merges=(\d+) service_cycles=(\d+) loss=0 duplicate=0 reorder=0 deadlock=0')
records=[{'seed':m.group(1),'sequence':int(m.group(2)),'tasks':int(m.group(3)),'merges':int(m.group(4)),'cycles':int(m.group(5))} for m in pattern.finditer(text)]
if len(records)!=24 or text.count('TB_PASS seed=')!=8:raise SystemExit('controller stress record count')
curves={}
for seq in (128,384,1024):
 vals=[r['cycles'] for r in records if r['sequence']==seq]
 curves[str(seq)]={'samples':len(vals),'min_cycles':min(vals),'mean_cycles':statistics.mean(vals),'max_cycles':max(vals),'spread_fraction':(max(vals)-min(vals))/statistics.mean(vals)}
q128=json.loads((ROOT/'reports/execution/l5_q128_single_sim_attempt_result.json').read_text());q384=json.loads((ROOT/'reports/execution/l5_q384_sampled_e2_result.json').read_text());q1024=json.loads((ROOT/'reports/execution/l5_q1024_reviewed_e2_result.json').read_text())
payload={'128':{'coverage':'full','rows':q128['observed_progress']['rows'],'tasks':q128['observed_progress']['tasks'],'rtl_cycles':q128['observed_progress']['rtl_cycles']},'384':{'coverage':'sampled','rows':q384['actual_compared_rows'],'tasks':q384['payload_tasks'],'rtl_cycles':q384['rtl_cycles']},'1024':{'coverage':'reviewed_two_shards','rows':q1024['actual_compared_rows'],'tasks':q1024['payload_tasks'],'rtl_cycles':q1024['aggregate_rtl_cycles']}}
for value in payload.values():value['cycles_per_payload_task']=value['rtl_cycles']/value['tasks']
output_result=ROOT/'reports/execution/l5_block128_local_e1_e4_result.json'
r={'schema_version':1,'status':'PASS','evidence_class':'controller_random_backpressure_E1_plus_payload_E2_service_curves','controller_stress':{'seeds':8,'tasks_per_flow':sum(x['tasks'] for x in records),'transactions_qk_sfu_pv':3*sum(x['tasks'] for x in records),'loss':0,'duplicate':0,'reorder':0,'deadlock':0,'curves':curves,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()},'output_backpressure':{'status':'PASS_COMPONENT_E1','evidence':str(output_result.relative_to(ROOT)),'sha256':hashlib.sha256(output_result.read_bytes()).hexdigest()},'payload_service_curves':payload,'score_ddr_bytes':0,'probability_ddr_bytes':0,'non_claims':['q384/q1024 payload curves are sampled, not full-sequence integrated E3','controller abstract service cycles are not physical Matrix/SFU latency','no SiLU producer-stall lane selection from this report']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
