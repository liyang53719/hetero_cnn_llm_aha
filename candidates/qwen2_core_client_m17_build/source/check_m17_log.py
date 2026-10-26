"""Future bounded normal-M17 C++ evidence contract. Pure stdlib; no simulation.
A successful synthetic log is not proof of execution. Real caller must separately
bind model/SV/harness/tool hashes, exit0 and cleanup; none are authorized here.
"""
import hashlib,re,importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location("m17_reference",Path(__file__).with_name("reference_events.py"));reference=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(reference)
PASS=re.compile(r'VERILATOR_CORE_CASE_PASS case=normal_m17 m=17 cycles=(\d+) groups=(\d+) qkAcceptedSteps=(\d+) accounting512Steps=(\d+) results=(\d+) dones=(\d+) scoreWrites=(\d+) targetPrefix=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16 ownerAccepts=(\d+) pvRequests=(\d+) pvReturns=(\d+) requestHoldChecks=(\d+) holdChecksByPort=\(group,(\d+)\),\(memory,(\d+)\),\(pv,(\d+)\),\(step,(\d+)\) memoryAccepted=(\d+) memoryReturned=(\d+) outputBytes=(\d+) checkedGroups=(\d+) checkedMemory=(\d+) checkedPv=(\d+) checkedVector=(\d+) numerical_matrix_verified=false')
FIELDS=('cycles','groups','qkAcceptedSteps','accounting512Steps','results','dones','scoreWrites','ownerAccepts','pvRequests','pvReturns','requestHoldChecks','hold_group','hold_memory','hold_pv','hold_step','memoryAccepted','memoryReturned','outputBytes','checkedGroups','checkedMemory','checkedPv','checkedVector')
OBS=re.compile(r'OBS cycle=(\d+) token=(\d+) head=(\d+) keyBase=(\d+) phase=(\d+) lane=(\d+) selected=(\d+) faults=(\d+) scoreWrite=(true|false) scoreIndex=(\d+) scoreData=(\d+) max=(\d+) resultReady=(true|false)')
READY='VERILATOR_CORE_SIM_READY case=normal_m17 m=17 scripted_matrix=true reset_clocks=3'
DONE=re.compile(r'VERILATOR_CORE_DONE case=normal_m17 completed=true total_rising_edges=(\d+) reset_clocks=3')
EXPECTED=dict(groups=216,qkAcceptedSteps=1728,accounting512Steps=28512,results=216,dones=216,scoreWrites=1836,ownerAccepts=1,pvRequests=14688,pvReturns=14688,memoryAccepted=32640,memoryReturned=32640,outputBytes=104448,checkedGroups=216,checkedMemory=32640,checkedPv=14688,checkedVector=8964)
def need(ok,reason):
 if not ok:raise ValueError(reason)
def check(raw):
 need(0<len(raw)<=2*1024*1024,'bounded log bytes');text=raw.decode('utf8');need('\x1b' not in text and '\x00' not in text,'plain UTF8')
 lines=text.splitlines();need(len(lines)<=10000 and all(len(x.encode())<=65536 for x in lines),'bounded lines')
 ready=[];passes=[];done=[];obs=[]
 for i,line in enumerate(lines):
  if line.startswith('VERILATOR_CORE_SIM_READY'):need(line==READY,'exact single-case readiness');ready.append(i)
  elif line.startswith('VERILATOR_CORE_CASE_PASS'):
   match=PASS.fullmatch(line);need(match is not None,'exact M17 terminal counters');passes.append((i,dict(zip(FIELDS,map(int,match.groups())))))
  elif line.startswith('VERILATOR_CORE_DONE'):
   match=DONE.fullmatch(line);need(match is not None,'exact final completion');done.append((i,int(match[1])))
  elif line.startswith('OBS'):
   match=OBS.fullmatch(line);need(match is not None and len(obs)<8964,'bounded exact observation marker');obs.append((i,match.groups()))
  else:raise ValueError('unknown log line; do not conceal HDL/native/error diagnostics')
 need(len(ready)==len(passes)==len(done)==1,'one ready/pass/done');pi,counts=passes[0];di,total=done[0]
 need(ready[0]==0 and ready[0]<pi<di and di==len(lines)-1,'readiness/observations/terminal/final order')
 need(12<=counts['cycles']<=499997 and total==counts['cycles']+3<=500000,'3 reset + bounded body rising edges')
 for key,value in EXPECTED.items():need(counts[key]==value,'independent endpoint count '+key)
 hs=[counts['hold_'+x] for x in ('group','memory','pv','step')]
 need(all(0<=x<=counts['cycles'] for x in hs) and sum(hs)==counts['requestHoldChecks'] and 0<sum(hs)<=4*counts['cycles'],'observed request-hold counts')
 need(len(obs)==8964,'independent M17 vector observations');expected=list(reference.vector_events());previous=-1;previous_pair=None;phase_counts={str(x):0 for x in (1,2,3,4)}
 for index,(li,g) in enumerate(obs):
  cycle,token,head,keybase,phase,lane,selected,faults=map(int,g[:8]);write=g[8]=='true';scoreindex,scoredata,maxscore=map(int,g[9:12]);rr=g[12]=='true'
  e=expected[index];pair=(token,head,keybase)
  need(ready[0]<li<pi and previous<cycle<counts['cycles'],'monotonic body event position')
  if pair==previous_pair:need(cycle==previous+1,'consecutive within-chunk ordered phases')
  need((token,head,keybase,phase,lane,selected,faults)==(e['token'],e['head'],e['keyBase'],e['phase'],e['lane'],e['selected'],0),'independent fixed M17 head/global-base/phase/lane/local-selection')
  need(not rr and write==(phase==4),'held result and actual score write-site retirement')
  if write:need(scoreindex==e['scoreIndex'] and scoredata==0,'ordered zero causal score retirement')
  need(maxscore==e['maxScore'],'pre-edge max inherited across chunk; -Inf only before global first retire')
  need(0<=scoreindex<1024 and 0<=scoredata<2**32 and 0<=maxscore<2**32,'observation widths')
  phase_counts[str(phase)]+=1;previous=cycle;previous_pair=pair
 return dict(status='PASS_LOG_CONTRACT_ONLY_CALLER_EXECUTION_PROOF_REQUIRED',counts=counts,total_rising_edges=total,explicit_reset_edges=3,observations=8964,phase_counts=phase_counts,covered_request_hold_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]>0],uncovered_request_hold_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]==0],log_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),passive_memory_pv_assertions_are_harness_source_bound_not_external_transaction_trace=True,runtime_provenance_verified=False,matrix_numerical_pass=False,full128_rtl_pass=False,matrix_mac_utilization=None)
