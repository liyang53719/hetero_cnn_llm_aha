#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'work/results/l5_matrix_rev8a'
OUT=ROOT/'reports/execution/l5_revision8a_local_result.json'

def sha(path:Path)->str|None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def fields(path:Path)->dict[str,str]:
    if not path.is_file(): return {}
    return dict(line.strip().split('=',1) for line in path.read_text(errors='replace').splitlines() if '=' in line)

def chosen(name:str)->tuple[Path,dict[str,str]]:
    accepted=RES/name/'accepted_status.txt'
    if accepted.is_file(): return accepted,fields(accepted)
    for effort in ('high','normal'):
        p=RES/name/effort/'status.txt'
        if p.is_file(): return p,fields(p)
    return accepted,{}

lane_path,lane=chosen('lane');cluster_path,cluster=chosen('cluster16');front_path,front=chosen('front')
top_path=RES/'top/status.txt';top=fields(top_path)
gate_path=ROOT/'reports/execution/l5_revision8a_gate_compare_result.json'
gate=json.loads(gate_path.read_text()) if gate_path.is_file() else {}
markers={
 'rev7_vs_rev8a':('work/results/l5_matrix_context_revision8a/rev7_vs_rev8a/tb.log','BF16_CONTEXT_REV7_VS_REV8A_PASS compared=120000'),
 'main_e1':('work/results/l5_matrix_context_revision8a/e1/tb.log','BF16_CONTEXT_ARRAY_E1_PASS main_steps=1000000 random_steps=10000 contexts=4 lanes=512'),
 'adversarial_e1':('work/results/l5_matrix_context_revision8a/adversarial_e1/tb.log','BF16_CONTEXT_REV8_ADVERSARIAL_PASS steps=50000'),
}
marker_results={}
for name,(rel,needle) in markers.items():
    p=ROOT/rel;text=p.read_text(errors='replace') if p.is_file() else ''
    marker_results[name]={'status':'PASS' if needle in text else 'MISSING_OR_FAIL','log_sha256':sha(p)}

def number(d:dict[str,str],key:str):
    try:return float(d[key])
    except (KeyError,ValueError):return None
def qor_path(name:str)->Path:
    for effort in ('high','normal'):
        p=RES/name/effort/'qor.rpt'
        if p.is_file(): return p
    return RES/name/'qor.rpt'
def qor_number(path:Path,label:str):
    if not path.is_file(): return None
    for line in path.read_text(errors='replace').splitlines():
        if label in line:
            try:return float(line.split(':',1)[1].strip())
            except (IndexError,ValueError):return None
    return None
def area(name:str,d:dict[str,str]):
    return number(d,'CELL_AREA') if number(d,'CELL_AREA') is not None else qor_number(qor_path(name),'Cell Area:')
checks={
 'lane': bool(lane) and number(lane,'WORST_SLACK_NS') is not None and number(lane,'WORST_SLACK_NS')>=0 and lane.get('UNMAPPED_CELLS')=='0' and lane.get('UNRESOLVED_REFERENCES')=='0',
 'cluster16': bool(cluster) and number(cluster,'WORST_SLACK_NS') is not None and number(cluster,'WORST_SLACK_NS')>=0 and cluster.get('LANE_INSTANCES')=='16' and cluster.get('UNMAPPED_CELLS')=='0',
 'front': bool(front) and number(front,'WORST_SLACK_NS') is not None and number(front,'WORST_SLACK_NS')>=0 and front.get('UNMAPPED_CELLS')=='0',
 'top': bool(top) and number(top,'WORST_SLACK_NS') is not None and number(top,'WORST_SLACK_NS')>=0 and top.get('CLUSTER16_INSTANCES')=='32' and top.get('PHYSICAL_LANES')=='512' and top.get('UNMAPPED_CELLS')=='0' and top.get('UNRESOLVED_REFERENCES')=='0',
 'equivalence': gate.get('status')=='PASS',
 **{k:v['status']=='PASS' for k,v in marker_results.items()},
}
status='PASS' if all(checks.values()) else 'INCOMPLETE_OR_FAIL'
result={
 'schema_version':1,'revision':'8A','status':status,'checks':checks,
 'candidate':'early_context_bank_commit_cluster16_front_control',
 'lane':{'status_path':str(lane_path.relative_to(ROOT)) if lane_path.exists() else None,'wns_ns':number(lane,'WORST_SLACK_NS'),'cell_area':area('lane',lane),'status_sha256':sha(lane_path)},
 'cluster16':{'status_path':str(cluster_path.relative_to(ROOT)) if cluster_path.exists() else None,'wns_ns':number(cluster,'WORST_SLACK_NS'),'cell_area':area('cluster16',cluster),'lane_instances':cluster.get('LANE_INSTANCES'),'status_sha256':sha(cluster_path)},
 'front_control':{'status_path':str(front_path.relative_to(ROOT)) if front_path.exists() else None,'wns_ns':number(front,'WORST_SLACK_NS'),'cell_area':area('front',front),'status_sha256':sha(front_path)},
 'structural_h3':{'wns_ns':number(top,'WORST_SLACK_NS'),'cell_area':area('top',top),'cluster_instances':top.get('CLUSTER16_INSTANCES'),'physical_lanes':top.get('PHYSICAL_LANES'),'max_transition_violations':qor_number(qor_path('top'),'Max Trans Violations:'),'max_cap_violations':qor_number(qor_path('top'),'Max Cap Violations:'),'status_sha256':sha(top_path)},
 'equivalence':gate,'e1':marker_results,
 'closure_rule':'L5.2 closes only if all checks are true; this remains component-level DC, not post-route signoff.',
}
OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if status=='PASS' else 1)
