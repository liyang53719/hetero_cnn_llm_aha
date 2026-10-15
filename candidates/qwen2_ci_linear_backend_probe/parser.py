"""Pure bounded parser for an isolated BF16 biased Q-linear oneDNN execution.

Format reference (3.7 family documentation, plus exact wheel source):
https://github.com/uxlfoundation/oneDNN/blob/8d263e693366ef8db40acc569cc7d8edf644556d/src/common/verbose.cpp
Source lines 84 (v1), 523-568 (colon-separated descriptor name),
709-712 (scratchpad), 795-803 (sum),
1242-1263 (no-bias matmul and two-operand problem descriptor).
https://uxlfoundation.github.io/oneDNN/v3.7/dev_guide_verbose.html
Only execution records count; info/dispatch/create do not prove execution.
Geometry identifies a primitive, not its Python caller. The caller must isolate
one synthetic Linear in each process. Missing evidence never proves fallback.
"""
import re

MAX_BYTES=262144
MAX_LINES=2048
MAX_LINE=4096
MAX_MATCHES=64
ISAS=frozenset(('AVX512_CORE_AMX','AVX512_CORE_AMX_FP16','AVX512_CORE_BF16',
    'AVX512_CORE','AVX2','SSE41','UNKNOWN','MIXED','UNOBSERVED'))
IMPLEMENTATIONS={prefix+suffix:label for prefix in ('brg:','brg_matmul:','jit:') for suffix,label in (
    ('avx512_core_amx','AVX512_CORE_AMX'),('avx512_core_amx_fp16','AVX512_CORE_AMX_FP16'),
    ('avx512_core_bf16','AVX512_CORE_BF16'),('avx512_core','AVX512_CORE'),
    ('avx2','AVX2'),('sse41','SSE41'))}
NUMBER=re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z')
MEMORY=re.compile(r'(src|wei|dst):bf16:([a-z]*):blocked:([A-Za-z0-9]+):([0-9x]*):(f0(?:_mask[0-9]+)?)\Z')
PROBLEMS=frozenset(('128x1536:1536x1536',))


def checked(value):
    if type(value) is not dict or any(type(k) is not str for k in value) or set(value)!={
        'schema','status','backend','isa','matched_primitive','matched_count','evidence'}:
        raise ValueError('invalid backend observation schema')
    if (type(value['schema']) is not int or value['schema']!=1 or
        type(value['status']) is not str or value['status']!='LINEAR_BACKEND_OBSERVATION' or
        type(value['backend']) is not str or value['backend'] not in ('ONEDNN','UNDETERMINED') or
        type(value['isa']) is not str or value['isa'] not in ISAS or
        type(value['matched_primitive']) is not bool or
        type(value['matched_count']) is not int or not 0<=value['matched_count']<=MAX_MATCHES or
        type(value['evidence']) is not str or value['evidence'] not in ('MATCHED','NO_MATCH','NO_LOG','UNSUPPORTED')):
        raise ValueError('invalid backend observation values')
    matched=value['matched_count']>0
    if (value['matched_primitive']!=matched or (value['backend']=='ONEDNN')!=matched or
        (value['evidence']=='MATCHED')!=matched or (value['isa']=='UNOBSERVED')==matched):
        raise ValueError('inconsistent backend observation')
    return dict(value)


def _memory(text):
    tokens=text.split(' ')
    if len(tokens)!=3:return False
    descriptors={}
    for token in tokens:
        match=MEMORY.fullmatch(token)
        if match is None:return False
        role,properties,tag,strides,flags=match.groups()
        if role in descriptors or properties!='':return False
        if tag!={'src':'ab','wei':'ba','dst':'ab'}[role] or strides!='':return False
        if flags!='f0':return False
        descriptors[role]=True
    return set(descriptors)=={'src','wei','dst'}


def parse(text):
    """Accept local log text only; never perform I/O or return raw log values."""
    if type(text) is not str or len(text)>MAX_BYTES or len(text.encode('utf-8'))>MAX_BYTES:
        raise ValueError('bounded native log text required')
    lines=text.splitlines()
    if len(lines)>MAX_LINES or any(len(line)>MAX_LINE for line in lines):
        raise ValueError('bounded native log lines required')
    seen=False;unsupported=False;isas=[]
    for line in lines:
        if not line.startswith('onednn_verbose,'):continue
        seen=True;fields=line.split(',')
        if len(fields)<4 or fields[1]!='v1':
            unsupported=True;continue
        fields=fields[2:]
        if NUMBER.fullmatch(fields[0]):fields=fields[1:]
        if not fields or fields[0] not in ('primitive','info','graph','common'):
            unsupported=True;continue
        if fields[0]!='primitive':continue
        if len(fields)<2:
            unsupported=True;continue
        if fields[1]!='exec':continue
        if len(fields)!=11:
            unsupported=True;continue
        _,_,engine,primitive,implementation,prop,memory,attributes,auxiliary,problem,timing=fields
        if engine!='cpu' or primitive!='matmul':continue
        if not NUMBER.fullmatch(timing):
            unsupported=True;continue
        if (prop!='undef' or problem not in PROBLEMS or not _memory(memory) or
            attributes!='attr-scratchpad:user attr-post-ops:sum' or auxiliary!=''):
            continue
        isas.append(IMPLEMENTATIONS.get(implementation,'UNKNOWN'))
        if len(isas)>MAX_MATCHES:raise ValueError('too many matching primitives')
    matched=bool(isas)
    return checked(dict(schema=1,status='LINEAR_BACKEND_OBSERVATION',
        backend='ONEDNN' if matched else 'UNDETERMINED',
        isa=(isas[0] if len(set(isas))==1 else 'MIXED') if matched else 'UNOBSERVED',
        matched_primitive=matched,matched_count=len(isas),
        evidence='MATCHED' if matched else 'UNSUPPORTED' if unsupported else 'NO_MATCH' if seen else 'NO_LOG'))
