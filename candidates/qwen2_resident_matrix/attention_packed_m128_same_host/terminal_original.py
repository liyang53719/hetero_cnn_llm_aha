"""Strict private-receipt postflight for original linked packed M128 Public21.

Stdlib only. Never imports DUT code, opens tensor/reference data, launches a
process, or grants execution. Caller must independently authenticate the child
exit/completion marker and hash of these exact bytes. Structural validation is
not proof against a malicious producer capable of forging an entire receipt.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import stat

PROFILE = 'qwen2-public-pv16-packed-m128-linked-v1'
ROWS = 128
PAST_TOKENS = 0
HEADS = 12
HEAD_DIM = 128
DOT_PART_WIDTH = 16
CAUSAL_WORDS = HEADS * ROWS * (ROWS + 1) // 2
PV_WORDS = HEADS * ROWS * HEAD_DIM
SILU_WORDS = ROWS * 8960
REFERENCE_REUSE = 'explicitly reused same-input M128 sequential/block-pair and native outputs; original gates retained'
POLICY = 'qwen2-public21-official-bf16-v2-qkv-explicit-block-pair-v1'
OBSERVER = 'qwen2-packed-tiled-causal-observation-v1'
OBSERVER_CODE_PINS = {
    'capture.py':'1b9d249efa9fba12c8956b4eeba3a7639f896434a239beb3e68dd95b7b2b9e9f',
    'monitor.py':'29bb957e28755e691a44768dffcc09bee0fa2c509ce8252d20fda1da41544bb5'}
PASS = 'PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES'
MAX_JSON = 16 * 1024 * 1024
MAX_CONTROL_JSON = 2 * 1024 * 1024
WIDTHS = dict(zip(('n0','qr','kr','v','q','k','att','o','r','n1','gate','up','act','down','y'),
                 (1536,1536,256,256,1536,256,1536,1536,1536,1536,8960,8960,8960,1536,1536)))
ACTUAL_WIDTHS = dict(WIDTHS, qraw=1536, kraw=256, vraw=256, kv=512)
FIELDS = ('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp',
          'softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
CAUSAL = ('scores','logits','softmax_fp32','prob')
OBSERVED = (*CAUSAL, 'pv', 'silu')
STAGE_SHAPES = {n:[1,ROWS,w] for n,w in WIDTHS.items()}
STAGE_SHAPES.update(q=[1,HEADS,ROWS,HEAD_DIM], k=[1,2,ROWS,HEAD_DIM], cache_k=[1,2,ROWS,HEAD_DIM],
    cache_v=[1,2,ROWS,HEAD_DIM], repeat_k=[1,HEADS,ROWS,HEAD_DIM], repeat_v=[1,HEADS,ROWS,HEAD_DIM],
    x=[1,ROWS,1536], cos=[ROWS,HEAD_DIM], sin=[ROWS,HEAD_DIM], silu=[1,ROWS,8960],
    scores=[1,HEADS,ROWS,ROWS], logits=[1,HEADS,ROWS,ROWS], softmax_fp32=[1,HEADS,ROWS,ROWS],
    prob=[1,HEADS,ROWS,ROWS], pv=[1,HEADS,ROWS,HEAD_DIM])
THRESHOLDS = dict(block=dict(max_abs=0.05,mean_abs=0.01),
    operator=dict(max_abs=0.03125,mean_abs=0.005),
    source='spec/numerical_contract.md',
    sha256='5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5',
    scope='Existing BF16 v0 operator/block budget; not an FP32, logits, or model-quality contract')
METRIC_KEYS = ('shape','elements','max_abs','mean_abs','relative_l2','cosine',
    'normalized_max_abs','different_elements','bit_exact','first_difference_flat',
    'actual_f32_sha256','reference_f32_sha256','finite')
TOP_KEYS = ('status','policy','rows','source_sha256','input_spec','binaries','snapshot',
    'snapshot_sha256','rtl_executed','scala_executed','hardware_cycles',
    'prelaunch_intermediate_payloads','old_pass_inherited','native_acceptance',
    'enable_raw_kv','raw_kv_source_profile','fresh_profile','fresh_assets','fresh_provenance',
    'loaded_inputs','metadata','prefix_execution','prefix_host_wall_seconds','execution',
    'whole_terminal_host_wall_seconds','observation','sealed_actual_outputs','sealed_silu_sha256',
    'comparison','source_sha256_after','executed_imports_observed','full_29_node_acceptance',
    'actual_dataflow_pass','host_wall_seconds','host_cpu_seconds','host_peak_rss_kib')
COMPARISON_KEYS = ('whole_outputs','actual_observed_nodes','fixed_arithmetic_pass','methods','thresholds',
    'historical_diagnostic_failures','full_29_node_acceptance','missing_nodes','partially_observed_nodes',
    'future_score_materialization','new_official_forward_executed','native_execution_reused',
    'reference_layout','reference_reuse','old_sequential_producer_diagnostic','independent_reference',
    'official_target','independent_self_cache_is_auxiliary','old_sequential_producer_is_auxiliary',
    'acceptance_requires_all_assigned_official_observed_node_gates')
OBSERVATION_KEYS = ('schema','status','source_sha256','source_version','job','terminal',
    'accepted_retirement','observer_error','fields','packed_multiplicity','trace_api',
    'prior_observation_results_inherited','full_29_node_gate','whole_block_terminal_observed',
    'physical_publication_observed','hardware_simulation','future_scores_observed','numerical_policy',
    'native_acceptance','matrix_binary_provenance_verified_by_observer','pv_bf16_boundary')


PREFIX = 'candidates/qwen2_resident_matrix/'
REQUIRED_SOURCES = (
    'attention_packed_m128_entry/pins.json', 'attention_packed_m128_entry/contract.py',
    'attention_packed_m128_entry/composition.py', 'attention_packed_m128_entry/profile.py',
    'attention_packed_m128_entry/prepare.py', 'attention_packed_m128_assets/pins.json',
    'attention_packed_m128_assets/admission.py', 'attention_packed_m128_assets/origin.py',
    'attention_packed_m128_assets/views.py', 'attention_packed_m128_assets/prerequisite.py',
    'attention_packed_m128_assets/provenance.json', 'attention_packed_tiled_observation/pins.json',
    'attention_packed_tiled_observation/monitor.py', 'attention_packed_tiled_observation/capture.py',
    'attention_packed_owner/schedule.py', 'dense_block_reduce/check_public_numeric.py',
    'official_bf16/check_numeric.py', 'ffn_public/fullgraph_execution.py')
INPUT_X_SHA256 = 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'
ARENA_SHA256 = 'e96def26157427fc60a44f1af7a9a8443010eb5327c1ccb9b93c3b0e70fcafe7'
NATIVE_RESULT_SHA256 = 'd2766a40113de2cb07c1b477e1ba17a624022f574f99b7cfa46b41210e4bb155'
ORIGIN_MANIFEST_SHA256 = '50c005dc917f08f56e47b35c45e030446377ce30b2e5f280e5c6f6dbc92e466b'
LIBRARY_SHA256 = 'a31f0cd5fd8184543ff489cc1cb2978d6f049c09eaa3edb24698e765360d4ff8'
COMPILE_SHA256 = '76ca454ca9433859b2cd517908759b26a5f311319efad9e780592c86a7d093ae'
SNAPSHOT_KEYS = ('schema','status','rows','epoch','enable_packed','enable_raw_kv','fresh_profile',
    'raw_kv_source_profile','reduction_policy','old_pass_inherited','source_sha256','source_manifest_sha256',
    'input_spec','binaries','loaded_inputs','metadata','fresh_assets','reference','independent_reference',
    'host_tools','original_snapshot','original_snapshot_sha256','policy','prelaunch_intermediate_payloads')
PROVENANCE_KEYS = ('profile','fresh_assets','new_official_forward_executed','native_execution_reused',
    'oracle_execution_reused','historical_receipts_reused','actual_chain_executed','old_pass_inherited',
    'full_29_node_acceptance','origin_identity','m16_prerequisite','original_m128_numerical_pass_inherited',
    'native_result_sha256','native_status','native_vs_independent_failed_stages','producer_sha256',
    'sequential_cpp_sha256','reduced_cpp_sha256','origin_before_after_unchanged')
REFERENCE_KEYS = ('fresh_profile','roots','directory','table_path','fresh_lookup','inputs','threshold_policy',
    'official_reference_identity','tensors','prior_failures','fresh_provenance','artifacts',
    'native_execution_reused','oracle_execution_reused','old_pass_inherited')
INDEPENDENT_REFERENCE_KEYS = ('fresh_profile','roots','directory','rows','past_tokens','result_sha256',
    'readonly_input','fresh_lookup','artifacts','actual_chain_executed','native_acceptance','fresh_provenance')
RAW_SHAPES = {'raw_stages/phase_%d_%s_recipe.f32le'%(i,n):[1,ROWS,w]
              for i,(n,w) in enumerate(WIDTHS.items())}
RAW_SHAPES.update({'raw_stages/'+n+'.f32le':STAGE_SHAPES[n]
                  for n in ('cache_k','cache_v','scores','logits','softmax_fp32','prob','silu')})
NATIVE_SHAPES = dict(STAGE_SHAPES,mask=[1,1,ROWS,ROWS])
REFERENCE_SHAPES = dict(RAW_SHAPES)
REFERENCE_SHAPES.update({'tensors/candidate_'+n+'.f32le':shape for n,shape in NATIVE_SHAPES.items()})
REFERENCE_SHAPES.update({'references/'+method+'/'+n+'.f32le':shape
    for method in ('official_self_cache','independent_self_cache') for n,shape in NATIVE_SHAPES.items()})


class InvalidReceipt(ValueError):
    """Constant error codes only: no caller data, paths, metrics, or log excerpts."""


def need(ok, code):
    if not ok:
        raise InvalidReceipt(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value, *, pretty=False):
    options = dict(sort_keys=True, allow_nan=False)
    options.update(dict(indent=2) if pretty else dict(separators=(',', ':')))
    return (json.dumps(value, **options)+'\n').encode()


def same(a,b):
    return encoded(a) == encoded(b)


def exact(obj, keys, code):
    need(type(obj) is dict and set(obj)==set(keys), code)


def fields_with_diagnostics(obj, required, optional, code):
    """Close terminal controls while retaining named original diagnostic branches."""
    need(type(obj) is dict and set(required)<=set(obj)<=set(required)|set(optional),code)


def integer(value, *, low=0, high=(1 << 63)-1):
    return type(value) is int and low <= value <= high


def digest(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def finite(value, *, nonnegative=False):
    return type(value) in (int,float) and math.isfinite(value) and (not nonnegative or value>=0)


def bounded_tree(value):
    stack=[(value,0)]; count=0
    while stack:
        item,depth=stack.pop();count+=1
        need(depth<=40 and count<=250000,'JSON_COMPLEXITY')
        if type(item) is dict:
            need(len(item)<=16384 and all(type(k) is str and len(k)<=4096 and '\x00' not in k and
                 all(not 0xd800<=ord(c)<=0xdfff for c in k) for k in item),'JSON_OBJECT')
            stack.extend((v,depth+1) for v in item.values())
        elif type(item) is list:
            need(len(item)<=16384,'JSON_ARRAY')
            stack.extend((v,depth+1) for v in item)
        elif type(item) is str:
            need(len(item)<=8192 and '\x00' not in item and
                 all(not 0xd800<=ord(c)<=0xdfff for c in item),'JSON_STRING')
        elif type(item) is float:
            need(math.isfinite(item),'JSON_NONFINITE')
        elif type(item) is int:
            need(-(1<<64)<=item<1<<64,'JSON_INTEGER')
        else:
            need(item is None or type(item) is bool,'JSON_TYPE')


def strict_json(raw, *, max_bytes=MAX_JSON):
    need(type(max_bytes) is int and 0<max_bytes<=MAX_JSON,'JSON_BOUND')
    need(type(raw) is bytes and 0<len(raw)<=max_bytes,'JSON_SIZE')
    def pairs(items):
        obj={}
        for k,v in items:
            need(k not in obj,'JSON_DUPLICATE')
            obj[k]=v
        return obj
    def constant(_):
        raise InvalidReceipt('JSON_NONFINITE')
    try:
        result=json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, InvalidReceipt):
            raise
        raise InvalidReceipt('JSON_DECODE') from None
    bounded_tree(result)
    return result


def read_bound(path, expected, *, max_bytes=MAX_JSON):
    need(type(max_bytes) is int and 0<max_bytes<=MAX_JSON,'JSON_BOUND')
    need(digest(expected),'EXPECTED_DIGEST')
    try:
        p=Path(path).absolute()
        need('..' not in p.parts,'PATH_TRAVERSAL')
        cur=Path(p.anchor)
        for part in p.parts[1:]:
            cur/=part
            need(not stat.S_ISLNK(cur.lstat().st_mode),'PATH_SYMLINK')
        fd=os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            need(stat.S_ISREG(before.st_mode) and 0<before.st_size<=max_bytes,'FILE_SIZE_OR_TYPE')
            raw=stream.read(max_bytes+1)
            after=os.fstat(stream.fileno())
        need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
             (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'FILE_CHANGED')
        need(len(raw)==before.st_size and sha(raw)==expected,'SAME_BYTE_DIGEST')
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc,InvalidReceipt):
            raise
        raise InvalidReceipt('FILE_READ') from None
    return p,raw,strict_json(raw,max_bytes=max_bytes)


def source_map(sources):
    need(type(sources) is dict and 1<=len(sources)<=1024,'SOURCE_MAP')
    for k,v in sources.items():
        need(type(k) is str and k and '\\' not in k and '\x00' not in k and
             not k.startswith('/') and all(p not in ('','.','..') for p in k.split('/')) and digest(v),'SOURCE_ENTRY')
    need(sources.get('spec/numerical_contract.md')==THRESHOLDS['sha256'],'POLICY_SOURCE')
    for k in REQUIRED_SOURCES:
        need(PREFIX+k in sources,'SOURCE_INCOMPLETE')
    for name,value in OBSERVER_CODE_PINS.items():
        need(sources[PREFIX+'attention_packed_tiled_observation/'+name]==value,'OBSERVER_SOURCE_PIN')


def canonical_path(value, *, absolute):
    need(type(value) is str and value and '\\' not in value and '\x00' not in value and
         value.startswith('/') is absolute and '..' not in value.split('/') and
         str(Path(value))==value and (absolute or all(x not in ('','.','..') for x in value.split('/'))),
         'REFERENCE_PATH')


def record(value, shape, *, absolute=False):
    exact(value,('root','path','bytes','sha256'),'REFERENCE_RECORD_FIELDS')
    need(value['root']=='origin' and integer(value['bytes'],low=1) and
         value['bytes']==4*math.prod(shape) and digest(value['sha256']),'REFERENCE_RECORD_IDENTITY')
    canonical_path(value['path'],absolute=absolute)


def check_snapshot_identity(s):
    """Authenticate no execution; enforce the frozen same-input/late-reference contract."""
    exact(s,SNAPSHOT_KEYS,'SNAPSHOT_FIELDS')
    identity=s['fresh_assets']
    exact(identity,('profile','manifest','manifest_sha256','enable_raw_kv'),'ASSET_IDENTITY_FIELDS')
    need(identity['profile']==PROFILE and identity['enable_raw_kv'] is True and
         digest(identity['manifest_sha256']),'ASSET_IDENTITY')
    canonical_path(identity['manifest'],absolute=True)
    need(s['prelaunch_intermediate_payloads']==[],'SNAPSHOT_PRELOADS')
    reference=s['reference'];independent=s['independent_reference']
    exact(reference,REFERENCE_KEYS,'REFERENCE_FIELDS')
    exact(independent,INDEPENDENT_REFERENCE_KEYS,'INDEPENDENT_REFERENCE_FIELDS')
    p=reference['fresh_provenance'];exact(p,PROVENANCE_KEYS,'PROVENANCE_FIELDS')
    need(p['profile']==PROFILE and same(p['fresh_assets'],identity) and
         p['native_result_sha256']==NATIVE_RESULT_SHA256 and p['native_status']=='PASS_BF16_STAGE_BUDGET' and
         p['native_vs_independent_failed_stages']==[],'PROVENANCE_IDENTITY')
    for name in ('native_execution_reused','oracle_execution_reused','historical_receipts_reused',
                 'origin_before_after_unchanged'):
        need(p[name] is True,'PROVENANCE_REUSE')
    for name in ('actual_chain_executed','new_official_forward_executed','old_pass_inherited',
                 'full_29_node_acceptance','original_m128_numerical_pass_inherited'):
        need(p[name] is False,'PROVENANCE_SCOPE')
    for name in ('producer_sha256','sequential_cpp_sha256','reduced_cpp_sha256'):
        need(digest(p[name]),'PROVENANCE_DIGEST')
    origin=p['origin_identity']
    need(type(origin) is dict and origin['profile']==PROFILE and
         origin['origin_manifest_sha256']==ORIGIN_MANIFEST_SHA256 and
         origin['payload_bytes_hashed'] is True and origin['actual_chain_executed'] is False and
         origin['old_pass_inherited'] is False and origin['full_29_node_acceptance'] is False,'ORIGIN_IDENTITY')
    prerequisite=p['m16_prerequisite']
    need(type(prerequisite) is dict and prerequisite['m16_completion_verified'] is True and
         prerequisite['m128_verdict_inherited'] is False and prerequisite['old_pass_inherited'] is False and
         prerequisite['full_29_node_acceptance'] is False,'M16_PREREQUISITE_SCOPE')
    roots=reference['roots'];exact(roots,('origin',),'REFERENCE_ROOTS')
    canonical_path(roots['origin'],absolute=True)
    need(roots['origin']==str(Path(origin['origin'])/'private/assets'),'ORIGIN_ROOT_IDENTITY')
    for ref,shapes in ((reference,REFERENCE_SHAPES),(independent,RAW_SHAPES)):
        need(ref['fresh_profile']==PROFILE and same(ref['roots'],roots) and
             same(ref['fresh_provenance'],p),'REFERENCE_PROFILE_IDENTITY')
        canonical_path(ref['directory'],absolute=True)
        exact(ref['fresh_lookup'],shapes,'REFERENCE_LOOKUP_SET')
        for name,value in ref['fresh_lookup'].items():record(value,shapes[name])
        need(type(ref['artifacts']) is list and len(ref['artifacts'])==len(shapes),'REFERENCE_ARTIFACTS')
        for item in ref['artifacts']:exact(item,('root','path','bytes','sha256'),'REFERENCE_ARTIFACT_FIELDS')
        need(all(type(item['path']) is str for item in ref['artifacts']) and
             same(sorted(ref['artifacts'],key=lambda item:item['path']),
                  sorted([dict(value,path=name) for name,value in ref['fresh_lookup'].items()],key=lambda item:item['path'])),
             'REFERENCE_ARTIFACTS')
    tensors=reference['tensors']
    need(type(tensors) is list and len(tensors)==len(NATIVE_SHAPES),'REFERENCE_TENSOR_SET')
    names=[]
    for tensor in tensors:
        exact(tensor,('name','shape','export_shape','path','sha256'),'REFERENCE_TENSOR_FIELDS')
        name=tensor['name'];need(type(name) is str and name in NATIVE_SHAPES,'REFERENCE_TENSOR_NAME')
        names.append(name)
        exported=[1,ROWS,1536 if name=='q' else 256] if name in ('q','k') else NATIVE_SHAPES[name]
        need(same(tensor['shape'],NATIVE_SHAPES[name]) and same(tensor['export_shape'],exported) and
             tensor['path']=='candidate_'+name+'.f32le' and tensor['sha256']==
             reference['fresh_lookup']['tensors/'+tensor['path']]['sha256'],'REFERENCE_TENSOR_IDENTITY')
    need(names==sorted(NATIVE_SHAPES),'REFERENCE_TENSOR_INVENTORY')
    need(integer(independent['rows']) and independent['rows']==ROWS and
         type(independent['past_tokens']) is int and independent['past_tokens']==PAST_TOKENS and
         independent['actual_chain_executed'] is False and independent['native_acceptance'] is False and
         digest(independent['result_sha256']),'INDEPENDENT_REFERENCE_SCOPE')
    need(reference['native_execution_reused'] is True and reference['oracle_execution_reused'] is True and
         reference['old_pass_inherited'] is False and reference['prior_failures']=={} and
         same(reference['threshold_policy'],THRESHOLDS),'REFERENCE_POLICY')
    original=s['input_spec']['original_input']
    need(s['input_spec']['fresh_profile']==PROFILE and
         same(s['input_spec']['metadata_sha256'],{identity['manifest']:identity['manifest_sha256']}) and
         same(original['token_ids'],list(range(ROWS))) and same(original['positions'],list(range(ROWS))) and
         original['input_x_sha256']==INPUT_X_SHA256 and original['readonly_sha256']==ARENA_SHA256 and
         type(original['intermediate_preloads']) is int and original['intermediate_preloads']==0 and
         same(reference['inputs'],dict(original,position_ids=list(range(ROWS)))),'SAME_INPUT_REFERENCE')
    readonly=independent['readonly_input']
    exact(readonly,('path','bytes','sha256','input_x_sha256'),'READONLY_FIELDS')
    need(readonly['sha256']==ARENA_SHA256 and readonly['input_x_sha256']==INPUT_X_SHA256 and
         integer(readonly['bytes'],low=1) and readonly['bytes']==original['readonly_bytes'],'READONLY_IDENTITY')
    canonical_path(readonly['path'],absolute=True)
    exact(s['loaded_inputs'],('x','rope','gamma0','gamma1','bq','bk','bv','wq','wk','wv','wo','wg','wu','wd'),
          'LOADED_INPUT_SET')
    for value in s['loaded_inputs'].values():
        exact(value,('bytes','sha256'),'LOADED_INPUT_FIELDS')
        need(integer(value['bytes'],low=1) and digest(value['sha256']),'LOADED_INPUT_IDENTITY')
    need(s['loaded_inputs']['x']==dict(bytes=ROWS*1536*4,sha256=INPUT_X_SHA256),'M128_INPUT_X')
    exact(s['binaries'],('compile_receipt','compile_sha256','library','library_sha256'),'BINARIES_FIELDS')
    need(s['binaries']['compile_sha256']==COMPILE_SHA256 and
         s['binaries']['library_sha256']==LIBRARY_SHA256,'BINARIES_IDENTITY')
    for key in ('compile_receipt','library'):canonical_path(s['binaries'][key],absolute=True)


def metric(m, shape, *, bit_exact=None):
    exact(m,METRIC_KEYS,'METRIC_FIELDS')
    need(type(m['shape']) is list and same(m['shape'],shape),'METRIC_SHAPE')
    n=math.prod(shape)
    need(integer(m['elements'],low=1) and m['elements']==n and m['finite'] is True,'METRIC_EXTENT')
    need(all(finite(m[k],nonnegative=True) for k in ('max_abs','mean_abs')),'METRIC_ERROR')
    need(m['mean_abs']<=m['max_abs'],'METRIC_ERROR_ORDER')
    need(finite(m['cosine']) and all(m[k] is None or finite(m[k],nonnegative=True)
        for k in ('relative_l2','normalized_max_abs')),'METRIC_RATIO')
    d=m['different_elements']
    need(integer(d,high=n) and type(m['bit_exact']) is bool and m['bit_exact']==(d==0),'METRIC_BITS')
    need((m['first_difference_flat'] is None if d==0 else integer(m['first_difference_flat'],high=n-1)),
         'METRIC_FIRST_DIFFERENCE')
    need(digest(m['actual_f32_sha256']) and digest(m['reference_f32_sha256']),'METRIC_HASH')
    need((m['actual_f32_sha256']==m['reference_f32_sha256'])==(d==0),'METRIC_HASH_BITS')
    if d==0:
        need(m['max_abs']==m['mean_abs']==0,'METRIC_EXACT_ERROR')
    if bit_exact is not None:
        need(m['bit_exact'] is bit_exact,'FIXED_ARITHMETIC')


def field_geometry(name):
    """Reconstruct full M128 causal occupancy, never substitute tile width for M."""
    need(name in FIELDS, 'CAPTURE_FIELD_NAME')
    shape=([HEADS,ROWS,ROWS,DOT_PART_WIDTH] if name=='dot_parts'
           else [HEADS,ROWS,3] if name=='normalizer'
           else [HEADS,ROWS,HEAD_DIM] if name in ('pv_raw','pv_bf16')
           else [HEADS,ROWS,ROWS])
    if name in ('normalizer','pv_raw','pv_bf16'):
        presence=bytes([1])*math.prod(shape)
    else:
        width=DOT_PART_WIDTH if name=='dot_parts' else 1
        presence=b''.join(b'\x01'*((t+1)*width)+b'\x00'*((ROWS-t-1)*width)
                          for t in range(ROWS))*HEADS
    frequency=bytearray(2*len(presence));frequency[::2]=presence
    return shape,presence,bytes(frequency)


def check_observation(o,sources,epoch):
    exact(o,OBSERVATION_KEYS,'OBSERVATION_FIELDS')
    need(o['schema']==o['source_version']==OBSERVER and
         o['status']=='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED' and
         same(o['source_sha256'],sources) and o['observer_error'] is None,'OBSERVATION_STATUS')
    for k in ('prior_observation_results_inherited','full_29_node_gate','whole_block_terminal_observed',
              'physical_publication_observed','hardware_simulation','future_scores_observed',
              'matrix_binary_provenance_verified_by_observer'):
        need(o[k] is False,'OBSERVATION_SCOPE')
    need(o['native_acceptance']=='NOT_EVALUATED_BY_OBSERVER' and
         o['numerical_policy']=='official-bf16-v1','OBSERVATION_CLAIM')
    exact(o['fields'],FIELDS,'CAPTURE_FIELD_SET')
    for name,f in o['fields'].items():
        exact(f,('shape','words','observed_words','raw_sha256','presence_sha256','frequency_sha256',
                 'writes','identical_repeats'),'CAPTURE_FIELDS')
        shape,presence,frequency=field_geometry(name)
        need(same(f['shape'],shape),'CAPTURE_SHAPE')
        for k,v in dict(words=len(presence),observed_words=sum(presence),writes=sum(presence),identical_repeats=0).items():
            need(integer(f[k]) and f[k]==v,'CAPTURE_COUNTS')
        need(digest(f['raw_sha256']) and f['presence_sha256']==sha(presence) and
             f['frequency_sha256']==sha(frequency),'CAPTURE_CAUSAL_MASK')
    need(same(o['packed_multiplicity'],dict(causal_field=1,normalizer_per_head_query=1,pv_word=1,
         legacy_probability_repeats=8,legacy_normalizer_repeats='8*(query+1)',synthetic_repeats=0)),
         'PACKED_MULTIPLICITY')
    need(o['trace_api']=='CPython sys.monitoring pinned packed run LINE and actual scalar/tick PY_RETURN' and
         o['pv_bf16_boundary']=='actual store words; ACK coverage requires accepted successful owner terminal',
         'OBSERVATION_PROVENANCE')
    j,t,r=o['job'],o['terminal'],o['accepted_retirement']
    exact(j,('a','b','c','dst','k','kind','m','n','tag','write_bytes',
             'activation_bf16','weight_bf16','output_bf16'),'OBSERVATION_JOB_FIELDS')
    exact(t,('cycles','executed_macs','status','tag','useful_macs','write_bytes'),'OBSERVATION_TERMINAL_FIELDS')
    need(integer(j['k']) and j['k']==HEAD_DIM and integer(j['n']) and j['n']==1536 and
         all(integer(j[k]) for k in ('a','b','c','dst')) and
         all(j[k] is False for k in ('activation_bf16','weight_bf16','output_bf16')) and
         all(integer(t[k]) for k in ('cycles','executed_macs','useful_macs')),'OBSERVATION_JOB_GEOMETRY')
    need(type(j) is dict and type(t) is dict and j['kind']=='Attention' and integer(j['m']) and j['m']==ROWS and
         integer(j['tag']) and j['tag']==(epoch<<16)|12 and t['tag']==j['tag'] and
         integer(t['tag']) and t['status'] is None and integer(j['write_bytes']) and
         integer(t['write_bytes']) and j['write_bytes']==t['write_bytes']==ROWS*1536*4,'OWNER_TERMINAL')
    exact(r,('state','poison','same_services','same_job','matrix_released','matrix_reset_required',
        'client_retired','memory_pending','scalar_released','scratch_pending','scratch_leased',
        'scratch_request','scratch_write_tag','packed_memory_tag'),'RETIREMENT_FIELDS')
    need(r['state']=='idle','OWNER_IDLE')
    for k in ('same_services','same_job','matrix_released','client_retired','scalar_released'):
        need(r[k] is True,'OWNER_RELEASE')
    for k in ('poison','matrix_reset_required','memory_pending','scratch_pending','scratch_leased',
              'scratch_request','scratch_write_tag','packed_memory_tag'):
        need(r[k] is False,'OWNER_OBLIGATION')


def check_comparison(c,s,o,actual):
    exact(c,COMPARISON_KEYS,'COMPARISON_FIELDS')
    need(c['fixed_arithmetic_pass'] is True and c['official_target']=='official_self_cache' and
         c['acceptance_requires_all_assigned_official_observed_node_gates'] is True and
         c['independent_self_cache_is_auxiliary'] is True and c['old_sequential_producer_is_auxiliary'] is True,
         'COMPARISON_POLICY')
    need(c['full_29_node_acceptance'] is False and c['future_score_materialization'] is False and
         c['new_official_forward_executed'] is False and c['native_execution_reused'] is True and
         c['missing_nodes']==['explicit_mask_tensor'] and
         c['partially_observed_nodes']==['scores','logits','prob','softmax_fp32'],'COMPARISON_SCOPE')
    need(same(c['thresholds'],THRESHOLDS) and same(c['thresholds'],s['reference']['threshold_policy']),
         'UNCHANGED_THRESHOLDS')
    need(same(c['independent_reference'],s['independent_reference']) and
         same(c['reference_layout'],dict(qk_storage='token_major',**s['reference']['fresh_provenance'])) and
         same(c['historical_diagnostic_failures'],s['reference']['prior_failures']),'REFERENCE_IDENTITY')
    need(c['reference_reuse']==REFERENCE_REUSE,
         'REFERENCE_REUSE')
    exact(c['whole_outputs'],WIDTHS,'FIXED_STAGE_SET')
    for name,m in c['whole_outputs'].items():
        metric(m,[ROWS*WIDTHS[name]],bit_exact=True)
        need(m['actual_f32_sha256']==actual[name]['sha256'],'FIXED_ACTUAL_HASH')
        relative='raw_stages/phase_%d_%s_recipe.f32le'%(list(WIDTHS).index(name),name)
        need(m['reference_f32_sha256']==s['independent_reference']['fresh_lookup'][relative]['sha256'],
             'FIXED_REFERENCE_HASH')
    exact(c['actual_observed_nodes'],OBSERVED,'FIXED_OBSERVED_SET')
    for name,m in c['actual_observed_nodes'].items():
        n=CAUSAL_WORDS if name in CAUSAL else PV_WORDS if name=='pv' else SILU_WORDS
        metric(m,[n],bit_exact=True)
    need(c['actual_observed_nodes']['silu']['reference_f32_sha256']==
         s['independent_reference']['fresh_lookup']['raw_stages/silu.f32le']['sha256'],'SILU_REFERENCE_HASH')
    need(c['actual_observed_nodes']['pv']['actual_f32_sha256']==o['fields']['pv_bf16']['raw_sha256'],
         'PV_OBSERVATION_HASH')
    exact(c['methods'],('official_self_cache','independent_self_cache'),'METHODS')
    for method,report in c['methods'].items():
        exact(report,('stages','failed_stages','numerical_status'),'METHOD_FIELDS')
        exact(report['stages'],STAGE_SHAPES,'OFFICIAL_STAGE_SET')
        failures=[]
        for name,stage in report['stages'].items():
            exact(stage,('metrics','verdict','original_shape','coverage','observed_elements','unobserved_elements'),
                  'OFFICIAL_STAGE_FIELDS')
            shape=STAGE_SHAPES[name]; count=math.prod(shape); causal=name in CAUSAL
            n=CAUSAL_WORDS if causal else count
            need(same(stage['original_shape'],shape) and integer(stage['observed_elements']) and
                 integer(stage['unobserved_elements']) and stage['observed_elements']==n and
                 stage['unobserved_elements']==count-n and stage['coverage']==
                 ('actual_causal_positions_only' if causal else 'complete'),'OFFICIAL_COVERAGE')
            # pv is also masked by the comparator, with all positions present.
            metric(stage['metrics'],[n] if causal or name=='pv' else shape)
            m=stage['metrics'];v=stage['verdict']
            if method=='independent_self_cache':
                need(m['actual_f32_sha256']==c['methods']['official_self_cache']['stages'][name]['metrics']['actual_f32_sha256'],
                     'SAME_ACTUAL_METHOD_INPUT')
            if name=='softmax_fp32':
                expected=dict(contract=None,passed=None,status='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE')
            else:
                role='block' if name=='y' else 'operator';limit=THRESHOLDS[role]
                passed=m['max_abs']<=limit['max_abs'] and m['mean_abs']<=limit['mean_abs']
                expected=dict(contract='spec/numerical_contract.md:'+role,limits=limit,passed=passed)
                if not passed:failures.append(name)
            need(same(v,expected),'ORIGINAL_VERDICT')
            if name in c['actual_observed_nodes']:
                need(m['actual_f32_sha256']==c['actual_observed_nodes'][name]['actual_f32_sha256'],
                     'OBSERVED_METRIC_HASH')
            elif name in WIDTHS and name not in ('q','k'):
                need(m['actual_f32_sha256']==actual[name]['sha256'],'OFFICIAL_ACTUAL_HASH')
        need(type(report['failed_stages']) is list and len(set(report['failed_stages']))==len(report['failed_stages']) and
             set(report['failed_stages'])==set(failures) and report['numerical_status']==
             ('FAIL' if failures else 'PASS_OBSERVED_ONLY'),'METHOD_STATUS')
        if method=='official_self_cache':
            need(not failures,'OFFICIAL_ASSIGNED_GATE_FAILURE')
    old=c['old_sequential_producer_diagnostic']
    exact(old,('whole_outputs','actual_observed_nodes','fixed_arithmetic_pass'),'OLD_DIAGNOSTIC_FIELDS')
    exact(old['whole_outputs'],WIDTHS,'OLD_DIAGNOSTIC_STAGES')
    exact(old['actual_observed_nodes'],OBSERVED,'OLD_DIAGNOSTIC_OBSERVED')
    for name,m in old['whole_outputs'].items():
        metric(m,[1,ROWS,WIDTHS[name]])
        need(m['actual_f32_sha256']==actual[name]['sha256'],'OLD_ACTUAL_HASH')
    for name,m in old['actual_observed_nodes'].items():
        n=CAUSAL_WORDS if name in CAUSAL else PV_WORDS if name=='pv' else SILU_WORDS
        metric(m,[n] if name!='silu' else [1,ROWS,8960])
        need(m['actual_f32_sha256']==c['actual_observed_nodes'][name]['actual_f32_sha256'],'OLD_OBSERVED_HASH')
    need(type(old['fixed_arithmetic_pass']) is bool and old['fixed_arithmetic_pass']==
         all(m['bit_exact'] for group in ('whole_outputs','actual_observed_nodes') for m in old[group].values()),
         'OLD_DIAGNOSTIC_STATUS')


def check_execution(e,actual,epoch):
    fields_with_diagnostics(e,('status','same_owner_and_banks','same_physical_memory_and_services',
        'full_block_executed','full_block_software_model_executed','attention_suffix_executed',
        'public_host_python_model_executed','scala_host_executed','rtl_executed','actual_idma',
        'protocol_model_ticks_are_hardware_cycles','reference_arithmetic_executed','hardware_cycles',
        'full_wall_mac_utilization','native_acceptance','inherited_native_acceptance_label',
        'host','memory','matrix','reports'),('virtual_outputs',),'EXECUTION_FIELDS')
    need(type(e) is dict and e['status']=='PUBLIC21_PC0_20_SOFTWARE_EXECUTED','EXECUTION_STATUS')
    for k in ('same_owner_and_banks','same_physical_memory_and_services','full_block_executed',
              'full_block_software_model_executed','attention_suffix_executed','public_host_python_model_executed'):
        need(e[k] is True,'EXECUTION_COMPLETION')
    for k in ('scala_host_executed','rtl_executed','actual_idma','protocol_model_ticks_are_hardware_cycles',
              'reference_arithmetic_executed'):
        need(e[k] is False,'EXECUTION_SCOPE')
    need(e['hardware_cycles'] is None and e['full_wall_mac_utilization'] is None and
         e['native_acceptance']=='NOT_EVALUATED_BY_EXECUTION_SEE_COMPARISON' and
         e['inherited_native_acceptance_label']=='UNCHANGED_FAIL_POLICY_PENDING','EXECUTION_CLAIM')
    h=e['host']
    fields_with_diagnostics(h,('launch_result','accepted','reset_required','same_owner_and_banks',
        'model_ticks_are_hardware_cycles','events','completions','requests'),
        ('counters_source','down_terminal_tick','hardware_cycles','numerical_policy','published',
        'qkv_reduction_profile','qkv_reductions','trace','validated_policy_jobs','virtual'),'HOST_FIELDS')
    result=h['launch_result'];accepted=h['accepted']
    fields_with_diagnostics(result,('status','completed','jobs','write_bytes'),
        ('executed_macs','useful_macs'),'LAUNCH_RESULT_FIELDS')
    fields_with_diagnostics(accepted,('request_fire','owner_result_fire','completion_fire','result_fire'),
        ('completion_backpressure_edges','host_model_ticks','idle_owner_edges','ordinary_owner_edges',
         'raw_kv_parent_edges','result_backpressure_edges'),'HOST_ACCEPTED_FIELDS')
    need(type(result) is dict and result['status'] is None and integer(result['completed']) and
         integer(result['jobs']) and result['completed']==21 and result['jobs']==17,'WHOLE_TERMINAL')
    for k,v in dict(request_fire=17,owner_result_fire=17,completion_fire=21,result_fire=1).items():
        need(integer(accepted[k]) and accepted[k]==v,'HOST_HANDSHAKES')
    need(h['reset_required'] is False and h['same_owner_and_banks'] is True and
         h['model_ticks_are_hardware_cycles'] is False and same(h['events'],list(range(22))),'HOST_RETIREMENT')
    need(type(h['completions']) is list and len(h['completions'])==21,'COMPLETION_COUNT')
    for pc,item in enumerate(h['completions']):
        fields_with_diagnostics(item,('pc','status','signal'),('engine','tick'),'COMPLETION_FIELDS')
        need(integer(item['pc']) and item['pc']==pc and item['status'] is None and
             integer(item['signal']) and item['signal']==pc+1,'COMPLETION_ORDER')
    need(type(h['requests']) is list and len(h['requests'])==17,'OWNER_JOB_COUNT')
    prefix=e['reports']
    need(type(prefix) is list and [v['pcs'] for v in prefix]==
         [[10,11,12],[13],[14],[15],[16,17,18],[19],[20]],'SUFFIX_REPORTS')
    outputs=e['memory']['outputs']
    exact(outputs,(*actual,'scores','probabilities','workspace'),'PHYSICAL_OUTPUTS')
    for name in ('gate','up','scores','probabilities','workspace'):
        item=outputs[name]
        exact(item,('bytes','written_bytes','ack_bytes','terminal','published','sha256'),'PHYSICAL_OUTPUT_FIELDS')
        need(item['terminal'] is False and item['published'] is False and
             all(integer(item[k]) for k in ('bytes','written_bytes','ack_bytes')) and
             item['bytes']>0 and item['written_bytes']==item['ack_bytes']<=item['bytes'] and
             digest(item['sha256']),'VIRTUAL_OUTPUT_SCOPE')
        if name!='workspace':
            extent=ROWS*ACTUAL_WIDTHS[name]*4 if name in ('gate','up') else HEADS*ROWS*ROWS*4
            need(item['bytes']==extent and item['written_bytes']==0,'VIRTUAL_OUTPUT_UNWRITTEN')
    total=0
    for name,record in actual.items():
        if name in ('gate','up'):continue
        item=outputs[name]
        exact(item,('bytes','written_bytes','ack_bytes','terminal','published','sha256'),'PHYSICAL_OUTPUT_FIELDS')
        need(item['terminal'] is True and item['published'] is True and
             all(integer(item[k]) and item[k]==record['bytes'] for k in ('bytes','written_bytes','ack_bytes')) and
             item['sha256']==record['sha256'],'PHYSICAL_ACK_PUBLICATION')
        total+=record['bytes']
    need(integer(result['write_bytes']) and result['write_bytes']==total,'WHOLE_WRITE_BYTES')
    need(e['matrix']['reset_required'] is False and e['matrix']['hardware_simulation'] is False and
         e['matrix']['same_accumulator_resource'] is True,'MATRIX_RETIREMENT')


def actual_statuses(value):
    """Successful original owner/backend reports cannot contain a failed status."""
    stack=[value]
    while stack:
        item=stack.pop()
        if type(item) is list:stack.extend(item)
        elif type(item) is dict:
            for key,v in item.items():
                if key=='status':need(v is None,'ACTUAL_FAILED_STATUS')
                stack.append(v)


def check_claims(value):
    """Reject upgraded/unknown acceptance claims anywhere, including diagnostics."""
    allowed_native={'PASS_OBSERVED_ONLY','NOT_EVALUATED_BY_EXECUTION_SEE_COMPARISON',
        'UNCHANGED_FAIL_POLICY_PENDING','NOT_EVALUATED_BY_OBSERVER','NOT_NATIVE_ACCEPTED',
        'NOT_EVALUATED','REFERENCE_ONLY_NOT_NATIVE_ACCEPTED'}
    stack=[(value,())]
    while stack:
        item,path=stack.pop()
        if type(item) is list:stack.extend((v,path+(str(i),)) for i,v in enumerate(item))
        elif type(item) is dict:
            for k,v in item.items():
                if 'acceptance' in k or k=='accepted_full_block':
                    if k=='acceptance_requires_all_assigned_official_observed_node_gates':
                        need(v is True and path==('comparison',),'UNKNOWN_ACCEPTANCE')
                    elif k=='native_acceptance':
                        need(v is False or (type(v) is str and v in allowed_native and
                             (v!='PASS_OBSERVED_ONLY' or path==())), 'UNKNOWN_ACCEPTANCE')
                    elif k in ('inherited_native_acceptance_label','native_m128_and_fp32_final_acceptance'):
                        need(v=='UNCHANGED_FAIL_POLICY_PENDING','UNKNOWN_ACCEPTANCE')
                    else:
                        need(v is False,'UNKNOWN_ACCEPTANCE')
                if k in ('rtl_accepted','hardware_accepted','full29_accepted','full_29_node_gate'):
                    need(v is False,'UNKNOWN_ACCEPTANCE')
                if k.endswith('_accepted') and type(v) is bool:
                    need(v is False,'UNKNOWN_ACCEPTANCE')
                stack.append((v,path+(k,)))


def validate_terminal(summary_path, expected_summary_sha256, expected_sources,
                      snapshot_path, expected_snapshot_sha256):
    """Return only bounded statuses/hash/count facts; errors have constant codes."""
    try:
        bounded_tree(expected_sources)
        source_map(expected_sources)
        snap_path,_snap_raw,s=read_bound(snapshot_path,expected_snapshot_sha256,max_bytes=MAX_CONTROL_JSON)
        _summary_path,raw,r=read_bound(summary_path,expected_summary_sha256)
        check_snapshot_identity(s)
        need(type(s) is dict and s['status']=='PREPARED_REDUCED_PUBLIC21_NOT_EXECUTED' and
             type(s['schema']) is int and s['schema']==1 and type(s['rows']) is int and s['rows']==ROWS and
             integer(s['epoch']) and s['enable_packed'] is True and s['enable_raw_kv'] is True and
             s['fresh_profile'] is True and s['raw_kv_source_profile']==PROFILE and
             s['reduction_policy']==POLICY and s['old_pass_inherited'] is False,'SNAPSHOT_PROFILE')
        need(same(s['source_sha256'],expected_sources) and
             s['source_manifest_sha256']==sha(encoded(expected_sources,pretty=True)),'SNAPSHOT_SOURCES')
        exact(r,TOP_KEYS,'SUMMARY_FIELDS')
        need(r['status']==PASS and type(r['rows']) is int and r['rows']==ROWS and r['policy']==POLICY and
             r['actual_dataflow_pass'] is True and r['native_acceptance']=='PASS_OBSERVED_ONLY', 'SUMMARY_STATUS')
        need(r['enable_raw_kv'] is True and r['fresh_profile'] is True and r['raw_kv_source_profile']==PROFILE and
             r['snapshot']==str(snap_path) and r['snapshot_sha256']==expected_snapshot_sha256,'SUMMARY_PROFILE')
        need(same(r['source_sha256'],expected_sources) and same(r['source_sha256_after'],expected_sources),
             'SUMMARY_SOURCES')
        for k in ('input_spec','binaries','loaded_inputs','metadata','fresh_assets'):
            need(same(r[k],s[k]),'SNAPSHOT_IDENTITY')
        need(same(r['fresh_provenance'],s['reference']['fresh_provenance']),'FRESH_PROVENANCE')
        for k in ('rtl_executed','scala_executed','old_pass_inherited','full_29_node_acceptance'):
            need(r[k] is False,'SUMMARY_SCOPE')
        need(r['hardware_cycles'] is None and r['prelaunch_intermediate_payloads']==[], 'PRELAUNCH_SCOPE')
        imports=r['executed_imports_observed']
        need(type(imports) is list and all(type(k) is str and k in expected_sources for k in imports) and
             imports==sorted(set(imports)), 'IMPORT_CLOSURE')
        for k in ('prefix_host_wall_seconds','whole_terminal_host_wall_seconds','host_wall_seconds','host_cpu_seconds'):
            need(finite(r[k],nonnegative=True),'TIMING_FINITE')
        need(r['prefix_host_wall_seconds']<=r['whole_terminal_host_wall_seconds']<=r['host_wall_seconds'] and
             integer(r['host_peak_rss_kib'],low=1),'TIMING_ORDER')
        p=r['prefix_execution']
        need(type(p) is list and len(p)==10 and all(integer(v['pc']) and v['pc']==i for i,v in enumerate(p)),
             'PREFIX_COMPLETION')
        actual=r['sealed_actual_outputs'];exact(actual,ACTUAL_WIDTHS,'SEALED_OUTPUT_SET')
        for name,v in actual.items():
            exact(v,('bytes','sha256'),'SEALED_OUTPUT_FIELDS')
            need(integer(v['bytes']) and v['bytes']==ROWS*ACTUAL_WIDTHS[name]*4 and digest(v['sha256']),
                 'SEALED_OUTPUT_IDENTITY')
        need(digest(r['sealed_silu_sha256']),'SILU_HASH')
        check_execution(r['execution'],actual,s['epoch'])
        actual_statuses(r['prefix_execution'])
        actual_statuses({k:v for k,v in r['execution'].items() if k!='status'})
        check_observation(r['observation'],expected_sources,s['epoch'])
        check_comparison(r['comparison'],s,r['observation'],actual)
        need(r['comparison']['actual_observed_nodes']['silu']['actual_f32_sha256']==r['sealed_silu_sha256'],
             'SILU_SEAL')
        check_claims(s)
        check_claims(r)
        return dict(schema=1,status='VALIDATED_ORIGINAL_M128_OBSERVED_GATES_ONLY',
            summary_sha256=sha(raw),snapshot_sha256=expected_snapshot_sha256,
            source_manifest_sha256=sha(encoded(expected_sources)),
            source_files=len(expected_sources),rows=ROWS,public_completions=21,owner_jobs=17,
            official_observed_stages=28,assigned_official_gates=27,diagnostic_fp32_stages=1,
            capture_fields=10,fixed_arithmetic_pass=True,observed_official_gates_pass=True,
            full_29_node_acceptance=False,rtl_acceptance=False,hardware_acceptance=False,
            execution_authenticated_by_this_validator=False)
    except (KeyError,TypeError,IndexError,OverflowError,RecursionError):
        raise InvalidReceipt('REQUIRED_FIELD_OR_TYPE') from None
