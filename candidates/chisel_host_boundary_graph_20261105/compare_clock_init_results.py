"""Exact structural/equation fixture comparison. No interpreter acceptance."""
import re
CASES=('print','stop','both')
ROW=re.compile(r'CLOCK_INIT_CASE_V1 id=(print|stop|both) corrected=([12]) negativeGuards=([0-9]+) equations=512 shapeChecks=1 driverChecks=3 boundChecks=9 sizingChecks=13 graphDigest=([0-9a-f]{64})')
GUARDS={'ANCHOR','ANNOTATION_EXTENSION','ANNOTATION_PRESET','ANNOTATION_SHAPE','ANNOTATION_TARGET','BOUND','CLOCK','CONSUMER','COUNT','DRIVER','DUPLICATE','INFO','NONINTERFERENCE','ORIGINAL_MODULE','PREEXISTING','REFERENCES','SHAPE','STRUCTURE','TYPE'}
FAIL=re.compile(r'CLOCK_INIT_FAILURE_V1 phase=(IDENTITY|LOWER|PREPARE|ORIGINAL_ERRORS|REPAIR|VALIDATE|NEGATIVE|GRAPH|EQUATIONS|CLEANUP) guard=(NONE|UNKNOWN|ANCHOR|ANNOTATION_EXTENSION|ANNOTATION_PRESET|ANNOTATION_SHAPE|ANNOTATION_TARGET|BOUND|CLOCK|CONSUMER|COUNT|DRIVER|DUPLICATE|INFO|NONINTERFERENCE|ORIGINAL_MODULE|PREEXISTING|REFERENCES|SHAPE|STRUCTURE|TYPE) driver=([A-Z_:]+) exceptionClassSha=([0-9a-f]{64})')
def need(x):
 if not x:raise ValueError('CLOCK_INIT_FIXTURE_SCHEMA')
def parse(text,label,process):
 need(label in ('official','cached')and type(text)is str and text.isascii()and len(text)<=4096 and text.endswith('\n'))
 need(type(process)is dict and set(process)=={'exit','errors','cleanup_complete','log_finalized'} and type(process['exit'])is int and process['exit']==0 and type(process['errors'])is list and process['errors']==[] and process['cleanup_complete']is True and process['log_finalized']is True)
 need('\r'not in text);parts=text.split('\n');need(len(parts)==5 and parts[-1]=='');lines=parts[:-1]
 rows=[]
 for i,line in enumerate(lines[:3]):
  m=ROW.fullmatch(line);need(m is not None and m[1]==CASES[i] and int(m[2])==(2 if i==2 else 1)and int(m[3])==(27 if i==2 else 0));rows.append(m.groups())
 need(lines[3]=='CLOCK_INIT_RUN_V1 label='+label+' pass=true cases=3 numericalPass=false interpreterExecuted=false fullHostAccepted=false')
 return rows
def compare(official,cached,official_process,cached_process):
 a=parse(official,'official',official_process);b=parse(cached,'cached',cached_process);need(a==b)
 return dict(status='PASS_CLOCK_INIT_STRUCTURAL_EQUATIONS_ONLY',cases=3,block_shape_cases=3,driver_diagnostic_cases=9,bound_diagnostic_cases=27,index_sizing_cases=39,negative_guards=27,equation_vectors_per_case=512,interpreter_executed=False)
def failure(text,label):
 need(label in ('official','cached')and type(text)is str and text.isascii()and len(text)<=4096 and text.endswith('\n'))
 need('\r'not in text);parts=text.split('\n');need(len(parts)==3 and parts[-1]=='');lines=parts[:-1]
 m=FAIL.fullmatch(lines[0]);need(m is not None)
 need(lines[1]=='CLOCK_INIT_RUN_V1 label='+label+' pass=false cases=0 numericalPass=false interpreterExecuted=false fullHostAccepted=false')
 if m[1]=='REPAIR':
  need(m[2]=='UNKNOWN' or m[2]in GUARDS)
  need(m[2]=='UNKNOWN' or m[4]=='6757b394f9b99b54cc59cd8f05528b770054c25bc6643d413f1a7337f96614d0')
 else:need(m[2]=='NONE')
 detail=driver_evidence(m[3])
 if m[1]=='REPAIR' and m[2]=='DRIVER':need(detail['status']!='NONE')
 else:need(detail['status']=='NONE')
 return dict(phase=m[1],guard=m[2],driver=detail,exception_class_sha256=m[4])

def driver_evidence(text):
 need(type(text)is str and len(text)<=192)
 if text in ('NONE','UNAVAILABLE'):return {'status':text}
 values=text.split(':');need(len(values)==13)
 step,count,typ,kind,flow,n,t,k,f,cons,ct,ck,cf=values
 need(step in ('SELECT','RHS')and count in ('ZERO','ONE','MANY')and cons in ('ZERO','ONE','MANY'))
 def metadata(count,t,k,f):
  if count=='ONE':need(t in ('CLOCK','OTHER')and k in ('NODE','REG','PORT','OTHER')and f in ('SOURCE','SINK','DUPLEX','UNKNOWN','OTHER'))
  else:need((t,k,f)==('NA','NA','NA'))
 metadata(count,typ,kind,flow);metadata(cons,ct,ck,cf)
 equality=(n,t,k,f);need(all(v in ('TRUE','FALSE')for v in equality)or equality==('NA',)*4)
 if count!='ONE':need(equality==('NA',)*4)
 if step=='RHS':need((count,typ,kind,flow)==('ONE','CLOCK','NODE','SINK')and equality!=('TRUE',)*4)
 if step=='SELECT' and count=='ONE':need((typ,kind,flow)!=('CLOCK','NODE','SINK'))
 return dict(status='AVAILABLE',step=step,direct_sink_count=count,sink_type=typ,sink_kind=kind,sink_flow=flow,rhs_name_equal=n,rhs_type_equal=t,rhs_kind_equal=k,rhs_flow_equal=f,direct_consumer_count=cons,consumer_type=ct,consumer_kind=ck,consumer_flow=cf)
