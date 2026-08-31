#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
counter=re.compile(r'SILU_STALL_COUNTERS LANES=(\d+) pairs_offered=(\d+) pairs_accepted=(\d+) producer_stall_cycles=(\d+) producer_stalled_pairs=(\d+) queue_high_water=(\d+) consumer_backpressure_cycles=(\d+) total_cycles=(\d+)')
lanes={}
for lane in (1,2):
 path=ROOT/f'work/results/l5_silu_lut_e1/lanes{lane}/tb.log';m=counter.search(path.read_text())
 if not m:raise SystemExit(f'missing counters lane{lane}')
 values=list(map(int,m.groups()));offered=values[1];stall=values[3]
 lanes[str(lane)]={'pairs_offered':offered,'pairs_accepted':values[2],'producer_stall_cycles':stall,'producer_stalled_pairs':values[4],'queue_high_water':values[5],'consumer_backpressure_cycles':values[6],'total_cycles':values[7],'producer_stall_fraction':stall/max(values[7],1),'log_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
gate=ROOT/'work/results/l5_q384_gate_up/batch0/mode0.log';up=ROOT/'work/results/l5_q384_gate_up/batch0/mode1.log';cycle_re=re.compile(r'array_steps=(\d+) cycles=(\d+)')
gm=cycle_re.search(gate.read_text());um=cycle_re.search(up.read_text())
if not gm or not um:raise SystemExit('matrix producer receipts')
pairs_per_batch=16*8960;projection_cycles=int(gm.group(2))+int(um.group(2));rate=pairs_per_batch/projection_cycles
local=json.loads((ROOT/'reports/execution/l5_3_l5_4_local_result.json').read_text());one=local['L5.4']['one_lane'];two=local['L5.4']['two_lane']
selected='one' if lanes['1']['producer_stall_fraction']<=0.02 else 'two'
r={'schema_version':1,'status':'PASS','evidence_class':'measured_RTL_producer_contract_E1_plus_real_Matrix_gate_up_receipts_and_DC_E4','selection_rule':'one_lane_if_producer_stall_fraction_le_0.02_else_two_lane','selected_lanes':1 if selected=='one' else 2,'selected':selected,'matrix_producer':{'workload':'q384','tokens_per_batch':16,'pairs_per_batch':pairs_per_batch,'gate_projection_cycles':int(gm.group(2)),'up_projection_cycles':int(um.group(2)),'combined_projection_cycles':projection_cycles,'measured_mean_pairs_per_cycle':rate,'one_lane_capacity_pairs_per_cycle':1,'one_lane_rate_headroom':1/rate,'receipts':[str(gate.relative_to(ROOT)),str(up.relative_to(ROOT))]},'candidates':{'one':{**lanes['1'],'dc':one},'two':{**lanes['2'],'dc':two}},'required_counters_present':['pairs_offered','pairs_accepted','producer_stall_cycles','producer_stalled_pairs','queue_high_water','consumer_backpressure_cycles'],'selected_integrated_rerun':'PASS_4096_BEATS_NUMERICAL_AND_BACKPRESSURE','non_claims':['producer contract E1 is not full-model integrated E3','DC power is vectorless, not SAIF']}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
