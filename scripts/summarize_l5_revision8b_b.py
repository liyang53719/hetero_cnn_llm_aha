#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def has(p:Path,s:str):return p.is_file() and s in p.read_text(errors='replace')
def status(p:Path):return dict(x.split('=',1) for x in p.read_text().splitlines() if '=' in x) if p.is_file() else {}
def metric(p:Path,label:str,integer=False):
 if not p.is_file():return None
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+(?:\.[0-9]+)?)',p.read_text(errors='replace'))
 if not m:return 0 if integer else None
 return int(float(m.group(1))) if integer else float(m.group(1))
def component(name:str):
 base=ROOT/'work/results/l5_matrix_rev8b_b'/name;s=status(base/'accepted_status.txt');q=base/'accepted_qor.rpt'
 return {'status_path':str((base/'accepted_status.txt').relative_to(ROOT)),'wns_ns':float(s['WORST_SLACK_NS']) if s else None,'area':metric(q,'Cell Area'),'max_transition':metric(q,'Max Trans Violations',True),'max_cap':metric(q,'Max Cap Violations',True),'unmapped':int(s['UNMAPPED_CELLS']) if s else None,'unresolved':int(s['UNRESOLVED_REFERENCES']) if s else None,'effort':s.get('EFFORT'),'sha256':sha(base/'accepted_status.txt')}
source=ROOT/'reports/execution/l5_revision8b_b_source_contract_result.json'
main=ROOT/'work/results/l5_matrix_context_revision8b_b/e1/tb.log';adv=ROOT/'work/results/l5_matrix_context_revision8b_b/adversarial_e1/tb.log';compare=ROOT/'work/results/l5_matrix_context_revision8b_b/rev8b_a_vs_rev8b_b/tb.log'
post_main=ROOT/'work/results/l5_matrix_context_revision8b_b/postmap_e1/tb.log';post_adv=ROOT/'work/results/l5_matrix_context_revision8b_b/postmap_adversarial_e1/tb.log'
gate_path=ROOT/'reports/execution/l5_revision8b_b_lane_gate_compare_result.json';gate=json.loads(gate_path.read_text()) if gate_path.is_file() else {}
h3_path=ROOT/'reports/execution/l5_revision8b_b_h3_result.json';h3=json.loads(h3_path.read_text()) if h3_path.is_file() else {}
h3['cell_area']=metric(ROOT/'work/results/l5_matrix_rev8b_b/top/qor.rpt','Cell Area')
components={name:component(name) for name in ('lane','cluster','front','broadcast','flags')}
component_pass={name:(v['wns_ns'] is not None and v['wns_ns']>=0 and v['max_transition']==0 and v['max_cap']==0 and v['unmapped']==0 and v['unresolved']==0) for name,v in components.items()}
checks={'source_contract':source.is_file() and json.loads(source.read_text())['status']=='PASS','main_e1':has(main,'main_steps=1000000 random_steps=10000 contexts=5 lanes=512'),'adversarial_e1':has(adv,'steps=50000 cycles=') and has(adv,'contexts=5 lanes=512'),'rev8b_a_compare':has(compare,'compared=120000 latency_shift=1 lanes=512'),'lane_dc':component_pass['lane'],'mapped_equivalence':gate.get('status')=='PASS' and gate.get('mismatches')==0 and gate.get('unknown_outputs')==0,'cluster_dc':component_pass['cluster'],'front_dc':component_pass['front'],'broadcast_dc':component_pass['broadcast'],'flags_dc':component_pass['flags'],'h3':h3.get('status')=='PASS' and h3.get('wns_ns',-1)>=0 and h3.get('max_transition')==0 and h3.get('max_cap')==0 and h3.get('unmapped')==0 and h3.get('unresolved')==0 and h3.get('clusters')==32 and h3.get('lanes')==512,'postmap_e1':has(post_main,'main_steps=1000000 random_steps=10000 contexts=5 lanes=512') and has(post_adv,'steps=50000 cycles=')}
r={'schema_version':1,'revision':'8B-B','status':'PASS' if all(checks.values()) else 'IN_PROGRESS_OR_FAIL','checks':checks,'architecture':{'fma_stages':5,'contexts':5,'internal_context_tag_bits':3,'lanes':512,'clock_period_ns':1.0,'completion_fifo_depth':5},'components':components,'h3':h3,'evidence_hashes':{'source':sha(source),'main_e1':sha(main),'adversarial_e1':sha(adv),'compare':sha(compare),'lane_gate_compare':sha(gate_path),'h3':sha(h3_path),'postmap_e1':sha(post_main),'postmap_adversarial':sha(post_adv)}}
out=ROOT/'reports/execution/l5_revision8b_b_local_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status']=='PASS' else 1)
