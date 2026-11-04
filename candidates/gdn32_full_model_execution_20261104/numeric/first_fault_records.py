"""Finite projection only; caller verifies owner cleanup and fixed output path.
No model execution, root-cause inference, numerical PASS or raw log retention.
"""
import hashlib,json,re
from pathlib import Path
SCHEMA_SHA256='75088081cf6c3425eba9af3b44c78244f8c62697b4390f992ad63e21f16c7de4'
LIMIT=8192
DEC=r'(0|[1-9][0-9]*)'
HEADER='HOST_FIRST_FAULT_V1 schema_sha256='+SCHEMA_SHA256+' fields=114 extra_eval=0 extra_clock=0'
SLOT=re.compile(r'HOST_FIRST_FAULT_SLOT_V1 slot=(previous_healthy|current_fault) valid=([01]) cycle='+DEC+r' active_cycle='+DEC+r' completions='+DEC+r' values=([0-9,]+)')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def schema():
 raw=Path(__file__).with_name('FIXED_NONHIER_SCHEMA.json').read_bytes()
 need(hashlib.sha256(raw).hexdigest()==SCHEMA_SHA256,'exact adjacent schema pin')
 s=json.loads(raw);need(s['signal_count']==114 and len(s['signals'])==114,'fixed cardinality');return s

def parse_records(lines):
 """Consume line iterator without retaining unrelated log; malformed records raise.
 ABSENT means only no snapshot records, never success. Upstream caller owns full
 log byte/line caps, full SHA hashed at projection (not a preexisting log pin),
 canonical fixed Popen output path and owner cleanup verification; this function
 cannot prove them. ValueError means MALFORMED, never ABSENT or PASS.
 """
 s=schema();widths=[r['width_bits']for r in s['signals']];count=0;size=0;samples={}
 for line in lines:
  need(type(line)is str,'text lines required')
  if not line.startswith('HOST_FIRST_FAULT'):continue
  need(len(line)<=LIMIT,'record length');size+=len(line.encode('utf-8'));need(size<=LIMIT,'aggregate record cap')
  text=line[:-1]if line.endswith('\n')else line
  need('\n'not in text and '\r'not in text,'one LF record')
  if count==0:need(text==HEADER,'exact first header')
  else:
   need(count in (1,2),'duplicate snapshot')
   m=SLOT.fullmatch(text);need(m is not None,'exact slot syntax')
   slot,valid,cycle,active,completed,vals=m.groups();need(slot==('previous_healthy'if count==1 else'current_fault'),'slot order')
   vals=vals.split(',');need(len(vals)==114,'value cardinality')
   nums=[]
   for token,width in zip(vals,widths):
    need(re.fullmatch(DEC,token)is not None and len(token)<=20,'canonical decimal');v=int(token);need(v<(1<<width),'signal width');nums.append(v)
   counters=[]
   for token in (cycle,active,completed):
    need(len(token)<=20,'counter width');v=int(token);need(v<(1<<64),'counter width');counters.append(v)
   need(slot!='current_fault'or valid=='1','current sample valid')
   if valid=='0':
    need(not any(counters)and not any(nums),'invalid history must be zero initialization');samples[slot]=None
   else:samples[slot]={'cycle':counters[0],'active_cycle':counters[1],'completions':counters[2],'values':nums}
  count+=1
 need(count in (0,3),'incomplete snapshot')
 if count==3:
  idx=[i for i,r in enumerate(s['signals'])if r['module']=='HostBlockTopV4'and r['sv_var']=='io_resetRequired'];need(len(idx)==1,'exact reset index')
  current=samples['current_fault'];previous=samples['previous_healthy']
  need(current['values'][idx[0]]==1,'current reset must be asserted')
  if previous is not None:need(previous['values'][idx[0]]==0,'previous reset must be clear')
  for v in (previous,current):
   if v is not None:need(v['active_cycle']<=v['cycle'],'active cycle exceeds total')
  if previous is not None:
   need(all(previous[k]<=current[k]for k in ('cycle','active_cycle','completions')),'nonmonotonic samples')
 return {'schema':'FINITE_FIRST_FAULT_LOG_PROJECTION_V1','status':'ABSENT'if count==0 else'PRESENT_VALID','schema_sha256':SCHEMA_SHA256,'record_count':count,'record_bytes':size,'samples':samples,'previous_healthy':samples.get('previous_healthy'),'current_fault':samples.get('current_fault'),'fault_observed':count==3,'fault_cause_established':False,'value_order':'PINNED_SCHEMA_SIGNALS_ORDER','qualifiers':'PINNED_SCHEMA_VALIDITY_AND_VALID_QUALIFIER_ZH','root_cause_inferred':False,'numerical_pass':False}
