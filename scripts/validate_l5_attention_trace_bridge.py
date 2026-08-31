#!/usr/bin/env python3
from __future__ import annotations
from collections import defaultdict
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
trace=ROOT/'work/results/l5_blocked_attention_controller_e1/task_trace.txt'
controller_log=ROOT/'work/results/l5_blocked_attention_controller_e1/tb.log'
mlo_log=ROOT/'work/results/l5_q128_mlo/tb.log'
e0=json.loads((ROOT/'reports/execution/l5_blocked_attention_controller_e0_result.json').read_text())
records=defaultdict(lambda:{'QK':[],'SFU':[],'PV':[]})
for line in trace.read_text().splitlines():
 fields=line.split();port=fields[0];seq=int(fields[1]);kind=int(fields[2]);values=tuple(map(int,fields[3:12]))
 name='SFU' if port=='S' else ('QK' if kind==0 else 'PV');records[seq][name].append(values)
expected_tasks={128:240,384:1872,1024:12672};expected_updates={128:99072,384:887040,1024:6297600};expected_merges={128:0,384:4608,1024:43008}
cases={}
for seq in (128,384,1024):
 qk=records[seq]['QK'];sfu=records[seq]['SFU'];pv=records[seq]['PV']
 if not(len(qk)==len(sfu)==len(pv)==expected_tasks[seq]):raise SystemExit(f'task count {seq}')
 for index,(a,b,c) in enumerate(zip(qk,sfu,pv,strict=True)):
  if a!=b or a!=c or a[0]!=index:raise SystemExit(f'metadata/order {seq} {index}')
 updates=0;merge_rows=0
 for task,qt,kt,qh,kh,rows,close,merge,last in qk:
  qbase=qt*16;kbase=kt*32
  for row in range(rows):updates+=max(0,min(32,qbase+row+1-kbase))
  if merge:merge_rows+=rows
 if updates!=expected_updates[seq] or merge_rows!=expected_merges[seq]:raise SystemExit(f'coverage {seq} {updates} {merge_rows}')
 cases[str(seq)]={'tasks':len(qk),'causal_updates':updates,'merge_rows':merge_rows,'metadata_order':'PASS'}
controller_text=controller_log.read_text();service={int(s):int(c) for s,c in re.findall(r'CASE_PASS seq=(128|384|1024).*?service_cycles=([0-9]+)',controller_text)}
if set(service)!={128,384,1024}:raise SystemExit('service curves missing')
for seq in service:cases[str(seq)]['controller_service_cycles']=service[seq]
mlo=mlo_log.read_text();match=re.search(r'L5_Q_PREFILL_MLO_PASS workload=128 updates=99072 .*?total_cycles=([0-9]+).*?o_fnv64=([0-9a-f]+) attention_fnv64=([0-9a-f]+)',mlo)
if not match:raise SystemExit('q128 numerical RTL evidence missing')
r={'schema_version':1,'status':'PASS_TRACE_COUPLED_BRIDGE','evidence_class':'controller_RTL_trace_plus_q128_numerical_RTL_E2_bridge_not_single_integrated_sim','cases':cases,'q128_numerical_RTL':{'status':'PASS','cycles':int(match.group(1)),'o_fnv64':match.group(2),'attention_fnv64':match.group(3),'threshold':0.002},'score_DDR_bytes':0,'probability_DDR_bytes':0,'controller_trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),'remaining_gate':'single_sim_controller_to_Revision8B_B_QK_Block32_weights_PV_Block128_merge'}
if e0['cases']['1024']['nominal']['score_ddr_bytes'] or e0['cases']['1024']['nominal']['probability_ddr_bytes']:raise SystemExit('DDR policy')
out=ROOT/'reports/execution/l5_attention_trace_bridge_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
