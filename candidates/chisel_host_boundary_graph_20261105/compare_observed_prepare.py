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
SIZING_CHECKS=56
QUOTA_CHECKS=6
CONSUMER_CHECKS=24
CONSUMER_PARITY_CHECKS=1
FORMAL_CHECKS=58
FORMAL_PARITY_CHECKS=2
ANCHOR_CHECKS=31
SELECTION_CHECKS=39
SELECTION_PARITY_CHECKS=4
INPUT_CHAIN_CHECKS=6
GRANT_CHECKS=72
GRANT_PARITY_CHECKS=15
GRANT_LIFECYCLE_CHECKS=8
ANNOTATION_SHAPE_CHECKS=25
ANNOTATION_OWNER_CHECKS=22
DEDUP_METADATA_CHECKS=82
DEDUP_METADATA_PARITY_CHECKS=3
ANNOTATION_OTHER_OWNER_CHECKS=23
COMBINATIONAL_PATH_CHECKS=99
USES_WORK_CHECKS=67
P54_WORK_CHECKS=55
P54_WORK_PARITY_CHECKS=20
COMBINATIONAL_PATH_PARITY_SELFCHECKS=7
COMBINATIONAL_PATH_PARITY_CHECKS=3
CASE=re.compile(r'OBSERVED_PREPARE_CASE_V1 mode=(print|stop|both) kind=(base|nested|recycled) parity=true records=([12]) suffixChecks=([036]) graphChecks=([04]) observerChecks=([0-9]+) parityChecks=11 failureParityChecks=([01]) sizingChecks=56 quotaChecks=6 consumerChecks=24 consumerParityChecks=1 formalChecks=58 formalParityChecks=2 anchorChecks=31 selectionChecks=39 selectionParityChecks=4 inputChainChecks=6 grantChecks=72 grantParityChecks=15 grantLifecycleChecks=8 annotationShapeChecks=25 ownerChecks=22 dedupMetadataChecks=82 dedupMetadataParityChecks=3 otherOwnerChecks=23 combinationalPathChecks=99 combinationalPathParitySelfChecks=7 combinationalPathParityChecks=3 usesWorkChecks=67 p54WorkChecks=55 p54WorkParityChecks=20 stateFields=3 form=ABSENT_IN_PINNED_API renames=NONE evidence=([^ ]+)')
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
  observer_checks=OBSERVER_CHECKS,parity_checks=11,failure_parity_cases=3,sizing_checks=SIZING_CHECKS,quota_checks=QUOTA_CHECKS,consumer_checks=CONSUMER_CHECKS,consumer_parity_checks=CONSUMER_PARITY_CHECKS,formal_checks=FORMAL_CHECKS,formal_parity_checks=FORMAL_PARITY_CHECKS,anchor_checks=ANCHOR_CHECKS,selection_checks=SELECTION_CHECKS,selection_parity_checks=SELECTION_PARITY_CHECKS,input_chain_checks=INPUT_CHAIN_CHECKS,grant_checks=GRANT_CHECKS,grant_parity_checks=GRANT_PARITY_CHECKS,grant_lifecycle_checks=GRANT_LIFECYCLE_CHECKS,annotation_shape_checks=ANNOTATION_SHAPE_CHECKS,annotation_owner_checks=ANNOTATION_OWNER_CHECKS,dedup_metadata_checks=DEDUP_METADATA_CHECKS,dedup_metadata_parity_checks=DEDUP_METADATA_PARITY_CHECKS,annotation_other_owner_checks=ANNOTATION_OTHER_OWNER_CHECKS,combinational_path_checks=COMBINATIONAL_PATH_CHECKS,combinational_path_parity_selfchecks=COMBINATIONAL_PATH_PARITY_SELFCHECKS,combinational_path_parity_checks=COMBINATIONAL_PATH_PARITY_CHECKS,uses_work_checks=USES_WORK_CHECKS,p54_work_checks=P54_WORK_CHECKS,p54_work_parity_checks=P54_WORK_PARITY_CHECKS,state_fields=3,form_absent_in_pinned_api=True,
  renames_none=True,diagnostic_only=True,interpreter_executed=False,full_host_accepted=False)
def failure(text,label):
 need(type(label)is str and label in ('official','cached'))
 need(type(text)is str and len(text)<=512 and text.isascii()and '\r'not in text)
 lines=text.split('\n');need(len(lines)==3 and lines[-1]=='')
 m=FAILURE.fullmatch(lines[0]);need(m is not None)
 need(lines[1]=='OBSERVED_PREPARE_RUN_V1 label='+label+' pass=false cases=0 diagnosticOnly=true interpreterExecuted=false fullHostAccepted=false')
 return dict(status='FAILED_OBSERVED_PREPARE_FIXTURE_ONLY',phase=m[1],code='REJECTED')

# Failure-only resource sizing. Raw prefixes never establish provenance.
SCAN_EXPR_LIMIT=1<<24 # Explicit measured auxiliary per-scan contract; shared Expr remains2^25.
BUDGET_LIMITS={'GLOBAL_VISIT':1<<24,'GLOBAL_EXPR':1<<25,'NAMES':1<<22,'HASH':1<<29,'EQUAL':1<<30,'PROBE':1<<26,'CLEAR':1<<22,'TEMP':1<<24,'SCAN_VISIT':1<<22,'SCAN_EXPR':SCAN_EXPR_LIMIT}
BUDGET_KEYS=('shared_used','scan_used','requested','limit','shared_expr','scan_expr','type','info','node','edge','other')
SIZING_KEYS=('modules','ports','statements','roots','nodes','edges','max_statement_depth','max_expression_depth','work','transient','traversal')
def numbers(fields,limits):
 need(len(fields)==len(limits));out=[]
 for value,limit in zip(fields,limits):
  need(re.fullmatch(r'0|[1-9][0-9]{0,9}',value)is not None);n=int(value);need(n<=limit);out.append(n)
 return out
def budget_evidence(text):
 need(type(text)is str and 0<len(text)<=512 and text.isascii())
 if text=='NONE':return None
 if text=='UNAVAILABLE':return {'status':'UNAVAILABLE'}
 f=text.split(':');need(len(f)==12 and f[0]in BUDGET_LIMITS)
 dim=f[0];v=numbers(f[1:],[1<<30,1<<24,1<<30,1<<30,1<<25,SCAN_EXPR_LIMIT]+[1<<25]*5)
 d=dict(dimension=dim,**dict(zip(BUDGET_KEYS,v)))
 need(d['requested']>0 and d['limit']==BUDGET_LIMITS[dim] and sum(v[6:])==d['shared_expr'] and d['scan_expr']<=d['shared_expr'])
 if dim in ('GLOBAL_VISIT','SCAN_VISIT'):need(d['shared_used']<=1<<24 and d['scan_used']<=1<<22 and d['scan_used']<=d['shared_used'])
 elif dim in ('GLOBAL_EXPR','SCAN_EXPR'):need(d['shared_used']==d['shared_expr'] and d['scan_used']==d['scan_expr'])
 else:need(d['scan_used']==0 and d['shared_used']<=d['limit'])
 if dim.startswith('SCAN_'):
  need(d['scan_used']<=d['limit'] and d['requested']>d['limit']-d['scan_used'])
  need(d['shared_used']+d['requested']<=((1<<24)if dim=='SCAN_VISIT'else(1<<25)))
 else:need(d['shared_used']<=d['limit'] and d['requested']>d['limit']-d['shared_used'])
 return d
def sizing_evidence(text):
 need(type(text)is str and 0<len(text)<=512 and text.isascii())
 if text=='NONE':return None
 f=text.split(':');need(len(f)==13)
 status,reason=f[:2]
 need(status in ('COMPLETE','TRUNCATED','ERROR'))
 reasons=('NONE','VISITS','NODES','EDGES','WORK','TRANSIENT','DEPTH','FAMILY','STRUCTURE','EXPRESSION','UNEXPECTED')
 need(reason in reasons and (reason=='NONE')==(status=='COMPLETE'))
 if status=='TRUNCATED':need(reason in ('VISITS','NODES','EDGES','WORK','TRANSIENT','DEPTH'))
 if status=='ERROR':need(reason in ('FAMILY','STRUCTURE','EXPRESSION','UNEXPECTED'))
 v=numbers(f[2:],[4096,1<<22,1<<22,1<<24,1<<24,1<<24,256,256,1<<26,1<<24,1<<25])
 d=dict(status=status,reason=reason,**dict(zip(SIZING_KEYS,v)))
 need(d['modules']+d['ports']+d['statements']<=1<<22 and d['traversal']==d['nodes']+d['edges'])
 if status=='COMPLETE':need(d['roots']<=d['nodes'] and d['edges']==d['nodes']-d['roots'])
 return d
def budget_for_provenance(provenance,budget):
 b=budget_evidence(budget)
 target=provenance['status']=='TRUNCATED'and provenance['step']=='INITIAL_USES'and provenance['reason']in ('BUDGET','SCAN_BUDGET')
 need((b is not None)==target)
 if target and b.get('status')!='UNAVAILABLE':
  need(b['shared_expr']==provenance['expressions'])
  if b['dimension']in ('GLOBAL_VISIT','SCAN_VISIT'):need(b['shared_used']==provenance['visits'])
  need(b['dimension'].startswith('SCAN_')==(provenance['reason']=='SCAN_BUDGET'))
 return b
def sizing_pair(provenance,budget,sizing):
 b=budget_for_provenance(provenance,budget);s=sizing_evidence(sizing)
 need((s is not None)==(b is not None))
 if b is not None and b.get('status')=='UNAVAILABLE':need(s==dict(status='ERROR',reason='UNEXPECTED',**dict.fromkeys(SIZING_KEYS,0)))
 return dict(budget=b,sizing=s)

# First INITIAL_USES CONSUMER failure only. Masks describe object identity,
# never operand traversal origin; neither names nor AST text are accepted.
CONSUMER_SITES=frozenset(('DUPLICATE','MISSING','FINAL_KIND'))
CONSUMER_MASK_MAX={'CONNECT':3,'PRINT':3,'STOP':3,'VERIFICATION':7,'OTHER':0}
CONSUMER_KINDS=frozenset(('NODE','PORT','REG','WIRE','INSTANCE','MEM','EXP','UNKNOWN','POISON','RANDOM','OTHER'))
CONSUMER_FLOWS=frozenset(('SOURCE','SINK','DUPLEX','UNKNOWN','OTHER'))
def consumer_evidence(text):
 need(type(text)is str and 0<len(text)<=512 and text.isascii())
 if text=='NONE':return None
 if text=='UNAVAILABLE':return {'status':'UNAVAILABLE'}
 fields=text.split(':');need(len(fields)==17 and fields[0]in CONSUMER_SITES)
 slots=[]
 for offset in (1,9):
  role,mask,direct,typ,kind,flow,op,message=fields[offset:offset+8]
  need(role in CONSUMER_MASK_MAX and re.fullmatch(r'[0-7]',mask)is not None and int(mask)<=CONSUMER_MASK_MAX[role])
  need(direct in ('TRUE','FALSE') and (direct=='TRUE')==(typ!='NA'))
  if typ=='NA':need(kind=='NA'and flow=='NA')
  else:need(typ in ('CLOCK','UINT','OTHER')and kind in CONSUMER_KINDS and flow in CONSUMER_FLOWS)
  if role=='VERIFICATION':need(op in ('ASSERT','ASSUME','COVER','OTHER')and message in ('EMPTY','NONEMPTY'))
  else:need(op=='NA'and message=='NA')
  slots.append(dict(role=role,operand_mask=int(mask),direct=direct=='TRUE',reference_type=typ,
   reference_kind=kind,reference_flow=flow,formal_op=op,message=message))
 return dict(status='AVAILABLE',site=fields[0],slots=slots)
def consumer_for_provenance(provenance,text):
 value=consumer_evidence(text)
 target=provenance['status']=='UNAVAILABLE'and provenance['step']=='INITIAL_USES'and provenance['reason']=='CONSUMER'
 need((value is not None)==target)
 if target and value.get('status')=='AVAILABLE':
  slots=value['slots']
  def matching(slot,roles):
   return slot['role']in roles and slot['operand_mask']&1 and slot['direct'] and (slot['reference_type'],slot['reference_kind'],slot['reference_flow'])==('CLOCK','NODE','SOURCE')
  consumers=sum(bool(matching(slot,('PRINT','STOP')) or
   (matching(slot,('VERIFICATION',)) and slot['formal_op']=='ASSERT' and slot['message']=='EMPTY'))for slot in slots)
  drivers=sum(bool(matching(slot,('CONNECT',)))for slot in slots)
  if value['site']=='MISSING':need(drivers==1 and consumers==0)
  elif value['site']=='DUPLICATE':need(consumers==2)
  else:
   # Defensive FINAL_KIND is unreachable in the current exact-class flow.
   # Retain its prior prerequisites, without claiming it occurred at runtime.
   need(drivers==1 and consumers==1)
 return value


# Clock-terminal transition counts only, never assertion-data equivalence.
def formal_evidence(text):
 need(type(text)is str and 0<len(text)<=256 and text.isascii())
 fields=text.split(':');need(len(fields)==5 and fields[0]in ('COMPLETE','UNAVAILABLE'))
 values=numbers(fields[1:],[1024]*4)
 if fields[0]=='COMPLETE':need(all(value==values[0]for value in values))
 else:need(values==[0]*4)
 return dict(status=fields[0],**dict(zip(('formal_count','p52','p53','p54'),values)))
def formal_for_provenance(provenance,text):
 value=formal_evidence(text)
 need((value['status']=='COMPLETE')==(provenance['status']=='COMPLETE'))
 if value['status']=='COMPLETE':need(value['formal_count']<=provenance['records'])
 return value

# First anchor failure only. Identity flags never authorize relinking or repair.
def anchor_evidence(text):
 need(type(text)is str and 0<len(text)<=160 and text.isascii())
 if text in ('NONE','UNAVAILABLE'):return dict(status=text)
 fields=text.split(':');need(len(fields)==7 and fields[0]=='AVAILABLE')
 _,site,role,name,info,clock,prior=fields
 need(site in ('FORMAL_NAME_INFO','FORMAL_CLOCK','FORMAL_DUPLICATE','ORDINARY_DUPLICATE','FINAL_MISSING'))
 need(role in ('PRINT','STOP','EMPTY_ASSERT','OTHER'))
 need(all(x in ('TRUE','FALSE','NA')for x in (name,info,clock))and prior in ('ZERO','ONE'))
 if site.startswith('FORMAL_'):
  need(role=='EMPTY_ASSERT'and name in ('TRUE','FALSE')and info in ('TRUE','FALSE')and clock in ('TRUE','FALSE'))
  if site=='FORMAL_NAME_INFO':need(name=='FALSE'or info=='FALSE')
  elif site=='FORMAL_CLOCK':need(name==info=='TRUE'and clock=='FALSE')
  else:need(name==info==clock=='TRUE'and prior=='ONE')
 elif site=='ORDINARY_DUPLICATE':need(role in ('PRINT','STOP')and prior=='ONE'and clock=='NA'and name in ('TRUE','FALSE')and info in ('TRUE','FALSE'))
 else:need(role in ('PRINT','STOP','EMPTY_ASSERT')and name==info==clock=='NA'and prior=='ZERO')
 return dict(status='AVAILABLE',site=site,role=role,name_identity=name,info_identity=info,clock_identity=clock,prior=prior)
def anchor_for_provenance(provenance,text):
 value=anchor_evidence(text)
 active=provenance['status']=='UNAVAILABLE'and provenance['step']=='ORIGINAL'and provenance['reason']=='ANCHOR'
 need((value['status']!='NONE')==active)
 return value
