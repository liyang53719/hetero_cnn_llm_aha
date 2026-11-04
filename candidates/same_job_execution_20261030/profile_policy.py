"""Selection metadata only; never qualifies a host, image, runtime or numerical result.
Registered hardware profiles remain five. Absence of policy preserves full-five V1.
"""
SCHEMA='REGISTERED_FIVE_ELIGIBLE_EXECUTION_POLICY_V1'
FULL='FULL_FIVE_ORIGINAL_HOST_POLICY'
DEFER='QWEN35_FOUR_P0_BLOCKED_ORIGINAL_HOST_POLICY'
SELECTED_FULL='FULL_READY_SELECTED_DEPENDENCIES_V1'
MAP=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
def selected_policy(profiles):
 if type(profiles)is not list or not profiles or any(type(i)is not int or not 0<=i<5 for i in profiles)or profiles!=sorted(set(profiles)):
  raise ValueError('exact nonempty ordered preparation profile subset')
 return dict(schema=SCHEMA,mode=SELECTED_FULL,registered_profiles=list(range(5)),eligible_profiles=list(profiles),blocked_profiles={str(i):'NOT_SELECTED_FOR_THIS_FULL_PREPARATION'for i in range(5)if i not in profiles},selection_reason='EXPLICIT_PINNED_FULL_V3_DEPENDENCIES_NOT_CPU_OBSERVATION',cpu_avx512_observation='NOT_ASSERTED_BY_SELECTION',p0_numeric_qualification='NOT_ESTABLISHED_BY_SELECTION'if 0 in profiles else'UNTESTED_IN_THIS_MODE')
def policy(mode=FULL):
 if mode not in (FULL,DEFER):raise ValueError('unknown execution policy')
 return dict(schema=SCHEMA,mode=mode,registered_profiles=list(range(5)),eligible_profiles=list(range(5))if mode==FULL else [1,2,3,4],blocked_profiles={}if mode==FULL else {'0':'BLOCKED_ORIGINAL_HOST_POLICY'},selection_reason='FULL_FIVE_ORIGINAL_CONTRACT'if mode==FULL else'EXPLICIT_POLICY_DEFERRAL_NOT_CPU_OBSERVATION',cpu_avx512_observation='NOT_ASSERTED_BY_SELECTION',p0_numeric_qualification='NOT_ESTABLISHED_BY_SELECTION'if mode==FULL else'UNTESTED_IN_THIS_MODE')
def checked(b):
 p=b.get('execution_policy',policy())
 if not isinstance(p,dict):raise ValueError('exact versioned registered/eligible/blocked execution policy')
 expected=selected_policy(p.get('eligible_profiles'))if p.get('mode')==SELECTED_FULL else policy(p.get('mode'))
 if p!=expected:raise ValueError('exact versioned registered/eligible/blocked execution policy')
 # bool equals int in Python: reject it explicitly.
 if any(type(i)is not int for i in p['registered_profiles']+p['eligible_profiles']):raise ValueError('integer profile identities')
 return p
def is_selected(b):return checked(b)['mode']==SELECTED_FULL
def require_selected_queue(b,doc):
 if not is_selected(b):raise ValueError('explicit selected preparation policy required')
 if b.get('execution_context')!='CLOUD_EXECUTOR_V1' or b.get('execution_mode')!='FULL_BLOCK_ACCEPTANCE':raise ValueError('selected dependencies only cloud ordinary FULL')
 if type(doc)is not dict or doc.get('schema')!='MODEL_CANDIDATE_FIVE_M128_FULL_READY_QUEUE_V3' or doc.get('queue_policy')!='PARALLEL_INDEPENDENT_FEASIBILITY_NO_PROFILE_COMPLETION_DEPENDENCY':raise ValueError('selected dependencies require exact V3 ready queue')
 if type(doc.get('selected_profiles'))is not list or any(type(i)is not int for i in doc['selected_profiles'])or doc['selected_profiles']!=eligible(b):raise ValueError('preparation and DUT selections must match exactly')
 if type(doc.get('profiles'))is not dict or set(doc['profiles'])!=set(map(str,range(5))):raise ValueError('selected dependencies retain five hardware inventory rows')
 for i,row in doc['profiles'].items():
  if type(row)is not dict or row.get('state')!=('READY_FULL_PREFILL'if int(i)in eligible(b)else'BLOCKED_NOT_RUN'):raise ValueError('selected dependency queue state mismatch')
 return checked(b)
def eligible(b):return checked(b)['eligible_profiles']
def runtimes(b):return tuple(dict.fromkeys(MAP[i]for i in eligible(b)))
def require_same(left,right):
 if checked(left)!=checked(right):raise ValueError('execution policy identity drift')
def require_profile(b,i):
 if type(i)is not int or i not in eligible(b):raise ValueError('profile blocked by original host policy; no lease or receipt')
def require_cpu(b,flags):
 if 0 in eligible(b)and 'avx512f'not in flags:raise ValueError('P0 original AVX512 contract, no fallback')
def require_references(b,refs):
 if set(refs)!=set(map(str,eligible(b))):raise ValueError('exact eligible references; no blocked-profile receipt')

def require_source_pin(pins):
 import hashlib,pathlib
 path=pathlib.Path(__file__).resolve()
 with path.open('rb')as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
 if pins.get(str(path))!=actual:raise ValueError('explicit execution policy source pin')
