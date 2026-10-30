"""Selection metadata only; never qualifies a host, image, runtime or numerical result.
Registered hardware profiles remain five. Absence of policy preserves full-five V1.
"""
SCHEMA='REGISTERED_FIVE_ELIGIBLE_EXECUTION_POLICY_V1'
FULL='FULL_FIVE_ORIGINAL_HOST_POLICY'
DEFER='QWEN35_FOUR_P0_BLOCKED_ORIGINAL_HOST_POLICY'
MAP=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
def policy(mode=FULL):
 if mode not in (FULL,DEFER):raise ValueError('unknown execution policy')
 return dict(schema=SCHEMA,mode=mode,registered_profiles=list(range(5)),eligible_profiles=list(range(5))if mode==FULL else [1,2,3,4],blocked_profiles={}if mode==FULL else {'0':'BLOCKED_ORIGINAL_HOST_POLICY'},selection_reason='FULL_FIVE_ORIGINAL_CONTRACT'if mode==FULL else'EXPLICIT_POLICY_DEFERRAL_NOT_CPU_OBSERVATION',cpu_avx512_observation='NOT_ASSERTED_BY_SELECTION',p0_numeric_qualification='NOT_ESTABLISHED_BY_SELECTION'if mode==FULL else'UNTESTED_IN_THIS_MODE')
def checked(b):
 p=b.get('execution_policy',policy())
 if not isinstance(p,dict)or p!=policy(p.get('mode')):raise ValueError('exact versioned registered/eligible/blocked execution policy')
 # bool equals int in Python: reject it explicitly.
 if any(type(i)is not int for i in p['registered_profiles']+p['eligible_profiles']):raise ValueError('integer profile identities')
 return p
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
