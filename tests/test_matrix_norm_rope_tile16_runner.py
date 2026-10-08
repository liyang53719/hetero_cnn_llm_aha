"""Source-only, fail-closed acceptance tests for the frozen tile16 RTL runner.

No test emits hardware, invokes Verilator, builds payloads, or runs MATLAB.
The log expectations are independently derived from the frozen packet/byte
geometry rather than copied out of the runner's acceptance implementation.
"""
from copy import deepcopy
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
SPEC = importlib.util.spec_from_file_location(
    'tile16_chain_runner_test', ROOT / 'scripts/run_matrix_norm_rope_tile16_candidate.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
from heteronpu import matrix_norm_rope_tile16_candidate as materializer
from verify_matrix_norm_rope_tile16_trace import REJECTS

PASS = 'QWEN35_MATRIX_NORM_ROPE_TILE16_PASS'
CASE_PASS = 'QWEN35_MATRIX_NORM_ROPE_TILE16_CASE_PASS'
RECEIPT = 'a' * 64
PRIMARY = (
    ('cold_Q', 0, 16, 8, 16),
    ('cold_K', 1, 16, 2, 8),
    ('carried_Q', 2, 16, 8, 16),
    ('carried_K', 3, 16, 2, 8),
)
SUPPLEMENTAL = (
    ('recovery_after_fault_or_reset', 1, 1, 2, 8),
    ('recovery_after_fault_or_reset', 1, 1, 2, 8),
    ('legal_exact_1p5MiB_end', 1, 1, 2, 8),
    ('tail_1', 1, 1, 2, 8),
    ('tail_3', 1, 3, 2, 8),
    ('tail_17', 1, 17, 2, 8),
)


def cases(suite='main'):
    geometry = PRIMARY + (SUPPLEMENTAL if suite == 'all' else ())
    result = []
    for ordinal, (name, command, tokens, heads, tiles) in enumerate(geometry):
        batches = (tokens + 15) // 16
        result.append(dict(
            name=name, command=command, heads=heads * tokens, tokens=tokens,
            matrix_steps=batches * heads * tiles * 1024,
            dma_requests=tokens + 2 * batches * heads * tiles + 2 * heads * tokens,
            cycles=1_000_000 + ordinal * 100_003,
            ddr_read_bytes=2048 * tokens + 65536 * batches * heads * tiles,
            ddr_write_bytes=tokens * heads * (64 * tiles + 1024),
        ))
    return result


def metrics(suite='main'):
    # all additionally exercises a full late K fault, one-head reset, and
    # two-head reset. The admitted count128 fault stops on its first DMA.
    rows = cases(suite)
    packets = sum(row['matrix_steps'] for row in rows)
    acks = sum(row['heads'] * (32 if row['command'] % 2 == 0 else 24)
               for row in rows)
    if suite == 'all':
        packets += 16384 + 8192 + 16384
        acks += 768 + 384 + 768
    return dict(successes=len(rows), rejects=35 if suite == 'all' else 0,
                faults=2 if suite == 'all' else 0, resets=2 if suite == 'all' else 0,
                actual_matrix_inputs=packets, actual_matrix_outputs=packets,
                matrix_lanes_per_output=512, explicit_write_acks=acks,
                read_stall_cycles=1, write_stall_cycles=1, dma_stall_cycles=1,
                delayed_ACK_cycles=1, same_cycle_ACKs=1,
                capacity_bytes=1572864, source_injection=0)


def case_line(row):
    return CASE_PASS + ' ' + ' '.join(
        ('test' if key == 'name' else key) + '=' + str(value)
        for key, value in row.items())


def log_text(suite='main', *, rows=None, totals=None):
    rows = cases(suite) if rows is None else rows
    totals = metrics(suite) if totals is None else totals
    return '\n'.join([*(case_line(row) for row in rows),
                     PASS + ' suite=' + suite + ' ' + ' '.join(
                         str(k) + '=' + str(v) for k, v in totals.items())]) + '\n'


@pytest.mark.parametrize('suite', ['main', 'all'])
def test_accepts_exact_frozen_inventory_and_equations(suite):
    actual_metrics, actual_cases = runner.verify_log(log_text(suite), suite)
    assert actual_metrics == metrics(suite)
    assert actual_cases == cases(suite)
    assert [row['name'] for row in actual_cases[:4]] == [row[0] for row in PRIMARY]
    assert sum(row['matrix_steps'] for row in actual_cases[:4]) == 294912
    assert sum(row['heads'] for row in actual_cases[:4]) == 320


def test_frozen_contract_matches_independent_tile16_geometry():
    frozen = json.loads((ROOT / runner.CONTRACT).read_text())['frozen_gate']
    commands = frozen['commands_per_variant']
    assert frozen['variants'] == ['baseline', 'avx2']
    assert [(row['phase'], row['role'], row['start'], row['count'], row['heads'])
            for row in commands] == [
                ('cold', 'q', 0, 16, 8), ('cold', 'k', 0, 16, 2),
                ('carried', 'q', 112, 16, 8), ('carried', 'k', 112, 16, 2)]
    packets = sum(((row['count'] + 15) // 16) * row['heads'] *
                  (16 if row['role'] == 'q' else 8) * 1024 for row in commands)
    useful = sum(row['count'] * row['heads'] *
                 (16 if row['role'] == 'q' else 8) * 1024 * 32 for row in commands)
    assert packets == frozen['primary_matrix_packets_per_variant'] == 294912
    assert useful == frozen['primary_active_fp32_accumulator_values_per_variant'] == packets * 512
    assert frozen['primary_heads_per_variant'] == 320
    assert frozen['full_M128_rtl_coverage'] is False


@pytest.mark.parametrize('suite', ['main', 'all'])
@pytest.mark.parametrize('mutation', ['missing', 'extra', 'duplicate', 'reordered', 'renamed'])
def test_rejects_missing_extra_duplicate_reordered_or_renamed_cases(suite, mutation):
    rows = cases(suite)
    if mutation == 'missing':
        rows.pop()
    elif mutation == 'extra':
        rows.append(deepcopy(rows[0]))
    elif mutation == 'duplicate':
        rows[-1] = deepcopy(rows[0])
    elif mutation == 'reordered':
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[-1]['name'] = 'unfrozen_case'
    with pytest.raises(ValueError):
        runner.verify_log(log_text(suite, rows=rows), suite)


@pytest.mark.parametrize('suite', ['main', 'all'])
@pytest.mark.parametrize('field', [
    'command', 'heads', 'tokens', 'matrix_steps', 'dma_requests',
    'ddr_read_bytes', 'ddr_write_bytes'])
def test_rejects_case_geometry_packet_dma_or_byte_drift(suite, field):
    rows = cases(suite)
    rows[-1][field] += 1
    with pytest.raises(ValueError):
        runner.verify_log(log_text(suite, rows=rows), suite)


@pytest.mark.parametrize('field', ['command', 'heads', 'tokens', 'matrix_steps',
                                 'dma_requests', 'cycles', 'ddr_read_bytes', 'ddr_write_bytes'])
def test_rejects_missing_case_counter(field):
    rows = cases()
    rows[0].pop(field)
    with pytest.raises(ValueError):
        runner.verify_log(log_text(rows=rows), 'main')


@pytest.mark.parametrize('value', [0, -1, 'nan', '1000000junk', '1000000.5', '1000000e2'])
def test_rejects_invalid_cycle_counter(value):
    rows = cases()
    rows[0]['cycles'] = value
    with pytest.raises(ValueError):
        runner.verify_log(log_text(rows=rows), 'main')


@pytest.mark.parametrize('suite', ['main', 'all'])
@pytest.mark.parametrize('field', list(metrics()))
@pytest.mark.parametrize('mutation', ['missing', 'wrong'])
def test_rejects_missing_or_wrong_coverage_metric(suite, field, mutation):
    totals = metrics(suite)
    if mutation == 'missing':
        totals.pop(field)
    elif field.endswith('_cycles') or field == 'same_cycle_ACKs':
        totals[field] = 0
    else:
        totals[field] += 1
    with pytest.raises(ValueError):
        runner.verify_log(log_text(suite, totals=totals), suite)


@pytest.mark.parametrize('change', [
    lambda text: text.replace('successes=4', 'successes=4junk'),
    lambda text: text.replace('successes=4', 'successes=4.5'),
    lambda text: text.replace('successes=4', 'successes=4e2'),
    lambda text: text.replace('source_injection=0', 'source_injection=0junk'),
    lambda text: text.replace('matrix_steps=131072', 'matrix_steps=131072junk', 1),
    lambda text: text.replace('test=cold_Q', 'test=wrong test=cold_Q', 1),
    lambda text: text.replace('cycles=1000000', 'cycles=0 cycles=1000000', 1),
    lambda text: text.replace('successes=4', 'successes=3 successes=4'),
    lambda text: text.replace('suite=main', 'suite=main suite=all'),
    lambda text: text.replace('suite=main', 'suite=main-extra'),
])
def test_rejects_ambiguous_duplicate_or_partially_parsed_fields(change):
    with pytest.raises(ValueError):
        runner.verify_log(change(log_text()), 'main')


@pytest.mark.parametrize('text,suite', [
    ('', 'main'),
    (log_text() + log_text(), 'main'),
    (log_text('all'), 'main'),
    (log_text(), 'all'),
    *[(log_text().replace('suite=main', 'suite=' + suite), suite)
      for suite in ('negative', 'fault', 'reset', 'tail', 'boundary', 'unknown', '')],
])
def test_rejects_missing_duplicate_wrong_or_incomplete_acceptance_suite(text, suite):
    with pytest.raises(ValueError):
        runner.verify_log(text, suite)


@pytest.mark.parametrize('target,field', [('aggregate', 'unexpected_counter'), ('case', 'unexpected_counter')])
def test_rejects_unrecognized_log_field_inventory(target, field):
    if target == 'aggregate':
        totals = metrics()
        totals[field] = 1
        text = log_text(totals=totals)
    else:
        rows = cases()
        rows[0][field] = 1
        text = log_text(rows=rows)
    with pytest.raises(ValueError):
        runner.verify_log(text, 'main')


@pytest.mark.parametrize('mutation', ['missing_test', 'missing_suite', 'empty_name', 'field_without_equals',
                                     'too_many_equals', 'plus_sign', 'leading_zero', 'negative_zero'])
def test_rejects_missing_identity_and_noncanonical_counts(mutation):
    text = log_text()
    replacements = {
        'missing_test': ('test=cold_Q ', ''),
        'missing_suite': ('suite=main ', ''),
        'empty_name': ('test=cold_Q', 'test='),
        'field_without_equals': ('cycles=1000000', 'cycles'),
        'too_many_equals': ('cycles=1000000', 'cycles==1000000'),
        'plus_sign': ('cycles=1000000', 'cycles=+1000000'),
        'leading_zero': ('cycles=1000000', 'cycles=01000000'),
        'negative_zero': ('source_injection=0', 'source_injection=-0'),
    }
    old, new = replacements[mutation]
    with pytest.raises(ValueError):
        runner.verify_log(text.replace(old, new, 1), 'main')


def trace_report(suite):
    totals = metrics(suite)
    successful = []
    for row in cases(suite):
        command = row['command']
        successful.append(dict(
            kind=('main' if row['name'] in [item[0] for item in PRIMARY] or row['name'].startswith('tail_')
                  else 'boundary' if row['name'] == 'legal_exact_1p5MiB_end' else 'recovery'),
            name=row['name'], case=(0, 8, 160, 168)[command], status=0,
            accepted_to_done_cycles=row['cycles'], matrix_packets=row['matrix_steps'],
            completed_heads=row['heads'], completed_tokens=row['tokens'],
            ddr_read_bytes=row['ddr_read_bytes'], ddr_write_bytes=row['ddr_write_bytes'],
            fixed_matrix_lanes=512, whole_block_metric=False,
        ))
    terminals = successful[:4]
    if suite == 'all':
        terminals += [dict(kind='reject', name=name, case=8, status=status, matrix_packets=0)
                      for name, status in REJECTS.items()]
        terminals += [dict(kind='fault', name='last_row_last_head_DMA_error', case=8, status=6, matrix_packets=16384),
                      dict(kind='fault', name='token_count128_admitted', case=8, status=6, matrix_packets=0),
                      successful[4],
                      dict(kind='reset', name='reset_late_row', case=8, status=None, matrix_packets=8192),
                      dict(kind='reset', name='reset_late_head', case=8, status=None, matrix_packets=16384),
                      *successful[5:]]
    return dict(suite=suite, terminals=terminals, transactions=len(terminals), primary_commands=4,
                events=dict(matrix=totals['actual_matrix_inputs'], l2_ack=totals['explicit_write_acks']),
                bitexact_matrix_packets=totals['actual_matrix_inputs'],
                matrix_lanes_checked_per_packet=512, missing_extra_reordered_oracle_values=0,
                actual_done_before_ack_checked=True, raw_fabric_ddr_store_data_checked=True,
                cumulative_arithmetic_flags_checked=True, fabric_guard_readback_in_trace=False,
                whole_block_MAC90_claimed=False)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Mock only expensive/external boundaries, retaining real log acceptance."""
    monkeypatch.setenv('VERILATOR_BIN', '/inherited/incorrect-verilator')
    args = SimpleNamespace(output=tmp_path / 'result', generated=tmp_path / 'generated',
                           verilator=None, jobs=1, payload_layer0=tmp_path / 'layer0',
                           payload_layer3=tmp_path / 'layer3', payload_extra=tmp_path / 'extra')
    args.output.mkdir()
    fixture = dict(summary_sha256=RECEIPT, native_gate_pass=True,
                   native_full_block_gate_pass={'baseline': False, 'avx2': False})
    h = SimpleNamespace(args=args, fixture=fixture, receipt_calls=[], emission_calls=[],
                        manifest_calls=[], build_calls=[], simulation_calls=[], trace_calls=[],
                        materialize_calls=[], reports={}, logs={}, source_calls=[],
                        source_values=[{'source.py': 'before'}],
                        receipt_failure=None, manifest_failure=None,
                        trace_failure=None, simulation_failure=None)

    def sources():
        index = min(len(h.source_calls), len(h.source_values) - 1)
        h.source_calls.append(index)
        return deepcopy(h.source_values[index])

    def materialize(*args):
        h.materialize_calls.append(args)
        return deepcopy(h.fixture)

    def receipt(path, *, trusted_summary_sha256):
        h.receipt_calls.append((path, trusted_summary_sha256))
        assert trusted_summary_sha256 == RECEIPT
        if h.receipt_failure == len(h.receipt_calls):
            raise ValueError('fixture/source receipt mismatch')
        return {key: deepcopy(value) for key, value in h.fixture.items() if key != 'summary_sha256'}

    def emission(command, path, **kwargs):
        h.emission_calls.append((command, path, kwargs))
        args.generated.mkdir(exist_ok=True)
        (args.generated / 'manifest.json').write_text(json.dumps(
            {'emitted_sha256': {'hardware.sv': 'hardware-hash'},
             'tool_versions': {'verilator': 'pinned-version'}}))
        path.write_text('mock emission\n')

    def manifest(command, **kwargs):
        h.manifest_calls.append((command, kwargs))
        if h.manifest_failure == len(h.manifest_calls):
            raise subprocess.CalledProcessError(3, command)

    def build(*args):
        h.build_calls.append(args)
        return tmp_path / 'fake-tb', ['verilator', '--binary', 'tile16']

    def simulation(binary, root, suite, log, trace):
        h.simulation_calls.append((binary, root, suite, log, trace))
        if h.simulation_failure == len(h.simulation_calls):
            raise ValueError('simulator failed')
        log.write_text(h.logs.get(suite, log_text(suite)))
        trace.write_bytes(gzip.compress(b'mocked full trace\n'))

    def verify(trace, root, *, suite):
        h.trace_calls.append((trace, root, suite))
        if h.trace_failure == len(h.trace_calls):
            raise ValueError('independent trace rejected')
        return deepcopy(h.reports.get(suite, trace_report(suite)))

    monkeypatch.setattr(runner, 'source_hashes', sources)
    monkeypatch.setattr(materializer, 'materialize', materialize)
    monkeypatch.setattr(materializer, 'verify_materialized', receipt)
    monkeypatch.setattr(runner.legacy, 'run_logged', emission)
    monkeypatch.setattr(runner.subprocess, 'run', manifest)
    monkeypatch.setattr(runner, 'build', build)
    monkeypatch.setattr(runner, 'run_compressed', simulation)
    monkeypatch.setattr(runner, 'verify_trace', verify)
    h.prepared = lambda fixture=None: runner.run_prepared(
        args, h.fixture if fixture is None else fixture, trusted_summary_sha256=RECEIPT)
    return h


@pytest.mark.parametrize('override', [None, 'custom-verilator'])
def test_prepared_binds_receipt_sources_variants_manifest_and_emission_environment(harness, override):
    h = harness
    h.args.verilator = h.args.output.parent / override if override else None
    result = h.prepared()
    assert result['status'] == 'PASS_Q8_K2_TOKEN_TILE16_RTL'
    assert h.receipt_calls == [(h.args.output / 'vectors', RECEIPT)] * 2
    assert len(h.source_calls) == 2
    assert len(h.emission_calls) == 1 and len(h.manifest_calls) == 2
    env = h.emission_calls[0][2]['env']
    assert env['OUT'] == str(h.args.generated) and env['PYTHON_BIN'] == sys.executable
    assert env.get('VERILATOR_BIN') == (str(h.args.verilator) if override else None)
    for command, kwargs in h.manifest_calls:
        assert command == [sys.executable, str(ROOT / 'chisel/matrix_norm_rope_hardware/manifest.py'),
                           'verify', str(ROOT), str(h.args.generated)]
        assert kwargs == dict(check=True, timeout=90, env=env)
    assert h.build_calls[0][0] == (h.args.verilator or ROOT / 'work/rope_hardware_oracle/bin/verilator')
    assert [(call[1], call[2]) for call in h.simulation_calls] == [
        (h.args.output / 'vectors', 'all'), (h.args.output / 'vectors' / 'avx2', 'main')]
    assert [(call[1], call[2]) for call in h.trace_calls] == [
        (h.args.output / 'vectors', 'all'), (h.args.output / 'vectors' / 'avx2', 'main')]
    assert result['fixture_summary_sha256'] == RECEIPT
    assert result['source_sha256'] == {'source.py': 'before'}
    assert result['hardware_manifest_sha256'] == runner.sha256(h.args.generated / 'manifest.json')
    assert result['generated_rtl_sha256'] == {'hardware.sv': 'hardware-hash'}
    assert result['tool_versions'] == {'verilator': 'pinned-version'}
    assert result['primary_tokens_per_source'] == 32
    assert result['primary_heads_per_source'] == 320
    assert result['actual_Matrix16x32_rows_verified'] is True
    for key in ('all_M128_tokens_rtl_verified', 'production_policy_changed',
                'matrix_producer_injected', 'generic_Command128_complete',
                'full_block_numerical_complete', 'PPA_measured',
                'whole_block_MAC90_measured', 'U00_2_complete', 'U01_complete'):
        assert result[key] is False
    assert [(row['source'], row['suite']) for row in result['rtl_suites']] == [('baseline', 'all'), ('avx2', 'main')]
    for row, call in zip(result['rtl_suites'], h.simulation_calls):
        assert row['trace_sha256'] == runner.sha256(call[4])
        assert row['log_sha256'] == runner.sha256(call[3])
        assert row['command_counters'] == cases(row['suite'])
    assert json.loads((h.args.output / 'summary.json').read_text()) == result


def test_native_failure_preserved_after_both_rtl_suites_and_is_cli_failure(harness):
    h = harness
    h.fixture['native_gate_pass'] = False
    result = h.prepared()
    assert len(h.simulation_calls) == len(h.trace_calls) == 2
    assert result['status'] == 'REJECTED_NATIVE_SOURCE_THRESHOLD_TILE16_RTL_MATCHED'
    assert result['native_selected_tile16_gate_pass'] is False
    assert result['native_full_block_gate_pass'] == {'baseline': False, 'avx2': False}
    assert json.loads((h.args.output / 'summary.json').read_text())['native_selected_tile16_gate_pass'] is False
    source = (ROOT / 'scripts/run_matrix_norm_rope_tile16_candidate.py').read_text()
    assert "raise SystemExit(0 if result['native_selected_tile16_gate_pass'] else 3)" in source


def test_prepared_rejects_fixture_object_receipt_disagreement_before_emission(harness):
    forged = {**harness.fixture, 'native_gate_pass': False}
    with pytest.raises(ValueError):
        harness.prepared(forged)
    assert harness.emission_calls == harness.build_calls == harness.simulation_calls == []
    assert not (harness.args.output / 'summary.json').exists()


@pytest.mark.parametrize('boundary', [1, 2])
def test_prepared_rechecks_materialized_sources_and_receipt_before_publishing(harness, boundary):
    harness.receipt_failure = boundary
    with pytest.raises(ValueError, match='receipt'):
        harness.prepared()
    assert len(harness.simulation_calls) == (0 if boundary == 1 else 2)
    assert not (harness.args.output / 'summary.json').exists()


@pytest.mark.parametrize('boundary', [1, 2])
def test_prepared_manifest_failure_is_fatal_without_summary(harness, boundary):
    harness.manifest_failure = boundary
    with pytest.raises(subprocess.CalledProcessError):
        harness.prepared()
    assert len(harness.simulation_calls) == (0 if boundary == 1 else 2)
    assert not (harness.args.output / 'summary.json').exists()


@pytest.mark.parametrize('kind', ['simulation_failure', 'trace_failure'])
@pytest.mark.parametrize('boundary', [1, 2])
def test_any_variant_simulator_or_independent_trace_failure_prevents_publication(harness, kind, boundary):
    setattr(harness, kind, boundary)
    with pytest.raises(ValueError):
        harness.prepared()
    assert len(harness.simulation_calls) == boundary
    assert not (harness.args.output / 'summary.json').exists()


def test_prepared_detects_source_drift_after_hardware_run(harness):
    harness.source_values = [{'source.py': 'before'}, {'source.py': 'after'}]
    with pytest.raises(ValueError, match='source changed'):
        harness.prepared()
    assert len(harness.trace_calls) == 2
    assert not (harness.args.output / 'summary.json').exists()


@pytest.mark.parametrize('suite', ['main', 'all'])
@pytest.mark.parametrize('field', ['accepted_to_done_cycles', 'matrix_packets',
                                 'ddr_read_bytes', 'ddr_write_bytes'])
def test_prepared_binds_each_command_counter_to_independent_trace(harness, suite, field):
    report = trace_report(suite)
    report['terminals'][0][field] += 1
    harness.reports[suite] = report
    with pytest.raises(ValueError):
        harness.prepared()
    assert not (harness.args.output / 'summary.json').exists()


@pytest.mark.parametrize('mutation', ['drop', 'extra', 'reorder', 'status', 'heads', 'tokens', 'recovery_reuse'])
def test_prepared_success_terminals_are_bound_one_to_one_in_order(harness, mutation):
    report = trace_report('all')
    terminals = report['terminals']
    if mutation == 'drop':
        terminals.pop(0)
    elif mutation == 'extra':
        terminals.insert(0, deepcopy(terminals[0]))
    elif mutation == 'reorder':
        terminals[0], terminals[1] = terminals[1], terminals[0]
    elif mutation == 'status':
        terminals[0]['status'] = 6
    elif mutation == 'heads':
        terminals[0]['completed_heads'] -= 1
    elif mutation == 'tokens':
        terminals[0]['completed_tokens'] -= 1
    else:
        recoveries = [terminal for terminal in terminals if terminal['name'] == 'recovery_after_fault_or_reset']
        assert len(recoveries) == 2
        # Name-based any() may reuse recovery one for both case lines. Change
        # both log cycle values to recovery one's while trace two differs.
        rows = cases('all')
        rows[5]['cycles'] = rows[4]['cycles']
        harness.logs['all'] = log_text('all', rows=rows)
    harness.reports['all'] = report
    with pytest.raises(ValueError):
        harness.prepared()
    assert not (harness.args.output / 'summary.json').exists()


@pytest.mark.parametrize('suite', ['main', 'all'])
@pytest.mark.parametrize('field', ['matrix', 'l2_ack'])
def test_prepared_aggregate_matrix_and_ack_claims_bind_to_events(harness, suite, field):
    report = trace_report(suite)
    report['events'][field] -= 1
    if field == 'matrix':
        report['bitexact_matrix_packets'] -= 1
    harness.reports[suite] = report
    with pytest.raises(ValueError):
        harness.prepared()
    assert not (harness.args.output / 'summary.json').exists()


def test_public_run_materializes_fresh_and_passes_the_in_process_receipt(harness):
    result = runner.run(harness.args)
    assert harness.materialize_calls == [(ROOT, harness.args.payload_layer0,
                                         harness.args.payload_layer3, harness.args.payload_extra,
                                         harness.args.output / 'vectors')]
    assert len(harness.source_calls) == 4
    assert harness.receipt_calls == [(harness.args.output / 'vectors', RECEIPT)] * 2
    assert result['native_selected_tile16_gate_pass'] is True


def test_public_run_rejects_nonempty_output_before_materialization(harness):
    (harness.args.output / 'old-result').write_text('stale')
    with pytest.raises(ValueError, match='new/empty'):
        runner.run(harness.args)
    assert harness.materialize_calls == harness.emission_calls == []


def test_public_run_rejects_source_drift_during_materialization(harness):
    harness.source_values = [{'source.py': 'before'}, {'source.py': 'after'}]
    with pytest.raises(ValueError, match='source changed during fresh materialization'):
        runner.run(harness.args)
    assert len(harness.materialize_calls) == 1
    assert harness.receipt_calls == harness.emission_calls == []


def test_source_hashes_cover_rtl_emitter_contract_oracles_and_materializers(monkeypatch):
    paths = []

    def digest(path):
        paths.append(path)
        return str(path.relative_to(ROOT))

    monkeypatch.setattr(runner, 'sha256', digest)
    actual = runner.source_hashes()
    expected = set(runner.RTL_SOURCES + runner.legacy.EMISSION_SOURCES +
                   runner.EXTRA_SOURCES + tuple(materializer.MATERIALIZER_SOURCES))
    assert set(actual) == expected
    assert paths == [ROOT / name for name in sorted(expected)]
    assert runner.CONTRACT in actual
    for name in ('scripts/run_matrix_norm_rope_tile16_candidate.py',
                 'scripts/verify_matrix_norm_rope_tile16_trace.py',
                 'scripts/verify_matrix_norm_rope_tensor_trace.py',
                 'src/heteronpu/matrix_norm_rope_tile16_candidate.py',
                 'tb/tb_qwen35_matrix_norm_rope_tile16.sv'):
        assert name in actual
    assert len([name for name in actual if name.startswith('tb/')]) == 1


def test_build_uses_existing_hardware_plus_tile16_testbench(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(runner.legacy, 'run_logged', lambda *args, **kwargs: calls.append((args, kwargs)))
    binary, command = runner.build(tmp_path / 'verilator', tmp_path / 'generated', tmp_path, 2)
    assert binary == tmp_path / 'obj_tile16' / 'tb'
    assert command[0] == str(tmp_path / 'verilator')
    assert command[command.index('-j') + 1] == '2'
    assert command[command.index('--top-module') + 1] == 'tb_qwen35_matrix_norm_rope_tile16'
    assert str(tmp_path / 'generated/HeteroMatrixNormRoPEHardwarePrimitives.sv') in command
    assert command[-len(runner.RTL_SOURCES):] == [str(ROOT / path) for path in runner.RTL_SOURCES]
    assert calls[0][0][1] == tmp_path / 'build.log'
    assert calls[0][1] == {'timeout': 3600}


class FakeProcess:
    def __init__(self, *, wait_code=0, wait_error=None, communication_error=None,
                 communication_code=0, stderr=b''):
        self.wait_code = wait_code
        self.wait_error = wait_error
        self.communication_error = communication_error
        self.communication_code = communication_code
        self.stderr = stderr
        self.returncode = None
        self.killed = False
        self.wait_timeouts = []

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self.wait_error is not None and not self.killed:
            raise self.wait_error
        self.returncode = -9 if self.killed else self.wait_code
        return self.returncode

    def communicate(self, timeout=None):
        if self.communication_error is not None:
            raise self.communication_error
        self.returncode = self.communication_code
        return b'', self.stderr

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True


@pytest.mark.parametrize('failure', [None, 'writer_exit', 'writer_timeout', 'writer_launch',
                                     'compressor_exit', 'compressor_timeout', 'gzip_crc', 'gzip_truncated'])
def test_compressed_trace_propagates_failures_and_cleans_fifo_and_children(tmp_path, monkeypatch, failure):
    writer = FakeProcess(wait_code=2 if failure == 'writer_exit' else 0,
                         wait_error=subprocess.TimeoutExpired('tb', 7) if failure == 'writer_timeout' else None)
    compressor = FakeProcess(
        communication_code=2 if failure == 'compressor_exit' else 0,
        communication_error=subprocess.TimeoutExpired('gzip', 120) if failure == 'compressor_timeout' else None,
        stderr=b'compressor error')
    calls = []
    trace, log = tmp_path / 'events.jsonl.gz', tmp_path / 'run.log'
    fifo = trace.with_suffix('.fifo')

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        assert fifo.is_fifo()
        if len(calls) == 1:
            payload = gzip.compress(b'event\n')
            if failure == 'gzip_crc':
                # Corrupt only the trailer CRC, leaving the payload readable.
                payload = payload[:-8] + bytes([payload[-8] ^ 1]) + payload[-7:]
            elif failure == 'gzip_truncated':
                payload = payload[:-4]
            kwargs['stdout'].write(payload)
            return compressor
        if failure == 'writer_launch':
            raise OSError('cannot launch simulator')
        return writer

    monkeypatch.setattr(runner.subprocess, 'Popen', popen)
    if failure:
        with pytest.raises((ValueError, OSError, EOFError, subprocess.SubprocessError)):
            runner.run_compressed(tmp_path / 'tb', tmp_path / 'vectors', 'main', log, trace, timeout=7)
    else:
        runner.run_compressed(tmp_path / 'tb', tmp_path / 'vectors', 'main', log, trace, timeout=7)
        assert gzip.decompress(trace.read_bytes()) == b'event\n'
    assert not fifo.exists()
    assert compressor.poll() is not None
    if failure != 'writer_launch':
        assert writer.poll() is not None
    assert calls[0][0][:2] == ['bash', '-c']
    assert calls[1][0] == [str(tmp_path / 'tb'), '+vectors=' + str(tmp_path / 'vectors'),
                           '+suite=main', '+trace=' + str(fifo)]
    assert calls[1][1]['cwd'] == ROOT
    if failure in ('writer_exit', 'writer_timeout', 'writer_launch', 'compressor_timeout'):
        assert compressor.killed
    if failure == 'writer_timeout':
        assert writer.killed and writer.wait_timeouts == [7, 30]


def test_compressed_trace_never_overwrites_preexisting_fifo_path(tmp_path, monkeypatch):
    trace = tmp_path / 'events.jsonl.gz'
    fifo = trace.with_suffix('.fifo')
    fifo.write_text('owned by another run')
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('must not launch'))
    with pytest.raises(ValueError, match='already exists'):
        runner.run_compressed(tmp_path / 'tb', tmp_path, 'main', tmp_path / 'run.log', trace)
    assert fifo.read_text() == 'owned by another run'
