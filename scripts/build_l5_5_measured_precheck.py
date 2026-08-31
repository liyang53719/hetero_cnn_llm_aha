#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from heteronpu.service_curve_importer import import_report
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--commit',required=True);p.add_argument('--curve-output',type=Path,required=True);p.add_argument('--report-output',type=Path,required=True);a=p.parse_args()
paths=[ROOT/'reports/execution/l5_q128_single_sim_attempt_result.json',ROOT/'reports/execution/l5_q384_sampled_e2_result.json',ROOT/'reports/execution/l5_q1024_reviewed_e2_result.json',ROOT/'reports/execution/l5_silu_lane_selection_result.json']
q128,q384,q1024,selection=[json.loads(x.read_text()) for x in paths]
A=np.asarray([[q128['observed_progress']['tasks'],0],[q384['payload_tasks'],q384['sampled_merge_rows']],[q1024['payload_tasks'],q1024['sampled_merge_rows']]],dtype=np.float64);y=np.asarray([q128['observed_progress']['rtl_cycles'],q384['rtl_cycles'],q1024['aggregate_rtl_cycles']],dtype=np.float64)
coef=np.linalg.lstsq(A,y,rcond=None)[0];pred=A@coef;residual=y-pred;full_attention=float(np.asarray([12672,43008])@coef)
# Revision8B-B II=1 optimistic Matrix bound: every task has 128 QK and 256 hi/lo PV steps plus ten fill/drain cycles.
attention_matrix=12672*(128+256+10);attention_sfu=max(0,round(full_attention-attention_matrix));silu_cycles=9_175_040
digest=hashlib.sha256();[digest.update(x.read_bytes()) for x in paths]
curve={'commit':a.commit,'source_sha256':digest.hexdigest(),'sequence':1024,'clock_hz':1_000_000_000,'attention_matrix_cycles':attention_matrix,'attention_sfu_cycles':attention_sfu,'silu_cycles':silu_cycles,'matrix_producer_stall_cycles':0,'matrix_queue_bubble_cycles':0,'sram_bank_conflict_cycles':0,'event_wait_signal_cycles':0,'ddr_read_bytes':93_585_408,'ddr_write_bytes':1_048_576,'ddr_read_efficiency':1.0,'ddr_write_efficiency':1.0,'score_ddr_bytes':0,'probability_ddr_bytes':0,'evidence_class':'E2_INTEGRATED'}
imported=import_report(curve);report={'schema_version':1,'status':imported['status'],'evidence_class':'measured_RTL_E2_extrapolation_precheck_not_L5_5_E3','fit':{'features':['payload_tasks','merge_rows'],'coefficients_cycles':{'base_task':float(coef[0]),'merge_row':float(coef[1])},'observed_cycles':y.astype(int).tolist(),'fitted_cycles':pred.tolist(),'residual_cycles':residual.tolist(),'full_q1024_attention_cycles':round(full_attention)},'optimistic_assumptions':['Revision8B-B II=1 Matrix bound','DDR efficiency=1','zero queue bubble','zero bank conflict','zero event wait','selected one-lane SiLU producer stall=0'],'curve':curve,'imported':imported,'stop_rule_applied':imported['status']=='FAIL_REOPEN_ARCHITECTURE','next_action':'Pipeline/parallelize Block32 softmax and global merge service before L5.5 E3; do not claim 300 token/s.'}
for path,data in ((a.curve_output,curve),(a.report_output,report)):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
print(json.dumps(report,indent=2,sort_keys=True));raise SystemExit(0 if imported['status']=='FAIL_REOPEN_ARCHITECTURE' else 1)
