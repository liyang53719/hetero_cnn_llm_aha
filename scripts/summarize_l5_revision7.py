#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RESULT=ROOT/'work/results/l5_matrix_hier_dc/rev7';OUT=ROOT/'reports/execution/l5_matrix_context_revision7_result.json'
def fields(path):return dict(line.strip().split('=',1) for line in path.read_text().splitlines() if '=' in line)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
normal=RESULT/'lane/normal';high=RESULT/'lane/high';lane_dir=high if (high/'status.txt').is_file() else normal
lane=fields(lane_dir/'status.txt') if (lane_dir/'status.txt').is_file() else {};top_dir=RESULT/'context';top=fields(top_dir/'status.txt') if (top_dir/'status.txt').is_file() else {}
eq_path=RESULT/'equivalence/result.json';eq=json.loads(eq_path.read_text()) if eq_path.is_file() else {'status':'MISSING'};e1_log=ROOT/'work/results/l5_matrix_context_array/tb.log';e1_pass=e1_log.is_file() and 'BF16_CONTEXT_ARRAY_E1_PASS main_steps=1000000 random_steps=10000 contexts=4 lanes=512' in e1_log.read_text(errors='replace')
def f(d,k):
 try:return float(d[k])
 except:return None
status='PASS' if f(lane,'WORST_SLACK_NS') is not None and f(lane,'WORST_SLACK_NS')>=0 and f(top,'WORST_SLACK_NS') is not None and f(top,'WORST_SLACK_NS')>=0 and eq.get('status')=='PASS' and e1_pass else 'INCOMPLETE'
result={'schema_version':1,'revision':7,'status':status,'lane':{'wns_ns':f(lane,'WORST_SLACK_NS'),'unmapped':lane.get('UNMAPPED_CELLS'),'unresolved':lane.get('UNRESOLVED_REFERENCES'),'area':f(lane,'CELL_AREA'),'source_remap':lane.get('SOURCE_REMAP'),'leaf_ddcs_read':lane.get('LEAF_DDCS_READ'),'retiming_authorized':lane.get('RETIMING_AUTHORIZED'),'status_sha256':digest(lane_dir/'status.txt') if (lane_dir/'status.txt').is_file() else None},'equivalence':eq,'full_context_top':{'wns_ns':f(top,'WORST_SLACK_NS'),'unmapped':top.get('UNMAPPED_CELLS'),'unresolved':top.get('UNRESOLVED_REFERENCES'),'context_lane_instances':top.get('INSTANCES_bf16_context_fma_pipeline_lane4')},'e1':{'status':'PASS' if e1_pass else 'MISSING_OR_FAIL','log_sha256':digest(e1_log) if e1_log.is_file() else None},'closure_rule':'L5.2 closes only when lane E4, equivalence, 512-lane E1 rerun, and structural H3 E4 all pass.'}
OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True));raise SystemExit(0 if status=='PASS' else 1)
