"""Synthetic source-only tensor traces, including adversarial accepted events.

These fixtures are mathematical test inputs, never substituted into RTL runs.
No captured output, generated hardware, or model payload is checked in.
"""
from collections import Counter
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tensor_trace_verifier', ROOT / 'scripts/verify_matrix_norm_rope_tensor_trace.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


@pytest.fixture(scope='module')
def cases():
    result = {}
    for case in range(40):
        columns = 512 if case % 10 < 8 else 256
        projected = np.asarray([0x3f00 + case + (i % 32) for i in range(columns)], dtype=np.uint32)
        fp32 = projected << 16
        steps = np.repeat(fp32.reshape(-1, 1, 32), 1024, axis=1).reshape(-1, 32)
        activation = np.zeros(1024, dtype=np.uint32)
        activation[0] = 0x3f80
        weight = np.zeros(1024 * columns, dtype=np.uint32)
        weight[:columns] = projected
        gamma = np.zeros(256, dtype=np.uint32)
        normalized = v.head_trace(tuple(int(x) << 16 for x in projected[:256]), (0,) * 256)
        norm = np.asarray([x >> 16 for x in normalized['output_bf16']], dtype=np.uint32)
        trig = np.asarray([0x3f80] * 32 + [0] * 32, dtype=np.uint32)
        result[case] = dict(columns=columns, projected=projected, projected_fp32=fp32,
                            projected_steps=steps.reshape(-1), steps=steps, activation=activation,
                            weight=weight, norm_weight=gamma, norm=norm, rope=norm.copy(),
                            trig=trig, norm_trace=normalized, rope_flags=0)
    return result


def begin(kind='boundary', name='legal_exact_1p5MiB_end', transaction=1):
    case, role, start, count = next((x[1:] for x in v.MAIN if x[0] == name),
                                   (8, 1, 0, 128 if name == 'token_count128_admitted' else 2 if kind == 'reset' else 1))
    return dict(event='begin', transaction=transaction, case=case, kind=kind, name=name,
                role=role, start_token=start, token_count=count, checking=1,
                **v._bases(start, kind == 'boundary'))


def packet(event, **fields):
    return dict(event=event, **fields)


def descriptors(b):
    count = {'bad_command': 0, 'malformed_descriptor': 1, 'unsupported_FP32_output': 5}.get(b['name'], 6)
    for i, data in enumerate(v._descriptors(b['role'], b['name'])[:count], 1):
        yield packet('descriptor_request', index=i)
        yield packet('descriptor', index=i, data=f'{data:032x}', error=0)


def dma(index, kind, source, destination, row_bytes, rows, source_stride, words=None):
    yield packet('dma', index=index, kind=kind, source=f'{source:016x}',
                 destination=f'{destination:016x}', row_bytes=row_bytes, rows=rows,
                 source_stride=source_stride, destination_stride=64)
    if words is not None:
        for beat in range(rows):
            yield packet('dma_data', index=index, source=f'{source + beat * 64:016x}',
                         destination=f'{destination + beat * 64:016x}',
                         data=f'{v._packed(words[beat * 32:(beat + 1) * 32]):0128x}')
    yield packet('dma_ack', index=index, error=0)


def read(region, address, words):
    yield packet('l2_read', region=region, byte_address=address)
    yield packet('l2_response', byte_address=address, error=0, data=f'{v._packed(words):0128x}')


def write(region, address, words):
    yield packet('l2_write', region=region, byte_address=address, mask='f' * 16,
                 data=f'{v._packed(words):0128x}')
    yield packet('l2_ack', byte_address=address, error=0)


def head_body(b, ex, ordinal):
    role, cols = b['role'], ex['columns']
    relative_token, head = divmod(ordinal, 8 if role == 0 else 2)
    token = b['start_token'] + relative_token
    case = v._case_id(role, token, head)
    full = 4096 if role == 0 else 512
    tiles = cols // 32
    first = ordinal * (3 + tiles * 2)
    yield packet('head_begin', case=case, head=head, token=token)
    yield from dma(first, 1, 0x100000000 + token * 2048, b['act_base'], 2, 1024, 2)
    for tile in range(tiles):
        yield from dma(first + tile * 2 + 1, 1, 0x200000000 + head * cols * 2 + tile * 64,
                       b['wgt_base'], 64, 1024, full * 2)
        for k in range(1024):
            yield from read(5, b['act_base'] + k * 64, [ex['activation'][k]] + [0] * 31)
            start = k * cols + tile * 32
            yield from read(6, b['wgt_base'] + k * 64, ex['weight'][start:start + 32])
            i = tile * 1024 + k
            yield packet('matrix', case=case, index=i, context=0, last=int(k == 1023),
                         fp32_row0=f"{v._packed(ex['steps'][i], 4):0256x}")
        words = ex['projected'][tile * 32:(tile + 1) * 32]
        yield from write(0, b['packed_base'] + tile * 64, words)
        yield from dma(first + tile * 2 + 2, 3, b['packed_base'] + tile * 64,
                       0x300000000 + token * full * 2 + head * cols * 2 + tile * 64,
                       64, 1, 64, words)
    for region, base, name in ((0, 'packed_base', 'projected'), (3, 'gamma_base', 'norm_weight')):
        for i in range(len(ex[name]) // 32):
            yield from read(region, b[base] + i * 64, ex[name][i * 32:(i + 1) * 32])
    trace = ex['norm_trace']
    yield packet('norm', status=0, mean_eps=f"{trace['mean_eps']:08x}", inv=f"{trace['inverse']:08x}",
                 flags=trace['aggregate_flags'], norm=f"{v._packed(ex['norm']):01024x}",
                 gate=f"{v._packed(ex['projected'][256:]) if role == 0 else 0:01024x}")
    for i in range(8):
        yield from write(1, b['norm_base'] + i * 64, ex['norm'][i * 32:(i + 1) * 32])
    for region, base, name in ((1, 'norm_base', 'norm'), (4, 'trig_base', 'trig')):
        for i in range(len(ex[name]) // 32):
            offset = relative_token * 128 if region == 4 else 0
            yield from read(region, b[base] + offset + i * 64, ex[name][i * 32:(i + 1) * 32])
    for i in range(8):
        yield from write(2, b['rope_base'] + i * 64, ex['rope'][i * 32:(i + 1) * 32])
    for region, name, base, ddr in ((1, 'norm', 'norm_base', 0x400000000), (2, 'rope', 'rope_base', 0x500000000)):
        if b['kind'] == 'boundary':
            ddr = (1 << 56) - (2048 if region == 1 else 1024)
        yield from dma(first + tiles * 2 + region, 3, b[base],
                       ddr + token * (4096 if role == 0 else 1024) + head * 512,
                       64, 8, 64, ex[name])
    yield packet('head_done', case=case, head=head, token=token)


def transaction(b, cases):
    yield b
    counts = Counter()
    flags = 0
    current_case = None
    head_count = 8 if b['role'] == 0 else 2
    heads = 0 if b['kind'] == 'reject' else b['token_count'] * head_count
    def body():
        yield from descriptors(b)
        for ordinal in range(heads):
            relative_token, head = divmod(ordinal, head_count)
            case = v._case_id(b['role'], b['start_token'] + relative_token, head)
            yield from head_body(b, cases[case], ordinal)
    for raw in body():
        r = dict(raw)
        event = r['event']
        if event == 'head_begin':
            current_case = r['case']
        if event == 'norm':
            flags |= cases[current_case]['norm_trace']['aggregate_flags']
        if event == 'l2_write' and r['region'] == 2:
            flags |= cases[current_case]['rope_flags']
        if event == 'head_done':
            r['flags'] = flags
        if b['kind'] == 'reset' and event == 'dma' and r['index'] == (37 if b['name'] == 'reset_late_head' else 75):
            yield r
            yield packet('reset_flush', stage=0 if b['name'] == 'reset_late_head' else 1)
            return
        failed = b['kind'] == 'fault' and event == 'dma_ack' and r['index'] == v.FAULTS[b['name']][1]
        if failed:
            r['error'] = 1
        counts[event] += 1
        yield r
        if failed:
            break
    status = v.REJECTS[b['name']] if b['kind'] == 'reject' else 6 if b['kind'] == 'fault' else 0
    yield packet('done', status=status)
    yield packet('terminal', status=status, matrix_inputs=counts['matrix'], matrix_outputs=counts['matrix'],
                 dma_count=counts['dma'], write_requests=counts['l2_write'], write_acks=counts['l2_ack'],
                 completed_heads=counts['head_done'], completed_tokens=counts['head_done'] // head_count,
                 total_tiles=head_count * (16 if b['role'] == 0 else 8) if counts['dma'] else 0, flags=flags)


def complete_records(records):
    cycle, owner = 0, None
    for raw in records:
        r = dict(raw)
        if r['event'] == 'begin':
            owner = r['transaction']
        else:
            r['transaction'] = owner
            if 'cycle' in v.SCHEMA[r['event']]:
                cycle += 1
                r['cycle'] = cycle
        yield r


def consume(records, cases, *, validate_json=False):
    active = None
    for raw in records:
        r = v._record(json.dumps(raw) + '\n') if validate_json else raw
        if r['event'] == 'begin':
            active = v._Transaction(r, cases)
        else:
            active.consume(r)
    return active


def mutate(records, event, field, value, occurrence=0):
    output = list(records)
    indices = [i for i, r in enumerate(output) if r['event'] == event]
    i = indices[occurrence]
    output[i] = {**output[i], field: value}
    return output


@pytest.fixture(scope='module')
def boundary(cases):
    return list(complete_records(transaction(begin(), cases)))


def test_complete_two_head_actual_packet_coverage(boundary, cases):
    result = consume(boundary, cases, validate_json=True)
    assert result.completed_heads == 2
    assert result.counts['matrix'] == 16384
    assert result.counts['dma'] == 38
    assert result.counts['dma_data'] == 48
    assert result.counts['l2_write'] == result.counts['l2_ack'] == 48


@pytest.mark.parametrize('name,case,role,start,count', v.MAIN)
def test_all_heads_and_tokens_complete_in_each_main_command(cases, name, case, role, start, count):
    records = complete_records(transaction(begin('main', name), cases))
    result = consume(records, cases)
    assert result.completed_heads == (16 if role == 0 else 4)
    assert result.counts['matrix'] == (262144 if role == 0 else 32768)
    assert result.counts['dma_data'] == (512 if role == 0 else 96)


@pytest.mark.parametrize('event,field,value,occurrence', [
    ('begin', 'checking', 0, 0), ('begin', 'packed_base', 0, 0),
    ('begin', 'token_count', 2, 0), ('begin', 'role', 0, 0),
    ('head_begin', 'case', 9, 0), ('head_begin', 'head', 1, 0),
    ('head_begin', 'token', 1, 0), ('head_begin', 'case', 8, 1),
    ('head_done', 'flags', 0, 0), ('terminal', 'flags', 0, 0),
    ('head_done', 'case', 9, 0), ('head_done', 'token', 1, 0),
    ('descriptor', 'data', '0' * 32, 0), ('descriptor', 'error', 1, 0),
    ('dma', 'index', 1, 0), ('dma', 'source', '0000000100000040', 0),
    ('dma', 'destination', '0000000000020000', 0), ('dma', 'kind', 3, 0),
    ('dma', 'row_bytes', 64, 0), ('dma', 'rows', 1023, 0),
    ('dma', 'source_stride', 8192, 1), ('dma_ack', 'index', 1, 0),
    ('dma_ack', 'error', 1, 0), ('l2_response', 'data', '0' * 128, 1),
    ('matrix', 'case', 9, 0), ('matrix', 'index', 1, 0), ('matrix', 'context', 1, 0),
    ('matrix', 'last', 1, 0), ('matrix', 'fp32_row0', '0' * 256, 0),
    ('l2_write', 'data', '0' * 128, 0), ('l2_write', 'mask', '0' * 16, 0),
    ('l2_ack', 'byte_address', 0, 0), ('l2_ack', 'error', 1, 0),
    ('norm', 'mean_eps', '00000000', 0), ('norm', 'inv', '00000000', 0),
    ('norm', 'norm', '0' * 1024, 0), ('norm', 'gate', '1' + '0' * 1023, 0),
    ('dma_data', 'index', 3, 0), ('dma_data', 'data', '0' * 128, 0),
    ('dma_data', 'source', '0000000000040000', 0),
    ('dma_data', 'destination', '0000000300000200', 0),
    ('dma_data', 'data', '0' * 128, 8), ('dma_data', 'data', '0' * 128, 16),
    ('dma_data', 'source', '000000000017fa00', 9),
    ('dma', 'destination', '0000000400000000', 36),
    ('done', 'status', 8, 0), ('terminal', 'status', 8, 0),
    ('terminal', 'matrix_inputs', 0, 0), ('terminal', 'dma_count', 0, 0),
    ('terminal', 'write_acks', 0, 0), ('terminal', 'completed_heads', 1, 0),
    ('terminal', 'completed_tokens', 0, 0), ('terminal', 'total_tiles', 32, 0),
])
def test_geometry_arithmetic_identity_and_fabric_mutations_fail_closed(boundary, cases, event, field, value, occurrence):
    with pytest.raises(ValueError):
        consume(mutate(boundary, event, field, value, occurrence), cases)


@pytest.mark.parametrize('event', ['descriptor', 'dma_ack', 'l2_response', 'l2_ack'])
def test_done_or_head_advance_cannot_overtake_pending_owner(boundary, cases, event):
    i = next(i for i, r in enumerate(boundary) if r['event'] == event)
    with pytest.raises(ValueError, match='before response or ACK'):
        consume(boundary[:i] + [packet('done', status=0)], cases)
    with pytest.raises(ValueError, match='before response or ACK'):
        consume(boundary[:i] + [packet('head_done', case=8, head=0, token=0)], cases)


@pytest.mark.parametrize('event', ['head_begin', 'head_done', 'dma_data', 'dma_ack', 'l2_ack', 'matrix', 'norm', 'done'])
def test_duplicate_and_missing_events_fail(boundary, cases, event):
    i = next(i for i, r in enumerate(boundary) if r['event'] == event)
    with pytest.raises(ValueError):
        consume(boundary[:i + 1] + [boundary[i]] + boundary[i + 1:], cases)
    with pytest.raises(ValueError):
        consume(boundary[:i] + boundary[i + 1:], cases)


def test_raw_store_data_cannot_be_substituted_by_terminal_counter(boundary, cases):
    records = [r for r in boundary if r['event'] != 'dma_data']
    with pytest.raises(ValueError, match='raw fabric data'):
        consume(records, cases)


@pytest.mark.parametrize('name', list(v.REJECTS))
def test_each_required_rejection_has_exact_status_and_no_head_or_side_effects(cases, name):
    records = list(complete_records(transaction(begin('reject', name), cases)))
    consume(records, cases, validate_json=True)
    with pytest.raises(ValueError, match='terminal status'):
        consume(mutate(records, 'done', 'status', 0), cases)
    with pytest.raises(ValueError, match='side effects'):
        consume(records[:1] + [packet('head_begin', case=8, head=0, token=0)] + records[1:], cases)


def test_final_output_fault_keeps_failed_head_and_token_incomplete(cases):
    records = list(complete_records(transaction(begin('fault', 'final_output_DMA_error'), cases)))
    result = consume(records, cases)
    assert result.completed_heads == 1
    assert result.errors == [('dma_ack', 37)]
    with pytest.raises(ValueError, match='transport error'):
        consume(mutate(records, 'dma_ack', 'error', 0, 37), cases)
    with pytest.raises(ValueError, match='head/token counters'):
        consume(mutate(records, 'terminal', 'completed_tokens', 1), cases)


@pytest.mark.parametrize('name,completed', [('reset_late_head', 1), ('reset_late_token', 3)])
def test_reset_hits_final_output_pending_on_required_later_head(cases, name, completed):
    records = list(complete_records(transaction(begin('reset', name), cases)))
    result = consume(records, cases)
    assert result.completed_heads == completed
    assert result.pending['dma']['index'] == (completed + 1) * 19 - 1
    with pytest.raises(ValueError, match='was not reached'):
        consume(records[:1] + [records[-1]], cases)
    with pytest.raises(ValueError, match='was not reached'):
        consume(mutate(records, 'reset_flush', 'stage', 9), cases)


@pytest.mark.parametrize('field,value', [('transaction', True), ('cycle', 1.0), ('index', '0'), ('error', 2), ('extra', 0)])
def test_json_types_fields_and_error_bits_fail_closed(field, value):
    r = packet('dma_ack', transaction=1, cycle=1, index=0, error=0)
    with pytest.raises(ValueError):
        v._record(json.dumps({**r, field: value}) + '\n')


@pytest.mark.parametrize('line', [
    '{"event":"done","event":"done","transaction":1,"cycle":1,"status":0}\n',
    '{"event":"done","transaction":1,"cycle":NaN,"status":0}\n',
    '{"event":"fabric_readback","transaction":1}\n',
    '{"event":"done","transaction":1,"cycle":1,"status":0}', '[]\n', '{}\n', '\n'])
def test_unknown_duplicate_truncated_and_malformed_json_fail(line):
    with pytest.raises(ValueError):
        v._record(line)


def test_public_verifier_exact_inventory_and_cross_owner_time_checks(tmp_path, monkeypatch, cases, boundary):
    monkeypatch.setattr(v, 'load_case', lambda root, case: cases[case])
    path = tmp_path / 'trace.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in boundary))
    result = v.verify_trace(path, tmp_path, suite='boundary')
    assert result['raw_fabric_ddr_store_data_checked']
    assert result['actual_done_before_ack_checked']
    assert result['events']['head_done'] == 2
    assert result['fabric_guard_readback_in_trace'] is False
    for records in (mutate(boundary, 'begin', 'kind', 'main'),
                    mutate(boundary, 'begin', 'transaction', 2),
                    mutate(boundary, 'dma_ack', 'transaction', 9),
                    mutate(boundary, 'dma_ack', 'cycle', 0), boundary[:-1], []):
        path.write_text(''.join(json.dumps(r) + '\n' for r in records))
        with pytest.raises(ValueError):
            v.verify_trace(path, tmp_path, suite='boundary')
    with pytest.raises(ValueError, match='required_main'):
        v.verify_trace(path, tmp_path, suite='main', required_main=0)
    assert len(v._suite_sequence('all')) == 41
    assert len(v._suite_sequence('negative')) == 30
    assert len(v._suite_sequence('fault')) == 3
    assert len(v._suite_sequence('reset')) == 3


def test_public_negative_suite_does_not_need_unconsumed_arithmetic_vectors(tmp_path):
    path = tmp_path / 'negative.jsonl'
    records = (r for owner, (kind, name, case) in enumerate(v._suite_sequence('negative'), 1)
               for r in transaction(begin(kind, name, owner), {}))
    path.write_text(''.join(json.dumps(r) + '\n' for r in complete_records(records)))
    result = v.verify_trace(path, tmp_path, suite='negative')
    assert result['transactions'] == 30
    assert result['bitexact_matrix_steps'] == 0
    with pytest.raises(ValueError):
        v.verify_trace(path, tmp_path, suite='all')


def test_vector_loader_exact_extent_and_independent_arithmetic_links(tmp_path, cases):
    ex = cases[39]
    folder = tmp_path / 'case39'
    folder.mkdir()
    for name in ('projected_steps', 'projected_fp32', 'projected', 'norm', 'rope',
                 'activation', 'weight', 'norm_weight', 'trig'):
        width = 8 if name in ('projected_steps', 'projected_fp32') else 4
        (folder / (name + '.memh')).write_text(''.join(f'{int(x):0{width}x}\n' for x in ex[name]))
    assert v.load_case(tmp_path, 39)['columns'] == 256
    for name in ('projected_steps', 'projected_fp32', 'projected', 'norm', 'rope'):
        path = folder / (name + '.memh')
        original = path.read_text()
        width = 8 if name in ('projected_steps', 'projected_fp32') else 4
        for invalid in (original[:-1], original + '0' * width + '\n',
                        '0' * width + '\n' + original.split('\n', 1)[1]):
            # A non-final sequential step is checked against the actual trace,
            # while its final step has the vector arithmetic link.
            if name == 'projected_steps' and invalid.endswith(original.split('\n', 1)[1]):
                continue
            path.write_text(invalid)
            with pytest.raises(ValueError):
                v.load_case(tmp_path, 39)
        path.write_text(original)
    for case in (-1, 40, True):
        with pytest.raises(ValueError):
            v.load_case(tmp_path, case)


def test_earlier_head_flags_remain_when_later_head_is_exact(cases):
    import copy
    modified = copy.deepcopy(cases)
    modified[8]['norm_trace']['aggregate_flags'] = 1
    modified[9]['norm_trace']['aggregate_flags'] = 0
    records = list(complete_records(transaction(begin(), modified)))
    assert consume(records, modified).expected_flags == 1
    with pytest.raises(ValueError, match='cumulative arithmetic flags'):
        consume(mutate(records, 'head_done', 'flags', 0, 1), modified)
    with pytest.raises(ValueError, match='cumulative arithmetic flags'):
        consume(mutate(records, 'terminal', 'flags', 0), modified)
