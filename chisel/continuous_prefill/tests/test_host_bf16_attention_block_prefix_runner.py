"""Synthetic bounded-prefix evidence and orchestration; no model, EDA or DUT run."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
prefix = importlib.import_module('host_bf16_attention_block_prefix')

HEADER = dict(schema='HOST_ATTENTION_BLOCK_PREFIX_EVENTS_V1',
              numerical_acceptance=False, payload_encoding='le_u32x16_hex',
              timing_excluded=True)
RAW_FIELDS = ('pre_w_payload_le_hex', 'pre_r_payload_le_hex')
SAFE_FIELDS = {'report_sha256', 'deterministic_sha256', 'counters',
               'terminal_event_sha256', 'step_elapsed_ns', 'event_sha256',
               'event_bytes', 'memory_bytes', 'memory_fnv1a64',
               'memory_hash_is_noncryptographic'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def object_sha(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


@pytest.fixture
def evidence():
    events = [dict(cycle=i, reset=int(i <= 6), pre_w_valid=0, pre_w_ready=0,
                   pre_r_valid=0, pre_r_ready=0, pre_b_valid=0, pre_b_ready=0,
                   end_pending_valid=0, end_reset_required=0, end_running=1,
                   end_idma_read_beats=int(i >= 100), pre_w_payload_le_hex='',
                   pre_r_payload_le_hex='') for i in range(1, 4097)]
    # A stalled payload remains in the local raw trace, including at its end.
    for event in (events[100], events[-1]):
        event.update(pre_r_valid=1, pre_r_payload_le_hex='ab' * 64)
    events[98].update(pre_ar_valid=1, pre_ar_ready=1)
    events[99].update(pre_r_valid=1, pre_r_ready=1, pre_r_payload_le_hex='ab' * 64)
    terminal = {key: value for key, value in events[-1].items() if key not in RAW_FIELDS}
    counters = dict(cycles=4096, reset_cycles=6, active_cycles=4060,
                    ar_handshakes=1, aw_handshakes=0, w_handshakes=0,
                    r_handshakes=1, b_handshakes=0)
    report = dict(schema='HOST_ATTENTION_BLOCK_PREFIX_V1',
                  status='BOUNDED_DIAGNOSTIC_PREFIX', numerical_acceptance=False,
                  prefix_reached=True, cycles=4096, cycle_limit=4096,
                  constructor_cycles=36, event_file='prefix_events.jsonl',
                  deterministic=dict(counters, terminal_event=terminal,
                                     memory_bytes=64, memory_fnv1a64='0123456789abcdef'),
                  memory_hash_is_noncryptographic=True,
                  step_elapsed_ns=100)
    return report, deepcopy(HEADER), events


def write_evidence(output, evidence):
    report, header, events = deepcopy(evidence)
    output.mkdir()
    data = b''.join((json.dumps(row, sort_keys=True) + '\n').encode()
                    for row in [header, *events])
    (output / 'prefix_events.jsonl').write_bytes(data)
    report['event_bytes'] = len(data)
    (output / 'prefix.json').write_text(json.dumps(report))
    return report, data


def rewrite_report(output, change):
    path = output / 'prefix.json'
    report = json.loads(path.read_text())
    change(report)
    path.write_text(json.dumps(report))


def test_reader_returns_only_scalars_and_hashes_even_with_unexpected_payloads(tmp_path, evidence):
    report, _, events = evidence
    report['arbitrary_report_payload'] = {'secret': 'DO_NOT_UPLOAD_REPORT'}
    report['deterministic']['arbitrary_payload'] = ['DO_NOT_UPLOAD_DETERMINISTIC']
    events[-1]['future_payload'] = 'DO_NOT_UPLOAD_TERMINAL'
    report['deterministic']['terminal_event']['future_payload'] = 'DO_NOT_UPLOAD_TERMINAL'
    output = tmp_path / 'prefix'
    saved, raw = write_evidence(output, evidence)

    result = prefix.read_prefix(output)

    assert set(result) == SAFE_FIELDS
    assert result['counters'] == {key: saved['deterministic'][key] for key in prefix.COUNTERS}
    assert result['counters']['reset_cycles'] == 6
    assert result['counters']['active_cycles'] == 4060
    assert result['report_sha256'] == sha((output / 'prefix.json').read_bytes())
    assert result['event_sha256'] == sha(raw)
    assert result['event_bytes'] == len(raw)
    assert result['deterministic_sha256'] == object_sha(saved['deterministic'])
    assert result['terminal_event_sha256'] == object_sha(saved['deterministic']['terminal_event'])
    assert result['step_elapsed_ns'] == 100
    assert result['memory_bytes'] == 64
    assert result['memory_fnv1a64'] == '0123456789abcdef'
    assert result['memory_hash_is_noncryptographic'] is True
    compact = json.dumps(result)
    assert 'DO_NOT_UPLOAD' not in compact and 'ab' * 64 not in compact
    assert 'payload' not in compact and 'terminal_event"' not in compact


@pytest.mark.parametrize('field,value,reason', [
    ('schema', 'OTHER_PREFIX', 'numerical acceptance'),
    ('status', 'PASS_NUMERICAL', 'numerical acceptance'),
    ('numerical_acceptance', True, 'numerical acceptance'),
    ('numerical_acceptance', 0, 'numerical acceptance'),
    ('prefix_reached', False, 'numerical acceptance'),
    ('prefix_reached', 1, 'numerical acceptance'),
    ('cycles', 4095, 'bounded prefix scope'),
    ('cycle_limit', 4097, 'bounded prefix scope'),
    ('constructor_cycles', 35, 'bounded prefix scope'),
    ('event_file', '../prefix_events.jsonl', 'bounded prefix scope'),
    ('event_bytes', 1, 'event byte count'),
    ('step_elapsed_ns', 0, 'completed-step time'),
    ('step_elapsed_ns', -1, 'completed-step time'),
    ('step_elapsed_ns', True, 'completed-step time'),
    ('step_elapsed_ns', 1.5, 'completed-step time'),
    ('step_elapsed_ns', None, 'completed-step time'),
    ('deterministic', [], 'deterministic prefix state'),
    ('memory_hash_is_noncryptographic', False, 'memory diagnostic digest'),
    ('memory_hash_is_noncryptographic', 1, 'memory diagnostic digest'),
])
def test_reader_rejects_invalid_report_fields(tmp_path, evidence, field, value, reason):
    output = tmp_path / 'prefix'
    write_evidence(output, evidence)
    rewrite_report(output, lambda report: report.update({field: value}))
    with pytest.raises(ValueError, match=reason):
        prefix.read_prefix(output)


@pytest.mark.parametrize('field,value,reason', [
    ('cycles', 4095, 'deterministic prefix state'),
    ('terminal_event', [], 'deterministic prefix state'),
    ('ar_handshakes', True, 'prefix counters'),
    ('aw_handshakes', -1, 'prefix counters'),
    ('w_handshakes', 4097, 'prefix counters'),
    ('r_handshakes', '0', 'prefix counters'),
    ('b_handshakes', None, 'prefix counters'),
    ('reset_cycles', 5, 'reset/active cycle scope'),
    ('active_cycles', 4090, 'reset/active cycle scope'),
    ('ar_handshakes', 0, 'actual AXI reads'),
    ('r_handshakes', 0, 'actual AXI reads'),
    ('memory_bytes', 0, 'memory diagnostic digest'),
    ('memory_bytes', -4, 'memory diagnostic digest'),
    ('memory_bytes', 63, 'memory diagnostic digest'),
    ('memory_bytes', True, 'memory diagnostic digest'),
    ('memory_bytes', 64.0, 'memory diagnostic digest'),
    ('memory_bytes', None, 'memory diagnostic digest'),
    ('memory_fnv1a64', None, 'memory diagnostic digest'),
    ('memory_fnv1a64', 1234567890123456, 'memory diagnostic digest'),
    ('memory_fnv1a64', '0123456789abcde', 'memory diagnostic digest'),
    ('memory_fnv1a64', '00123456789abcdef', 'memory diagnostic digest'),
    ('memory_fnv1a64', '0123456789ABCDEF', 'memory diagnostic digest'),
    ('memory_fnv1a64', '0123456789abcdeg', 'memory diagnostic digest'),
])
def test_reader_rejects_invalid_deterministic_state(tmp_path, evidence, field, value, reason):
    output = tmp_path / 'prefix'
    write_evidence(output, evidence)
    rewrite_report(output, lambda report: report['deterministic'].update({field: value}))
    with pytest.raises(ValueError, match=reason):
        prefix.read_prefix(output)


@pytest.mark.parametrize('field,value', [
    ('schema', 'OTHER_EVENTS'), ('numerical_acceptance', True),
    ('payload_encoding', 'unbounded'), ('timing_excluded', False),
    ('unexpected_header_field', 'payload'),
])
def test_reader_rejects_event_header_schema_or_timing_claim(tmp_path, evidence, field, value):
    evidence[1][field] = value
    output = tmp_path / 'prefix'
    write_evidence(output, evidence)
    with pytest.raises(ValueError, match='prefix event schema'):
        prefix.read_prefix(output)


@pytest.mark.parametrize('fault,reason', [
    ('reorder', 'ordered event'), ('duplicate', 'ordered event'),
    ('missing_cycle', 'ordered event'), ('extra', 'ordered event'),
    ('short', 'incomplete prefix events'), ('header_only', 'incomplete prefix events'),
    ('terminal', 'terminal event mismatch'), ('terminal_raw_payload', 'terminal event mismatch'),
])
def test_reader_requires_complete_ordered_events_and_matching_terminal(tmp_path, evidence, fault, reason):
    report, _, events = evidence
    if fault == 'reorder':
        events[20], events[21] = events[21], events[20]
    elif fault == 'duplicate':
        events[20]['cycle'] = events[19]['cycle']
    elif fault == 'missing_cycle':
        del events[20]['cycle']
    elif fault == 'extra':
        events.append(dict(events[-1], cycle=4097))
    elif fault == 'short':
        events.pop()
    elif fault == 'header_only':
        events.clear()
    elif fault == 'terminal':
        report['deterministic']['terminal_event']['pre_b_valid'] = 1
    else:
        report['deterministic']['terminal_event']['pre_r_payload_le_hex'] = events[-1]['pre_r_payload_le_hex']
    output = tmp_path / 'prefix'
    write_evidence(output, evidence)
    with pytest.raises(ValueError, match=reason):
        prefix.read_prefix(output)


@pytest.mark.parametrize('field,value', [
    ('end_reset_required', 1), ('end_running', 0), ('end_idma_read_beats', 0),
])
def test_reader_rejects_unhealthy_actual_terminal_even_when_trace_agrees(tmp_path, evidence, field, value):
    report, _, events = evidence
    events[-1][field] = value
    report['deterministic']['terminal_event'][field] = value
    output = tmp_path / 'prefix'
    write_evidence(output, evidence)
    with pytest.raises(ValueError, match='healthy active execution'):
        prefix.read_prefix(output)


@pytest.fixture
def harness(tmp_path, monkeypatch, evidence):
    build, path = tmp_path / 'build', tmp_path / 'fixture'
    build.mkdir()
    path.mkdir()
    authorities = {name: object() for name in
                   ('block_session', 'session', 'projection_session', 'attention_session')}
    admitted = dict(source_sha256={'source.py': 'a' * 64}, input_sha256={'hidden.bf16le': 'b' * 64})
    identity = {'obj/VHostBlockTop': 'c' * 64, 'generated/HostBlockTop.sv': 'd' * 64,
                'build_ready.json': 'e' * 64}
    state = SimpleNamespace(calls=[], admission_calls=0, identity_calls=0,
                            sources=[], timeline=[], drift_kind=None, drift_call=None,
                            failure=None, failure_index=0, clock=10.)

    def admit(given_path, **given_authorities):
        assert given_path == path and given_authorities == authorities
        state.admission_calls += 1
        state.timeline.append('admit')
        result = deepcopy(admitted)
        if state.drift_kind == 'admission' and state.admission_calls == state.drift_call:
            result['input_sha256']['hidden.bf16le'] = 'f' * 64
        return result

    def build_identity(given_build, sources):
        assert given_build == build and sources == admitted['source_sha256']
        state.identity_calls += 1
        state.timeline.append('identity')
        result = dict(identity)
        if state.drift_kind == 'identity' and state.identity_calls == state.drift_call:
            result['obj/VHostBlockTop'] = 'f' * 64
        return result

    def verify_sources(given_build, log_name):
        assert given_build == build
        state.sources.append(log_name)
        state.timeline.append(log_name)
        if state.failure == log_name:
            raise ValueError('source closure mismatch')

    def execute(argv, *, cwd, stdout, stderr, timeout):
        index = len(state.calls)
        assert cwd == prefix.live.ROOT and stderr == prefix.subprocess.STDOUT
        assert argv == [str(build / 'obj/VHostBlockTop'), str(path),
                        str(build / f'diagnostic_prefix{index}'), 'pass',
                        '--diagnostic-prefix=4096']
        assert not Path(argv[2]).exists()
        state.calls.append((argv, timeout))
        state.timeline.append(f'execute{index}')
        state.clock += index + .5
        fault = state.failure if index == state.failure_index else None
        if fault == 'timeout':
            raise prefix.subprocess.TimeoutExpired(argv, timeout)
        run_evidence = deepcopy(evidence)
        # Measured wall/step timing may differ without changing deterministic evidence.
        run_evidence[0]['step_elapsed_ns'] += index
        if fault == 'eventbits':
            run_evidence[2][100]['pre_r_payload_le_hex'] = 'aa' + 'ab' * 63
        if fault == 'counter':
            run_evidence[0]['deterministic']['ar_handshakes'] = 2
        if fault == 'memorybits':
            run_evidence[0]['deterministic']['memory_fnv1a64'] = '1123456789abcdef'
        if fault == 'memorysize':
            run_evidence[0]['deterministic']['memory_bytes'] = 128
        write_evidence(Path(argv[2]), run_evidence)
        stdout.write('HOST_ATTN_BLOCK_PAIR pass\n' if fault == 'completion_marker' else
                     'changed stdout\n' if fault == 'stdout' else 'bounded prefix diagnostic\n')
        return SimpleNamespace(returncode=9 if fault == 'nonzero' else 0)

    monkeypatch.setattr(prefix.live, 'admit_fixture', admit)
    monkeypatch.setattr(prefix.live, 'build_identity', build_identity)
    monkeypatch.setattr(prefix.live, 'verify_all_build_sources', verify_sources)
    monkeypatch.setattr(prefix.subprocess, 'run', execute)
    monkeypatch.setattr(prefix.time, 'monotonic', lambda: state.clock)
    return build, path, authorities, state, admitted, identity


@pytest.mark.parametrize('timeout', [1, 240])
def test_pair_runs_same_elf_twice_with_live_authorities_and_only_diagnostic_acceptance(harness, timeout):
    build, path, authorities, state, admitted, identity = harness

    result = prefix.run_pair(build, path, timeout_seconds=timeout, **authorities)

    assert result['status'] == 'PASS_PRODUCTION_BLOCK_PREFIX_DETERMINISM_ONLY'
    assert result['numerical_acceptance'] is False
    assert result['full_block_m1_executed'] is False
    assert result['raw_prefix_events_upload_allowed'] is False
    assert result['actual_dut_identity_verified'] is result['live_authorities_verified'] is True
    assert result['binary_sha256'] == identity['obj/VHostBlockTop']
    assert result['rtl_sha256'] == identity['generated/HostBlockTop.sv']
    assert result['build_ready_sha256'] == identity['build_ready.json']
    assert result['input_sha256'] == admitted['input_sha256']
    assert result['cycles_per_prefix'] == 4096
    assert result['timeout_seconds_per_prefix'] == timeout
    assert [call[1] for call in state.calls] == [timeout, timeout]
    assert state.admission_calls == state.identity_calls == 4
    assert state.timeline == [
        'admit', 'identity', 'prefix_initial_source_verify.log',
        'admit', 'identity', 'execute0', 'admit', 'identity', 'execute1',
        'admit', 'identity', 'prefix_final_source_verify.log',
    ]
    first, second = result['prefixes']
    assert set(first) == set(second) == SAFE_FIELDS | {'elapsed_seconds', 'log_sha256'}
    assert first['step_elapsed_ns'] != second['step_elapsed_ns']
    assert first['elapsed_seconds'] != second['elapsed_seconds']
    assert first['report_sha256'] != second['report_sha256']
    for field in ('event_sha256', 'event_bytes', 'deterministic_sha256', 'log_sha256'):
        assert first[field] == second[field]
    assert first['elapsed_seconds'] == .5 and second['elapsed_seconds'] == 1.5
    assert json.loads((build / 'diagnostic_prefix_pair.json').read_text()) == result
    assert all((build / f'diagnostic_prefix{i}.exit').read_text() == '0\n' for i in range(2))
    assert 'ab' * 64 not in json.dumps(result)


@pytest.mark.parametrize('timeout', [0, -1, 241, True, 1.5, '240', None])
def test_pair_rejects_unbounded_timeout_before_admission(harness, timeout):
    build, path, authorities, state, _, _ = harness
    with pytest.raises(ValueError, match='bounded prefix timeout'):
        prefix.run_pair(build, path, timeout_seconds=timeout, **authorities)
    assert not state.timeline and not state.calls
    assert not (build / 'diagnostic_prefix_pair.json').exists()


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('target', ['output', 'log'])
def test_pair_rejects_preexisting_output_or_log_without_overwriting(harness, index, target):
    build, path, authorities, state, _, _ = harness
    stale = build / (f'diagnostic_prefix{index}' + ('.log' if target == 'log' else ''))
    if target == 'output':
        stale.mkdir()
        protected = stale / 'existing'
    else:
        protected = stale
    protected.write_text('retain existing evidence')
    with pytest.raises(ValueError, match='fresh prefix evidence'):
        prefix.run_pair(build, path, **authorities)
    assert len(state.calls) == index and protected.read_text() == 'retain existing evidence'
    assert not (build / 'diagnostic_prefix_pair.json').exists()


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('fault,reason,exit_text', [
    ('nonzero', 'execution failed', '9\n'),
    ('timeout', 'timed out', 'TIMEOUT\n'),
    ('completion_marker', 'completed numerical pair', '0\n'),
])
def test_pair_rejects_failed_incomplete_or_numerical_run(harness, index, fault, reason, exit_text):
    build, path, authorities, state, _, _ = harness
    state.failure, state.failure_index = fault, index
    with pytest.raises(ValueError, match=reason):
        prefix.run_pair(build, path, **authorities)
    assert len(state.calls) == index + 1
    assert (build / f'diagnostic_prefix{index}.exit').read_text() == exit_text
    assert state.sources == ['prefix_initial_source_verify.log']
    assert not (build / 'diagnostic_prefix_pair.json').exists()


@pytest.mark.parametrize('fault', ['eventbits', 'stdout', 'counter', 'memorybits', 'memorysize'])
def test_pair_rejects_different_payload_bits_stdout_or_deterministic_state(harness, fault):
    build, path, authorities, state, _, _ = harness
    state.failure, state.failure_index = fault, 1
    with pytest.raises(ValueError, match='prefixes are not deterministic'):
        prefix.run_pair(build, path, **authorities)
    assert len(state.calls) == 2
    assert all((build / f'diagnostic_prefix{i}.exit').read_text() == '0\n' for i in range(2))
    assert not (build / 'diagnostic_prefix_pair.json').exists()


@pytest.mark.parametrize('kind', ['admission', 'identity'])
@pytest.mark.parametrize('call,executions', [(2, 0), (3, 1), (4, 2)])
def test_pair_rechecks_fixture_and_dut_identity_before_each_run_and_after_pair(harness, kind, call, executions):
    build, path, authorities, state, _, _ = harness
    state.drift_kind, state.drift_call = kind, call
    with pytest.raises(ValueError, match='identity changed'):
        prefix.run_pair(build, path, **authorities)
    assert len(state.calls) == executions
    assert state.sources == ['prefix_initial_source_verify.log']
    assert not (build / 'diagnostic_prefix_pair.json').exists()


@pytest.mark.parametrize('stage,executions', [
    ('prefix_initial_source_verify.log', 0), ('prefix_final_source_verify.log', 2),
])
def test_pair_source_verification_failure_cannot_publish_pass(harness, stage, executions):
    build, path, authorities, state, _, _ = harness
    state.failure = stage
    with pytest.raises(ValueError, match='source closure mismatch'):
        prefix.run_pair(build, path, **authorities)
    assert len(state.calls) == executions
    assert state.sources[-1] == stage
    assert not (build / 'diagnostic_prefix_pair.json').exists()
