"""Strict cold receipt integrity; no model/native execution or numeric approval."""
import hashlib
import json
import math
from pathlib import Path

FILE_SHA256 = '518cac8d40c7301b1a4694e476fd60ba978121d1fc30aba3e48251b148ae0fff'
CANONICAL_SHA256 = '445b36489818df1949f2c95a967b61e50c54c58557c4d884e9b1b54ce9067351'
MAX_BYTES = 24576
FIELDS = ('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp',
          'softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')


def require(ok, message):
    if not ok:raise ValueError(message)


def _tree(value, depth=0):
    require(depth <= 12, 'evidence nesting bound')
    if type(value) is dict:
        require(len(value)<=64 and all(type(k) is str for k in value), 'evidence object bound')
        for child in value.values():_tree(child,depth+1)
    elif type(value) is list:
        require(len(value)<=32, 'evidence list bound')
        for child in value:_tree(child,depth+1)
    else:
        require(type(value) in (str,int,float,bool,type(None)), 'evidence scalar type')
        if type(value) is str:require(len(value)<=256, 'evidence text bound')
        if type(value) is float:require(math.isfinite(value), 'nonfinite evidence')


def validate(evidence):
    _tree(evidence)
    encoded=json.dumps(evidence,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    require(hashlib.sha256(encoded).hexdigest()==CANONICAL_SHA256, 'recorded evidence identity changed')
    require(evidence['status']=='PASS_BOUNDED_NATIVE_CAPTURE_ONLY' and evidence['official_payload_used'] is False,
            'bounded synthetic scope')
    require(all(flag is False for flag in evidence['claims'].values()), 'broader acceptance forbidden')
    failed=evidence['failed_attempt'];passed=evidence['success_postflight']
    require(failed['status']=='FAILED' and failed['returncode']==1 and failed['capture_sha256'] is None and
            failed['owner_job_started'] is False and failed['git_source_guard_bypassed'] is False,
            'pre-owner failure must remain failed')
    require(passed['status']=='PASS_BOUNDED_NATIVE_CAPTURE' and passed['returncode']==0 and
            passed['elapsed_seconds']<passed['deadline_seconds']==20 and passed['previous_attempt_pass_inherited'] is False,
            'bounded retry receipt')
    require([c['rows'] for c in evidence['cases']]==[1,2], 'bounded case inventory')
    for case in evidence['cases']:
        rows=case['rows'];observation=case['observation'];fields=observation['fields']
        require(set(fields)==set(FIELDS) and observation['status']=='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED',
                'complete ten-field capture required')
        require(case['all_ten_fields_complete'] is True and case['pv_store_hash_matches_acknowledged_output'] is True and
                case['scores_match_original_fraction_oracle'] is True, 'actual checks required')
        causal=12*rows*(rows+1)//2
        for name,f in fields.items():
            shape=([12,rows,rows,16] if name=='dot_parts' else [12,rows,3] if name=='normalizer' else
                   [12,rows,128] if name in ('pv_raw','pv_bf16') else [12,rows,rows])
            count=16*causal if name=='dot_parts' else 36*rows if name=='normalizer' else 1536*rows if name in ('pv_raw','pv_bf16') else causal
            require(f['shape']==shape and f['observed_words']==f['writes']==count and f['identical_repeats']==0,
                    'packed multiplicity/geometry')
        require(observation['native_acceptance']=='NOT_EVALUATED_BY_OBSERVER' and observation['observer_error'] is None,
                'observation is not native acceptance')
    return evidence


def load(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_BYTES, 'bounded regular evidence file')
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==FILE_SHA256, 'archived evidence bytes changed')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'duplicate evidence key');result[key]=value
        return result
    def constant(value):raise ValueError('nonfinite JSON')
    return validate(json.loads(raw,object_pairs_hook=pairs,parse_constant=constant))


def verify_observer(root):
    relative='candidates/qwen2_resident_matrix/attention_packed_observation/pins.json'
    raw=(Path(root)/relative).read_bytes()
    require(hashlib.sha256(raw).hexdigest()=='10f4c2fcaafe9be96298049611c86307ebff54787a2490b6bbe62e9b01153a8f',
            'executed observer version changed')
    p=json.loads(raw);mapping={**p['runtime'],**p['own'],relative:hashlib.sha256(raw).hexdigest()}
    require(len(mapping)==184 and hashlib.sha256(json.dumps(mapping,sort_keys=True,separators=(',',':')).encode()).hexdigest()==
            '92268dce7c2ab0a65168a75219191a405891b2d4d2e0b61d919900a4d43c927c', 'executed source map differs')
    return True
