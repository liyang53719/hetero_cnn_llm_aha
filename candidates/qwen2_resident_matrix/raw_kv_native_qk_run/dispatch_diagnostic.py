"""Strict, bounded metadata projections; no numerical acceptance or raw log export.

Reviewed format: oneDNN v3.7+ v1 primitive execution CSV, documented at
https://uxlfoundation.github.io/oneDNN/v3.7/dev_guide_verbose.html
PyTorch 2.10 scoped capture: https://docs.pytorch.org/docs/2.10/backends.html
Only explicitly enumerated implementation/layout names are recognized. A later
oneDNN spelling requires review rather than being silently labelled equivalent.
"""
import math
import re

MAX_LOG_BYTES = 2 * 1024 * 1024
CPU_MAX_BYTES = MAX_LOG_BYTES
MAX_LINE_BYTES = 4096
MAX_LINES = 8192
MAX_RECORDS = 4096
MAX_GROUPS = 24
REQUIRED_FLAGS = ('avx512f', 'avx512vl', 'avx512bw', 'avx512dq', 'fma')
OPTIONAL_FLAGS = ('avx512_bf16', 'avx512_vnni', 'amx_bf16', 'amx_tile', 'amx_int8', 'avx2')
FLAGS = REQUIRED_FLAGS + OPTIONAL_FLAGS
STAGES = ('x', 'n0', 'qr', 'kr', 'v', 'q', 'k', 'cache_k', 'cache_v',
          'repeat_k', 'repeat_v', 'scores', 'logits', 'prob', 'pv', 'att',
          'o', 'r', 'n1', 'gate', 'up', 'silu', 'act', 'down', 'y', 'cos',
          'sin', 'mask', 'softmax_fp32')
PAYLOAD_SHAPES = {
    'embed_tokens.rows_0_255': [256, 1536], 'input_layernorm.weight': [1536],
    'mlp.down_proj.weight': [1536, 8960], 'mlp.gate_proj.weight': [8960, 1536],
    'mlp.up_proj.weight': [8960, 1536], 'post_attention_layernorm.weight': [1536],
    'self_attn.k_proj.bias': [256], 'self_attn.k_proj.weight': [256, 1536],
    'self_attn.o_proj.weight': [1536, 1536], 'self_attn.q_proj.bias': [1536],
    'self_attn.q_proj.weight': [1536, 1536], 'self_attn.v_proj.bias': [256],
    'self_attn.v_proj.weight': [256, 1536],
}
IMPL_ISA = {
    **{f'brg_matmul:{isa}': isa for isa in (
        'avx2', 'avx512_core', 'avx512_core_bf16', 'avx512_core_amx',
        'avx512_core_amx_fp16', 'avx10_1_512', 'avx10_1_512_amx')},
    **{f'brg:{isa}': isa for isa in ('avx2', 'avx512_core',
        'avx512_core_bf16', 'avx512_core_amx', 'avx10_1_512_amx')},
    **{name: 'unspecified' for name in ('gemm:jit:bf16', 'gemm:jit',
        'gemm:blas', 'gemm:ref', 'jit:uni', 'jit_direct_copy:uni', 'ref:any')},
    'jit:avx512_core': 'avx512_core', 'jit:avx512_core_bf16': 'avx512_core_bf16',
    'jit:avx2': 'avx2',
}
LAYOUTS = ('a', 'ab', 'ba', 'abc', 'acb', 'abcd', 'abdc', 'abcde', 'abcdef',
           'AB16a16b', 'BA16a16b', 'BA16a32b2a', 'BA16a48b2a', 'BA16a64b2a',
           'BA16a64b', 'AB16a32b', 'AB16a64b', 'undef', 'any')
DTYPES = ('bf16', 'f32', 'f16', 's8', 'u8', 's32', 'undef')
ROLES = ('QKV_KV', 'DENSE_HIDDEN', 'QK', 'PV', 'ATTENTION_SQUARE', 'MLP', 'OTHER')
ATTRS = ('attr-scratchpad:user', 'attr-fpmath:strict', 'attr-fpmath:bf16',
         'attr-fpmath:bf16:true', 'attr-scales:wei:2:f32', 'attr-post-ops:sum')
PROPS = ('undef', 'forward', 'forward_training', 'forward_inference')
HASH_FIELDS = ('actual_f32_sha256', 'reference_f32_sha256')
UNSUPPORTED_REASONS = ('verbose_version', 'engine', 'primitive', 'implementation',
    'prop_kind', 'memory_descriptor', 'attributes', 'auxiliary',
    'information_header', 'information_record', 'unknown_operation')
UNSUPPORTED_INFO_SUBTYPES = ('version', 'cpu_runtime', 'cpu_isa', 'gpu_runtime',
    'graph_backend', 'other')


def need(ok):
    if not ok:
        raise ValueError('dispatch diagnostic contract')


def _keys(value, keys):
    need(type(value) is dict and all(type(k) is str for k in value) and set(value) == set(keys))


def _int(value, lo, hi):
    need(type(value) is int and lo <= value <= hi)


def _hash(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None)
    return value


def validate_payload_hashes(value):
    _keys(value, PAYLOAD_SHAPES)
    return {name: _hash(value[name]) for name in PAYLOAD_SHAPES}


def payload_hashes(verified_manifest):
    """Project metadata from the already verified load_payload manifest.

    This helper neither accesses nor independently verifies tensor file bytes.
    """
    need(type(verified_manifest) is dict)
    tensors = verified_manifest.get('tensors')
    need(type(tensors) is list and len(tensors) == 13)
    result = {}
    for record in tensors:
        need(type(record) is dict)
        name = record.get('local_name')
        need(type(name) is str and name in PAYLOAD_SHAPES and name not in result)
        shape = record.get('shape')
        need(type(shape) is list and all(type(d) is int for d in shape) and
             shape == PAYLOAD_SHAPES[name] and type(record.get('dtype')) is str and record['dtype'] == 'BF16')
        result[name] = _hash(record.get('sha256'))
    return validate_payload_hashes(result)


def validate_stage_hashes(value):
    _keys(value, ('bf16', 'fp32'))
    result = {}
    for mode in ('bf16', 'fp32'):
        _keys(value[mode], STAGES)
        result[mode] = {}
        for name in STAGES:
            _keys(value[mode][name], HASH_FIELDS)
            result[mode][name] = {key: _hash(value[mode][name][key]) for key in HASH_FIELDS}
    return result


def stage_hashes(original_result, *, tokens):
    _int(tokens, 16, 128)
    need(tokens in (16, 128) and type(original_result) is dict)
    need(type(original_result.get('tokens')) is int and original_result['tokens'] == tokens and
         original_result.get('carried') is False)
    modes = original_result.get('modes')
    _keys(modes, ('bf16', 'fp32'))
    result = {}
    for mode in ('bf16', 'fp32'):
        need(type(modes[mode]) is dict)
        phases = modes[mode].get('phases')
        need(type(phases) is list and len(phases) == 1 and type(phases[0]) is dict)
        phase = phases[0]
        for key in ('phase', 'past_tokens'):
            need(type(phase.get(key)) is int and phase[key] == 0)
        for key in ('token_ids', 'position_ids'):
            ids = phase.get(key)
            need(type(ids) is list and len(ids) == tokens and all(type(i) is int for i in ids) and ids == list(range(tokens)))
        _keys(phase.get('stages'), STAGES)
        result[mode] = {}
        for name in STAGES:
            record = phase['stages'][name]
            need(type(record) is dict)
            result[mode][name] = {key: _hash(record.get(key)) for key in HASH_FIELDS}
    return validate_stage_hashes(result)


def validate_cpu_features(value):
    _keys(value, ('schema', 'diagnostic_only', 'processor_records', 'flags'))
    need(type(value['schema']) is int and value['schema'] == 1 and value['diagnostic_only'] is True)
    _int(value['processor_records'], 1, 4096)
    _keys(value['flags'], FLAGS)
    need(all(type(v) is bool for v in value['flags'].values()))
    return dict(schema=1, diagnostic_only=True, processor_records=value['processor_records'], flags=dict(value['flags']))


def cpu_features(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_LOG_BYTES)
    try:
        text = raw.decode('ascii')
    except UnicodeError:
        raise ValueError('dispatch diagnostic contract') from None
    records = re.split(r'\n\s*\n', text.strip())
    need(1 <= len(records) <= 4096)
    ids, common = set(), None
    for record in records:
        fields = {}
        for line in record.splitlines():
            need(len(line) <= MAX_LINE_BYTES and ':' in line)
            key, value = (part.strip() for part in line.split(':', 1))
            if key in ('processor', 'flags'):
                need(key not in fields)
                fields[key] = value
        need(set(fields) == {'processor', 'flags'} and re.fullmatch('0|[1-9][0-9]{0,5}', fields['processor']) is not None)
        number = int(fields['processor'])
        need(number not in ids)
        ids.add(number)
        words = fields['flags'].split()
        need(0 < len(words) <= 4096 and len(set(words)) == len(words) and
             all(re.fullmatch('[a-z0-9_]{1,64}', w) is not None for w in words))
        flags = set(words)
        common = flags if common is None else common & flags
    return validate_cpu_features(dict(schema=1, diagnostic_only=True,
        processor_records=len(ids), flags={flag: flag in common for flag in FLAGS}))


class _Unsupported(Exception):
    def __init__(self, reason, info_subtype=None):
        self.reason = reason
        self.info_subtype = info_subtype
        super().__init__()


def _known(ok, reason):
    if not ok:
        raise _Unsupported(reason)


def _shape(text):
    need(re.fullmatch(r'[1-9][0-9]*(?:x[1-9][0-9]*){0,5}', text) is not None)
    dims = tuple(int(d) for d in text.split('x'))
    need(all(d <= 1000000 for d in dims))
    return dims


def _role(primitive, problem):
    shapes = problem.split(':')
    need(1 <= len(shapes) <= 3)
    dims = [_shape(part) for part in shapes]
    if primitive != 'matmul' or len(dims) != 2:
        return 'OTHER'
    a, b = dims
    if len(a) == len(b) == 2 and a[0] in (16, 128):
        if a[1] == 1536 and b == (1536, 256): return 'QKV_KV'
        if a[1] == 1536 and b == (1536, 1536): return 'DENSE_HIDDEN'
        if (a[1], b) in ((1536, (1536, 8960)), (8960, (8960, 1536))): return 'MLP'
    if len(a) == len(b) == 3 and a[0] == b[0] == 12:
        if a[1:] == (16, 128) and b[1:] == (128, 16): return 'QK'
        if a[1:] == (16, 16) and b[1:] == (16, 128): return 'PV'
        if a[1:] == b[1:] == (128, 128): return 'ATTENTION_SQUARE'
    return 'OTHER'


def _descriptor(text):
    fields = text.split(':')
    need(len(fields) == 7)
    role, dtype, prop, fmt, layout, strides, flags = fields
    _known(role in ('src', 'wei', 'bia', 'dst') and dtype in DTYPES and
           prop in ('', 'a', 'b', 'ab', 'abc', 'abcd', 'abcde', 'abcdef') and
           fmt in ('blocked', 'undef', 'any'), 'memory_descriptor')
    if dtype == 'undef' and layout == '': layout = 'undef'
    _known(layout in LAYOUTS and flags in ('', 'f0'), 'memory_descriptor')
    need(strides == '' or re.fullmatch(r'[0-9]+(?:x[0-9]+){0,5}', strides) is not None)
    return role, dict(dtype=dtype, layout=layout)


def _execution(parts):
    need(len(parts) == 13)
    _, _, _, _, engine, primitive, impl, prop, memory, attrs, aux, problem, timing = parts
    _known(engine == 'cpu', 'engine')
    _known(primitive in ('matmul', 'inner_product', 'reorder'), 'primitive')
    _known(impl in IMPL_ISA, 'implementation')
    _known(prop in PROPS, 'prop_kind')
    need(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', timing) is not None)
    elapsed = float(timing)
    need(math.isfinite(elapsed) and 0 <= elapsed <= 1000000000)
    _known(all(attr in ATTRS for attr in attrs.split()), 'attributes')
    _known(aux == '', 'auxiliary')
    desc = {}
    for raw in memory.split():
        key, value = _descriptor(raw)
        need(key not in desc)
        desc[key] = value
    required = {'src', 'dst'} if primitive == 'reorder' else {'src', 'wei', 'dst'}
    need(required <= set(desc) <= required | {'bia'})
    return dict(primitive=primitive, implementation=impl, isa=IMPL_ISA[impl],
                role=_role(primitive, problem), descriptors=desc, count=1)


def _info_subtype(body):
    # These labels describe only validated v1 info records, never executions.
    if body[0].startswith('oneDNN '): return 'version'
    if len(body) >= 2:
        if body[0] == 'cpu' and body[1].startswith('runtime:'): return 'cpu_runtime'
        if body[0] == 'cpu' and body[1].startswith('isa:'): return 'cpu_isa'
        if body[0] == 'gpu' and body[1].startswith('runtime:'): return 'gpu_runtime'
        if body[:2] == ['graph', 'backend']: return 'graph_backend'
    return 'other'


def _information(parts):
    # Headers are recognized, discarded, and never used as execution evidence.
    if parts[2:4] == ['primitive', 'info']:
        _known(parts[4:] == ['template:operation', 'engine', 'primitive', 'implementation',
             'prop_kind', 'memory_descriptors', 'attributes', 'auxiliary', 'problem_desc', 'exec_time'],
             'information_header')
        return
    # Exact oneDNN 3.7.1 header observed in the reviewed historical capture.
    if parts[2:4] == ['graph', 'info']:
        _known(parts[4:] == ['template:operation', 'engine', 'partition_id', 'partition_kind',
             'op_names', 'data_formats', 'logical_tensors', 'fpmath_mode', 'implementation',
             'backend', 'exec_time'], 'information_header')
        return
    _known(parts[2] == 'info', 'unknown_operation')
    body = parts[3:]
    need(all(part.strip() and all(' ' <= char <= '~' for char in part) for part in body))
    if len(body) == 1:
        version = re.fullmatch(r'oneDNN v3\.([0-9]{1,2})\.[0-9]+ \(commit [0-9a-f]{7,40}\)', body[0])
        if version and int(version[1]) >= 7: return
    if len(body) == 3 and body[0] == 'cpu' and body[1] in ('runtime:OpenMP', 'runtime:TBB', 'runtime:sequential') and re.fullmatch(r'nthr:[1-9][0-9]{0,3}', body[2]): return
    if body == ['gpu', 'runtime:none']: return
    if body == ['graph', 'backend', '0:dnnl_backend']: return
    # ISA descriptions may themselves contain commas in the documented CSV.
    # Reassemble only for exact membership; never retain the raw description.
    if len(body) >= 2 and body[0] == 'cpu' and ','.join(body[1:]) in (
        'isa:Intel AVX2', 'isa:Intel AVX-512',
        'isa:Intel AVX-512 with Intel DL Boost',
        'isa:Intel AVX-512 with Intel DL Boost and bfloat16 support',
        'isa:Intel AVX-512 with float16, Intel DL Boost and bfloat16 support and Intel AMX with bfloat16 and 8-bit integer support',
        # oneDNN 8d263e693366ef8db40acc569cc7d8edf644556d, cpu_isa_traits.cpp.
        'isa:Intel AVX-512 with float16, Intel DL Boost and bfloat16 support and Intel AMX with bfloat16, float16 and 8-bit integer support',
        'isa:Intel AVX-512 with Intel DL Boost and bfloat16 support and Intel AMX with bfloat16 and 8-bit integer support',
        'isa:Intel AVX10.1 and Intel AMX with bfloat16 and 8-bit integer support'): return
    raise _Unsupported('information_record', _info_subtype(body))


def parse_verbose(raw, *, truncated=False):
    need(type(raw) is bytes and type(truncated) is bool)
    out = dict(schema=1, diagnostic_only=True, backend_order_proven=False,
        numerical_acceptance=False, status='INCOMPLETE', truncated=truncated,
        lines_observed=0, exec_records=0, info_records=0, unsupported_records=0,
        unsupported_reasons={reason: 0 for reason in UNSUPPORTED_REASONS},
        unsupported_info_subtypes={subtype: 0 for subtype in UNSUPPORTED_INFO_SUBTYPES},
        malformed_records=0, records=[])
    if len(raw) > MAX_LOG_BYTES:
        out['truncated'] = True
        return validate_verbose(out)
    lines = raw.splitlines()
    if len(lines) > MAX_LINES:
        out['truncated'] = True
        lines = lines[:MAX_LINES]
    if raw and not raw.endswith(b'\n'):
        out['truncated'] = True
    for line in lines:
        out['lines_observed'] += 1
        if len(line) > MAX_LINE_BYTES:
            out['malformed_records'] += 1
            continue
        try:
            parts = line.decode('ascii').split(',')
            need(len(parts) >= 4 and parts[0] == 'onednn_verbose')
            _known(parts[1] == 'v1', 'verbose_version')
            if parts[2:4] == ['primitive', 'exec']:
                record = _execution(parts)
                if out['exec_records'] >= MAX_RECORDS:
                    out['truncated'] = True
                    break
                records = out['records']
                if records and all(records[-1][k] == record[k] for k in record if k != 'count'):
                    records[-1]['count'] += 1
                elif len(records) < MAX_GROUPS:
                    records.append(record)
                else:
                    out['truncated'] = True
                    break
                out['exec_records'] += 1
            else:
                _information(parts)
                out['info_records'] += 1
        except _Unsupported as error:
            out['unsupported_records'] += 1
            # Count only the first failing check, using fixed labels, never input.
            out['unsupported_reasons'][error.reason] += 1
            if error.reason == 'information_record':
                out['unsupported_info_subtypes'][error.info_subtype] += 1
        except (ValueError, UnicodeError, OverflowError):
            out['malformed_records'] += 1
    if not out['truncated'] and not out['malformed_records'] and out['exec_records']:
        out['status'] = 'UNSUPPORTED' if out['unsupported_records'] else 'COMPLETE_DIAGNOSTIC'
    elif not out['truncated'] and not out['malformed_records']:
        out['status'] = 'UNSUPPORTED' if out['unsupported_records'] else 'NO_ONEDNN_EXECUTION_OBSERVED'
    return validate_verbose(out)


def validate_verbose(value):
    _keys(value, ('schema', 'diagnostic_only', 'backend_order_proven', 'numerical_acceptance',
        'status', 'truncated', 'lines_observed', 'exec_records', 'info_records',
        'unsupported_records', 'unsupported_reasons', 'unsupported_info_subtypes',
        'malformed_records', 'records'))
    need(type(value['schema']) is int and value['schema'] == 1 and value['diagnostic_only'] is True and
         value['backend_order_proven'] is False and value['numerical_acceptance'] is False and type(value['truncated']) is bool)
    for key in ('lines_observed', 'info_records', 'unsupported_records', 'malformed_records'):
        _int(value[key], 0, MAX_LINES)
    _keys(value['unsupported_reasons'], UNSUPPORTED_REASONS)
    for count in value['unsupported_reasons'].values():
        _int(count, 0, MAX_LINES)
    need(sum(value['unsupported_reasons'].values()) == value['unsupported_records'])
    _keys(value['unsupported_info_subtypes'], UNSUPPORTED_INFO_SUBTYPES)
    for count in value['unsupported_info_subtypes'].values():
        _int(count, 0, MAX_LINES)
    need(sum(value['unsupported_info_subtypes'].values()) == value['unsupported_reasons']['information_record'])
    _int(value['exec_records'], 0, MAX_RECORDS)
    need(type(value['records']) is list and len(value['records']) <= MAX_GROUPS)
    records = []
    for record in value['records']:
        _keys(record, ('primitive', 'implementation', 'isa', 'role', 'descriptors', 'count'))
        need(type(record['primitive']) is str and record['primitive'] in ('matmul', 'inner_product', 'reorder'))
        need(type(record['implementation']) is str and record['implementation'] in IMPL_ISA and
             type(record['isa']) is str and record['isa'] == IMPL_ISA[record['implementation']] and
             type(record['role']) is str and record['role'] in ROLES)
        _int(record['count'], 1, MAX_RECORDS)
        desc = record['descriptors']
        need(type(desc) is dict and all(type(k) is str for k in desc))
        required = {'src', 'dst'} if record['primitive'] == 'reorder' else {'src', 'wei', 'dst'}
        need(required <= set(desc) <= required | {'bia'})
        for descriptor in desc.values():
            _keys(descriptor, ('dtype', 'layout'))
            need(type(descriptor['dtype']) is str and descriptor['dtype'] in DTYPES and
                 type(descriptor['layout']) is str and descriptor['layout'] in LAYOUTS)
        records.append({**record, 'descriptors': {key: dict(item) for key, item in desc.items()}})
    need(sum(r['count'] for r in records) == value['exec_records'])
    accounted = sum(value[k] for k in ('exec_records', 'info_records', 'unsupported_records', 'malformed_records'))
    need(accounted <= value['lines_observed'] and (value['truncated'] or accounted == value['lines_observed']))
    expected = 'INCOMPLETE'
    if not value['truncated'] and not value['malformed_records']:
        if value['unsupported_records']: expected = 'UNSUPPORTED'
        elif value['exec_records']: expected = 'COMPLETE_DIAGNOSTIC'
        else: expected = 'NO_ONEDNN_EXECUTION_OBSERVED'
    need(type(value['status']) is str and value['status'] == expected)
    return {**value, 'unsupported_reasons': dict(value['unsupported_reasons']),
        'unsupported_info_subtypes': dict(value['unsupported_info_subtypes']), 'records': records}


def has_only_informational_unknowns(value):
    """Classify a complete capture's unknowns; do not certify execution coverage.

    The report remains UNSUPPORTED. Header mismatches, unknown operations and
    execution-format or field failures never qualify as informational unknowns.
    """
    value = validate_verbose(value)
    return (value['status'] == 'UNSUPPORTED' and
        value['unsupported_records'] == value['unsupported_reasons']['information_record'])
