"""Exact closed-log comparator; source-only tests are not Scala qualification."""
import re
CASES=('base','true_cycle','self_loop','registered','boundary_cycle','boundary_registered','arithmetic','whole_bus','mux_narrow_true','mux_narrow_false','mux_boundary_cycle','mux_boundary_registered','validif_full','validif_mixed','validif_nested','validif_zero','validif_cycle','validif_registered')
CYCLES=frozenset(('true_cycle','self_loop','boundary_cycle','mux_boundary_cycle','validif_cycle'))
VALIDITY_CASES=frozenset({'validif_mixed', 'validif_cycle', 'validif_registered', 'validif_full', 'validif_zero', 'validif_nested'})
HEX=r'[0-9a-f]{64}'
OUTCOME=r'(CYCLE|GRAPH:'+HEX+r')'
CASE=re.compile(r'BOUNDARY_GRAPH_CASE_V1 id=([a-z_]+) lowOriginal='+OUTCOME+r' lowTransformed='+OUTCOME+r' original='+OUTCOME+r' transformed='+OUTCOME+r' bitEquationPhases=2 bitEquationVectors=(3730|3731|3794|3795|6892|6894) lowSemantics=(CONCRETE|VALIDITY_MASK) preparedSemantics=CONCRETE')
FINAL=re.compile(r'BOUNDARY_GRAPH_RUN_V1 label=(official|cached) pass=true cases=18 negativeGuards=29 validityCases=6 numericalPass=false fullHostAccepted=false')
def need(ok):
 if not ok:raise ValueError('boundary fixture receipt rejected')
def process_ok(p):
 need(type(p)is dict and set(p)=={'exit','errors','cleanup_complete','log_finalized'})
 need(type(p['exit'])is int and p['exit']==0 and type(p['errors'])is list and p['errors']==[])
 need(p['cleanup_complete']is True and p['log_finalized']is True)
def pins_ok(p):
 need(type(p)is dict and set(p)=={'source_sha256','class_sha256','companion_sha256'})
 need(all(type(v)is str and re.fullmatch(HEX,v) for v in p.values()))
def expected_vectors(name):
 if name in VALIDITY_CASES:return 6894 if name=='validif_registered'else 6892
 return 3730+(1 if name in ('boundary_registered','mux_boundary_registered','validif_registered')else 0)+(64 if name.startswith('mux_')else 0)
def parse(text,label,process):
 process_ok(process)
 need(label in ('official','cached'))
 need(type(text)is str and text.isascii() and 0<len(text)<=16384 and text.endswith('\n'))
 # Only LF, exactly nineteen ordered records; no duplicate/extra/CR/blank records.
 lines=text.split('\n');need(len(lines)==20 and lines[-1]=='');lines=lines[:-1]
 rows=[]
 for name,line in zip(CASES,lines[:-1]):
  m=CASE.fullmatch(line);need(m is not None and m[1]==name)
  low_old,low_new,old,new=m.groups()[1:5]
  need(low_old=='CYCLE' and old=='CYCLE')
  need((low_new=='CYCLE')==(name in CYCLES) and (new=='CYCLE')==(name in CYCLES))
  need(int(m[6])==expected_vectors(name))
  need(m[7]==('VALIDITY_MASK' if name in VALIDITY_CASES else 'CONCRETE'))
  rows.append(m.groups())
 m=FINAL.fullmatch(lines[-1]);need(m is not None and m[1]==label)
 return tuple(rows)
def compare(official_text,cached_text,official_pins,cached_pins,official_process,cached_process):
 # Fixture itself checks loaded class bytes AND protection-domain location
 # against these independently pinned arguments before it can emit success.
 pins_ok(official_pins);pins_ok(cached_pins)
 need(official_pins['source_sha256']!=cached_pins['source_sha256'])
 need(official_pins['companion_sha256']!=cached_pins['companion_sha256'])
 a=parse(official_text,'official',official_process);b=parse(cached_text,'cached',cached_process)
 need(a==b)
 return {'status':'PASS_ISOLATED_BOUNDARY_FIXTURE_ONLY','cases':18,'negative_guard_cases':29,'validity_mask_cases':6,'bit_equation_phases':2,'vectors_per_phase':{'default':3730,'boundary_registered':3731,'unequal_mux':3794,'mux_boundary_registered':3795,'validity_default':6892,'validity_registered':6894},'official_cached_exact_agreement':True,'full_host_accepted':False,'numerical_pass':False}

# Failure diagnostics are a separate, strictly rejecting channel. They can
# never satisfy parse()/compare(), even when a process receipt looks successful.
PHASES=('identity','parse','lower','negative_guards','type_flow','projection','bit_equations','prepare','graph','cleanup')
FAILURE_CODES=('UNKNOWN','UNSUPPORTED_OPERATOR','UNSUPPORTED_WIDTH','BIT_MISMATCH','FEEDBACK_MISMATCH','VECTOR_MISMATCH','AND_WIDTH','AND_SELFCHECK','VALIDITY_COVERAGE','VALIDITY_MASK_MISMATCH','VALIDITY_PARTIAL_OPERATOR','VALIDITY_PREPARED_RESIDUE','VALIDITY_STRUCTURE','VALIDITY_UNDEFINED_CONDITION','VALIDITY_UNSUPPORTED_OPERATOR','VALIDITY_VALUE_MISMATCH')
FAILURE=re.compile(r'BOUNDARY_GRAPH_FAILURE_V1 case=(none|'+('|'.join(CASES))+r') phase=('+('|'.join(PHASES))+r') comparisonStep=(NONE|LOW|PREPARED) failureCode=('+('|'.join(FAILURE_CODES))+r') exceptionClassSha=('+HEX+r')')
FAIL_FINAL=re.compile(r'BOUNDARY_GRAPH_RUN_V1 label=(official|cached) pass=false numericalPass=false fullHostAccepted=false')
def parse_failure(text,label):
 need(label in ('official','cached'))
 need(type(text)is str and text.isascii() and 0<len(text)<=2048)
 lines=text.split('\n');need(len(lines)==3 and lines[-1]=='')
 m=FAILURE.fullmatch(lines[0]);f=FAIL_FINAL.fullmatch(lines[1])
 need(m is not None and f is not None and f[1]==label)
 need(m[1]!='none' or m[2] in ('identity','cleanup'))
 need(m[2]!='identity' or m[1]=='none')
 need((m[3] in ('LOW','PREPARED'))==(m[2]=='bit_equations'))
 need(m[4]=='UNKNOWN' or (m[2]=='bit_equations' and m[5]=='6757b394f9b99b54cc59cd8f05528b770054c25bc6643d413f1a7337f96614d0'))
 return {'status':'FIXTURE_REPORTED_FAILURE','process_label':label,'case':m[1],'phase':m[2],'comparison_step':m[3],'failure_code':m[4],'exception_class_sha256':m[5]}
