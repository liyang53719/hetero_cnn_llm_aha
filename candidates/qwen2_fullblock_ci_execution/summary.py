"""Local output validation; exported aggregate contains no per-tensor metadata."""
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
PIN='candidates/qwen2_fullblock_reference_m128/pins.json'
FROZEN='candidates/qwen2_fullblock_reference_m128/FROZEN_CONTRACT.json'
FROZEN_SHA='64835641b2c0c16d83beb75fbcd9d1c83ade8676fbd825f5e6ab646167af723f'
PIN_SHA='48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'
FIXED=('shape','bytes','native_bytes','native_dtype','export_dtype')
DIGESTS=('sha256','native_sha256','token_major_sha256')
RECORD_KEYS=set(FIXED+DIGESTS+('file','native_stride','is_contiguous','storage_offset'))

def need(ok,message):
    if not ok:raise ValueError(message)

def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value),'SHA256 required')
    return value

def specs():
    raw=(ROOT/PIN).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==PIN_SHA,'original shape contract drift')
    return json.loads(raw)['references']

def observations(outputs,*,git_sha,source_digest):
    need(type(git_sha) is str and re.fullmatch('[0-9a-f]{40}',git_sha),'Git identity required')
    digest(source_digest)
    expected=specs()
    need(type(outputs) is dict and set(outputs)==set(expected) and len(outputs)==29,'exact 29 outputs required')
    clean={}
    for name,shape in expected.items():
        item=outputs[name]
        need(type(item) is dict and set(item)==RECORD_KEYS,'unknown reference field')
        need(item['file']==name+'.f32le','canonical output filename')
        for key in FIXED:
            need(type(item[key]) is type(shape[key]) and item[key]==shape[key],'fixed output geometry/dtype: '+key)
        need(all(type(v) is int for v in item['shape']),'integer output dimensions')
        for key in DIGESTS:digest(item[key])
        need(type(item['native_stride']) is list and len(item['native_stride'])==len(item['shape']) and
             all(type(v) is int and 0<=v<=100000000 for v in item['native_stride']),'bounded native strides')
        need(type(item['is_contiguous']) is bool and type(item['storage_offset']) is int and item['storage_offset']==0,'layout flags')
        clean[name]={key:item[key] for key in sorted(RECORD_KEYS-{'file'})}
    result=dict(schema=1,status='BOOTSTRAP_REFERENCE_OBSERVED_PENDING_REVIEW',git_sha=git_sha,
        source_digest=source_digest,reference_outputs_checked=len(clean),reference_executed=True,dut_executed=False,
        rtl_executed=False,numerical_acceptance_claimed=False,independently_approved=False)
    return json.loads(json.dumps(result,allow_nan=False))


def checked_aggregate(outputs,*,git_sha,source_digest):
    """Compare new observations locally; never export expected/observed records."""
    result=observations(outputs,git_sha=git_sha,source_digest=source_digest)
    raw=(ROOT/FROZEN).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==FROZEN_SHA,'existing tracked expectation source drift')
    expected=json.loads(raw)['outputs']
    # JSON serialization preserves bool/int distinctions as well as exact fields.
    need(json.dumps(outputs,sort_keys=True,allow_nan=False)==json.dumps(expected,sort_keys=True,allow_nan=False),
         'fresh reference differs from fixed expectations; local inspection required')
    result['fixed_expectations_match']=True
    return result
