"""Source-only runner acceptance inventory cannot be replaced by a PASS label."""
from pathlib import Path
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('matrix_chain_runner', ROOT/'scripts/run_matrix_norm_rope_candidate.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def marker(suite='main'):
    counts = 'successes=4 rejects=0 faults=0 resets=0' if suite == 'main' else 'successes=7 rejects=21 faults=10 resets=7'
    return ('QWEN35_MATRIX_NORM_ROPE_CHAIN_PASS suite='+suite+' '+counts+
            ' actual_matrix_inputs=49152 actual_matrix_outputs=49152 explicit_write_acks=112'
            ' read_stall_cycles=1 write_stall_cycles=1 dma_stall_cycles=1 delayed_ACK_cycles=1'
            ' capacity_bytes=1572864 source_injection=0\n')


@pytest.mark.parametrize('suite',['main','all'])
def test_exact_suite_inventory(suite):
    assert runner.verify_log(marker(suite),suite)['capacity_bytes'] == 1572864


@pytest.mark.parametrize('old,new',[
    ('successes=4','successes=3'),('rejects=0','rejects=1'),('faults=0','faults=1'),
    ('resets=0','resets=1'),('capacity_bytes=1572864','capacity_bytes=2097152'),
    ('source_injection=0','source_injection=1'),('actual_matrix_inputs=49152','actual_matrix_inputs=49151'),
    ('actual_matrix_outputs=49152','actual_matrix_outputs=49151'),
    ('explicit_write_acks=112','explicit_write_acks=0'),('read_stall_cycles=1','read_stall_cycles=0'),
    ('write_stall_cycles=1','write_stall_cycles=0'),('dma_stall_cycles=1','dma_stall_cycles=0'),
    ('delayed_ACK_cycles=1','delayed_ACK_cycles=0')])
def test_missing_coverage_rejected(old,new):
    with pytest.raises(ValueError):runner.verify_log(marker().replace(old,new),'main')


def test_missing_duplicate_wrong_suite_marker_rejected():
    for value in ('',marker()+marker(),marker('all')):
        with pytest.raises(ValueError):runner.verify_log(value,'main')


def test_native_acceptance_and_source_freeze_are_required():
    source = (ROOT/'scripts/run_matrix_norm_rope_candidate.py').read_text()
    assert "require(fixture['native_gate_pass']" in source
    assert 'source changed during verification' in source
    assert 'verify_materialized(fixture_dir,trusted_summary_sha256=fixture_hash)' in source
    assert 'verify_trace(trace,root,suite=suite)' in source


def test_native_threshold_failure_stops_before_emission(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from heteronpu import matrix_norm_rope_candidate as oracle
    monkeypatch.setattr(oracle,'materialize',lambda *args: {'native_gate_pass': False})
    args = SimpleNamespace(output=tmp_path/'run',payload_layer0=tmp_path/'l0',
                           payload_layer3=tmp_path/'l3',payload_extra=tmp_path/'prefix')
    with pytest.raises(ValueError,match='selected-head native numerical thresholds failed'):
        runner.run(args)
    assert not (args.output/'emission.log').exists()
