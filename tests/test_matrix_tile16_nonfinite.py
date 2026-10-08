"""The real multirow payload rejects a nonfinite active tile before any write."""
from pathlib import Path
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tile16_nonfinite_runner', ROOT / 'scripts/run_matrix_tile16_nonfinite.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def marker():
    return ('MATRIX_TILE16_NONFINITE_MODE_PASS candidate=1 cases=32 rejections=18 resets=2 write_stalls=8\n'
            'MATRIX_TILE16_NONFINITE_MODE_PASS candidate=0 cases=31 rejections=0 resets=1 write_stalls=7\n'
            'MATRIX_TILE16_NONFINITE_PASS actual_payload=1 actual_converter=1 matrix_arithmetic_claimed=0\n')


def test_complete_exact_inventory():
    assert runner.verify_log(marker())[1] == dict(cases=32, rejections=18, resets=2, write_stalls=8)


@pytest.mark.parametrize('old,new', [
    ('cases=32', 'cases=31'), ('rejections=18', 'rejections=17'),
    ('resets=2', 'resets=1'), ('cases=31', 'cases=32'),
    ('rejections=0', 'rejections=1'), ('resets=1', 'resets=0'),
    ('write_stalls=8', 'write_stalls=0'), ('write_stalls=7', 'write_stalls=0'),
    ('candidate=0', 'candidate=1'), ('candidate=0', 'candidate=2'),
    ('actual_payload=1', 'actual_payload=0'), ('actual_converter=1', 'actual_converter=0'),
    ('matrix_arithmetic_claimed=0', 'matrix_arithmetic_claimed=1'),
])
def test_missing_or_misrepresented_coverage_rejected(old, new):
    with pytest.raises(ValueError):
        runner.verify_log(marker().replace(old, new))


@pytest.mark.parametrize('text', ['', marker() + marker(), '\n'.join(marker().splitlines()[1:])])
def test_truncated_duplicate_empty_inventory_rejected(text):
    with pytest.raises(ValueError):
        runner.verify_log(text)


def test_actual_payload_candidate_and_legacy_rtl(tmp_path):
    try:
        verilator = runner.find_verilator()
    except ValueError as error:
        pytest.skip(str(error))
    result = runner.run(tmp_path / 'payload_guard', verilator)
    assert result['status'] == 'PASS_MATRIX_TILE16_NONFINITE_GUARD'
    assert result['modes'][1]['rejections'] == 18
    assert not result['matrix_arithmetic_verified'] and not result['full_chain_verified']
    assert len(result['source_sha256']) == 3


def test_runner_refuses_to_overwrite_existing_evidence(tmp_path):
    (tmp_path / 'existing').write_text('keep')
    with pytest.raises(ValueError, match='new or empty'):
        runner.run(tmp_path)
    assert (tmp_path / 'existing').read_text() == 'keep'
