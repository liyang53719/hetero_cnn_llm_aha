"""Source-only accounting fixtures; these are never RTL or numerical evidence."""
from collections import Counter
import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tile16_phases_under_test', ROOT / 'scripts/analyze_matrix_norm_rope_tile16_phases.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
from verify_matrix_norm_rope_tile16_trace import SCHEMA, STRINGS


def record(event, cycle=None, **fields):
    out = {key: '' if key in STRINGS or (key == 'kind' and event == 'begin') else 0 for key in SCHEMA[event]}
    out.update(event=event, transaction=1)
    if cycle is not None:
        out['cycle'] = cycle
    out.update(fields)
    return out


def sample():
    """Abbreviated, non-arithmetic fault fixture with every observed boundary."""
    b = record('begin', kind='fault', name='accounting_fixture', role=1, checking=1,
               token_count=1, packed_base=0x40000, norm_base=0x60000, rope_base=0x80000,
               act_base=0x10000, wgt_base=0x20000, gamma_base=0x2000, trig_base=0x3000)
    rows = [b, record('accepted_start', 10), record('descriptor_request', 12, index=1),
            record('descriptor', 16, index=1)]

    def dma(index, first, last, name, kind, size, count):
        src = b[name + '_base'] if kind == 3 else 0x100000000
        rows.extend([record('dma', first, index=index, kind=kind, row_bytes=size, rows=count,
                            source=f'{src:016x}', destination='0000000000000000'),
                     record('dma_ack', last, index=index)])
        if kind == 3:
            rows.append(record('dma_data', first + 2, index=index))

    def read(region, first, last, address):
        rows.extend([record('l2_read', first, region=region, byte_address=address),
                     record('l2_response', last, byte_address=address)])

    def write(region, first, last, address):
        rows.extend([record('l2_write', first, region=region, byte_address=address),
                     record('l2_ack', last, byte_address=address)])

    dma(0, 18, 24, 'act', 1, 2, 1024)
    rows.append(record('projection_begin', 26, rows=1))
    dma(1, 26, 35, 'wgt', 1, 64, 1024)
    read(5, 36, 40, b['act_base'])
    rows.append(record('matrix', 39, rows=1))
    read(6, 42, 45, b['wgt_base'])
    rows.append(record('matrix', 48, rows=1, last=1, index=1))
    write(0, 50, 50, b['packed_base'])
    dma(2, 52, 56, 'packed', 3, 64, 1)
    rows.append(record('head_begin', 60))
    read(0, 60, 62, b['packed_base'])
    for i in range(8):
        read(3, 70 + i * 4, 72 + i * 4, b['gamma_base'] + i * 64)
    rows.append(record('norm', 108))
    for i in range(8):
        write(1, 110 + i * 4, 112 + i * 4, b['norm_base'] + i * 64)
        read(1, 144 + i * 4, 146 + i * 4, b['norm_base'] + i * 64)
    for i in range(2):
        read(4, 176 + i * 4, 178 + i * 4, b['trig_base'] + i * 64)
    for i in range(8):
        write(2, 190 + i * 4, 192 + i * 4, b['rope_base'] + i * 64)
    dma(3, 224, 228, 'norm', 3, 64, 8)
    dma(4, 230, 744, 'rope', 3, 64, 8)
    rows.extend([record('head_done', 744),
                 record('projection_done', 748, rows=1, matrix_inputs=2, matrix_outputs=2, write_acks=17),
                 record('done', 750, status=6)])
    rows[1:] = sorted(rows[1:], key=lambda r: r['cycle'])
    # The first accepted weight DMA shares the projection begin cycle. Place
    # same-cycle begin before the request, matching the frozen testbench.
    rows.append(record('terminal', status=6, matrix_inputs=2, matrix_outputs=2, matrix_steps=2,
                       dma_count=5, write_requests=17, write_acks=17, completed_heads=1,
                       ddr_read_bytes=67584, ddr_write_bytes=1088, command_cycles=741))
    return rows


def verified_for(result):
    terminals = []
    for c in result['commands']:
        v = {key: c[key] for key in ('kind', 'name', 'case', 'status', 'completed_heads', 'completed_tokens', 'ddr_read_bytes', 'ddr_write_bytes')}
        v['matrix_packets'] = c['observed_matrix_output_count']
        if c['status'] is not None:
            v.update(accepted_to_done_cycles=c['command_cycles'], fixed_matrix_lanes=512)
        if c['status'] == 0:
            v.update(useful_fma=c['useful_fma'], candidate_useful_wall_fraction=c['candidate_useful_wall_fraction'])
        terminals.append(v)
    return dict(events=result['events'], transactions=len(terminals), terminals=terminals)


def save_trace(path, records):
    with gzip.open(path, 'wt') as stream:
        for r in records:
            stream.write(json.dumps(r) + '\n')


def fixture_files(tmp_path):
    records = sample()
    trace = tmp_path / 'baseline_all.jsonl.gz'
    save_trace(trace, records)
    check = verified_for(p.analyze_records(records))
    verified = tmp_path / 'verified.json'
    verified.write_text(json.dumps(check))
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps(dict(status='REJECTED_NATIVE_SOURCE_THRESHOLD_TILE16_RTL_MATCHED', source_sha256=p.source_hashes(), rtl_suites=[
        dict(source='baseline', suite='all', trace_sha256=p.digest(trace), independent_trace=check)])))
    return trace, verified, summary


def test_exact_cycle_partition_and_overlap_are_independent():
    records = sample()
    result = p.analyze_records(records)
    c = result['commands'][0]
    # Independent explicit-cycle oracle for this tiny fixture. Production uses
    # streaming interval accounting and never allocates a cycle-sized array.
    expected = dict.fromkeys(range(10, 751), 'control_admission')
    for first, last, label in (
        (36, 48, 'matrix_residual_input_control_pipeline'),
        (49, 56, 'packed_output_control_admission'),
        (60, 100, 'norm_input_control_admission'),
        (101, 108, 'norm_compute_boundary_residual'),
        (109, 140, 'norm_output_control_admission'),
        (141, 182, 'rope_input_control_admission'),
        (183, 189, 'rope_compute_boundary_residual'),
        (190, 220, 'rope_output_control_admission'),
        (221, 744, 'final_store_control_admission'),
    ):
        expected.update(dict.fromkeys(range(first, last + 1), label))
    expected.update(dict.fromkeys(range(12, 17), 'descriptor_owner'))
    for first, last, name in ((18, 24, 'activation'), (26, 35, 'weight'), (52, 56, 'packed'), (224, 228, 'norm'), (230, 744, 'rope')):
        expected.update(dict.fromkeys(range(first, last + 1), p.DMA_BUCKETS[name]))
    pending = None
    for r in records:
        if r['event'] in ('l2_read', 'l2_write'):
            pending = r
        elif r['event'] in ('l2_response', 'l2_ack'):
            q = pending
            if q['event'] == 'l2_read':
                group = 'matrix_operand' if q['region'] in (5, 6) else 'norm_input' if q['region'] in (0, 3) else 'rope_input'
                expected[q['cycle']] = group + '_read_request'
                expected.update(dict.fromkeys(range(q['cycle'] + 1, r['cycle'] + 1), group + '_read_owner_wait'))
            else:
                name = ('packed', 'norm', 'rope')[q['region']]
                expected.update(dict.fromkeys(range(q['cycle'], r['cycle'] + 1), name + '_producer_write_ack'))
            pending = None
    assert +Counter(c['exclusive_cycles']) == Counter(expected.values())
    assert c['exclusive_cycle_sum'] == c['command_cycles'] == 741
    assert c['exclusive_cycles']['norm_compute_boundary_residual'] == 8
    assert c['exclusive_cycles']['rope_compute_boundary_residual'] == 7
    assert c['same_cycle_producer_acks'] == 1
    assert c['matrix_input_fire_timestamps_available'] is False
    assert c['observed_matrix_outputs_by_exclusive_bucket'] == {
        'matrix_operand_read_owner_wait': 1, 'matrix_residual_input_control_pipeline': 1}
    assert c['overlapping_observable_intervals']['matrix_tile_after_weight_ack_to_last_output']['sum_cycles'] == 13
    assert c['overlapping_observable_intervals']['matrix_operand_response_to_next_request_gap']['sum_cycles'] == 1
    assert c['overlapping_observable_intervals']['matrix_last_operand_response_to_final_output']['sum_cycles'] == 3
    assert c['overlapping_observable_intervals']['row_head_envelope']['sum_cycles'] == 685
    assert c['exclusive_cycles']['ddr_rope_store_owner'] == 515
    assert result['aggregates']['successful_primary_commands']['commands'] == 0
    assert result['aggregates']['failed_completed_commands']['command_cycles'] == 741


def test_compressed_final_sha_binding_and_provisional_distinction(tmp_path):
    trace, verified, summary = fixture_files(tmp_path)
    provisional = p.analyze_trace(trace, provisional_verified_summary=verified)
    final = p.analyze_trace(trace, runner_summary=summary, suite_key='baseline_all')
    assert provisional['binding']['final_runner_bound'] is False
    assert provisional['binding']['mode'] == 'provisional_verified_inventory_only'
    assert final['binding']['final_runner_bound'] is True
    assert final['trace_sha256'] == p.digest(trace)
    assert final['analysis_source_sha256'] == p.source_hashes()
    assert final['source_hashes_unchanged_after_analysis'] is True
    assert final['trace_sha256_rechecked_after_analysis'] is True
    assert final['commands'] == provisional['commands']
    assert 'rejected' in final['binding']['runner_status'].lower()
    for phrase in ('physical DDR', 'PPA', 'whole-block', '512-cycle'):
        assert phrase in final['conventions']['environment']


@pytest.mark.parametrize('mutation,match', [
    ('trace', 'SHA differs'), ('cycles', 'denominator drift'), ('count', 'Matrix count drift'),
    ('inventory', 'event inventory drift'), ('lanes', 'denominator drift'), ('missing_suite', 'suite missing'),
    ('status', 'not a completed'), ('source', 'source differs'),
])
def test_final_binding_fails_closed(tmp_path, mutation, match):
    trace, _, summary = fixture_files(tmp_path)
    raw = json.loads(summary.read_text())
    check = raw['rtl_suites'][0]['independent_trace']
    if mutation == 'trace':
        raw['rtl_suites'][0]['trace_sha256'] = '0' * 64
    elif mutation == 'cycles':
        check['terminals'][0]['accepted_to_done_cycles'] += 1
    elif mutation == 'count':
        check['terminals'][0]['matrix_packets'] += 1
    elif mutation == 'inventory':
        check['events']['matrix'] += 1
    elif mutation == 'lanes':
        check['terminals'][0]['fixed_matrix_lanes'] = 32
    elif mutation == 'missing_suite':
        raw['rtl_suites'] = []
    elif mutation == 'status':
        raw['status'] = 'RUNNING'
    elif mutation == 'source':
        raw['source_sha256'][p.VERIFIER_SOURCES[0]] = '0' * 64
    summary.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match=match):
        p.analyze_trace(trace, runner_summary=summary, suite_key='baseline_all')


@pytest.mark.parametrize('event,field,value,match', [
    ('terminal', 'command_cycles', 740, 'denominator drift'),
    ('terminal', 'matrix_inputs', 3, 'counter drift'),
    ('terminal', 'ddr_write_bytes', 0, 'DMA bytes drift'),
    ('l2_response', 'byte_address', 1, 'identity mismatch'),
    ('dma_ack', 'index', 99, 'identity mismatch'),
    ('projection_done', 'matrix_inputs', 1, 'counter drift'),
    ('head_done', 'row', 1, 'identity drift'),
    ('accepted_start', 'cycle', 11, 'denominator drift'),
])
def test_corrupt_accounting_rejected_even_under_python_O(event, field, value, match):
    records = sample()
    next(r for r in records if r['event'] == event)[field] = value
    with pytest.raises(ValueError, match=match):
        p.analyze_records(records)


def test_missing_terminal_and_response_rejected():
    with pytest.raises(ValueError, match='missing complete'):
        p.analyze_records(sample()[:-1])
    records = sample()
    records = [r for r in records if not (r['event'] == 'l2_response' and r['cycle'] == 40)]
    with pytest.raises(ValueError, match='duplicate pending'):
        p.analyze_records(records)


def test_reset_is_not_a_done_cycle_denominator(tmp_path):
    records = sample()[:5]
    records[0]['kind'] = 'reset'
    # Pending activation DMA is discarded at reset, not counted as an ACK.
    records.append(record('reset_flush'))
    assert 'cycle' not in records[-1]
    # Unlike a made-up timed reset event, every record matches the actual
    # frozen verifier schema before entering the accounting core.
    records = [p._record(json.dumps(r) + '\n') for r in records]
    result = p.analyze_records(records)
    c = result['commands'][0]
    assert c['excluded_from_completed_cycle_aggregates'] is True
    assert 'command_cycles' not in c and 'exclusive_cycles' not in c
    assert c['last_observed_cycle'] == 18
    assert c['reset_flush_timestamp_available'] is False
    assert 'reset_flush' not in c
    assert result['aggregates']['all_completed_commands']['command_cycles'] == 0
    p.check_verified(result, verified_for(result))
    trace = tmp_path / 'reset.jsonl.gz'
    save_trace(trace, records)
    verified = tmp_path / 'verified_reset.json'
    verified.write_text(json.dumps(verified_for(result)))
    from_file = p.analyze_trace(trace, provisional_verified_summary=verified)
    assert from_file['commands'] == result['commands']


def test_trace_and_analyzer_hashes_are_checked_after_analysis(tmp_path, monkeypatch):
    trace, verified, _ = fixture_files(tmp_path)
    real_digest = p.digest
    calls = 0

    def changing_digest(path):
        nonlocal calls
        if Path(path) == trace:
            calls += 1
            if calls == 2:
                return '0' * 64
        return real_digest(path)

    monkeypatch.setattr(p, 'digest', changing_digest)
    with pytest.raises(ValueError, match='trace content SHA changed'):
        p.analyze_trace(trace, provisional_verified_summary=verified)
    assert calls == 2
    monkeypatch.setattr(p, 'digest', real_digest)
    real_sources = p.source_hashes
    calls = 0

    def changing_sources():
        nonlocal calls
        calls += 1
        out = real_sources()
        if calls == 2:
            out[p.ANALYSIS_SOURCES[0]] = '0' * 64
        return out

    monkeypatch.setattr(p, 'source_hashes', changing_sources)
    with pytest.raises(ValueError, match='source changed during analysis'):
        p.analyze_trace(trace, provisional_verified_summary=verified)


def test_same_cycle_cross_channel_boundary_has_one_owner():
    records = sample()
    # Move weight acceptance to the activation ACK boundary. Descriptor and DMA
    # ownership is otherwise unchanged; the old DMA owns this shared cycle.
    for r in records:
        if r['event'] == 'projection_begin' or (r['event'] == 'dma' and r['index'] == 1):
            r['cycle'] = 24
    result = p.analyze_records(records)
    c = result['commands'][0]
    assert c['service_owner_boundary_overlap_cycles'] == 1
    assert c['exclusive_cycle_sum'] == 741
    assert c['exclusive_cycles']['dma_activation_owner'] == 7
    assert c['exclusive_cycles']['dma_weight_owner'] == 11
    assert c['overlapping_observable_intervals']['dma_weight_request_to_ack']['sum_cycles'] == 12


def test_no_cycle_allocation_needed_for_very_long_idle_gap():
    records = [record('begin', kind='reject', name='bad_command'), record('accepted_start', 1),
               record('done', 10**12, status=4), record('terminal', status=4, command_cycles=10**12)]
    c = p.analyze_records(records)['commands'][0]
    assert c['command_cycles'] == c['exclusive_cycles']['control_admission'] == 10**12


def test_fixed512_denominator_aggregation_does_not_use_active_rows():
    c = p.analyze_records(sample())['commands'][0]
    c.update(status=0, useful_fma=16384)
    out = p.aggregate([c, copy.deepcopy(c)])
    assert out['candidate_useful_wall_fraction'] == 32768 / (512 * 1482)
    assert out['fixed_matrix_lanes'] == 512 and out['whole_block_metric'] is False


def test_binding_mode_is_required_and_unambiguous(tmp_path):
    trace, verified, summary = fixture_files(tmp_path)
    with pytest.raises(ValueError, match='exactly one'):
        p.analyze_trace(trace)
    with pytest.raises(ValueError, match='exactly one'):
        p.analyze_trace(trace, runner_summary=summary, provisional_verified_summary=verified)
    with pytest.raises(ValueError, match='requires suite_key'):
        p.analyze_trace(trace, runner_summary=summary)
    with pytest.raises(ValueError, match='requires final runner'):
        p.analyze_trace(trace, provisional_verified_summary=verified, suite_key='baseline_all')


def test_batch_cli_analyzes_both_final_suites_and_preserves_rejection(tmp_path):
    trace, _, summary = fixture_files(tmp_path)
    avx2 = tmp_path / 'avx2_main.jsonl.gz'
    avx2.write_bytes(trace.read_bytes())
    raw = json.loads(summary.read_text())
    second = copy.deepcopy(raw['rtl_suites'][0])
    second.update(source='avx2', suite='main')
    raw['rtl_suites'].append(second)
    summary.write_text(json.dumps(raw))
    output = tmp_path / 'phases.json'
    p.main(['--runner-summary', str(summary), '--trace-directory', str(tmp_path), '--output', str(output)])
    result = json.loads(output.read_text())
    assert result['final_runner_bound'] is True
    assert set(result['suites']) == {'baseline_all', 'avx2_main'}
    assert result['suites']['baseline_all']['binding']['runner_status'] == raw['status']


def test_gzip_truncation_and_unknown_event_fail_closed(tmp_path):
    trace, verified, _ = fixture_files(tmp_path)
    trace.write_bytes(trace.read_bytes()[:-8])
    with pytest.raises((EOFError, OSError)):
        p.analyze_trace(trace, provisional_verified_summary=verified)
    rows = sample()
    rows[1]['event'] = 'matrix_input_fire'
    save_trace(trace, rows)
    with pytest.raises(ValueError, match='unknown trace event'):
        p.analyze_trace(trace, provisional_verified_summary=verified)


def test_observable_interval_math_and_aggregate_min_max():
    stats = {}
    p.add_interval(stats, 'empty', 3, 2)
    p.add_interval(stats, 'owner', 2, 4)
    p.add_interval(stats, 'owner', 5, 5)
    p.merge_intervals(stats, {'owner': dict(count=1, sum_cycles=7, min_cycles=7, max_cycles=7)})
    assert stats['empty']['sum_cycles'] == 0
    assert stats['owner'] == dict(count=3, sum_cycles=11, min_cycles=1, max_cycles=7)
    with pytest.raises(ValueError, match='negative observable'):
        p.add_interval(stats, 'bad', 5, 3)


def successful_accounting_fixture(token_count):
    """Boundary-only core fixture, deliberately not a verifier/numerical input."""
    b = sample()[0]
    b.update(kind='main', name='tail_' + str(token_count), token_count=token_count)
    yield b
    cycle = 0
    counts = Counter()
    dma_index = 0
    read_bytes = write_bytes = 0

    def emit(event, **fields):
        nonlocal cycle
        cycle += 1
        counts[event] += 1
        return record(event, cycle, **fields)

    def dma(kind, name, size, rows):
        nonlocal dma_index, read_bytes, write_bytes
        source = b[name + '_base'] if kind == 3 else 0x100000000
        yield emit('dma', index=dma_index, kind=kind, source=f'{source:016x}', row_bytes=size, rows=rows)
        yield emit('dma_ack', index=dma_index)
        if kind == 1:
            read_bytes += size * rows
        else:
            write_bytes += size * rows
        dma_index += 1

    def read(region, address):
        yield emit('l2_read', region=region, byte_address=address)
        yield emit('l2_response', byte_address=address)

    def write(region, address):
        yield emit('l2_write', region=region, byte_address=address)
        yield emit('l2_ack', byte_address=address)

    yield emit('accepted_start')
    for batch in range(0, token_count, 16):
        rows = min(16, token_count - batch)
        for row in range(rows):
            yield from dma(1, 'act', 2, 1024)
        for head in range(2):
            yield emit('projection_begin', head=head, batch_start=batch, rows=rows)
            for tile in range(8):
                yield from dma(1, 'wgt', 64, 1024)
                # Only output boundaries are needed by the accounting core;
                # real final-file use is separately bound to the full verifier.
                for step in range(1024):
                    yield emit('matrix', head=head, batch_start=batch, rows=rows,
                               tile=tile, index=tile * 1024 + step, last=int(step == 1023))
                for row in range(rows):
                    yield from write(0, b['packed_base'] + tile * 1024 + row * 64)
                yield from dma(3, 'packed', 64, rows)
            for row in range(rows):
                identity = dict(head=head, row=row, token=batch + row)
                yield emit('head_begin', **identity)
                for i in range(8):
                    yield from read(0, b['packed_base'] + i * 1024 + row * 64)
                for i in range(8):
                    yield from read(3, b['gamma_base'] + i * 64)
                yield emit('norm')
                for i in range(8):
                    yield from write(1, b['norm_base'] + i * 64)
                for i in range(8):
                    yield from read(1, b['norm_base'] + i * 64)
                for i in range(2):
                    yield from read(4, b['trig_base'] + i * 64)
                for i in range(8):
                    yield from write(2, b['rope_base'] + i * 64)
                yield from dma(3, 'norm', 64, 8)
                yield from dma(3, 'rope', 64, 8)
                yield emit('head_done', **identity)
            yield emit('projection_done', head=head, batch_start=batch, rows=rows,
                       matrix_inputs=8192, matrix_outputs=8192, write_acks=rows * 24)
    yield emit('done')
    yield record('terminal', matrix_inputs=counts['matrix'], matrix_outputs=counts['matrix'], matrix_steps=counts['matrix'],
                 dma_count=counts['dma'], write_requests=counts['l2_write'], write_acks=counts['l2_ack'],
                 completed_heads=token_count * 2, completed_tokens=token_count,
                 command_cycles=cycle, ddr_read_bytes=read_bytes, ddr_write_bytes=write_bytes)


@pytest.mark.parametrize('token_count', [1, 3, 17])
def test_successful_tail_batch_geometry_fixed512_and_aggregate_separation(token_count):
    result = p.analyze_records(successful_accounting_fixture(token_count))
    c = result['commands'][0]
    assert c['exclusive_cycle_sum'] == c['command_cycles']
    assert c['useful_fma'] == token_count * 2 * 8 * 1024 * 32
    assert c['candidate_useful_wall_fraction'] == c['useful_fma'] / (512 * c['command_cycles'])
    assert c['accepted_matrix_input_count'] == ((token_count + 15) // 16) * 16384
    assert c['overlapping_observable_intervals']['projection_envelope']['count'] == ((token_count + 15) // 16) * 2
    assert result['aggregates']['successful_auxiliary_commands']['commands'] == 1
    assert result['aggregates']['successful_primary_commands']['commands'] == 0
    assert result['aggregates']['failed_completed_commands']['commands'] == 0
    p.check_verified(result, verified_for(result))
