#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def text(path:Path)->str:return path.read_text(errors='replace') if path.is_file() else ''
def sha(path:Path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
def load(relative:str):
 path=ROOT/relative;return json.loads(path.read_text()) if path.is_file() else {}
def status(path:Path):return dict(line.split('=',1) for line in text(path).splitlines() if '=' in line)
def area(path:Path):
 m=re.search(r'Cell Area:\s*([0-9.]+)',text(path));return float(m.group(1)) if m else None
def power_mw(path:Path,label:str):
 m=re.search(rf'{re.escape(label)}\s*=\s*([0-9.]+)\s*([mun]?W)',text(path))
 return None if not m else float(m.group(1))*{'W':1000.,'mW':1.,'uW':.001,'nW':.000001}[m.group(2)]
def dc_result(directory:Path):
 s=status(directory/'status.txt');p=directory/'power_estimate.rpt'
 return {'wns_ns':float(s['WORST_SLACK_NS']) if s else None,'unmapped':int(s['UNMAPPED_CELLS']) if s else None,'cell_area':area(directory/'qor.rpt'),'dynamic_power_mw_estimate':power_mw(p,'Total Dynamic Power'),'leakage_power_mw_estimate':power_mw(p,'Cell Leakage Power'),'evidence_class':'DC_WLM_vectorless_power','status_sha256':sha(directory/'status.txt')}
controller_log=ROOT/'work/results/l5_blocked_attention_controller_e1/tb.log';silu1_log=ROOT/'work/results/l5_silu_lut_e1/lanes1/tb.log';silu2_log=ROOT/'work/results/l5_silu_lut_e1/lanes2/tb.log';weight_log=ROOT/'work/results/l5_block32_softmax_weight_e1/tb.log'
controller_dc=dc_result(ROOT/'work/results/l5_blocked_attention_controller_dc');silu1_dc=dc_result(ROOT/'work/results/l5_silu_lut_dc/lanes1');silu2_dc=dc_result(ROOT/'work/results/l5_silu_lut_dc/lanes2');weight_dc=dc_result(ROOT/'work/results/l5_block32_softmax_weight_dc')
bridge=load('reports/execution/l5_attention_trace_bridge_result.json');q128=load('reports/execution/l5_q128_single_sim_attempt_result.json');q384=load('reports/execution/l5_q384_sampled_e2_result.json');q1024=load('reports/execution/l5_q1024_reviewed_e2_result.json');stress=load('reports/execution/l5_attention_stress_service_result.json');selection=load('reports/execution/l5_silu_lane_selection_result.json')
checks={'controller_e1':all(x in text(controller_log) for x in ('seq=128 tasks=240 merges=0','seq=384 tasks=1872 merges=4608','seq=1024 tasks=12672 merges=43008','TB_PASS')),'controller_dc':controller_dc['wns_ns'] is not None and controller_dc['wns_ns']>=0 and controller_dc['unmapped']==0,'attention_trace_bridge':bridge.get('status')=='PASS_TRACE_COUPLED_BRIDGE','block32_weight_e1':'BLOCK32_SOFTMAX_WEIGHT_PASS rows=2 weights=64' in text(weight_log),'block32_weight_dc':weight_dc['wns_ns'] is not None and weight_dc['wns_ns']>=0 and weight_dc['unmapped']==0,'silu_1lane_e1':'TB_PASS LANES=1 cases=4096' in text(silu1_log),'silu_2lane_e1':'TB_PASS LANES=2 cases=4096' in text(silu2_log),'silu_1lane_dc':silu1_dc['wns_ns'] is not None and silu1_dc['wns_ns']>=0 and silu1_dc['unmapped']==0,'silu_2lane_dc':silu2_dc['wns_ns'] is not None and silu2_dc['wns_ns']>=0 and silu2_dc['unmapped']==0,'full_attention_numerical_e2':q128.get('status')=='PASS_Q128_SINGLE_PROCESS_E2' and q384.get('status')=='PASS_Q384_SAMPLED_E2' and q1024.get('status')=='PASS_Q1024_REVIEWED_E2','silu_lane_selection':selection.get('status')=='PASS' and selection.get('selected_lanes')==1}
components=all(checks[k] for k in checks if k not in ('full_attention_numerical_e2','silu_lane_selection'));passed=components and checks['full_attention_numerical_e2'] and checks['silu_lane_selection'] and stress.get('status')=='PASS'
r={'schema_version':1,'status':'L5_3_L5_4_PASS_L5_5_OPEN' if passed else 'FAIL_OR_INCOMPLETE','checks':checks,'L5.3':{'status':'PASS' if checks['full_attention_numerical_e2'] and stress.get('status')=='PASS' else 'OPEN','controller_dc':controller_dc,'block32_weight_dc':weight_dc,'q128_tasks':240,'q384_tasks':1872,'q1024_tasks':12672,'q1024_merge_rows':43008,'stress_service_evidence':'reports/execution/l5_attention_stress_service_result.json'},'L5.4':{'status':'PASS' if checks['silu_lane_selection'] else 'OPEN','one_lane':silu1_dc,'two_lane':silu2_dc,'selection':'ONE_LANE' if checks['silu_lane_selection'] else 'OPEN','selection_evidence':'reports/execution/l5_silu_lane_selection_result.json','producer_stall_fraction':selection.get('candidates',{}).get('one',{}).get('producer_stall_fraction')},'evidence_hashes':{'controller_e1':sha(controller_log),'block32_weight_e1':sha(weight_log),'silu1_e1':sha(silu1_log),'silu2_e1':sha(silu2_log)}}
out=ROOT/'reports/execution/l5_3_l5_4_local_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if passed else 1)
