"""Bind original L3 inputs and captured read-only trig to the Norm/RoPE chain.

Native intermediates are metadata selections only. They are never execution
inputs. A table row is 32 BF16 cos words followed by 32 BF16 sin words, indexed
by absolute position. Uncaptured positions are explicitly zero-filled and must
remain unread. No independent trig-generation or full-block claim is made.
"""
from pathlib import Path
import hashlib
import json

import numpy as np

from .. import input_fixture

ROOT = input_fixture.ROOT
CONTRACT_PATH = 'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json'
CONTRACT_SHA256 = '13b52da81746346f62c6a2f28cc1d6fa565989bd71d834dd4951ee2056355d97'
WEIGHT_SHA256 = {
    'q_norm': '6fbc460e96b527aa6b54ab345195d141716dd4e34094baec92c65344f8bac298',
    'k_norm': '424ead8a89f71d4e83858da7f28335665c4d61a8797b121cfaa26a56d1f5ea6a',
}
NORM_FIELDS = ('squares', 'mean', 'mean_eps', 'inverse', 'scaled', 'gamma', 'weighted', 'output')
NORM_OPS = ('aten.pow.Tensor_Scalar', 'aten.mean.dim', 'aten.add.Tensor',
            'aten.rsqrt.default', 'aten.mul.Tensor', 'aten.add.Tensor',
            'aten.mul.Tensor', 'aten.type_as.default')


def require(ok, detail):
    if not ok:
        raise ValueError('L3 Norm/RoPE fixture: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_contract(root=ROOT):
    raw = (Path(root) / CONTRACT_PATH).read_bytes()
    require(sha(raw) == CONTRACT_SHA256, 'original numerical contract changed')
    return json.loads(raw)


def _tensor_ref(value):
    require(type(value) is dict and set(value) == {'tensor'} and type(value['tensor']) is str,
            'exact tensor reference required')
    return value['tensor']


def _record(manifest, name, shape, dtype):
    require(name in manifest['tensors'], 'missing tensor metadata: ' + name)
    record = manifest['tensors'][name]
    require(type(record['shape']) is list and all(type(n) is int for n in record['shape']) and
            record['shape'] == list(shape) and record['dtype'] == dtype and
            type(record['bytes']) is int and record['bytes'] == int(np.prod(shape)) *
            {'BF16': 2, 'F32': 4, 'I64': 8}[dtype], 'tensor geometry/dtype/bytes: ' + name)
    require(type(record['sha256']) is str and len(record['sha256']) == 64 and
            all(c in '0123456789abcdef' for c in record['sha256']), 'tensor digest: ' + name)
    return record


def _function(case, name, module=None):
    events = [e for e in case['function_observations'] if e['function'] == name and
              (module is None or e['values'].get('module') == module)]
    require(len(events) == 1, 'unique function observation: ' + name + '/' + str(module))
    require(events[0]['observation'] == 'original Python return-frame locals', 'function provenance')
    return events[0]['values']


def select_case_references(manifest, case, contract):
    """Validate identities, producer keys and full layouts without reading arrays."""
    rows = manifest['query_tokens']
    require(type(rows) is int and rows in (16, 128), 'complete M16/M128 only')
    require(manifest['contract_sha256'] == CONTRACT_SHA256 and
            manifest['original_producer_sequence'] == contract['producer_sequence'] and
            (manifest['model_id'], manifest['revision']) == (contract['model_id'], contract['revision']),
            'exact pinned contract and producer sequence required')
    keys = [p['key'] for p in contract['producer_sequence']]
    require(len(keys) == 57 and len(set(keys)) == 57, 'complete unique 57-producer contract')
    storage = {p['key']: p['storage_dtype'] for p in contract['producer_sequence']}
    name = case['name']
    require(name in ('cold' + str(rows), 'carried' + str(rows)), 'case label')
    base = 0 if name.startswith('cold') else 128
    require(case['position_span'] == [base, base + rows] and
            case['past_tokens'] == (0 if base == 0 else rows), 'cache/absolute position identity')
    for key, shape, dtype in ((case['rope_cos'], (1, rows, 64), 'BF16'),
                              (case['rope_sin'], (1, rows, 64), 'BF16'),
                              (case['position_ids'], (1, rows), 'I64'),
                              (case['rope_position_ids'], (3, 1, rows), 'I64')):
        _record(manifest, key, shape, dtype)
    events = case['dispatch_events']
    indices = [e['index'] for e in events]
    require(all(type(i) is int for i in indices) and indices == sorted(set(indices)),
            'duplicate or unordered dispatch indices')
    by_index = {e['index']: e for e in events}
    refs = {}

    def bind(label, event, shape, dtype, key=None):
        tensor = _tensor_ref(event['result'])
        _record(manifest, tensor, shape, dtype)
        if key is not None:
            require(key in storage and storage[key] == {'F32': 'float32', 'BF16': 'bfloat16'}[dtype],
                    'exact producer key/storage contract: ' + str(key))
        refs[label] = dict(tensor=tensor, shape=list(shape), dtype=dtype, producer_key=key)
        return tensor

    def event_at(index, op, args):
        require(index in by_index, 'missing dispatch index ' + str(index))
        event = by_index[index]
        require(event['module'] == 'self_attn' and event['op'] == op and
                event['args'] == args and event['kwargs'] == {}, 'RoPE/layout dispatch metadata ' + str(index))
        return event

    def ref(tensor):
        return {'tensor': tensor}

    for role, heads in (('q', 8), ('k', 2)):
        module = 'self_attn.' + role + '_norm'
        boundary = case['module_boundaries'][module]
        source = _tensor_ref(boundary['input']['args'][0])
        require(boundary['input']['args'] == [ref(source)] and boundary['input']['kwargs'] == {},
                'norm module input metadata')
        _record(manifest, source, (1, rows, heads, 256), 'BF16')
        norm_events = [e for e in events if e['module'] == module]
        require(len(norm_events) == 10 and [e['op'] for e in norm_events] ==
                ['aten.to.dtype', *NORM_OPS[:5], 'aten.to.dtype', *NORM_OPS[5:]],
                'norm event sequence: ' + module)
        converted = _tensor_ref(norm_events[0]['result'])
        converted_weight = _tensor_ref(norm_events[6]['result'])
        _record(manifest, converted, (1, rows, heads, 256), 'F32')
        _record(manifest, converted_weight, (256,), 'F32')
        require(norm_events[0]['args'] == [ref(source), {'torch_type': 'torch.float32'}] and
                norm_events[6]['args'] == [{'parameter': 'layers.3.' + module + '.weight'},
                                           {'torch_type': 'torch.float32'}], 'FP32 input/weight casts')
        selected = [e for e in norm_events if e['op'] != 'aten.to.dtype']
        counts, bound = {}, {}
        for field, event in zip(NORM_FIELDS, selected):
            op = 'cast_bf16' if field == 'output' else event['op']
            occurrence = counts.get(op, 0)
            counts[op] = occurrence + 1
            key = f'{module}|{op}|{occurrence}'
            shape = (256,) if field == 'gamma' else (1, rows, heads, 1 if field in ('mean', 'mean_eps', 'inverse') else 256)
            bound[field] = bind(role + '_norm.' + field, event, shape, 'BF16' if field == 'output' else 'F32', key)
        expected_args = ([ref(converted), 2], [ref(bound['squares']), [-1], True],
                         [ref(bound['mean']), 1e-6], [ref(bound['mean_eps'])],
                         [ref(converted), ref(bound['inverse'])], [ref(converted_weight), 1.0],
                         [ref(bound['scaled']), ref(bound['gamma'])], [ref(bound['weighted']), ref(source)])
        require(all(e['args'] == args and e['kwargs'] == {} for e, args in zip(selected, expected_args)) and
                all(e['kwargs'] == {} for e in norm_events), 'norm producer dataflow')
        require(_tensor_ref(boundary['output']['result']) == bound['output'], 'norm output binding')
        fn = _function(case, 'norm', module)
        core = _function(case, 'norm_core', module)
        require(fn['input'] == ref(source) and fn['result'] == ref(bound['output']) and
                fn['fp32_weighted_output'] == ref(bound['weighted']) and
                core['input'] == ref(converted) and core['result'] == ref(bound['scaled']),
                'norm function identity')
        layout_index = 25 if role == 'q' else 38
        bind(role + '_norm.head_major', event_at(layout_index, 'aten.transpose.int',
             [ref(bound['output']), 1, 2]), (1, heads, rows, 256), 'BF16')

    # Bind the gate to the actual q-projection split, never to a supplied native input.
    packed = _tensor_ref(case['module_boundaries']['self_attn.q_proj']['output']['result'])
    _record(manifest, packed, (1, rows, 4096), 'BF16')
    view = _tensor_ref(event_at(11, 'aten.view.default', [ref(packed), [1, rows, -1, 512]])['result'])
    _record(manifest, view, (1, rows, 8, 512), 'BF16')
    split = event_at(12, 'aten.chunk.default', [ref(view), 2, -1])['result']
    require(type(split) is list and len(split) == 2, 'packed Q/gate split')
    q_input, gate_input = map(_tensor_ref, split)
    require(case['module_boundaries']['self_attn.q_norm']['input']['args'] == [ref(q_input)],
            'Q norm consumes packed Q half')
    _record(manifest, gate_input, (1, rows, 8, 256), 'BF16')
    gate = bind('raw_gate', event_at(13, 'aten.reshape.default', [ref(gate_input), [1, rows, -1]]),
                (1, rows, 2048), 'BF16')
    require(_function(case, 'attention')['gate'] == ref(gate), 'raw gate function binding')
    k_projected = _tensor_ref(case['module_boundaries']['self_attn.k_proj']['output']['result'])
    _record(manifest, k_projected, (1, rows, 512), 'BF16')
    k_view = _tensor_ref(event_at(27, 'aten.view.default', [ref(k_projected), [1, rows, -1, 256]])['result'])
    require(case['module_boundaries']['self_attn.k_norm']['input']['args'] == [ref(k_view)],
            'K norm consumes projected K view')
    rope = _function(case, 'rope')
    for trig, index in (('cos', 42), ('sin', 43)):
        tensor = _tensor_ref(event_at(index, 'aten.unsqueeze.default', [ref(case['rope_' + trig]), 1])['result'])
        _record(manifest, tensor, (1, 1, rows, 64), 'BF16')
        require(rope[trig] == ref(tensor), 'RoPE trig function binding')
    for role, heads, start, mul, add, terminal, slice_index in (
            ('q', 8, 48, 0, 0, 62, 44), ('k', 2, 55, 2, 1, 63, 46)):
        norm = refs[role + '_norm.head_major']['tensor']
        require(rope[role] == ref(norm), 'RoPE normalized head-major input')
        rot = _tensor_ref(event_at(slice_index, 'aten.slice.Tensor', [ref(norm), 3, 0, 64])['result'])
        tail = _tensor_ref(event_at(slice_index + 1, 'aten.slice.Tensor', [ref(norm), 3, 64, 9223372036854775807])['result'])
        _record(manifest, rot, (1, heads, rows, 64), 'BF16')
        _record(manifest, tail, (1, heads, rows, 192), 'BF16')
        require(rope[role + '_rot'] == ref(rot) and rope[role + '_pass'] == ref(tail), 'RoPE partial64 slices')
        cos = bind(role + '_rope.cos_product', event_at(start, 'aten.mul.Tensor', [ref(rot), rope['cos']]),
                   (1, heads, rows, 64), 'BF16', f'self_attn|aten.mul.Tensor|{mul}')
        first = _tensor_ref(event_at(start + 1, 'aten.slice.Tensor', [ref(rot), 3, 0, 32])['result'])
        second = _tensor_ref(event_at(start + 2, 'aten.slice.Tensor', [ref(rot), 3, 32, 9223372036854775807])['result'])
        neg = _tensor_ref(event_at(start + 3, 'aten.neg.default', [ref(second)])['result'])
        rotated_input = _tensor_ref(event_at(start + 4, 'aten.cat.default', [[ref(neg), ref(first)], -1])['result'])
        for tensor, width in ((first, 32), (second, 32), (neg, 32), (rotated_input, 64)):
            _record(manifest, tensor, (1, heads, rows, width), 'BF16')
        sin = bind(role + '_rope.sin_product', event_at(start + 5, 'aten.mul.Tensor', [ref(rotated_input), rope['sin']]),
                   (1, heads, rows, 64), 'BF16', f'self_attn|aten.mul.Tensor|{mul + 1}')
        result = bind(role + '_rope.rotated', event_at(start + 6, 'aten.add.Tensor', [ref(cos), ref(sin)]),
                      (1, heads, rows, 64), 'BF16', f'self_attn|aten.add.Tensor|{add}')
        whole = bind(role + '_rope.output', event_at(terminal, 'aten.cat.default', [[ref(result), ref(tail)], -1]),
                     (1, heads, rows, 256), 'BF16')
        require(rope[role + '_embed'] == ref(whole), 'RoPE function output binding')
    producers = [r['producer_key'] for r in refs.values() if r['producer_key'] is not None]
    require(len(producers) == len(set(producers)) == 22, '22 unique required producer bindings')
    return refs


def select_norm_weights(manifest, payload):
    selected = {}
    for role, digest in WEIGHT_SHA256.items():
        name = 'self_attn.' + role + '.weight'
        matches = [p for p in payload['tensors'] if p['local_name'] == name]
        require(len(matches) == 1, 'unique original norm parameter ' + role)
        record = matches[0]
        require(record['shape'] == [256] and record['dtype'] == 'BF16' and record['bytes'] == 512 and
                record['sha256'] == digest, 'pinned BF16 norm weight ' + role)
        require(all(manifest['parameters']['layers.3.' + name][key] == record[key]
                    for key in ('shape', 'dtype', 'bytes', 'sha256')), 'captured norm weight identity')
        selected[role] = record
    return selected


def build_trig_table(case_rows, rows, *, windows=('cold', 'carried')):
    """Pack captured BF16 constants into one 256-position absolute-index table."""
    names = input_fixture.requested_case_names(rows, windows)
    require(set(case_rows) == set(names), 'exact selected complete trig windows')
    table = np.zeros((256, 64), dtype='<u2')
    loaded = []
    for name in names:
        base = 0 if name.startswith('cold') else 128
        trig = []
        for label in ('cos', 'sin'):
            raw = case_rows[name][label]
            require(type(raw) is bytes and len(raw) == rows * 64 * 2, 'full captured trig bytes')
            words = np.frombuffer(raw, '<u2').reshape(rows, 64)
            require(not np.any((words & 0x7f80) == 0x7f80), 'finite captured trig')
            require(np.array_equal(words[:, :32], words[:, 32:]), 'equal captured trig halves')
            trig.append(words[:, :32])
        table[base:base + rows] = np.concatenate(trig, axis=1)
        loaded.append([base, base + rows])
    unread, cursor = [], 0
    for begin, end in loaded:
        if cursor < begin:
            unread.append([cursor, begin])
        cursor = end
    if cursor < 256:
        unread.append([cursor, 256])
    return table.tobytes(), dict(bytes_per_position=128, trig_tokens=256,
        captured_position_spans=loaded, zero_filled_unread_spans=unread,
        provenance='original captured BF16 cos/sin; duplicate halves checked; absent rows are explicit unread zeros',
        independent_trig_generation=False)


def load_fixture(directory, payload_directory, root=ROOT, *, windows=('cold', 'carried')):
    """Return prefix fixture's four values plus raw norm weights/trig metadata."""
    manifest, prefix_weights, inputs, identity = input_fixture.load_fixture(directory, payload_directory, root, windows=windows)
    contract = load_contract(root)
    payload_directory = Path(payload_directory)
    payload = json.loads((payload_directory / 'manifest.json').read_text())
    weights, weight_files = {}, {}
    for role, record in select_norm_weights(manifest, payload).items():
        path = (payload_directory / record['file']).resolve(strict=True)
        require(path.is_relative_to(payload_directory.resolve()), 'norm weight path outside payload')
        raw = path.read_bytes()
        require(len(raw) == 512 and sha(raw) == record['sha256'], 'original norm weight bytes changed')
        weights[role] = raw
        weight_files[role] = dict(sha256=sha(raw), bytes=len(raw), original_bf16_weight=True, one_plus_precomputed=False)
    cases, captured = {}, {}
    for case in input_fixture.select_windows(manifest, windows):
        name, rows = case['name'], manifest['query_tokens']
        refs = select_case_references(manifest, case, contract)
        base = case['position_span'][0]
        for key, shape in ((case['position_ids'], (1, rows)), (case['rope_position_ids'], (3, 1, rows))):
            raw = input_fixture.read_tensor(directory, manifest, key)
            positions = np.frombuffer(raw, '<i8').reshape(shape)
            require(np.array_equal(positions, np.broadcast_to(np.arange(base, base + rows), shape)),
                    'actual absolute position values')
        captured[name] = {label: input_fixture.read_tensor(directory, manifest, case['rope_' + label])
                          for label in ('cos', 'sin')}
        cases[name] = dict(position_base=base, trig_tokens=256, references=refs,
                           captured_trig_sha256={label: sha(raw) for label, raw in captured[name].items()})
    table, provenance = build_trig_table(captured, manifest['query_tokens'], windows=windows)
    for case in cases.values():
        case['trig'] = table
        case['trig_provenance'] = {**provenance, 'table_sha256': sha(table)}
    identity = {**identity, 'norm_rope': dict(weight_files=weight_files, trig=provenance,
        trig_table_sha256=sha(table), contract_sha256=CONTRACT_SHA256,
        native_capture_integrity_prevalidated=True, native_intermediates_used_as_execution_inputs=False,
        native_intermediates_injected=False, native_trig_tables_used=True,
        independent_trig_generation=False, full_contract_accepted=False)}
    return manifest, prefix_weights, inputs, identity, dict(weights=weights, cases=cases)
