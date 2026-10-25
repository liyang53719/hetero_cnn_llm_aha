"""Future bounded normal-M1 C++ evidence contract. Pure stdlib; no simulation.
A successful synthetic log is not proof of execution. Real caller must separately
bind model/SV/harness/tool hashes, exit0 and cleanup; none are authorized here.
"""
import hashlib,re
PASS=re.compile(r'VERILATOR_CORE_CASE_PASS case=normal_m1 m=1 cycles=(\d+) groups=(\d+) qkAcceptedSteps=(\d+) accounting512Steps=(\d+) results=(\d+) dones=(\d+) scoreWrites=(\d+) targetPrefix= ownerAccepts=(\d+) pvRequests=(\d+) pvReturns=(\d+) requestHoldChecks=(\d+) holdChecksByPort=\(group,(\d+)\),\(memory,(\d+)\),\(pv,(\d+)\),\(step,(\d+)\) memoryAccepted=(\d+) memoryReturned=(\d+) outputBytes=(\d+) numerical_matrix_verified=false')
FIELDS=('cycles','groups','qkAcceptedSteps','accounting512Steps','results','dones','scoreWrites','ownerAccepts','pvRequests','pvReturns','requestHoldChecks','hold_group','hold_memory','hold_pv','hold_step','memoryAccepted','memoryReturned','outputBytes')
OBS=re.compile(r'OBS cycle=(\d+) token=(\d+) head=(\d+) phase=(\d+) lane=(\d+) selected=(\d+) faults=(\d+) scoreWrite=(true|false) scoreIndex=(\d+) scoreData=(\d+) max=(\d+) resultReady=(true|false)')
READY='VERILATOR_CORE_SIM_READY case=normal_m1 m=1 scripted_matrix=true reset_clocks=3'
DONE=re.compile(r'VERILATOR_CORE_DONE case=normal_m1 completed=true total_rising_edges=(\d+) reset_clocks=3')
EXPECTED=dict(groups=12,qkAcceptedSteps=96,accounting512Steps=864,results=12,dones=12,scoreWrites=12,ownerAccepts=1,pvRequests=96,pvReturns=96,memoryAccepted=384,memoryReturned=384,outputBytes=6144)
def need(ok,reason):
 if not ok:raise ValueError(reason)
def check(raw):
 need(0<len(raw)<=2*1024*1024,'bounded log bytes');text=raw.decode('utf8');need('\x1b' not in text and '\x00' not in text,'plain UTF8')
 lines=text.splitlines();need(len(lines)<=10000 and all(len(x.encode())<=65536 for x in lines),'bounded lines')
 ready=[];passes=[];done=[];obs=[]
 for i,line in enumerate(lines):
  if line.startswith('VERILATOR_CORE_SIM_READY'):need(line==READY,'exact single-case readiness');ready.append(i)
  elif line.startswith('VERILATOR_CORE_CASE_PASS'):
   match=PASS.fullmatch(line);need(match is not None,'exact M1 terminal counters');passes.append((i,dict(zip(FIELDS,map(int,match.groups())))))
  elif line.startswith('VERILATOR_CORE_DONE'):
   match=DONE.fullmatch(line);need(match is not None,'exact final completion');done.append((i,int(match[1])))
  elif line.startswith('OBS'):
   match=OBS.fullmatch(line);need(match is not None and len(obs)<408,'bounded exact observation marker');obs.append((i,match.groups()))
  else:raise ValueError('unknown log line; do not conceal HDL/native/error diagnostics')
 need(len(ready)==len(passes)==len(done)==1,'one ready/pass/done');pi,counts=passes[0];di,total=done[0]
 need(ready[0]==0 and ready[0]<pi<di and di==len(lines)-1,'readiness/observations/terminal/final order')
 need(12<=counts['cycles']<=99997 and total==counts['cycles']+3<=100000,'3 reset + bounded body rising edges')
 for key,value in EXPECTED.items():need(counts[key]==value,'independent endpoint count '+key)
 hs=[counts['hold_'+x] for x in ('group','memory','pv','step')]
 need(all(0<=x<=counts['cycles'] for x in hs) and sum(hs)==counts['requestHoldChecks'] and 0<sum(hs)<=4*counts['cycles'],'observed request-hold counts')
 need(len(obs)==408,'12 heads x 34 ordered vector observations');previous=-1;phase_counts={str(x):0 for x in (1,2,3,4)}
 for index,(li,g) in enumerate(obs):
  cycle,token,head,phase,lane,selected,faults=map(int,g[:7]);write=g[7]=='true';scoreindex,scoredata,maxscore=map(int,g[8:11]);rr=g[11]=='true'
  h,offset=divmod(index,34);wantphase=1 if offset<16 else 2 if offset<32 else 3 if offset==32 else 4;wantlane=offset if offset<16 else offset-16 if offset<32 else 15
  need(ready[0]<li<pi and previous<cycle<counts['cycles'],'monotonic body event position')
  if offset:need(cycle==previous+1,'consecutive within-head ordered phases')
  need((token,head,phase,lane,selected,faults)==(0,h,wantphase,wantlane,0,0),'independent fixed M1 head/phase/lane/causal selection')
  need(not rr and write==(phase==4),'held result and actual score write-site retirement')
  if write:need(scoreindex==scoredata==0,'zero causal score retirement')
  need(0<=scoreindex<1024 and 0<=scoredata<2**32 and 0<=maxscore<2**32,'observation widths')
  phase_counts[str(phase)]+=1;previous=cycle
 return dict(status='PASS_LOG_CONTRACT_ONLY_CALLER_EXECUTION_PROOF_REQUIRED',counts=counts,total_rising_edges=total,explicit_reset_edges=3,observations=408,phase_counts=phase_counts,covered_request_hold_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]>0],uncovered_request_hold_ports=[p for p in ('group','memory','pv','step') if counts['hold_'+p]==0],log_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),runtime_provenance_verified=False,matrix_numerical_pass=False,full128_rtl_pass=False,matrix_mac_utilization=None)
