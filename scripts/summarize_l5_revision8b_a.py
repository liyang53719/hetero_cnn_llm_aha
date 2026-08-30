#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(path:Path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
def marker(path:Path,text:str): return path.is_file() and text in path.read_text(errors='replace')
def status(path:Path): return dict(x.split('=',1) for x in path.read_text().splitlines() if '=' in x) if path.is_file() else {}
def qor_metric(path:Path,label:str):
 if not path.is_file(): return None
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+)',path.read_text(errors='replace'));return int(m.group(1)) if m else None
def qor_float(path:Path,label:str):
 if not path.is_file(): return None
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+(?:\.[0-9]+)?)',path.read_text(errors='replace'));return float(m.group(1)) if m else None
def chosen(component:str):
 base=ROOT/'work/results/l5_matrix_rev8b_a'/component
 for name in ('accepted','high','normal','dc'):
  status_path=base/(f'{name}_status.txt' if name=='accepted' else f'{name}/status.txt')
  qor_path=base/(f'{name}_qor.rpt' if name=='accepted' else f'{name}/qor.rpt')
  if status_path.is_file(): return status_path,qor_path
 return base/'missing.status',base/'missing.qor'

source=ROOT/'reports/execution/l5_revision8b_a_source_contract_result.json'
broadcast,bq=chosen('broadcast32')
operand,oq=chosen('operand_distribution')
top,tq=chosen('top')
decision=ROOT/'reports/execution/l5_revision8b_a_phase_decision.json'
s_b=status(broadcast);s_o=status(operand);s_t=status(top)
gate_path=ROOT/'reports/execution/l5_revision8b_a_broadcast_gate_compare_result.json'
gate=json.loads(gate_path.read_text()) if gate_path.is_file() else {}
phase=json.loads(decision.read_text()) if decision.is_file() else None
checks={
 'source_contract': source.is_file() and json.loads(source.read_text())['status']=='PASS',
 'broadcast_e1': marker(ROOT/'work/results/l5_matrix_rev8b_a/broadcast_e1/tb.log','L5_REV8B_A_BROADCAST_E1_PASS operations=100000'),
 'rev8a_vs_rev8b_a': marker(ROOT/'work/results/l5_matrix_context_revision8b_a/rev8a_vs_rev8b_a/tb.log','L5_REV8A_VS_REV8B_A_PASS compared=120000'),
 'main_e1': marker(ROOT/'work/results/l5_matrix_context_revision8b_a/e1/tb.log','BF16_CONTEXT_ARRAY_E1_PASS main_steps=1000000 random_steps=10000'),
 'adversarial_e1': marker(ROOT/'work/results/l5_matrix_context_revision8b_a/adversarial_e1/tb.log','BF16_CONTEXT_REV8_ADVERSARIAL_PASS steps=50000'),
 'broadcast_dc': bool(s_b) and float(s_b['WORST_SLACK_NS'])>=0 and qor_metric(bq,'Max Trans Violations')==0 and qor_metric(bq,'Max Cap Violations')==0,
 'broadcast_gate_compare': gate.get('status')=='PASS' and gate.get('mismatches')==0 and gate.get('unknown_outputs')==0,
 'operand_distribution': bool(s_o) and float(s_o['WORST_SLACK_NS'])>=0 and qor_metric(oq,'Max Trans Violations')==0 and qor_metric(oq,'Max Cap Violations')==0,
 'h3_drc_clean': bool(s_t) and qor_metric(tq,'Max Trans Violations')==0 and qor_metric(tq,'Max Cap Violations')==0 and s_t.get('UNMAPPED_CELLS')=='0' and s_t.get('UNRESOLVED_REFERENCES')=='0',
 'h3': bool(s_t) and float(s_t['WORST_SLACK_NS'])>=0 and qor_metric(tq,'Max Trans Violations')==0 and qor_metric(tq,'Max Cap Violations')==0,
}
functional=all(checks[k] for k in ('source_contract','broadcast_e1','rev8a_vs_rev8b_a','main_e1','adversarial_e1','broadcast_dc','broadcast_gate_compare','operand_distribution','h3_drc_clean'))
if all(checks.values()): result_status='PASS'
elif functional and phase and phase.get('decision')=='TRIGGER_REVISION8B_B_5STAGE_5CONTEXT': result_status='TRIGGER_REVISION8B_B'
else: result_status='IN_PROGRESS_OR_FAIL'
r={'schema_version':1,'revision':'8B-A','status':result_status,'checks':checks,'broadcast':{'wns_ns':float(s_b['WORST_SLACK_NS']) if s_b else None,'mapped_cells':int(s_b['MAPPED_CELL_COUNT']) if s_b else None,'max_transition':qor_metric(bq,'Max Trans Violations'),'max_cap':qor_metric(bq,'Max Cap Violations')},'operand_distribution':{'wns_ns':float(s_o['WORST_SLACK_NS']) if s_o else None,'mapped_cells':int(s_o['MAPPED_CELL_COUNT']) if s_o else None,'max_transition':qor_metric(oq,'Max Trans Violations'),'max_cap':qor_metric(oq,'Max Cap Violations')},'h3':{'wns_ns':float(s_t['WORST_SLACK_NS']) if s_t else None,'cell_area':float(s_t['CELL_AREA']) if s_t and s_t.get('CELL_AREA') else qor_float(tq,'Cell Area'),'max_transition':qor_metric(tq,'Max Trans Violations'),'max_cap':qor_metric(tq,'Max Cap Violations'),'unmapped':int(s_t['UNMAPPED_CELLS']) if s_t else None,'unresolved':int(s_t['UNRESOLVED_REFERENCES']) if s_t else None},'phase_decision':phase,'evidence_hashes':{'source_contract':sha(source),'broadcast_status':sha(broadcast),'operand_status':sha(operand),'h3_status':sha(top),'compare_log':sha(ROOT/'work/results/l5_matrix_context_revision8b_a/rev8a_vs_rev8b_a/tb.log'),'main_e1_log':sha(ROOT/'work/results/l5_matrix_context_revision8b_a/e1/tb.log'),'adversarial_log':sha(ROOT/'work/results/l5_matrix_context_revision8b_a/adversarial_e1/tb.log')}}
out=ROOT/'reports/execution/l5_revision8b_a_local_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if result_status in {'PASS','TRIGGER_REVISION8B_B'} else 1)
