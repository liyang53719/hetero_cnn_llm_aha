#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def has(p,s):return p.is_file() and s in p.read_text(errors='replace')
source=ROOT/'reports/execution/l5_revision8b_b_source_contract_result.json'
main=ROOT/'work/results/l5_matrix_context_revision8b_b/e1/tb.log'
adv=ROOT/'work/results/l5_matrix_context_revision8b_b/adversarial_e1/tb.log'
compare=ROOT/'work/results/l5_matrix_context_revision8b_b/rev8b_a_vs_rev8b_b/tb.log'
checks={'source_contract':source.is_file() and json.loads(source.read_text())['status']=='PASS','main_e1':has(main,'main_steps=1000000 random_steps=10000 contexts=5 lanes=512'),'adversarial_e1':has(adv,'steps=50000 cycles=') and has(adv,'contexts=5 lanes=512'),'rev8b_a_compare':has(compare,'compared=120000 latency_shift=1 lanes=512'),'lane_dc':False,'mapped_equivalence':False,'cluster_dc':False,'front_dc':False,'broadcast_dc':False,'h3':False,'postmap_e1':False}
r={'schema_version':1,'revision':'8B-B','status':'FUNCTIONAL_E1_PASS_WAIT_E4' if all(checks[k] for k in ('source_contract','main_e1','adversarial_e1','rev8b_a_compare')) else 'IN_PROGRESS_OR_FAIL','checks':checks,'architecture':{'fma_stages':5,'contexts':5,'internal_context_tag_bits':3,'lanes':512,'clock_period_ns':1.0},'evidence_hashes':{'source':sha(source),'main_e1':sha(main),'adversarial_e1':sha(adv),'compare':sha(compare)}}
out=ROOT/'reports/execution/l5_revision8b_b_local_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status']=='FUNCTIONAL_E1_PASS_WAIT_E4' else 1)
