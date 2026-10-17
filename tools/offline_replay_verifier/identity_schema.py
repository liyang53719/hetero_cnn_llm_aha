"""Strict, offline public replay-identity schema and consistency validator.

API: validate_manifest(value, source_inputs, *, compile_sources) -> safe inventory summary.
source_inputs is the caller-authenticated complete 464-entry raw source map.
compile_sources is the separately caller-authenticated exact four-entry combined
ELF build map: three raw source inputs and the generated matrix source. The
caller derives it from the hash-authenticated tiny input contract and verifies
its equality with both composed maps. It is deliberately not inferred from raw
checkout hashes, which differ for the generated matrix translation unit.
The caller must strictly parse JSON, validate exact whole-file canonical bytes,
verify the actual CI/artifact and bind public receipts. No model/runtime-source imports, production execution, file reads, private-byte
rehashing, numerical recomputation or acceptance are performed here. SHA256
operates on public JSON identities and deterministic coverage-mask patterns;
no actual tensor values are regenerated.

Constants and projection layouts copied from reviewed replay_identity.py SHA256
f3f842ccc8e68bb34778303c110a6c92d053c0adac37dbc1bcf6dc8a2c9fe84a.
Payload pins copied from ledger SHA256
190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88.
"""
import hashlib
import json
import math
import re

EMITTER_SHA = 'f3f842ccc8e68bb34778303c110a6c92d053c0adac37dbc1bcf6dc8a2c9fe84a'
SCHEMA = 'qwen2-same-host-replay-identity-v1'
BASE = 'candidates/qwen2_resident_matrix/'
MODEL = 'Qwen/Qwen2-1.5B-Instruct'
REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
FORWARD = '9fe3f585bb4ea29f209dc705d269fbe292e1128f'
POLICY_SHA = '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'
LEDGER = 'config/payload_pins/qwen2_layer0.json'
LEDGER_SHA = '190e1fca0edff7c783c6981a6759f57162e63c4754ffc0f3481df64de9d06f88'
CONFIG = 'config/upstream/weight_headers/qwen2_1p5b/config.json'
CONFIG_SHA = 'a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136'
TABLE_SHA = '5edc3314874c1cf4a7dc9cb54f2c824b18272048f70abcf9021f021308589045'
RUNNER_SHA = 'd7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64'
MAX_JSON = 16 * 1024 * 1024
MAX_FILE = 188043264
MAX_CAPTURE = 32 * 1024 * 1024
MAX_TOTAL = 8 * 1024**3
MAX_RECORDS = 4096
CHUNK = 1024 * 1024
WIDTHS = dict(zip(('n0','qr','kr','v','q','k','att','o','r','n1','gate','up','act','down','y'),
                 (1536,1536,256,256,1536,256,1536,1536,1536,1536,8960,8960,8960,1536,1536)))
ACTUAL_WIDTHS = dict(WIDTHS, qraw=1536, kraw=256, vraw=256, kv=512, silu=8960)
STAGES = tuple(sorted((*WIDTHS, 'x','cache_k','cache_v','repeat_k','repeat_v','scores','logits',
                       'prob','pv','silu','cos','sin','mask','softmax_fp32')))
METHODS = ('official_self_cache','independent_self_cache')
MODES = ('bf16','fp32')
FIELDS = ('dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp',
          'softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16')
CAUSAL_FIELDS = FIELDS[:7]
OBSERVED_STAGES = tuple(n for n in STAGES if n != 'mask')
SCALAR_FLAGS = ('-O2','-std=c++17','-ffp-contract=off','-fno-fast-math')
LIBRARY_FLAGS = ('-shared','-fPIC','-O2','-ffp-contract=off','-fno-fast-math')
RECIPE_FLAGS = ('-shared','-fPIC','-O2','-std=c++17','-ffp-contract=off','-fno-fast-math','-fno-builtin-fmaf')
PAYLOAD_NAMES = ('embed_tokens.rows_0_255','input_layernorm.weight','mlp.down_proj.weight',
 'mlp.gate_proj.weight','mlp.up_proj.weight','post_attention_layernorm.weight','self_attn.k_proj.bias',
 'self_attn.k_proj.weight','self_attn.o_proj.weight','self_attn.q_proj.bias','self_attn.q_proj.weight',
 'self_attn.v_proj.bias','self_attn.v_proj.weight')
INPUT_PINS = {
 16:('271b8498d6c764d48a7f63fb3f314a49b3bafb7b8f62e15bf70fb2595777349c',
     '0a94ea142c28a6c1ce4b8ad928caecee9c5721bb6e4bc0eb097eebd8202aabf8'),
 128:('ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df',
      'e96def26157427fc60a44f1af7a9a8443010eb5327c1ccb9b93c3b0e70fcafe7')}
PROVIDERS = {
 'gamma0':([1,1536],'float32','input_layernorm.weight','BF16_EXPAND_F32'),
 'gamma1':([1,1536],'float32','post_attention_layernorm.weight','BF16_EXPAND_F32'),
 'bq':([1,1536],'float32','self_attn.q_proj.bias','BF16_EXPAND_F32'),
 'bk':([1,256],'float32','self_attn.k_proj.bias','BF16_EXPAND_F32'),
 'bv':([1,256],'float32','self_attn.v_proj.bias','BF16_EXPAND_F32'),
 'wq':([1536,1536],'bfloat16','self_attn.q_proj.weight','BF16_TRANSPOSE_2D'),
 'wk':([1536,256],'bfloat16','self_attn.k_proj.weight','BF16_TRANSPOSE_2D'),
 'wv':([1536,256],'bfloat16','self_attn.v_proj.weight','BF16_TRANSPOSE_2D'),
 'wo':([1536,1536],'bfloat16','self_attn.o_proj.weight','BF16_TRANSPOSE_2D'),
 'wg':([1536,8960],'bfloat16','mlp.gate_proj.weight','BF16_TRANSPOSE_2D'),
 'wu':([1536,8960],'bfloat16','mlp.up_proj.weight','BF16_TRANSPOSE_2D'),
 'wd':([8960,1536],'bfloat16','mlp.down_proj.weight','BF16_TRANSPOSE_2D')}
RECIPE_SOURCES = {
 'payload_loader':'scripts/qwen2_layer0_payload.py',
 'native_gate':'scripts/qwen2_layer0_model_gate.py',
 'scalar_layout':'scripts/qwen2_block_recipe_model.py',
 'scalar_materialization':'scripts/qwen2_bf16_materialization_candidate.py',
 'input_and_tables':'scripts/qwen2_rms_rope_prefill_candidate.py',
 'loaded_provider_recipe':BASE+'official_bf16/check_numeric.py',
 'actual_persistence':BASE+'ffn_public/fullgraph_execution.py',
 'scalar_inventory':BASE+'dense_block_reduce/reference/workload.py',
 'm16_capture':BASE+'attention_packed_observation/capture.py',
 'm128_capture':BASE+'attention_packed_tiled_observation/capture.py'}


PAYLOAD_PINS = {'embed_tokens.rows_0_255': {'shape': [256, 1536], 'source_shape': [151936, 1536], 'bytes': 786432, 'sha256': '3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014'}, 'input_layernorm.weight': {'shape': [1536], 'source_shape': [1536], 'bytes': 3072, 'sha256': 'ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e'}, 'mlp.down_proj.weight': {'shape': [1536, 8960], 'source_shape': [1536, 8960], 'bytes': 27525120, 'sha256': '8a9657234cffb29cec816483e03454846d80d3a1f4171e6bc40479f3ba73ce5a'}, 'mlp.gate_proj.weight': {'shape': [8960, 1536], 'source_shape': [8960, 1536], 'bytes': 27525120, 'sha256': '0219acbf1f5bc38fc55ee56fa6b55c82150a1a4279915090e857beb382cc0d7e'}, 'mlp.up_proj.weight': {'shape': [8960, 1536], 'source_shape': [8960, 1536], 'bytes': 27525120, 'sha256': 'a403942b0dc208a543e8434d091564cfd4b7a091c291d02d7a62ae46884e61ed'}, 'post_attention_layernorm.weight': {'shape': [1536], 'source_shape': [1536], 'bytes': 3072, 'sha256': '762cfb39d378a8f4f1d2cdf1781a94089613e51d395acc0f4d3578be2459400a'}, 'self_attn.k_proj.bias': {'shape': [256], 'source_shape': [256], 'bytes': 512, 'sha256': '56a716f9fd535d659a918afc9b7d25ad1d159dc0e9bd6da68549a155bb62ada0'}, 'self_attn.k_proj.weight': {'shape': [256, 1536], 'source_shape': [256, 1536], 'bytes': 786432, 'sha256': 'addac2eb287cc8d8caa24178c94156c67bab35bc6a9f76927f50a4f0be0ade47'}, 'self_attn.o_proj.weight': {'shape': [1536, 1536], 'source_shape': [1536, 1536], 'bytes': 4718592, 'sha256': '7613bde8e47278a40bbf05222cd0799ed873194e56a96f2f6167d4580bb1a735'}, 'self_attn.q_proj.bias': {'shape': [1536], 'source_shape': [1536], 'bytes': 3072, 'sha256': 'c68e4379e1c3701dabe73e98cda2fc87c85cce47adb6e4dc7f871fba9f497d9d'}, 'self_attn.q_proj.weight': {'shape': [1536, 1536], 'source_shape': [1536, 1536], 'bytes': 4718592, 'sha256': '142ece1271ee9eb6b1e91055e2a6293a5572bf9b5395c56c77f9584728ee89d4'}, 'self_attn.v_proj.bias': {'shape': [256], 'source_shape': [256], 'bytes': 512, 'sha256': '4ed960cd1895ac1bcc5012a0948f9b73e50b411b9b8015e9941d28e8d45fd29d'}, 'self_attn.v_proj.weight': {'shape': [256, 1536], 'source_shape': [256, 1536], 'bytes': 786432, 'sha256': 'e99b01559f13e11a0c96309f5b4e11664223aa31a2f318e49597ad8e66b0ea32'}}


class ManifestError(ValueError):
    """Fixed, path-free error code; never echo rejected public/private text."""


class _Rule:
    def __init__(self, kind):
        self.kind = kind


_HASH = _Rule('sha256')
_COMMIT = _Rule('commit')
_RUN_ID = _Rule('run_id')
_VERSION = _Rule('version')
_BOOL = _Rule('bool')


def _need(condition, code):
    if not condition:
        raise ManifestError(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def identity_digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _digest(value, size=64):
    return type(value) is str and len(value) == size and all(c in '0123456789abcdef' for c in value)


def _json_guard(value):
    """Bounded exact JSON types, including rejection of bool-as-int and cycles."""
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        _need(depth <= 48 and count <= 100000, 'JSON_COMPLEXITY')
        if type(item) is dict:
            _need(len(item) <= 4096 and all(type(k) is str and len(k) <= 256 for k in item), 'JSON_OBJECT')
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            _need(len(item) <= 4096, 'JSON_ARRAY')
            stack.extend((v, depth + 1) for v in item)
        elif type(item) is str:
            # The public grammar contains no free-form paths, logs or banners.
            _need(len(item) <= 256 and item.isascii() and all(32 <= ord(c) < 127 for c in item), 'UNSAFE_STRING')
        elif type(item) is float:
            _need(math.isfinite(item), 'JSON_NONFINITE')
        elif type(item) is int:
            _need(abs(item) < 2 ** 128, 'JSON_INTEGER')
        else:
            _need(item is None or type(item) is bool, 'JSON_TYPE')


def _match(value, expected):
    if isinstance(expected, _Rule):
        kind = expected.kind
        if kind in ('sha256', 'commit'):
            _need(_digest(value, 64 if kind == 'sha256' else 40), 'DIGEST')
        elif kind == 'run_id':
            _need(type(value) is str and 0 < len(value) <= 24 and value.isascii() and value.isdecimal()
                  and 0 < int(value) < 10 ** 24, 'CI_IDENTITY')
        elif kind == 'version':
            _need(type(value) is int and 0 <= value <= 99, 'COMPILER_VERSION')
        elif kind == 'bool':
            _need(type(value) is bool, 'SCALAR_TYPE')
        else:
            raise ManifestError('VALIDATOR_RULE')
    elif type(expected) is dict:
        _need(type(value) is dict and set(value) == set(expected), 'FIELDS')
        for key in expected:
            _match(value[key], expected[key])
    elif type(expected) is list:
        _need(type(value) is list and len(value) == len(expected), 'ARRAY')
        for item, schema in zip(value, expected):
            _match(item, schema)
    else:
        _need(type(value) is type(expected), 'SCALAR_TYPE')
        _need(value == expected, 'SCHEMA_VALUE')


def _source_map(source_inputs):
    _need(type(source_inputs) is dict and len(source_inputs) == 464, 'SOURCE_COUNT')
    for key, value in source_inputs.items():
        _need(type(key) is str and len(key) <= 2048 and
              re.fullmatch(r'[A-Za-z0-9_./-]+', key) is not None and
              all(p not in ('', '.', '..') for p in key.split('/')), 'SOURCE_PATH')
        _need(_digest(value), 'SOURCE_DIGEST')
    required = {LEDGER: LEDGER_SHA, CONFIG: CONFIG_SHA, 'spec/numerical_contract.md': POLICY_SHA,
                BASE + 'portable_same_host_m128_launch/replay_identity.py': EMITTER_SHA}
    for path, pin in required.items():
        _need(source_inputs.get(path) == pin, 'SOURCE_PIN')
    for path in (*RECIPE_SOURCES.values(), BASE + 'portable_official_producer/driver.py',
                 BASE + 'portable_official_producer_m128/driver.py',
                 BASE + 'portable_official_producer_launch/wheel-lock.json'):
        _need(path in source_inputs, 'SOURCE_REQUIRED')


def _shapes(rows):
    result = {name: [1, rows, width] for name, width in WIDTHS.items()}
    result.update(x=[1, rows, 1536], silu=[1, rows, 8960])
    for name, heads in (('q', 12), ('k', 2), ('cache_k', 2), ('cache_v', 2),
                        ('repeat_k', 12), ('repeat_v', 12), ('pv', 12)):
        result[name] = [1, heads, rows, 128]
    for name in ('scores', 'logits', 'prob', 'softmax_fp32'):
        result[name] = [1, 12, rows, rows]
    result.update(mask=[1, 1, rows, rows], cos=[rows, 128], sin=[rows, 128])
    return result


def _descriptor(stored, logical=None, *, dtype='bfloat16', encoding='float32_le',
                mapping='IDENTITY_C_ORDER', origin='REFERENCE_EXPORT', pin=_HASH):
    logical = stored if logical is None else logical
    width = 2 if encoding in ('bfloat16_le', 'uint16_le') else 1 if encoding == 'uint8' else 4
    return dict(stored_shape=stored, logical_shape=logical, logical_dtype=dtype,
                storage_encoding=encoding, bytes=math.prod(stored) * width,
                file_sha256=pin, content_sha256=pin, canonical_mapping=mapping,
                verification='DIRECT_FILE_REHASH', origin=origin)


def _tensor(rows, name, mode='bf16', raw_cache=False):
    logical = _shapes(rows)[name]
    stored = [1, rows, 2, 128] if raw_cache else [1, rows, 1536 if name == 'q' else 256] if name in ('q', 'k') else logical
    return _descriptor(stored, logical,
                       dtype='float32' if mode == 'fp32' or name == 'softmax_fp32' else 'bfloat16',
                       mapping='TOKEN_HEAD_BYTE_PERMUTATION' if name in ('q', 'k') or raw_cache else 'IDENTITY_C_ORDER')


def _capture_shape(rows, name):
    return ([12, rows, rows, 16] if name == 'dot_parts' else [12, rows, 3] if name == 'normalizer'
            else [12, rows, 128] if name in ('pv_raw', 'pv_bf16') else [12, rows, rows])


def _coverage_hash(rows, name, kind):
    """Hash the prescribed mask/count pattern, never absent numerical bytes."""
    width = 1 if kind == 'presence' else 2
    one = b'\x01' if width == 1 else b'\x01\x00'
    zero = bytes(width)
    result = hashlib.sha256()
    if name in CAUSAL_FIELDS:
        lanes = 16 if name == 'dot_parts' else 1
        for _ in range(12):
            for query in range(rows):
                result.update(one * ((query + 1) * lanes))
                result.update(zero * ((rows - query - 1) * lanes))
    else:
        result.update(one * math.prod(_capture_shape(rows, name)))
    return result.hexdigest()


def _derived(shape, recipe, source_ids):
    return dict(logical_shape=shape, logical_dtype='bfloat16', storage_encoding='float32_le',
                bytes=math.prod(shape) * 4, file_sha256=None, content_sha256=_HASH,
                verification='DERIVED_BYTE_MAPPING', reconstruction=dict(recipe=recipe, source_tensors=source_ids))


def _run_schema(rows):
    payload = {}
    for name, pin in PAYLOAD_PINS.items():
        payload[name] = _descriptor(pin['shape'], encoding='bfloat16_le',
                                    origin='SELECTED_CHECKPOINT_RANGE', pin=pin['sha256'])
        payload[name].update(source_shape=pin['source_shape'], selected_rows=[0, 256] if name == PAYLOAD_NAMES[0] else None)
    readonly = {}
    for name, shape, dtype, mapping, pin in (
        ('arena', [188043264 // 4], 'float32', 'SOURCE_BOUND_ARENA_V1', INPUT_PINS[rows][1]),
        ('table', [192 + 5 * 16384], 'float32', 'PREFIX192_THEN_5X256X64', TABLE_SHA),
        ('input_x', [1, rows, 1536], 'bfloat16', 'IDENTITY_C_ORDER', INPUT_PINS[rows][0])):
        readonly[name] = _descriptor(shape, dtype=dtype, mapping=mapping, origin='COLD_READONLY_INPUT', pin=pin)
    native = {}
    for mode in MODES:
        for method in METHODS:
            for name in STAGES:
                item = _tensor(rows, name, mode)
                item['native_storage'] = (dict(verification='QUALIFIED_METADATA_ONLY',
                    dtype='torch.bfloat16' if mode == 'bf16' and name != 'softmax_fp32' else 'torch.float32',
                    content_sha256=_HASH, logical_shape=_shapes(rows)[name]) if method == METHODS[0] else
                    dict(verification='NOT_EMITTED_BY_PRODUCER', dtype=None, content_sha256=None))
                item['acceptance_scope'] = 'BF16_REFERENCE' if mode == 'bf16' else 'FP32_DIAGNOSTIC_ONLY'
                native[f'{mode}.{method}.{name}'] = item
    raw_names = (*WIDTHS, 'cache_k', 'cache_v', 'scores', 'logits', 'softmax_fp32', 'prob', 'silu')
    scalar_raw = {role: {name: _tensor(rows, name, raw_cache=name in ('cache_k', 'cache_v')) for name in raw_names}
                  for role in ('sequential', 'reduced')}
    sequential = {name: _tensor(rows, name) for name in STAGES}
    actual = {}
    for name, width in ACTUAL_WIDTHS.items():
        stored = [2, rows, 2, 128] if name == 'kv' else [1, rows, width]
        logical = _shapes(rows).get(name, stored)
        actual[name] = _descriptor(stored, logical, dtype='float32' if name in ('qraw', 'kraw', 'vraw') else 'bfloat16',
            origin='ACTUAL_FFN_TILE_READ_AUDIT' if name in ('gate', 'up') else 'OBSERVED_SILU_SEAL' if name == 'silu' else 'ACKED_PHYSICAL_OUTPUT',
            mapping='TOKEN_HEAD_BYTE_PERMUTATION' if name in ('q', 'k') else 'K_PLANE_THEN_V_PLANE' if name == 'kv' else 'IDENTITY_C_ORDER')
    captures = {}
    for name in FIELDS:
        shape = _capture_shape(rows, name)
        causal = name in CAUSAL_FIELDS
        count = math.prod(shape)
        observed = (12 * rows * (rows + 1) // 2 * (16 if name == 'dot_parts' else 1)) if causal else count
        item = {kind: _descriptor(shape, dtype=dtype, encoding=encoding, origin='ACTUAL_ATTENTION_CAPTURE')
                for kind, dtype, encoding in (('raw', 'uint32', 'uint32_le'), ('presence', 'uint8', 'uint8'), ('frequency', 'uint16', 'uint16_le'))}
        for kind in ('presence', 'frequency'):
            pin = _coverage_hash(rows, name, kind)
            item[kind]['file_sha256'] = item[kind]['content_sha256'] = pin
        item.update(present_content_sha256=_HASH, observed_elements=observed, unobserved_elements=count-observed,
            coverage='CAUSAL_KEY_LE_QUERY' if causal else 'COMPLETE', absent_word_hex='a5963cc3' if causal else None,
            semantic_value_dtype='bfloat16' if name in ('dot_bf16', 'scores_bf16', 'prob_bf16', 'pv_bf16') else 'float32',
            raw_hash_scope='FULL_STORAGE_INCLUDING_UNOBSERVED_SENTINELS' if causal else 'COMPLETE_OBSERVED_STORAGE',
            present_hash_scope='OBSERVED_LOGICAL_VALUES_ONLY', present_mapping='PRESENCE1_WORDS_IN_C_ORDER',
            future_positions_observed=False if causal else None)
        captures[name] = item
    stages = {name: actual[name] for name in (*WIDTHS, 'silu')}
    for name in ('cache_k', 'cache_v'):
        stages[name] = _derived([1, 2, rows, 128], 'KV_PLANE_TOKEN_TO_HEAD', ['full.persisted_actual:kv'])
        repeat = 'repeat_k' if name == 'cache_k' else 'repeat_v'
        stages[repeat] = _derived([1, 12, rows, 128], 'REPEAT_EACH_KV_HEAD6', ['full.actual_stages:' + name])
    stages['x'] = _derived([1, rows, 1536], 'LOADED_INPUT_X', ['readonly:input_x'])
    for name in ('cos', 'sin'):
        stages[name] = _derived([rows, 128], 'TABLE_BF16_SLICE_DUPLICATE_HALF', ['readonly:table'])
        stages[name]['origin'] = 'REFERENCE_TABLE_DATA_NOT_ENGINE_OUTPUT'
    for name, field in dict(scores='scores_bf16', logits='scores_bf16', softmax_fp32='softmax_fp32', prob='prob_bf16', pv='pv_bf16').items():
        cap = captures[field]
        stages[name] = dict(logical_shape=_shapes(rows)[name], logical_dtype='float32' if name == 'softmax_fp32' else 'bfloat16',
            storage_encoding='uint32_le_fp32_bits', file_sha256=_HASH, content_sha256=_HASH, present_content_sha256=_HASH,
            verification='DIRECT_FILE_REHASH', origin='ACTUAL_ATTENTION_CAPTURE', content_hash_scope=cap['raw_hash_scope'],
            present_hash_scope='OBSERVED_LOGICAL_VALUES_ONLY', coverage=cap['coverage'], observed_elements=cap['observed_elements'],
            unobserved_elements=cap['unobserved_elements'], capture_field=field)
    providers = {}
    for name in (*PROVIDERS, 'x', 'rope'):
        if name == 'x':
            shape, dtype, source, recipe = [1, rows, 1536], 'float32', 'embed_tokens.rows_0_255', 'EMBEDDING_ROWS_BF16_EXPAND_F32'
        elif name == 'rope':
            shape, dtype, source, recipe = [2, 1024, 64], 'float32', 'table', 'COS_SIN_FP32_FIRST_M_ZERO_PAD1024'
        else:
            shape, dtype, source, recipe = PROVIDERS[name]
        direct = name == 'x'
        source_hash = TABLE_SHA if name == 'rope' else PAYLOAD_PINS[source]['sha256']
        providers[name] = dict(logical_shape=shape, logical_dtype='bfloat16' if direct else dtype,
            storage_encoding='bfloat16_le' if dtype == 'bfloat16' else 'float32_le',
            bytes=math.prod(shape) * (2 if dtype == 'bfloat16' else 4), content_sha256=INPUT_PINS[rows][0] if direct else _HASH,
            file_sha256=INPUT_PINS[rows][0] if direct else None, verification='DIRECT_FILE_REHASH' if direct else 'QUALIFIED_METADATA_ONLY',
            qualified_origin='SNAPSHOT_LOADED_INPUTS', qualified_snapshot_rows=rows,
            reconstruction=dict(recipe=recipe, source_tensor='readonly:table' if name == 'rope' else 'payload:' + source,
                                source_content_sha256=source_hash, rows=rows if name in ('x', 'rope') else None))
    gates = {}
    for method in METHODS:
        gates[method] = {}
        for name in OBSERVED_STAGES:
            diagnostic = name == 'softmax_fp32'
            gates[method][name] = dict(actual_tensor='full.actual_stages:' + name,
                reference_tensor='native:bf16.' + method + '.' + name,
                actual_comparison_sha256=_HASH, reference_comparison_sha256=_HASH,
                comparison_mapping='CAUSAL_PRESENT_ONLY' if name in ('scores', 'logits', 'prob', 'softmax_fp32') else 'LOGICAL_C_ORDER',
                policy='DIAGNOSTIC_NO_FP32_TOLERANCE' if diagnostic else 'BF16_BLOCK' if name == 'y' else 'BF16_OPERATOR',
                qualified_verdict=None if diagnostic else True if method == METHODS[0] else _BOOL,
                assigned=method == METHODS[0] and not diagnostic)
    fixed = {}
    for name in WIDTHS:
        fixed[name] = dict(actual_tensor='full.persisted_actual:' + name, reference_tensor='scalar_raw.reduced:' + name,
            comparison_mapping='STORED_C_ORDER', actual_comparison_sha256=_HASH, reference_comparison_sha256=_HASH, qualified_bit_exact=True)
    for name in ('scores', 'logits', 'softmax_fp32', 'prob', 'pv', 'silu'):
        fixed[name] = dict(actual_tensor='full.actual_stages:' + name, reference_tensor='scalar_raw.reduced:' + ('att' if name == 'pv' else name),
            comparison_mapping='TOKEN_HEAD_BYTE_PERMUTATION' if name == 'pv' else 'LOGICAL_C_ORDER' if name == 'silu' else 'CAUSAL_PRESENT_ONLY',
            actual_comparison_sha256=_HASH, reference_comparison_sha256=_HASH, qualified_bit_exact=True)
    return dict(payload=payload, readonly=readonly, native=native, scalar_raw=scalar_raw, sequential_exports=sequential,
                full=dict(persisted_actual=actual, attention_captures=captures, actual_stages=stages,
                          loaded_providers=providers, gate_bindings=gates, fixed_arithmetic_bindings=fixed))


# Source closure from official_bf16/dense_silu.py SOURCE_CLOSURE.
# Audited SHA256 dfd44e15f274090ba7d1eca4fa6c59248e11029dad3c5fcfc0b45693c6267699. The caller's
# authenticated compile map binds those inputs without executing that builder.
# matrix_numeric.cpp is generated; its compile hash can differ from checkout.
COMBINED_SOURCE_PATHS = tuple(BASE + path for path in (
    'ffn_attention/matrix_numeric.cpp', 'official_bf16/silu_recipe.cpp',
    'transposed_down/numeric_smoke.cpp', 'ffn_tiles/silu_recipe.cpp'))


def _compile_map(compile_sources, source_inputs):
    """Check the public map shape; authentication is the caller's obligation."""
    _need(type(compile_sources) is dict and set(compile_sources) == set(COMBINED_SOURCE_PATHS), 'COMPILE_SOURCE_SET')
    for path, digest in compile_sources.items():
        _need(_digest(digest), 'COMPILE_SOURCE_DIGEST')
        if path != COMBINED_SOURCE_PATHS[0]:
            _need(digest == source_inputs.get(path), 'COMPILE_RAW_SOURCE_BINDING')
    return compile_sources


def _manifest_schema(source_inputs, *, compile_sources):
    _compile_map(compile_sources, source_inputs)
    identity = dict(
        model=dict(model_id=MODEL, revision=REVISION, layer=0, selected_embedding_rows=[0, 256],
                   whole_checkpoint_hash_verified=False, config_sha256=CONFIG_SHA, payload_ledger_sha256=LEDGER_SHA),
        serialization=dict(schema=1, hash='SHA256', byte_order='LITTLE_ENDIAN', canonical_tensor_order='LOGICAL_C_ORDER',
                           numeric_conversion_performed=False, logical_id_scope='PER_ROWS_RUN', logical_id_separator='COLON'),
        stimulus=dict(batch=1, past_tokens=0, carried=False, rows=[16, 128], token_ids='RANGE_ZERO_TO_ROWS_EXCLUSIVE',
            position_ids='RANGE_ZERO_TO_ROWS_EXCLUSIVE', tokenizer_or_template=False, intermediate_preloads=0,
            input_source='SELECTED_CHECKPOINT_EMBEDDINGS', stimulus_random_draw=False, stimulus_seed=None,
            framework_construction_rng_claim=False, eval=True, dropout=False),
        recipe_sources={name: source_inputs[path] for name, path in RECIPE_SOURCES.items()},
        policy=dict(numerical_contract_sha256=POLICY_SHA, operator=dict(max_abs=0.03125, mean_abs=0.005),
            block=dict(max_abs=0.05, mean_abs=0.01), assigned_official_gates=27, observed_stages=28,
            diagnostic_stages=['softmax_fp32'], missing_stages=['explicit_mask_tensor'],
            partially_observed_stages=['scores', 'logits', 'prob', 'softmax_fp32'],
            fixed_arithmetic_reference='REDUCED_BLOCK_PAIR_SCALAR', official_reference='OFFICIAL_SELF_CACHE',
            auxiliary_references=['INDEPENDENT_SELF_CACHE', 'SEQUENTIAL_SCALAR'], new_tolerances=False),
        runs={str(rows): _run_schema(rows) for rows in (16, 128)})
    runtime = dict(packages=dict(python='3.12.15', torch='2.10.0+cpu', numpy='2.3.5', transformers='4.40.1'),
        compiler=dict(family='GNU_GXX', version_components=[_VERSION, _VERSION, _VERSION],
                      version_text_sha256=_HASH, executable_sha256=_HASH, verification='QUALIFIED_METADATA_ONLY'),
        torch_commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
        runtime_files=dict(python=_HASH, libc=_HASH, libm=_HASH), runtime_files_verification='QUALIFIED_METADATA_ONLY',
        fenv=dict(status='OBSERVED', x87_round=0, sse_round=0, ftz=False, daz=False), mkldnn_enabled=True,
        threads=4, interop_threads=1, deterministic_algorithms=True, device='cpu', attention='eager',
        settings_basis=dict(threads='QUALIFIED_NATIVE_METADATA', interop_threads='SOURCE_ENFORCED_CONFIGURATION',
                            deterministic_algorithms='SOURCE_ENFORCED_CONFIGURATION'),
        blas_environment=dict(OPENBLAS_NUM_THREADS='4', MKL_NUM_THREADS='4', OMP_NUM_THREADS='4'),
        build_hashes={name: _HASH for name in ('cache_utils_sha256', 'mask_utils_sha256', 'activations_sha256',
                                             'torch_build_sha256', 'numpy_build_sha256')},
        dispatch_metadata_sha256=_HASH, cpu_metadata_sha256=_HASH)
    builds = {str(rows): dict(
        scalar_builds={role: dict(cpp_sha256=_HASH, header_sha256=_HASH, executable_sha256=_HASH, flags=list(SCALAR_FLAGS))
                       for role in ('sequential', 'reduced')},
        recipe_libraries={role: dict(library_sha256=_HASH, cpp_sha256=_HASH, generated_module_sha256=_HASH,
                                    flags=list(RECIPE_FLAGS), compiler_executable_sha256=_HASH) for role in ('qkv', 'qk')})
        for rows in (16, 128)}
    provenance = {name: _HASH for name in (
        'm16_composed_source_map_sha256', 'm128_composed_source_map_sha256', 'qualification_sha256',
        'm16_prerequisite_sha256', 'producer_context_sha256', 'm16_summary_sha256', 'm16_snapshot_sha256',
        'm16_full_receipt_sha256', 'verifier_receipt_sha256', 'm128_summary_sha256', 'm128_snapshot_sha256',
        'm128_full_receipt_sha256', 'm128_child_result_sha256')}
    provenance.update(ci=dict(commit=_COMMIT, run_id=_RUN_ID, run_attempt='1'),
        raw_source_map_sha256=identity_digest(source_inputs),
        producer_manifest_sha256={'16': _HASH, '128': _HASH}, native_result_sha256={'16': _HASH, '128': _HASH},
        runtime=runtime, builds=builds,
        combined_library=dict(content_sha256=_HASH, flags=list(LIBRARY_FLAGS), compiler_executable_sha256=_HASH,
            source_map_sha256=identity_digest(compile_sources),
            shared_m16_m128=True, verification='DIRECT_FILE_REHASH'),
        driver_sha256={rows: source_inputs[BASE + directory + '/driver.py'] for rows, directory in (
            ('16', 'portable_official_producer'), ('128', 'portable_official_producer_m128'))},
        package_scope='FOUR_QUALIFIED_RUNTIME_VERSIONS_PLUS_PINNED_COMPLETE_WHEEL_LOCK',
        wheel_lock_sha256=source_inputs[BASE + 'portable_official_producer_launch/wheel-lock.json'], emitter_sha256=EMITTER_SHA)
    return dict(schema=SCHEMA, status='IDENTITY_METADATA_REQUIRES_PARENT_COMPLETION', identity=identity, identity_sha256=_HASH,
        provenance=provenance, authority=dict(numerical_acceptance_granted=False, freeze_readiness_granted=False,
            full_29_node_acceptance=False, rtl_acceptance=False, hardware_acceptance=False,
            parent_postflight_required=True, parent_publication_and_deadline_check_required=True))


def _equal(left, right, code='CONTENT_BINDING'):
    _need(type(left) is type(right) and left == right, code)


def _resolve(run, logical_id):
    # Expected schema already fixes each reference; retain explicit resolution
    # to make a missing namespace or dangling ID fail independently.
    _need(type(logical_id) is str and logical_id.count(':') == 1, 'LOGICAL_ID')
    namespace, name = logical_id.split(':')
    full = run['full']
    namespaces = {'payload': run['payload'], 'readonly': run['readonly'], 'native': run['native'],
        'scalar_raw.sequential': run['scalar_raw']['sequential'], 'scalar_raw.reduced': run['scalar_raw']['reduced'],
        'sequential_exports': run['sequential_exports'], 'full.persisted_actual': full['persisted_actual'],
        'full.actual_stages': full['actual_stages'], 'full.loaded_providers': full['loaded_providers']}
    _need(namespace in namespaces and name in namespaces[namespace], 'LOGICAL_REFERENCE')
    return namespaces[namespace][name]


def _bind_run(run):
    full = run['full']
    tables = (run['payload'], run['readonly'], run['native'], *run['scalar_raw'].values(),
              run['sequential_exports'], full['persisted_actual'])
    seen = {}
    for table in tables:
        for item in table.values():
            key = (item['file_sha256'], tuple(item['stored_shape']), tuple(item['logical_shape']),
                   item['storage_encoding'], item['canonical_mapping'])
            if key in seen:
                _equal(item['content_sha256'], seen[key], 'CANONICAL_BYTE_IDENTITY')
            seen[key] = item['content_sha256']
            if item['canonical_mapping'] != 'TOKEN_HEAD_BYTE_PERMUTATION':
                _equal(item['file_sha256'], item['content_sha256'])
    for name in (*WIDTHS, 'silu'):
        _equal(full['actual_stages'][name], full['persisted_actual'][name])
    _equal(full['actual_stages']['x']['content_sha256'], run['readonly']['input_x']['content_sha256'])
    for cap in full['attention_captures'].values():
        for part in ('raw', 'presence', 'frequency'):
            _equal(cap[part]['file_sha256'], cap[part]['content_sha256'])
        if cap['coverage'] == 'COMPLETE':
            _equal(cap['present_content_sha256'], cap['raw']['content_sha256'])
    for stage in full['actual_stages'].values():
        if 'capture_field' in stage:
            cap = full['attention_captures'][stage['capture_field']]
            for key in ('file_sha256', 'content_sha256'):
                _equal(stage[key], cap['raw'][key])
            _equal(stage['present_content_sha256'], cap['present_content_sha256'])
    for table in (full['actual_stages'], full['loaded_providers']):
        for item in table.values():
            recipe = item.get('reconstruction', {})
            for logical_id in recipe.get('source_tensors', []):
                _resolve(run, logical_id)
            if 'source_tensor' in recipe:
                _equal(_resolve(run, recipe['source_tensor'])['content_sha256'], recipe['source_content_sha256'])
    for table in (*full['gate_bindings'].values(), full['fixed_arithmetic_bindings']):
        for gate in table.values():
            actual = _resolve(run, gate['actual_tensor'])
            reference = _resolve(run, gate['reference_tensor'])
            mapping = gate['comparison_mapping']
            if mapping == 'STORED_C_ORDER':
                expected_actual, expected_reference = actual['file_sha256'], reference['file_sha256']
            else:
                expected_actual = actual.get('present_content_sha256', actual['content_sha256'])
                expected_reference = reference['content_sha256'] if mapping == 'LOGICAL_C_ORDER' else None
            _equal(gate['actual_comparison_sha256'], expected_actual)
            if expected_reference is not None:
                _equal(gate['reference_comparison_sha256'], expected_reference)
            if 'qualified_bit_exact' in gate:
                # A qualified bit-exact comparison must commit to equal bytes.
                _equal(gate['actual_comparison_sha256'], gate['reference_comparison_sha256'], 'FIXED_HASH_EQUALITY')
    # Public values bind full-storage and present-only views separately. The
    # causal native slices, KV/repeat/transpose recipes and absent raw captures
    # cannot be rehashed without private bytes and remain commitments.


def validate_manifest(value, source_inputs, *, compile_sources):
    """Validate the public body only; return bounded, path-free inventory facts.

    Exact CI/artifact/source-file authentication and receipt equalities belong
    to the caller. In particular, compile_sources must come from the authenticated
    tiny contract and both composed maps, never a guessed raw-source substitution.
    A valid body, including a synthetic body, grants no readiness.
    """
    _source_map(source_inputs)
    for path in COMBINED_SOURCE_PATHS:
        _need(path in source_inputs, 'SOURCE_REQUIRED')
    _json_guard(value)
    _match(value, _manifest_schema(source_inputs, compile_sources=compile_sources))
    _need(len(canonical(value)) <= 2 * 1024 * 1024, 'PUBLIC_SIZE')
    _equal(value['identity_sha256'], identity_digest(value['identity']), 'IDENTITY_SHA256')
    runs = value['identity']['runs']
    _equal(runs['16']['payload'], runs['128']['payload'], 'SHARED_PAYLOAD')
    _equal(runs['16']['readonly']['table'], runs['128']['readonly']['table'], 'SHARED_TABLE')
    for run in runs.values():
        _bind_run(run)
    p = value['provenance']
    compiler = p['runtime']['compiler']['executable_sha256']
    _equal(compiler, p['combined_library']['compiler_executable_sha256'], 'COMPILER_BINDING')
    for build in p['builds'].values():
        for lib in build['recipe_libraries'].values():
            _equal(compiler, lib['compiler_executable_sha256'], 'COMPILER_BINDING')
    return dict(status='PUBLIC_IDENTITY_SCHEMA_AND_BINDINGS_VALID', schema=SCHEMA,
        identity_sha256=value['identity_sha256'], raw_source_count=464,
        runs={rows: dict(payload=13, readonly=3, native_exports=116, scalar_outputs_each=22,
            sequential_exports=29, persisted_actual=20, attention_fields=10, capture_parts_each=3,
            actual_stages=28, loaded_providers=14, gates_each_method=28, assigned_official_gates=27,
            fixed_arithmetic_bindings=21,
            causal_observed_elements=1632 if rows == '16' else 99072,
            causal_future_elements=1440 if rows == '16' else 97536) for rows in ('16', '128')},
        private_tensor_bytes_rehashed=False, numerical_replay_performed=False,
        provenance_authenticated_by_this_function=False, parent_completion_verified_by_this_function=False,
        numerical_acceptance_granted=False, freeze_readiness_granted=False,
        full_29_node_acceptance=False, rtl_acceptance=False, hardware_acceptance=False)
