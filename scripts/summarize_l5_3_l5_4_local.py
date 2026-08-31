#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def text(path:Path)->str:return path.read_text(errors='replace') if path.is_file() else ''
def sha(path:Path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
def status(path:Path):return dict(line.split('=',1) for line in text(path).splitlines() if '=' in line)
def area(path:Path):
 m=re.search(r'Cell Area:\s*([0-9.]+)',text(path));return float(m.group(1)) if m else None
def power_mw(path:Path,label:str):
 m=re.search(rf'{re.escape(label)}\s*=\s*([0-9.]+)\s*([mun]?W)',text(path))
 if not m:return None
 value=float(m.group(1));return value*({'W':1000.0,'mW':1.0,'uW':0.001,'nW':0.000001}[m.group(2)])
def dc_result(directory:Path):
 s=status(directory/'status.txt');q=directory/'qor.rpt';p=directory/'power_estimate.rpt'
 return {'wns_ns':float(s['WORST_SLACK_NS']) if s else None,'unmapped':int(s['UNMAPPED_CELLS']) if s else None,'cell_area':area(q),'dynamic_power_mw_estimate':power_mw(p,'Total Dynamic Power'),'leakage_power_mw_estimate':power_mw(p,'Cell Leakage Power'),'evidence_class':'DC_WLM_vectorless_power','status_sha256':sha(directory/'status.txt')}
controller_log=ROOT/'work/results/l5_blocked_attention_controller_e1/tb.log'
silu1_log=ROOT/'work/results/l5_silu_lut_e1/lanes1/tb.log';silu2_log=ROOT/'work/results/l5_silu_lut_e1/lanes2/tb.log'
controller_dc=dc_result(ROOT/'work/results/l5_blocked_attention_controller_dc');silu1_dc=dc_result(ROOT/'work/results/l5_silu_lut_dc/lanes1');silu2_dc=dc_result(ROOT/'work/results/l5_silu_lut_dc/lanes2')
bridge_path=ROOT/'reports/execution/l5_attention_trace_bridge_result.json';bridge=json.loads(bridge_path.read_text()) if bridge_path.is_file() else {}
attempt_path=ROOT/'reports/execution/l5_q128_single_sim_attempt_result.json';attempt=json.loads(attempt_path.read_text()) if attempt_path.is_file() else {}
weight_log=ROOT/'work/results/l5_block32_softmax_weight_e1/tb.log';weight_dc=dc_result(ROOT/'work/results/l5_block32_softmax_weight_dc')
checks={'controller_e1':all(x in text(controller_log) for x in ('CASE_PASS seq=128 tasks=240 merges=0','CASE_PASS seq=384 tasks=1872 merges=4608','CASE_PASS seq=1024 tasks=12672 merges=43008','TB_PASS')),'controller_dc':controller_dc['wns_ns'] is not None and controller_dc['wns_ns']>=0 and controller_dc['unmapped']==0,'attention_trace_bridge':bridge.get('status')=='PASS_TRACE_COUPLED_BRIDGE','block32_weight_e1':'BLOCK32_SOFTMAX_WEIGHT_PASS rows=2 weights=64' in text(weight_log),'block32_weight_dc':weight_dc['wns_ns'] is not None and weight_dc['wns_ns']>=0 and weight_dc['unmapped']==0,'silu_1lane_e1':'TB_PASS LANES=1 cases=4096' in text(silu1_log),'silu_2lane_e1':'TB_PASS LANES=2 cases=4096' in text(silu2_log),'silu_1lane_dc':silu1_dc['wns_ns'] is not None and silu1_dc['wns_ns']>=0 and silu1_dc['unmapped']==0,'silu_2lane_dc':silu2_dc['wns_ns'] is not None and silu2_dc['wns_ns']>=0 and silu2_dc['unmapped']==0,'full_attention_numerical_e2':False,'silu_lane_selection':False}
components_pass=all(checks[k] for k in ('controller_e1','controller_dc','attention_trace_bridge','block32_weight_e1','block32_weight_dc','silu_1lane_e1','silu_2lane_e1','silu_1lane_dc','silu_2lane_dc'))
r={'schema_version':1,'status':'BRIDGE_AND_COMPONENT_GATES_PASS_SINGLE_SIM_DIAGNOSTIC_IN_PROGRESS' if components_pass else 'FAIL_OR_INCOMPLETE','checks':checks,'L5.3':{'controller_dc':controller_dc,'block32_weight_dc':weight_dc,'q128_tasks':240,'q384_tasks':1872,'q1024_tasks':12672,'q1024_merge_rows':43008,'trace_bridge_status':bridge.get('status'),'full_numeric_status':'IN_PROGRESS_SINGLE_SIM_TIMEOUT_AFTER_FIRST_QK'},'L5.4':{'one_lane':silu1_dc,'two_lane':silu2_dc,'selection':'WAIT_MEASURED_MATRIX_PRODUCER_STALL','selection_rule':'one_lane_if_stall_le_2_percent_else_two_lane'},'single_sim_attempt':{'evidence':'reports/execution/l5_q128_single_sim_attempt_result.json','status':'TIMEOUT_AFTER_FIRST_QK','qk_steps':attempt.get('observed_progress',{}).get('steps_completed'),'rtl_cycles':attempt.get('observed_progress',{}).get('rtl_cycles'),'generated_rtl_modified':attempt.get('source_policy',{}).get('generated_rtl_modified')},'evidence_hashes':{'controller_e1':sha(controller_log),'trace_bridge':sha(bridge_path),'block32_weight_e1':sha(weight_log),'silu1_e1':sha(silu1_log),'silu2_e1':sha(silu2_log)}}
out=ROOT/'reports/execution/l5_3_l5_4_local_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status'].startswith('BRIDGE_AND_COMPONENT_GATES_PASS') else 1)
