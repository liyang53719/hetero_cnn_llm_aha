"""Future bounded normal-M2 C++ evidence contract. Pure stdlib; no simulation.
A successful synthetic log is not proof of execution. Real caller must separately
bind model/SV/harness/tool hashes, exit0 and cleanup; none are authorized here.
"""
import hashlib,re,importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location("m2_reference",Path(__file__).with_name("reference_events.py"));reference=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(reference)
PASS=re.compile(r'VERILATOR_CORE_CASE_PASS case=normal_m2 m=2 cycles=(\d+) groups=(\d+) qkAcceptedSteps=(\d+) accounting512Steps=(\d+) results=(\d+) dones=(\d+) scoreWrites=(\d+) targetPrefix= ownerAccepts=(\d+) pvRequests=(\d+) pvReturns=(\d+) requestHoldChecks=(\d+) holdChecksByPort=\(group,(\d+)\),\(memory,(\d+)\),\(pv,(\d+)\),\(step,(\d+)\) memoryAccepted=(\d+) memoryReturned=(\d+) outputBytes=(\d+) checkedMemory=(\d+) checkedPv=(\d+) checkedVector=(\d+) numerical_matrix_verified=false')
FIELDS=('cycles','groups','qkAcceptedSteps','accounting512Steps','results','dones','scoreWrites','ownerAccepts','pvRequests','pvReturns','requestHoldChecks','hold_group','hold_memory','hold_pv','hold_step','memoryAccepted','memoryReturned','outputBytes','checkedMemory','checkedPv','checkedVector')
OBS=re.compile(r'OBS cycle=(\d+) token=(\d+) head=(\d+) phase=(\d+) lane=(\d+) selected=(\d+) faults=(\d+) scoreWrite=(true|false) scoreIndex=(\d+) scoreData=(\d+) max=(\d+) resultReady=(true|false)')
READY='VERILATOR_CORE_SIM_READY case=normal_m2 m=2 scripted_matrix=true reset_clocks=3'
DONE=re.compile(r'VERILATOR_CORE_DONE case=normal_m2 completed=true total_rising_edges=(\d+) reset_clocks=3')
EXPECTED=dict(groups=24,qkAcceptedSteps=192,accounting512Steps=1824,results=24,dones=24,scoreWrites=36,ownerAccepts=1,pvRequests=288,pvReturns=288,memoryAccepted=960,memoryReturned=960,outputBytes=12288,checkedMemory=960,checkedPv=288,checkedVector=828)
def need(ok,reason):
 if not ok:raise ValueError(reason)
def check(raw):
 need(0<len(raw)<=2*1024*1024,'bounded log bytes');text=raw.decode('utf8');need('\x1b' not in text and '\x00' not in text,'plain UTF8')
 lines=text.splitlines();need(len(lines)<=10000 and all(len(x.encode())<=65536 for x in lines),'bounded lines')
 ready=[];passes=[];done=[];obs=[]
 for i,line in enumerate(lines):
  if line.startswith('VERILATOR_CORE_SIM_READY'):need(line==READY,'exact single-case readiness');ready.append(i)
  elif line.startswith('VERILATOR_CORE_CASE_PASS'):
   match=PASS.fullmatch(line);need(match is not None,'exact M2 terminal counters');passes.append((i,dict(zip(FIELDS,map(int,match.groups())))))
  elif line.startswith('VERILATOR_CORE_DONE'):
   match=DONE.fullmatch(line);need(match is not None,'exact final completion');done.append((i,int(match[1])))
  elif line.startswith('OBS'):
   match=OBS.fullmatch(line);need(match is not None and len(obs)<828,'bounded exact observation marker');obs.append((i,match.groups()))
  else:raise ValueError('unknown log line; do not conceal HDL/native/error diagnostics')
 need(len(ready)==len(passes)==len(done)==1,'one ready/pass/done');pi,counts=passes[0];di,total=done[0]
 need(ready[0]==0 and ready[0]<pi<di and di==len(lines)-1,'readiness/observations/terminal/final order')
 need(12<=counts['cycles']<=99997 and total==counts['cycles']+3<=100000,'3 reset + bounded body rising edges')
 for key,value in EXPECTED.items():need(counts[key]==value,'independent endpoint count '+key)
 hs=[counts['hold_'+x] for x in ('group','memory','pv','step')]
 need(all(0<=x<=counts['cycles'] for x in hs) and sum(hs)==counts['requestHoldChecks'] and 0<sum(hs)<=4*counts['cycles'],'observed request-hold counts')
 need(len(obs)==828,'independent M2 vector observations');expected=list(reference.vector_events(2));previous=-1;previous_pair=None;phase_counts={str(x):0 for x in (1,2,3,4)}
 for index,(li,g) in enumerate(obs):
  cycle,token,head,phase,lane,selected,faults=map(int,g[:7]);write=g[7]=='true';scoreindex,scoredata,maxscore=map(int,g[8:11]);rr=g[11]=='true'
  e=expected[index];pair=(e['token'],e['head'])
  need(ready[0]<li<pi and previous<cycle<counts['cycles'],'monotonic body event position')
  if pair==previous_pair:need(cycle==previous+1,'consecutive within-head ordered phases')
  need((token,head,phase,lane,selected,faults)==(e['token'],e['head'],e['phase'],e['lane'],e['selected'],0),'independent fixed M2 head/phase/lane/causal selection')
  need(not rr and write==(phase==4),'held result and actual score write-site retirement')
  if write:need(scoreindex==e['selected'] and scoredata==0,'ordered zero causal score retirement')
  need(maxscore==e['maxScore'],'pre-edge retirement max -Inf then zero')
  need(0<=scoreindex<1024 and 0<=scoredata<2**32 and 0<=maxscore<2**32,'observation widths')
  phase_counts[str(phase)]+=1;previous=cycle;previous_pair=pair
 return dict(status='PASS_LOG_CONTRACT_ONLY_CALLER_EXECUTION_PROOF_REQUIRED',counts=counts,total_rising_edges=total,explicit_reset_edges=3,observations=828,phase_counts=phase_counts,covered_request_hold_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]>0],uncovered_request_hold_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]==0],log_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),passive_memory_pv_assertions_are_harness_source_bound_not_external_transaction_trace=True,runtime_provenance_verified=False,matrix_numerical_pass=False,full128_rtl_pass=False,matrix_mac_utilization=None)
