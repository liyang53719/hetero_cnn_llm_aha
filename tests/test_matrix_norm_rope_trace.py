"""Source-only synthetic accepted-event traces and fail-closed mutations.

No model weights, native captures, saved manifests, or generated RTL artifacts
are checked in. Synthetic arrays/traces exist only in pytest temporary files.
"""
from collections import Counter
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('chain_trace_verifier', ROOT / 'scripts/verify_matrix_norm_rope_trace.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


@pytest.fixture(scope='module')
def cases():
    result = {}
    for case in range(4):
        columns = 512 if case % 2 == 0 else 256
        projected = np.asarray([0x3f00 + (i % 32) for i in range(columns)], dtype=np.uint32)
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
                            trig=trig, norm_trace=normalized)
    return result


def begin(case=1, kind='boundary', name='legal_exact_1p5MiB_end', transaction=1):
    return dict(event='begin', transaction=transaction, case=case, kind=kind, name=name,
                checking=1, **v._bases(case, kind == 'boundary'))


def packet(event, **fields):
    return dict(event=event, **fields)


def descriptors(case, name):
    count = {'bad_command': 0, 'malformed_descriptor': 1,
             'unsupported_FP32_output': 5, 'descriptor_fetch_error': 1}.get(name, 6)
    for i, data in enumerate(v._descriptors(case, name)[:count], 1):
        yield packet('descriptor_request', index=i)
        yield packet('descriptor', index=i, data=f'{data:032x}', error=0)


def dma(index, kind, source, destination, row_bytes, rows, source_stride):
    yield packet('dma', index=index, kind=kind, source=f'{source:016x}',
                 destination=f'{destination:016x}', row_bytes=row_bytes, rows=rows,
                 source_stride=source_stride, destination_stride=64)
    yield packet('dma_ack', index=index, error=0)


def read(region, address, words):
    yield packet('l2_read', region=region, byte_address=address)
    yield packet('l2_response', byte_address=address, error=0, data=f'{v._packed(words):0128x}')


def write(region, address, words):
    yield packet('l2_write', region=region, byte_address=address,
                 mask='f' * 16, data=f'{v._packed(words):0128x}')
    yield packet('l2_ack', byte_address=address, error=0)


def success_body(b, ex):
    case, cols = b['case'], ex['columns']
    head, token = (7 if case == 2 else 1 if case == 3 else 0), (127 if case >= 2 else 0)
    full = 4096 if case % 2 == 0 else 512
    yield from descriptors(case, b['name'])
    yield from dma(0, 1, 0x100000000 + token * 2048, b['act_base'], 2, 1024, 2)
    for tile in range(cols // 32):
        yield from dma(tile * 2 + 1, 1, 0x200000000 + head * cols * 2 + tile * 64,
                       b['wgt_base'], 64, 1024, full * 2)
        for k in range(1024):
            yield from read(5, b['act_base'] + k * 64, [ex['activation'][k]] + [0] * 31)
            start = k * cols + tile * 32
            yield from read(6, b['wgt_base'] + k * 64, ex['weight'][start:start + 32])
            i = tile * 1024 + k
            yield packet('matrix', case=case, index=i, context=0, last=int(k == 1023),
                         fp32_row0=f"{v._packed(ex['steps'][i], 4):0256x}")
        yield from write(0, b['packed_base'] + tile * 64, ex['projected'][tile * 32:(tile + 1) * 32])
        yield from dma(tile * 2 + 2, 3, b['packed_base'] + tile * 64,
                       0x300000000 + token * full * 2 + head * cols * 2 + tile * 64, 64, 1, 64)
    for region, base, name in ((0, 'packed_base', 'projected'), (3, 'gamma_base', 'norm_weight')):
        for i in range(len(ex[name]) // 32):
            yield from read(region, b[base] + i * 64, ex[name][i * 32:(i + 1) * 32])
    trace = ex['norm_trace']
    yield packet('norm', status=0, mean_eps=f"{trace['mean_eps']:08x}", inv=f"{trace['inverse']:08x}",
                 flags=trace['aggregate_flags'], norm=f"{v._packed(ex['norm']):01024x}",
                 gate=f"{v._packed(ex['projected'][256:]) if case % 2 == 0 else 0:01024x}")
    for i in range(8):
        yield from write(1, b['norm_base'] + i * 64, ex['norm'][i * 32:(i + 1) * 32])
    for region, base, name in ((1, 'norm_base', 'norm'), (4, 'trig_base', 'trig')):
        for i in range(len(ex[name]) // 32):
            yield from read(region, b[base] + i * 64, ex[name][i * 32:(i + 1) * 32])
    for i in range(8):
        yield from write(2, b['rope_base'] + i * 64, ex['rope'][i * 32:(i + 1) * 32])


def transaction(b, ex):
    yield b
    kind, name = b['kind'], b['name']
    counts, regions = Counter(), Counter()
    region = None
    stage = int(name[-1]) if kind == 'reset' else None
    body = descriptors(b['case'], name) if kind == 'reject' else success_body(b, ex)
    for raw in body:
        r = dict(raw)
        event = r['event']
        if event in ('l2_read', 'l2_write'):
            region = r['region']
        coordinate = r.get('index') if event in ('descriptor', 'dma_ack') else region
        failed = kind == 'fault' and v.FAULTS[name][:2] == (event, coordinate)
        if failed:
            r['error'] = 1
        counts[event] += 1
        if event == 'l2_write':
            regions[region] += 1
        yield r
        if failed:
            break
        reset = kind == 'reset' and (
            (stage == 0 and event == 'descriptor_request') or
            (stage == 1 and event == 'dma') or
            (stage == 2 and event == 'l2_response' and counts[event] == 16) or
            (stage == 3 and event == 'l2_response' and counts[event] == ex['columns'] // 32 * 2048 + ex['columns'] // 32 + 8) or
            (stage == 4 and event == 'l2_write' and region == 1) or
            (stage == 5 and event == 'l2_response' and counts[event] == ex['columns'] // 32 * 2048 + ex['columns'] // 32 + 18) or
            (stage == 6 and event == 'l2_write' and regions[2] == 8))
        if reset:
            yield packet('reset_flush', stage=stage)
            return
    status = v.REJECTS[name] if kind == 'reject' else v.FAULTS[name][2] if kind == 'fault' else 0
    yield packet('done', status=status)
    yield packet('terminal', status=status, matrix_inputs=counts['matrix'], matrix_outputs=counts['matrix'],
                 dma_count=counts['dma'], write_requests=counts['l2_write'], write_acks=counts['l2_ack'])


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


def suite_records(suite, cases):
    for owner, (kind, name, case) in enumerate(v._suite_sequence(suite), 1):
        yield from transaction(begin(case, kind, name, owner), cases[case])


def save_trace(path, records):
    with path.open('w') as f:
        for r in complete_records(records):
            f.write(json.dumps(r, separators=(',', ':')) + '\n')
    return path


@pytest.fixture
def mock_vectors(monkeypatch, cases):
    monkeypatch.setattr(v, 'load_case', lambda root, case: cases[case])
    return cases


@pytest.mark.parametrize('suite,transactions,main', [('main', 4, 4), ('negative', 21, 0), ('all', 45, 4)])
def test_complete_requested_suite_independent_acceptance(tmp_path, mock_vectors, suite, transactions, main):
    path = save_trace(tmp_path / 'trace.jsonl', suite_records(suite, mock_vectors))
    result = v.verify_trace(path, tmp_path, suite=suite)
    assert result['transactions'] == transactions
    assert result['main_cases'] == main
    assert result['actual_done_before_ack_checked']
    assert result['fabric_guard_readback_in_trace'] is False


@pytest.fixture(scope='module')
def boundary(cases):
    return list(complete_records(transaction(begin(), cases[1])))


def consume(records, cases):
    a = None
    for raw in records:
        r = v._record(json.dumps(raw) + '\n')
        if r['event'] == 'begin':
            a = v._Transaction(r, cases[r['case']])
        else:
            a.consume(r)
    return a


def mutate(records, event, field, value, occurrence=0):
    output = list(records)
    indices = [i for i, r in enumerate(output) if r['event'] == event]
    i = indices[occurrence]
    output[i] = {**output[i], field: value}
    return output


@pytest.mark.parametrize('event,field,value,occurrence', [
    ('begin', 'checking', 0, 0), ('begin', 'packed_base', 0, 0),
    ('descriptor_request', 'index', 2, 0), ('descriptor', 'index', 2, 0),
    ('descriptor', 'data', '0' * 32, 0), ('descriptor', 'error', 1, 0),
    ('dma', 'index', 1, 0), ('dma', 'source', '0000000100000040', 0),
    ('dma', 'destination', '0000000000020000', 0), ('dma', 'kind', 3, 0),
    ('dma', 'row_bytes', 64, 0), ('dma', 'rows', 1023, 0),
    ('dma', 'source_stride', 64, 0), ('dma', 'destination_stride', 2, 0),
    ('dma', 'source_stride', 8192, 1), ('dma_ack', 'index', 1, 0),
    ('dma_ack', 'error', 1, 0), ('l2_read', 'byte_address', 65538, 0),
    ('l2_read', 'region', 6, 0), ('l2_response', 'byte_address', 0, 0),
    ('l2_response', 'data', f'{0x13f80:0128x}', 0),
    ('l2_response', 'data', '0' * 128, 1), ('l2_response', 'error', 1, 0),
    ('matrix', 'case', 0, 0), ('matrix', 'index', 1, 0), ('matrix', 'context', 1, 0),
    ('matrix', 'last', 1, 0), ('matrix', 'fp32_row0', '0' * 256, 0),
    ('l2_write', 'data', '0' * 128, 0), ('l2_write', 'mask', '0' * 16, 0),
    ('l2_write', 'byte_address', 1572864, 0), ('l2_write', 'region', 1, 0),
    ('l2_ack', 'byte_address', 0, 0), ('l2_ack', 'error', 1, 0),
    ('norm', 'status', 1, 0), ('norm', 'mean_eps', '00000000', 0),
    ('norm', 'inv', '00000000', 0), ('norm', 'flags', 31, 0),
    ('norm', 'norm', '0' * 1024, 0), ('norm', 'gate', '1' + '0' * 1023, 0),
    ('l2_write', 'data', '0' * 128, 8), ('l2_write', 'data', '0' * 128, 16),
    ('done', 'status', 8, 0), ('terminal', 'status', 8, 0),
    ('terminal', 'matrix_inputs', 0, 0), ('terminal', 'matrix_outputs', 0, 0),
    ('terminal', 'dma_count', 0, 0), ('terminal', 'write_requests', 0, 0),
    ('terminal', 'write_acks', 0, 0),
])
def test_packet_arithmetic_geometry_and_owner_mutations_fail_closed(boundary, cases, event, field, value, occurrence):
    with pytest.raises(ValueError):
        consume(mutate(boundary, event, field, value, occurrence), cases)


@pytest.mark.parametrize('event', ['descriptor', 'dma_ack', 'l2_response', 'l2_ack'])
def test_actual_done_before_each_owner_response_fails(boundary, cases, event):
    i = next(i for i, r in enumerate(boundary) if r['event'] == event)
    records = boundary[:i] + [packet('done', transaction=1, cycle=boundary[i]['cycle'], status=0)]
    with pytest.raises(ValueError, match='before response or ACK'):
        consume(records, cases)


@pytest.mark.parametrize('event', ['descriptor_request', 'descriptor', 'dma', 'dma_ack',
                                  'l2_read', 'l2_response', 'matrix', 'norm', 'l2_write', 'l2_ack', 'done'])
def test_duplicate_accepted_events_fail(boundary, cases, event):
    i = next(i for i, r in enumerate(boundary) if r['event'] == event)
    with pytest.raises(ValueError):
        consume(boundary[:i + 1] + [boundary[i]] + boundary[i + 1:], cases)


def test_missing_last_ack_and_done_are_not_hidden_by_terminal(boundary, cases):
    for event in ('l2_ack', 'done'):
        i = max(i for i, r in enumerate(boundary) if r['event'] == event)
        with pytest.raises(ValueError):
            consume(boundary[:i] + boundary[i + 1:], cases)


@pytest.mark.parametrize('field,value', [('transaction', True), ('cycle', 1.0), ('index', '0'),
                                         ('error', 2), ('extra', 0)])
def test_json_types_and_fields_are_not_coerced(field, value):
    r = packet('dma_ack', transaction=1, cycle=1, index=0, error=0)
    with pytest.raises(ValueError):
        v._record(json.dumps({**r, field: value}) + '\n')


@pytest.mark.parametrize('line', [
    '{"event":"done","event":"done","transaction":1,"cycle":1,"status":0}\n',
    '{"event":"done","transaction":1,"cycle":NaN,"status":0}\n',
    '{"event":"fabric_readback","transaction":1}\n',
    '{"event":"done","transaction":1,"cycle":1,"status":0}',
    '[]\n', '{}\n', '\n',
])
def test_malformed_unknown_duplicate_and_truncated_json_fail(line):
    with pytest.raises(ValueError):
        v._record(line)


def test_all_cannot_be_satisfied_by_main_or_weakened_required_main(tmp_path, mock_vectors):
    path = save_trace(tmp_path / 'main.jsonl', suite_records('main', mock_vectors))
    with pytest.raises(ValueError, match='suite test inventory'):
        v.verify_trace(path, tmp_path, suite='all')
    with pytest.raises(ValueError, match='required_main'):
        v.verify_trace(path, tmp_path, suite='main', required_main=0)
    path.write_text('')
    with pytest.raises(ValueError, match='suite test inventory'):
        v.verify_trace(path, tmp_path, suite='main')


def test_main_relabeling_transaction_owner_and_backwards_time_fail(tmp_path, mock_vectors, boundary):
    for records in (mutate(boundary, 'begin', 'kind', 'main'),
                    mutate(boundary, 'begin', 'transaction', 2),
                    mutate(boundary, 'dma_ack', 'transaction', 9),
                    mutate(boundary, 'dma_ack', 'cycle', 0)):
        path = tmp_path / 'mutant.jsonl'
        # Preserve deliberately malformed owner/time values.
        path.write_text(''.join(json.dumps(r) + '\n' for r in records))
        with pytest.raises(ValueError):
            v.verify_trace(path, tmp_path, suite='boundary')


@pytest.mark.parametrize('name', list(v.REJECTS))
def test_each_negative_status_bound_to_name(cases, name):
    records = list(complete_records(transaction(begin(1, 'reject', name), cases[1])))
    consume(records, cases)
    with pytest.raises(ValueError, match='terminal status'):
        consume(mutate(records, 'done', 'status', 0), cases)


@pytest.mark.parametrize('name', list(v.FAULTS))
def test_each_fault_requires_actual_error_from_target(cases, name):
    records = list(complete_records(transaction(begin(1, 'fault', name), cases[1])))
    consume(records, cases)
    event = v.FAULTS[name][0]
    occurrence = sum(r['event'] == event for r in records) - 1
    with pytest.raises(ValueError, match='transport error'):
        consume(mutate(records, event, 'error', 0, occurrence), cases)


@pytest.mark.parametrize('stage', range(7))
def test_each_reset_requires_reaching_its_actual_stage(cases, stage):
    b = begin(1, 'reset', f'reset_stage{stage}')
    records = list(complete_records(transaction(b, cases[1])))
    consume(records, cases)
    with pytest.raises(ValueError, match='stage was not reached'):
        consume([b, packet('reset_flush', transaction=1, stage=stage)], cases)
    with pytest.raises(ValueError, match='wrong-stage reset'):
        consume(mutate(records, 'reset_flush', 'stage', 9), cases)


def test_success_cannot_finish_with_reset(boundary, cases):
    records = boundary[:-2] + [packet('reset_flush', transaction=1, stage=6)]
    with pytest.raises(ValueError, match='unsolicited'):
        consume(records, cases)


def test_vector_loader_strict_extent_encoding_and_arithmetic_links(tmp_path, cases):
    ex = cases[1]
    folder = tmp_path / 'case1'
    folder.mkdir()
    names = ('projected_steps', 'projected_fp32', 'projected', 'norm', 'rope',
             'activation', 'weight', 'norm_weight', 'trig')
    for name in names:
        width = 8 if name in ('projected_steps', 'projected_fp32') else 4
        (folder / (name + '.memh')).write_text(''.join(f'{int(x):0{width}x}\n' for x in ex[name]))
    assert v.load_case(tmp_path, 1)['columns'] == 256
    path = folder / 'projected_steps.memh'
    original = path.read_text()
    for invalid in (original[:-1], original + '00000000\n', 'fffffffff\n' + original.split('\n', 1)[1]):
        path.write_text(invalid)
        with pytest.raises(ValueError):
            v.load_case(tmp_path, 1)
    path.write_text(original)
    for name in ('projected_fp32', 'projected', 'norm', 'rope'):
        path = folder / (name + '.memh')
        original = path.read_text()
        width = 8 if name == 'projected_fp32' else 4
        path.write_text('0' * width + '\n' + original.split('\n', 1)[1])
        with pytest.raises(ValueError):
            v.load_case(tmp_path, 1)
        path.write_text(original)


def test_recovery_is_ordered_after_faults_and_resets(tmp_path, mock_vectors):
    sequence = v._suite_sequence('all')
    recovery = ('recovery', 'recovery_after_fault_or_reset', 1)
    positions = [i for i, identity in enumerate(sequence) if identity == recovery]
    assert positions == [35, 43]
    assert sequence[positions[0] - 1] == ('fault', 'RoPE_L2_write_error', 1)
    assert sequence[positions[1] - 1] == ('reset', 'reset_stage6', 1)
    # Starting with a clean recovery may not stand in for the required faults.
    path = save_trace(tmp_path / 'reordered.jsonl', [begin(1, *recovery[:2])])
    with pytest.raises(ValueError, match='reordered test identity'):
        v.verify_trace(path, tmp_path, suite='fault')


@pytest.mark.parametrize('value', ['F' * 16, '0' * 15, '0' * 17, '0x' + '0' * 14,
                                   '-000000000000001', ' ' + '0' * 15, 0, True])
def test_hex_width_case_and_types_fail_closed(value):
    with pytest.raises(ValueError):
        v._hex(value, 16)


def test_q_gate_mutation_is_independently_rejected(cases):
    records = list(complete_records(transaction(begin(0, 'main', 'source_case0'), cases[0])))
    consume(records, cases)
    with pytest.raises(ValueError, match='raw Q gate'):
        consume(mutate(records, 'norm', 'gate', '0' * 1024), cases)


def test_terminal_and_reset_do_not_allow_late_activity(boundary, cases):
    # Actual completion forbids even a fully valid next Matrix packet for the
    # previous transaction. Public verifier also rejects activity after reset.
    matrix = next(r for r in boundary if r['event'] == 'matrix')
    with pytest.raises(ValueError, match='activity after done'):
        consume(boundary[:-1] + [matrix], cases)
