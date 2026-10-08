"""The tensor gate requires all frozen commands, not merely a PASS label."""
from pathlib import Path
import importlib.util
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('tensor_chain_runner', ROOT / 'scripts/run_matrix_norm_rope_tensor_candidate.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def marker(suite='main'):
    counts = 'successes=4 rejects=0 faults=0 resets=0' if suite == 'main' else 'successes=7 rejects=30 faults=2 resets=2'
    return ('QWEN35_MATRIX_NORM_ROPE_TENSOR_PASS suite=' + suite + ' ' + counts +
            ' actual_matrix_inputs=589824 actual_matrix_outputs=589824 explicit_write_acks=1216' +
            ' read_stall_cycles=1 write_stall_cycles=1 dma_stall_cycles=1 delayed_ACK_cycles=1' +
            ' same_cycle_ACKs=1 capacity_bytes=1572864 source_injection=0\n')


@pytest.mark.parametrize('suite', ['main', 'all'])
def test_exact_inventory(suite):
    assert runner.verify_log(marker(suite), suite)['capacity_bytes'] == 1572864


@pytest.mark.parametrize('old,new', [
    ('successes=4', 'successes=3'), ('rejects=0', 'rejects=1'),
    ('faults=0', 'faults=1'), ('resets=0', 'resets=1'),
    ('capacity_bytes=1572864', 'capacity_bytes=2097152'),
    ('source_injection=0', 'source_injection=1'),
    ('actual_matrix_inputs=589824', 'actual_matrix_inputs=589823'),
    ('actual_matrix_outputs=589824', 'actual_matrix_outputs=589825'),
    ('explicit_write_acks=1216', 'explicit_write_acks=0'),
    ('read_stall_cycles=1', 'read_stall_cycles=0'),
    ('write_stall_cycles=1', 'write_stall_cycles=0'),
    ('dma_stall_cycles=1', 'dma_stall_cycles=0'),
    ('delayed_ACK_cycles=1', 'delayed_ACK_cycles=0'),
    ('same_cycle_ACKs=1', 'same_cycle_ACKs=0')])
def test_missing_coverage_rejected(old, new):
    with pytest.raises(ValueError):
        runner.verify_log(marker().replace(old, new), 'main')


@pytest.mark.parametrize('text', ['', marker() + marker(), marker('all')])
def test_missing_duplicate_wrong_suite_rejected(text):
    with pytest.raises(ValueError):
        runner.verify_log(text, 'main')


def test_contract_matches_expected_hardware_steps():
    import json
    contract = json.loads((ROOT / runner.CONTRACT).read_text())
    frozen = contract['frozen_gate']
    steps = sum(c['count'] * c['heads'] * (16 if c['role'] == 'q' else 8) * 1024
                for c in frozen['commands_per_variant'])
    assert steps == frozen['primary_matrix_steps_per_variant'] == 589824
    assert steps * 32 == frozen['primary_fp32_accumulator_values_per_variant']
    assert not frozen['full_M128_rtl_coverage']


def test_native_failures_are_saved_separately_and_fail_exit():
    source = (ROOT / 'scripts/run_matrix_norm_rope_tensor_candidate.py').read_text()
    assert "'REJECTED_NATIVE_SOURCE_THRESHOLD_RTL_MATCHED'" in source
    assert 'raise SystemExit(0 if result[\'native_all_head_selected_tokens_gate_pass\'] else 3)' in source
    assert 'require(fixture[\'native_gate_pass\']' not in source
    assert 'verify_materialized(fixture_dir, trusted_summary_sha256=fixture_hash)' in source
    assert 'source changed during tensor verification' in source
    assert 'verify_trace(trace, root, suite=suite)' in source


def test_streaming_hash_reads_complete_file(tmp_path):
    import hashlib
    path = tmp_path / 'trace'
    data = b'a' * (1024 * 1024 + 7)
    path.write_bytes(data)
    assert runner.sha256(path) == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('override', [None, 'custom-verilator'])
def test_hardware_manifest_verification_uses_emission_tool_environment(tmp_path, monkeypatch, override):
    """Both manifest checks must verify the tool selected for this emission."""
    import json
    from types import SimpleNamespace
    from heteronpu import matrix_norm_rope_tensor_candidate as tensor
    import verify_matrix_norm_rope_tensor_trace as trace

    monkeypatch.setenv('VERILATOR_BIN', '/inherited/different-verilator')
    selected = tmp_path / override if override else None
    args = SimpleNamespace(output=tmp_path / 'result', generated=tmp_path / 'generated',
                           verilator=selected, jobs=1, payload_layer0=None,
                           payload_layer3=None, payload_extra=None)
    fixture = {'summary_sha256': 'test-digest', 'native_gate_pass': True,
               'native_full_block_gate_pass': {'baseline': False, 'avx2': False}}
    monkeypatch.setattr(tensor, 'materialize', lambda *args: fixture)
    monkeypatch.setattr(tensor, 'verify_materialized', lambda *args, **kwargs: fixture)
    monkeypatch.setattr(runner, 'sha256', lambda path: 'test-digest')
    monkeypatch.setattr(runner, 'build', lambda *args: (tmp_path / 'fake-tb', []))
    monkeypatch.setattr(trace, 'verify_trace', lambda *args, **kwargs: {})
    emission_environments, verification_environments = [], []

    def logged(command, path, **kwargs):
        if path.name == 'emission.log':
            emission_environments.append(kwargs['env'])
            args.generated.mkdir()
            (args.generated / 'manifest.json').write_text(json.dumps(
                {'emitted_sha256': {}, 'tool_versions': {}}))
            path.write_text('emitted\n')
        else:
            suite = next(str(arg).split('=', 1)[1] for arg in command if str(arg).startswith('+suite='))
            path.write_text(marker(suite))

    def verify(command, **kwargs):
        assert command[1].endswith('/chisel/matrix_norm_rope_hardware/manifest.py')
        verification_environments.append(kwargs.get('env'))

    monkeypatch.setattr(runner.legacy, 'run_logged', logged)
    monkeypatch.setattr(runner.subprocess, 'run', verify)
    result = runner.run(args)
    assert result['status'] == 'PASS_Q8_K2_TOKEN_WINDOW_OWNER_RTL'
    assert len(emission_environments) == 1 and len(verification_environments) == 2
    assert all(env == emission_environments[0] for env in verification_environments)
    assert emission_environments[0].get('VERILATOR_BIN') == (str(selected) if selected else None)
