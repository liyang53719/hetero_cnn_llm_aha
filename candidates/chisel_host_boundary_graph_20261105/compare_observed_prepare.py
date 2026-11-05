"""Finite observation diagnostics, never provenance authority or repair acceptance."""
import re
REASONS=frozenset(('NONE','NOT_RUN','MULTIPLE_CIRCUITS','BUDGET','SCAN_BUDGET','BOUND','FAMILY','DUPLICATE','STRUCTURE','EXPRESSION','TYPE','INFO','SHAPE','CLOCK','RECLAIMED','RELATION','REFERENCES','DRIVER','CONSUMER','ANCHOR','PREEXISTING','COUNT','ORIGINAL_MODULE','UNEXPECTED'))
STEPS=frozenset(('CENSUS','DISCOVERY','INITIAL_USES','ORIGINAL','P52','P53','P54','DONE'))
KEYS=('records','created','p52','p53','p54','identity_lost','clock_changed','visits','expressions')
def need(ok):
 if not ok:raise ValueError('OBSERVED_PREPARE_SCHEMA')
def evidence(text,expected=None):
 need(type(text)is str and 0<len(text)<=256 and text.isascii())
 if expected is not None:need(type(expected)is int and 1<=expected<=1024)
 fields=text.split(':');need(len(fields)==12)
 status,step,reason=fields[:3];need(status in ('COMPLETE','TRUNCATED','UNAVAILABLE')and step in STEPS and reason in REASONS)
 values=[]
 for value,limit in zip(fields[3:],[1024]*7+[1<<24,1<<25]):
  need(re.fullmatch(r'0|[1-9][0-9]{0,7}',value)is not None);n=int(value);need(n<=limit);values.append(n)
 if status=='COMPLETE':
  need(step=='DONE'and reason=='NONE'and 1<=values[0]<=1024 and all(x==values[0]for x in values[:7]))
  if expected is not None:need(values[0]==expected)
 else:
  need(reason!='NONE'and values[:7]==[0]*7)
  if status=='TRUNCATED':need(reason in ('BUDGET','SCAN_BUDGET','BOUND'))
 return dict(status=status,step=step,reason=reason,**dict(zip(KEYS,values)))

MODES=('print','stop','both')
KINDS=('base','nested','recycled')
OBSERVER_CHECKS=69
PARITY_CHECKS=11
CASE=re.compile(r'OBSERVED_PREPARE_CASE_V1 mode=(print|stop|both) kind=(base|nested|recycled) parity=true records=([12]) suffixChecks=([036]) graphChecks=([04]) observerChecks=([0-9]+) parityChecks=11 failureParityChecks=([01]) stateFields=3 form=ABSENT_IN_PINNED_API renames=NONE evidence=([^ ]+)')
FINAL=re.compile(r'OBSERVED_PREPARE_RUN_V1 label=(official|cached) pass=true cases=9 diagnosticOnly=true interpreterExecuted=false fullHostAccepted=false')
FAILURE=re.compile(r'OBSERVED_PREPARE_FAILURE_V1 phase=(IDENTITY|SELFTEST|LOWER|OFFICIAL|OBSERVED|OBSERVED_FAILURE|PARITY|SUFFIX|GRAPH|CLEANUP) code=REJECTED')
def process_ok(value):
 need(type(value)is dict and set(value)=={'exit','errors','cleanup_complete','log_finalized'})
 need(type(value['exit'])is int and value['exit']==0 and type(value['errors'])is list and value['errors']==[])
 need(type(value['cleanup_complete'])is bool and value['cleanup_complete']is True and type(value['log_finalized'])is bool and value['log_finalized']is True)
def fixture(text,label,process):
 need(label in ('official','cached')and type(label)is str);process_ok(process)
 need(type(text)is str and 0<len(text)<=32768 and text.isascii()and '\r'not in text)
 lines=text.split('\n');need(len(lines)==11 and lines[-1]=='')
 final=FINAL.fullmatch(lines[9]);need(final is not None and final[1]==label)
 rows=[]
 for index,(mode,kind)in enumerate((m,k)for m in MODES for k in KINDS):
  match=CASE.fullmatch(lines[index]);need(match is not None and match[1]==mode and match[2]==kind)
  records=2 if mode=='both'else 1
  need(int(match[3])==records and int(match[4])==(records*3 if kind=='base'else 0)and int(match[5])==(4 if kind=='base'else 0))
  need(int(match[7])==(1 if kind=='base'else 0)and match[6]==str(OBSERVER_CHECKS))
  proof=evidence(match[8],records)
  need(proof['status']=='COMPLETE')
  rows.append(dict(mode=mode,kind=kind,records=records,proof=proof))
 return rows
def compare(official,cached,official_process,cached_process):
 a=fixture(official,'official',official_process);b=fixture(cached,'cached',cached_process)
 # Counters and exact prepared-state observations must also match across key implementations.
 need(a==b)
 return dict(status='PASS_OBSERVED_PREPARE_FIXTURE_ONLY',cases=9,parity_cases=9,suffix_checks=12,graph_checks=12,
  observer_checks=OBSERVER_CHECKS,parity_checks=11,failure_parity_cases=3,state_fields=3,form_absent_in_pinned_api=True,
  renames_none=True,diagnostic_only=True,interpreter_executed=False,full_host_accepted=False)
def failure(text,label):
 need(type(label)is str and label in ('official','cached'))
 need(type(text)is str and len(text)<=512 and text.isascii()and '\r'not in text)
 lines=text.split('\n');need(len(lines)==3 and lines[-1]=='')
 m=FAILURE.fullmatch(lines[0]);need(m is not None)
 need(lines[1]=='OBSERVED_PREPARE_RUN_V1 label='+label+' pass=false cases=0 diagnosticOnly=true interpreterExecuted=false fullHostAccepted=false')
 return dict(status='FAILED_OBSERVED_PREPARE_FIXTURE_ONLY',phase=m[1],code='REJECTED')
