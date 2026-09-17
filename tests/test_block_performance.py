from fractions import Fraction
from pathlib import Path
import subprocess
import sys

import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.block_performance import audit


def original():
    return (ROOT / 'tests/fixtures/coalesced_real2_terminal_summary.txt').read_text()


def test_exact_archive_metrics_and_separate_efficiency():
    result = audit(original())
    assert result['metrics']['useful_wall_mac_utilization'] == pytest.approx(0.021982131089758324)
    assert result['metrics']['useful_fraction_of_executed'] == pytest.approx(0.9830043859649122)
    assert result['derived_work'] == {'dense_macs': 1497366528, 'causal_attention_macs': 835584}
    assert result['bounds']['read_min_cycles'] == 3093464
    assert result['bounds']['useful_wall_upper_bound'] == pytest.approx(0.11824026398884875)
    assert not result['bounds']['target_feasible_with_unchanged_traffic']
    assert result['scope']['full_model_tokens_per_second'] is None
    assert not result['scope']['new_rtl_run']
    assert audit(original(), target=Fraction(1, 10))['bounds']['target_feasible_with_unchanged_traffic']


@pytest.mark.parametrize('old,new', [
    ('tokens=16', 'tokens=0'), ('hidden=1536', 'hidden=2048'), ('layers=2', 'layers=4'),
    ('completed=42', 'completed=41'), ('owner_jobs=38', 'owner_jobs=42'),
    ('matrix_commands=18', 'matrix_commands=17'), ('sfu_commands=22', 'sfu_commands=21'),
    ('kv_commands=2', 'kv_commands=1'), ('checked_fp32=1409024', 'checked_fp32=100'),
    ('bit_differences=0', 'bit_differences=1'), ('useful_macs=1498202112', 'useful_macs=1498202111'),
    ('executed_macs=1524105216', 'executed_macs=1'), ('cycles=16639515', 'cycles=1000000'),
    ('cycles=16639515', 'cycles=0'), ('read_bytes=197981696', 'read_bytes=197981695'),
    ('write_ack_bytes=5636096', 'write_ack_bytes=0'), ('write_ack_bytes=5636096', 'write_ack_bytes=64'),
    ('host_intermediate_writes=0', 'host_intermediate_writes=1'),
    ('legacy_block_launch=0', 'legacy_block_launch=1'), ('score_ddr_accesses=0', 'score_ddr_accesses=1'),
    ('original_matrix_instances=8', 'original_matrix_instances=1'), ('matrix_macs=4096', 'matrix_macs=512'),
    ('original_idma_instances=1', 'original_idma_instances=2'),
    ('logical_matrix_engines=1', 'logical_matrix_engines=2'),
    ('cycles=16639515', 'cycles=1.5'), ('cycles=16639515', 'cycles=-1'),
    ('cycles=16639515', 'cycles=18446744073709551616'),
    ('cycles=16639515', 'cycles=16639515 cycles=100'), ('cycles=16639515', '')])
def test_reject_incomplete_or_impossible_log(old, new):
    with pytest.raises(ValueError): audit(original().replace(old, new))


@pytest.mark.parametrize('text', ['', 'HOST_BLOCK_ALL_OWNERS_PASS', '%Error stale PASS\n', 'HOST_BLOCK_FAIL\n'])
def test_reject_failure_or_missing_marker(text):
    with pytest.raises(ValueError): audit(text if not 'FAIL' in text and not '%Error' in text else original() + text)


def test_duplicate_summary_rejected():
    with pytest.raises(ValueError): audit(original() + original())


@pytest.mark.parametrize('clock,beat,target', [(True, 64, Fraction(1, 2)), (0, 64, Fraction(1, 2)),
    (800000000, 128, Fraction(1, 2)), (800000000, 64, Fraction(0)), (800000000, 64, Fraction(2))])
def test_reject_invalid_assumptions(clock, beat, target):
    with pytest.raises(ValueError): audit(original(), clock, beat, target)


def test_cli_no_overwrite(tmp_path):
    output = tmp_path / 'result.json'; output.write_text('preserve me')
    r = subprocess.run([sys.executable, str(ROOT / 'scripts/audit_block_performance.py'),
                        str(ROOT / 'tests/fixtures/coalesced_real2_terminal_summary.txt'), '--output', str(output)],
                       capture_output=True, text=True)
    assert r.returncode == 2 and output.read_text() == 'preserve me'


def test_output_is_stable_across_hash_seeds():
    import os
    command = [sys.executable, str(ROOT / 'scripts/audit_block_performance.py'),
               str(ROOT / 'tests/fixtures/coalesced_real2_terminal_summary.txt')]
    out = [subprocess.run(command, env={**os.environ, 'PYTHONHASHSEED': seed},
                          capture_output=True, text=True, check=True).stdout for seed in ('1', '2')]
    assert out[0] == out[1]
