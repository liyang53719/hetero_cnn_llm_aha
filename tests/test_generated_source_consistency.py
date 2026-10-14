"""Cold tests for the read-only gate; writes are confined to pytest temp fixtures.

Fixture source identities are intentionally rebound only in the temporary copy
so success/rejection tests are independent of the live checkout's current pins.
No production source, generated file, Git state, model, weights or RTL is run.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

HERE = Path(__file__).resolve().parent
ENTRYPOINT = HERE / 'check_generated_source_consistency.py'
if not ENTRYPOINT.is_file():
    ENTRYPOINT = HERE.parent / 'scripts/check_generated_source_consistency.py'
SPEC = importlib.util.spec_from_file_location('cold_consistency', ENTRYPOINT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
ROOT = Path(os.environ.get('HETERO_PREFLIGHT_TEST_ROOT', HERE.parent)).resolve()


def copy_file(root, relative):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, target)


def rebind_fixture_pins(root, name):
    """Test setup only, never part of the preflight under test."""
    module = gate.load_module(root, 'scripts/' + name + '.py')
    text = Path(module.__file__).read_text()
    maps = [module.SOURCE_PINS]
    if hasattr(module, 'HOST_SOURCE_PINS'):
        maps.append(module.HOST_SOURCE_PINS)
    for pins in maps:
        for relative, old in pins.items():
            text = text.replace(old, gate.sha(root / relative))
    Path(module.__file__).write_text(text)



@pytest.fixture(scope='session')
def baseline(tmp_path_factory):
    root = tmp_path_factory.mktemp('cold_baseline')
    shutil.copytree(ROOT / 'src', root / 'src', ignore=shutil.ignore_patterns('__pycache__'))
    relatives = {
        'scripts/generate_shape_layout_vectors.py', 'scripts/block_checklist.py',
        'scripts/validate_typical_block_plan.py', 'doc/block_checklist.yaml',
        'scripts/qwen2_dense_residency_numeric.py', 'scripts/qwen2_rectangular_attention_numeric.py',
        'reports/execution/QWEN2_SFU_TIMING_20261011/V0_SAVED_GATE_AUDIT.json',
        'doc/three_model_typical_block_closure_20260917_zh.yaml',
        str(gate.PROJECT / 'scripts/plan_continuous_suites.py'),
        str(gate.PROJECT / 'scripts/run_continuous_ci_gate.sh'),
        *(entry[1] for entry in gate.EXTERNAL.values()),
    }
    for name in gate.ACTIVE_MODELS:
        module = gate.load_module(ROOT, 'scripts/' + name + '.py')
        relatives.add('scripts/' + name + '.py')
        relatives.update(module.SOURCE_PINS)
        relatives.update(getattr(module, 'HOST_SOURCE_PINS', {}))
    observer = gate.load_module(ROOT, 'scripts/observe_qwen2_attention_model.py')
    relatives.add('scripts/observe_qwen2_attention_model.py')
    relatives.add(observer.RECEIPT)
    relatives.update(observer.PINS)
    relatives.update(json.loads((ROOT / observer.RECEIPT).read_text())['source_sha256'])
    for directory in ('official_bf16', 'dense_block_reduce', 'ffn_attention', 'ffn_public', 'transposed_down'):
        for path in (ROOT / 'candidates/qwen2_resident_matrix' / directory).glob('*.py'):
            relatives.add(str(path.relative_to(ROOT)))
    for relative in relatives:
        copy_file(root, relative)
    for path in (ROOT / gate.PROJECT / 'src/test/scala/heteronpu/continuous').glob('*Spec.scala'):
        copy_file(root, path.relative_to(ROOT))
    # The real generated artifact construction is used only in temporary test
    # setup. The preflight itself invokes only --check.
    shape = gate.load_module(root, 'scripts/generate_shape_layout_vectors.py')
    for relative, content in shape.artifacts(root).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    # A cold ledger avoids copying historical evidence and preserves real plan
    # validation, task coverage and plan-byte identity semantics.
    ledger_path = root / 'doc/block_checklist.yaml'
    ledger = yaml.safe_load(ledger_path.read_text())
    for parent in ledger['任务']:
        for row in [parent] + parent.get('子项', []):
            row['状态'] = 'to do'
            row['负责人'] = ''
            row['证据'] = []
    ledger['计划SHA256'] = gate.sha(root / ledger['计划'])
    ledger_path.write_text(yaml.safe_dump(ledger, allow_unicode=True, sort_keys=False))
    for name in ('qwen2_prefill_traffic_bound', 'qwen2_rectangular_attention_model',
                 'qwen2_shared_sfu_schedule', 'qwen2_prefill_resource_schedule'):
        rebind_fixture_pins(root, name)
    dense = root / 'scripts/qwen2_dense_residency_numeric.py'
    text = dense.read_text()
    module = gate.load_module(root, 'scripts/qwen2_dense_residency_numeric.py')
    for key, relative in [('BASE_SHA256', 'scripts/qwen2_block_recipe_model.py'),
                          ('SCHEDULE_SHA256', 'scripts/qwen2_prefill_resource_schedule.py'),
                          ('ATTENTION_EVENT_SHA256', 'scripts/qwen2_rectangular_attention_model.py')]:
        text = text.replace(getattr(module, key), gate.sha(root / relative))
    dense.write_text(text)
    return root


@pytest.fixture
def repo(tmp_path, baseline):
    root = tmp_path / 'repo'
    shutil.copytree(baseline, root)
    return root


def fingerprint(root):
    return {str(path.relative_to(root)): gate.sha(path) for path in root.rglob('*') if path.is_file()}


def run_cli(root, *arguments):
    return subprocess.run([sys.executable, '-B', *(['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []), str(ENTRYPOINT),
                           '--root', str(root), *map(str, arguments)],
                          env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                          text=True, capture_output=True, timeout=20)


def run_one(root, name, tmp_path):
    scratch = tmp_path / ('scratch_' + name)
    scratch.mkdir()
    result = run_cli(root, '--_check', name, '--_scratch', scratch)
    return result, json.loads(result.stdout)


def test_all_real_validators_pass_without_repository_writes(repo, tmp_path):
    before = fingerprint(repo)
    receipt = tmp_path / 'receipt.json'
    result = run_cli(repo, '--receipt', receipt)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(receipt.read_text())
    assert [row['check'] for row in report['checks']] == list(gate.CHECKS)
    assert report['check_counts'] == {'PASS': len(gate.CHECKS)}
    assert report['hardware_acceptance_claimed'] is False
    assert report['scope']['refresh_attempted'] is False
    assert report['scope']['numerical_models_executed'] is False
    assert before == fingerprint(repo)
    assert not list(repo.rglob('__pycache__'))


@pytest.mark.parametrize('relative', [
    'tests/fixtures/block_contracts/shape_layout_vectors.json',
    'tests/fixtures/block_contracts/legacy_layout_vectors.tsv',
    'chisel/continuous_prefill/src/test/resources/c03_3/legacy_layout_vectors.tsv',
])
def test_each_generated_shape_artifact_drift_is_rejected_without_refresh(repo, tmp_path, relative):
    path = repo / relative
    path.write_text(path.read_text() + '\n')
    before = fingerprint(repo)
    result, row = run_one(repo, 'shape_vectors', tmp_path)
    assert result.returncode == 1
    assert row['status'] == 'FAIL' and 'STALE_VECTOR' in row['error']
    assert before == fingerprint(repo)


def test_shape_source_identity_drift_is_rejected(repo, tmp_path):
    path = repo / gate.PROJECT / 'src/main/scala/heteronpu/continuous/Qwen2Block.scala'
    path.write_text(path.read_text() + '\n// cold test source drift\n')
    result, row = run_one(repo, 'shape_vectors', tmp_path)
    assert result.returncode == 1 and 'STALE_VECTOR' in row['error']


def test_checklist_plan_byte_drift_rejected(repo, tmp_path):
    plan = repo / 'doc/three_model_typical_block_closure_20260917_zh.yaml'
    plan.write_text(plan.read_text() + '\n# cold plan-byte drift\n')
    before = fingerprint(repo)
    result, row = run_one(repo, 'block_checklist', tmp_path)
    assert result.returncode == 1 and 'plan bytes changed' in row['stderr']
    assert before == fingerprint(repo)


@pytest.mark.parametrize('name', gate.ACTIVE_MODELS)
def test_each_active_model_source_drift_rejected_without_model_run(repo, tmp_path, name):
    path = repo / gate.PROJECT / 'src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala'
    path.write_text(path.read_text() + '\n// cold identity drift\n')
    before = fingerprint(repo)
    result, row = run_one(repo, name, tmp_path)
    assert result.returncode == 1 and row['status'] == 'FAIL'
    assert 'QwenOwnerProtocol.scala' in row['error']
    assert before == fingerprint(repo)


def test_traffic_host_only_pin_drift_rejected(repo, tmp_path):
    path = repo / gate.PROJECT / 'src/main/scala/heteronpu/continuous/ElementwiseMemoryEngine.scala'
    path.write_text(path.read_text() + '\n// host-only drift\n')
    result, row = run_one(repo, 'qwen2_prefill_traffic_bound', tmp_path)
    assert result.returncode == 1 and 'ACTIVE_SOURCE_DRIFT' in row['error']


@pytest.mark.parametrize('name,boundary', [
    ('qwen2_rectangular_attention_model', 'calculate'),
    ('qwen2_prefill_resource_schedule', 'timing_profile'),
])
def test_embedded_source_gate_never_reaches_model(repo, name, boundary):
    module = gate.load_module(repo, 'scripts/' + name + '.py')
    def forbidden(*args, **kwargs):
        raise AssertionError('MODEL_WAS_EXECUTED')
    setattr(module, boundary, forbidden)
    assert gate.source_only_report(module, repo, boundary) == module.SOURCE_PINS
    assert getattr(module, boundary) is forbidden


def test_model_gate_api_change_fails_closed(repo, tmp_path):
    path = repo / 'scripts/qwen2_rectangular_attention_model.py'
    path.write_text(path.read_text().replace('    result = calculate(tokens, contexts)',
                                             '    result = calculate(tokens, contexts + 0)'))
    result, row = run_one(repo, 'qwen2_rectangular_attention_model', tmp_path)
    assert result.returncode == 1 and 'SOURCE_GATE_API_CHANGED' in row['error']


def test_no_historical_candidate_pin_rebasing_or_validation(repo, tmp_path):
    path = repo / 'candidates/historical/SOURCE_SNAPSHOT.json'
    path.parent.mkdir(parents=True)
    content = '{"source_sha256":{"historical_source.scala":"' + '0' * 64 + '"}}\n'
    path.write_text(content)
    before = fingerprint(repo)
    result = run_cli(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert before == fingerprint(repo) and path.read_text() == content


def test_new_general_suite_discovered_exactly_once(repo, tmp_path):
    path = repo / gate.PROJECT / 'src/test/scala/heteronpu/continuous/NewColdSpec.scala'
    path.write_text('// source discovery only\n')
    result, row = run_one(repo, 'continuous_suite_partition', tmp_path)
    assert result.returncode == 0
    flat = [s for ss in row['detail']['plan'].values() for s in ss]
    assert flat.count('heteronpu.continuous.NewColdSpec') == 1


@pytest.mark.parametrize('group', tuple(gate.EXTERNAL))
def test_missing_external_suite_rejected(repo, tmp_path, group):
    suite = gate.EXTERNAL[group][0]
    (repo / gate.PROJECT / 'src/test/scala/heteronpu/continuous' /
     (suite.rsplit('.', 1)[-1] + '.scala')).unlink()
    result, row = run_one(repo, 'continuous_suite_partition', tmp_path)
    assert result.returncode == 1 and 'MISSING_FIXTURE_SUITE' in row['error']


def test_duplicate_suite_partition_rejected(repo, tmp_path):
    path = repo / gate.PROJECT / 'scripts/plan_continuous_suites.py'
    path.write_text(path.read_text().replace('    return result',
        '    result["general"].append(result["tiny"][0])\n    return result'))
    result, row = run_one(repo, 'continuous_suite_partition', tmp_path)
    assert result.returncode == 1 and 'SUITE_COVERAGE_MISMATCH' in row['error']


def test_external_cannot_move_into_runnable_plan(repo, tmp_path):
    path = repo / gate.PROJECT / 'scripts/plan_continuous_suites.py'
    path.write_text(path.read_text().replace('    return result',
        '    result["general"] += result.pop("frozen_actual_h2048_rms")\n    return result'))
    result, row = run_one(repo, 'continuous_suite_partition', tmp_path)
    assert result.returncode == 1 and 'UNKNOWN_OR_MISSING_SUITE_GROUP' in row['error']


@pytest.mark.parametrize('old,new,expected', [
    ("'counted_as_pass':False", "'counted_as_pass':True", 'EXTERNAL_RECEIPT_FALSE_PASS'),
    ('NOT_EXECUTED_REQUIRES_FROZEN_ACTUAL_FIXTURE', 'PASS', 'EXTERNAL_RECEIPT_FALSE_PASS'),
    ("'frozen_actual_h2048_rms_executed':False", "'frozen_actual_h2048_rms_executed':True", 'EXTERNAL_EXECUTION_FALSE_CLAIM'),
    ("'total_tests':sum(x['tests'] for x in groups.values())", "'total_tests':sum(x['tests'] for x in groups.values())+1", 'EXTERNAL_TESTS_COUNTED_AS_PASS'),
    ('for group in general tiny real native;do', 'for group in general tiny real native frozen_actual_h2048_rms;do', 'SHELL_RUN_GROUP_CONTRACT_DRIFT'),
])
def test_each_external_false_pass_contract_rejected(repo, tmp_path, old, new, expected):
    path = repo / gate.PROJECT / 'scripts/run_continuous_ci_gate.sh'
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))
    result, row = run_one(repo, 'continuous_external_contract', tmp_path)
    assert result.returncode == 1 and expected in row['error']


@pytest.mark.parametrize('replacement', ['assume(false)', 'cancel("missing fixture")'])
def test_external_skip_or_cancel_rejected(repo, tmp_path, replacement):
    suite = gate.EXTERNAL['frozen_actual_h2048_rms'][0]
    path = repo / gate.PROJECT / 'src/test/scala/heteronpu/continuous' / (suite.rsplit('.', 1)[-1] + '.scala')
    path.write_text(path.read_text() + '\n' + replacement + '\n')
    result, row = run_one(repo, 'continuous_external_contract', tmp_path)
    assert result.returncode == 1 and 'EXTERNAL_SUITE_SKIP_OR_CANCEL' in row['error']


def test_all_checks_still_attempted_after_failure(repo, tmp_path):
    path = repo / 'tests/fixtures/block_contracts/shape_layout_vectors.json'
    path.write_text('stale')
    result = run_cli(repo)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert [row['check'] for row in report['checks']] == list(gate.CHECKS)
    assert report['checks'][0]['status'] == 'FAIL'
    assert all(row['status'] == 'PASS' for row in report['checks'][1:])


def test_missing_validator_is_blocked_and_other_checks_attempted(repo):
    (repo / 'scripts/generate_shape_layout_vectors.py').unlink()
    result = run_cli(repo)
    report = json.loads(result.stdout)
    assert result.returncode == 3
    assert report['checks'][0]['status'] == 'BLOCKED'
    assert len(report['checks']) == len(gate.CHECKS)


@pytest.mark.parametrize('relative', ['doc/no_write.json', '.git/no_write.json', 'generated/no_write.json'])
def test_receipt_cannot_write_source_generated_or_git(repo, relative):
    path = repo / relative
    path.parent.mkdir(exist_ok=True)
    before = fingerprint(repo)
    result = run_cli(repo, '--receipt', path)
    assert result.returncode == 2
    assert 'RECEIPT_MUST_USE_IGNORED_WORK_OR_TEMP' in result.stderr
    assert before == fingerprint(repo)


def test_existing_receipt_is_not_overwritten(repo, tmp_path):
    receipt = tmp_path / 'existing.json'
    receipt.write_text('keep')
    result = run_cli(repo, '--receipt', receipt)
    assert result.returncode == 2 and receipt.read_text() == 'keep'


def test_symlink_receipt_cannot_escape_into_source(repo, tmp_path):
    link = tmp_path / 'through_link'
    link.symlink_to(repo / 'doc', target_is_directory=True)
    result = run_cli(repo, '--receipt', link / 'no_write.json')
    assert result.returncode == 2 and not (repo / 'doc/no_write.json').exists()


def test_validator_repository_write_is_denied(repo, tmp_path):
    path = repo / 'scripts/generate_shape_layout_vectors.py'
    path.write_text('from pathlib import Path\nPath(__file__).write_text("destroy")\n')
    before = fingerprint(repo)
    result, row = run_one(repo, 'shape_vectors', tmp_path)
    assert result.returncode == 1 and 'READ_ONLY_WRITE_REJECTED' in row['error']
    assert before == fingerprint(repo)


def test_validator_external_build_tool_is_denied(repo, tmp_path):
    path = repo / 'scripts/generate_shape_layout_vectors.py'
    path.write_text('import subprocess\nsubprocess.run(["sbt", "compile"])\n')
    result, row = run_one(repo, 'shape_vectors', tmp_path)
    assert result.returncode == 1 and 'CHILD_TOOL_REJECTED' in row['error']


@pytest.mark.parametrize('constant', ['BASE_SHA256', 'SCHEDULE_SHA256', 'ATTENTION_EVENT_SHA256'])
def test_each_downstream_dense_pin_drift_is_rejected_without_numerics(repo, tmp_path, constant):
    path = repo / 'scripts/qwen2_dense_residency_numeric.py'
    module = gate.load_module(repo, 'scripts/qwen2_dense_residency_numeric.py')
    path.write_text(path.read_text().replace(getattr(module, constant), '0' * 64))
    before = fingerprint(repo)
    result, row = run_one(repo, 'qwen2_dense_residency_source_identity', tmp_path)
    assert result.returncode == 1 and 'dense-residency active source changed' in row['error']
    assert before == fingerprint(repo)


def test_saved_v0_receipt_bytes_cannot_be_rebased(repo, tmp_path):
    path = repo / 'reports/execution/QWEN2_SFU_TIMING_20261011/V0_SAVED_GATE_AUDIT.json'
    path.write_text(path.read_text() + '\n')
    before = fingerprint(repo)
    result, row = run_one(repo, 'qwen2_saved_v0_source_review', tmp_path)
    assert result.returncode == 1 and 'SAVED_V0_RECEIPT_CHANGED' in row['error']
    assert before == fingerprint(repo)


def test_saved_v0_unknown_historical_pair_rejected(repo, tmp_path):
    path = repo / 'scripts/qwen2_prefill_resource_schedule.py'
    module = gate.load_module(repo, path.relative_to(repo))
    pair = next(iter(module.V0_HOST_SOURCE_REVIEW.values()))
    path.write_text(path.read_text().replace(pair['historical_sha256'], '0' * 64))
    result, row = run_one(repo, 'qwen2_saved_v0_source_review', tmp_path)
    assert result.returncode == 1 and 'SAVED_V0_UNKNOWN_HISTORICAL_IDENTITY' in row['error']


@pytest.mark.parametrize('filename', ['Qwen2Block.scala', 'QwenOwnerProtocol.scala', 'BlockFloat.scala'])
def test_saved_v0_unknown_current_and_unreviewed_source_drift_rejected(repo, tmp_path, filename):
    path = repo / gate.PROJECT / 'src/main/scala/heteronpu/continuous' / filename
    path.write_text(path.read_text() + '\n// unknown current source\n')
    result, row = run_one(repo, 'qwen2_saved_v0_source_review', tmp_path)
    assert result.returncode == 1 and 'SOURCE_DRIFT' in row['error']


def test_saved_v0_cannot_expand_review_scope(repo, tmp_path):
    path = repo / 'scripts/qwen2_prefill_resource_schedule.py'
    text = path.read_text()
    marker = 'def _current_v0_hardware_pins('
    assert marker in text
    path.write_text(text.replace(marker,
        'V0_HOST_SOURCE_REVIEW["unknown.scala"] = {"historical_sha256": "0" * 64, "current_sha256": "1" * 64}\n\n\n' + marker))
    result, row = run_one(repo, 'qwen2_saved_v0_source_review', tmp_path)
    assert result.returncode == 1 and 'SAVED_V0_REVIEW_SCOPE_CHANGED' in row['error']


def test_saved_v0_reports_historical_and_current_identity_separately(repo, tmp_path):
    result, row = run_one(repo, 'qwen2_saved_v0_source_review', tmp_path)
    assert result.returncode == 0, row
    detail = row['detail']
    assert detail['historical_hardware_sha256'] != detail['current_hardware_sha256']
    for key in ('historical_receipt_rewritten', 'bound_calculated',
                'current_host_reexecuted', 'current_rtl_measured', 'h2048_borrower_included'):
        assert detail[key] is False


@pytest.mark.parametrize('name', ['qwen2_current_matrix_source_identity',
                                 'qwen2_current_prefix_source_identity',
                                 'qwen2_current_attention_execution_inventory'])
def test_historical_replay_source_drift_rejected_without_snapshot_rewrite(repo, tmp_path, name):
    path = repo / gate.PROJECT / 'src/main/scala/heteronpu/continuous/Qwen2Block.scala'
    path.write_text(path.read_text() + '\n// unknown replay source\n')
    before = fingerprint(repo)
    result, row = run_one(repo, name, tmp_path)
    assert result.returncode == 1 and 'Qwen2Block.scala' in row['error']
    assert before == fingerprint(repo)


def test_sealed_attention_inventory_cannot_be_rewritten(repo, tmp_path):
    observer = gate.load_module(repo, 'scripts/observe_qwen2_attention_model.py')
    path = repo / observer.RECEIPT
    path.write_text(path.read_text() + '\n')
    result, row = run_one(repo, 'qwen2_current_attention_execution_inventory', tmp_path)
    assert result.returncode == 1 and 'FROZEN_EXECUTION_RECEIPT_CHANGED' in row['error']


def test_historical_failure_is_explicit_global_failure_even_when_active_checks_pass(repo):
    path = repo / 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'
    text = path.read_text()
    marker = 'def source_identity(root=ROOT, *, enable_h2048_rms_borrower=False,\n                    external_elementwise_loan=False):'
    path.write_text(text.replace(marker, marker + '\n    raise ValueError("historical snapshot requires review")'))
    # The sealed inventory also notices that its candidate source changed.
    result = run_cli(repo)
    report = json.loads(result.stdout)
    assert result.returncode == 1 and report['status'] == 'FAIL'
    assert all(row['status'] == 'PASS' for row in report['checks'][:10])
    assert 'qwen2_current_matrix_source_identity' in report['current_runtime_identity_blockers']
    assert report['full_workflow_executed'] is False


@pytest.mark.parametrize('name,relative', [
    ('qwen2_current_matrix_source_identity', 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'),
    ('qwen2_current_prefix_source_identity', 'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py'),
    ('qwen2_current_attention_execution_inventory', 'scripts/observe_qwen2_attention_model.py'),
])
def test_v3_default_false_must_not_be_integer_zero(repo, tmp_path, name, relative):
    path = repo / relative
    path.write_text(path.read_text().replace('enable_h2048_rms_borrower=False', 'enable_h2048_rms_borrower=0'))
    result, row = run_one(repo, name, tmp_path)
    assert result.returncode == 1 and 'V3_DEFAULT_PROFILE_API_CHANGED' in row['error']


@pytest.mark.parametrize('name,relative', [
    ('qwen2_current_matrix_source_identity', 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'),
    ('qwen2_current_prefix_source_identity', 'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py'),
    ('qwen2_current_attention_execution_inventory', 'scripts/observe_qwen2_attention_model.py'),
])
def test_v3_enabled_only_guard_cannot_accept_nonbool_profiles(repo, tmp_path, name, relative):
    path = repo / relative
    path.write_text(path.read_text().replace('enable_h2048_rms_borrower is not False', 'enable_h2048_rms_borrower is True'))
    result, row = run_one(repo, name, tmp_path)
    assert result.returncode != 0 and row['status'] != 'PASS'


@pytest.mark.parametrize('name,relative', [
    ('qwen2_current_matrix_source_identity', 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'),
    ('qwen2_current_prefix_source_identity', 'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py'),
])
@pytest.mark.parametrize('old,new', [
    ('source_commit=None', "source_commit='f16df50adfb0f1f4bc668c517a2e29accffe6753'"),
    ('historical_results_inherited=False', 'historical_results_inherited=True'),
    ('borrower_enabled=False', 'borrower_enabled=True'),
])
def test_v3_current_guards_cannot_claim_commit_or_inherited_execution(repo, tmp_path, name, relative, old, new):
    path = repo / relative
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))
    result, row = run_one(repo, name, tmp_path)
    assert result.returncode == 1 and 'V3_CURRENT_SOURCE_METADATA_CHANGED' in row['error']


@pytest.mark.parametrize('old,new,expected', [
    ('SOURCE_COMMIT = None', "SOURCE_COMMIT = 'f16df50adfb0f1f4bc668c517a2e29accffe6753'", 'V3_OBSERVER_CURRENT_SOURCE_METADATA_CHANGED'),
    ("SOURCE_VERSION = 'qwen2-existing-attention-observation-v3'", "SOURCE_VERSION = 'qwen2-existing-attention-observation-v2'", 'V3_OBSERVER_CURRENT_SOURCE_METADATA_CHANGED'),
    ('prior_observation_results_inherited=False', 'prior_observation_results_inherited=True', 'V3_METADATA_CHANGED'),
    ('sha256=RECEIPT_SHA, results_inherited=False', 'sha256=RECEIPT_SHA, results_inherited=True', 'V3_METADATA_CHANGED'),
    ('execution_source_commit=SOURCE_COMMIT', 'execution_source_commit=SOURCE_BASE_COMMIT', 'V3_OBSERVER_METADATA_BINDING_CHANGED'),
])
def test_v3_observer_metadata_cannot_inherit_history_or_mislabel_commit(repo, tmp_path, old, new, expected):
    path = repo / 'scripts/observe_qwen2_attention_model.py'
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))
    result, row = run_one(repo, 'qwen2_current_attention_execution_inventory', tmp_path)
    assert result.returncode == 1 and expected in row['error']


@pytest.mark.parametrize('kind', ['remove', 'add', 'historical_hash', 'current_hash'])
def test_v3_exact_five_replacements_reject_unknown_pairs_and_scope(repo, tmp_path, kind):
    path = repo / 'scripts/observe_qwen2_attention_model.py'
    module = gate.load_module(repo, path.relative_to(repo))
    name = next(iter(module.EXECUTION_SOURCE_REPLACEMENTS))
    old, current = module.EXECUTION_SOURCE_REPLACEMENTS[name]
    text = path.read_text()
    if kind == 'remove':
        mutation = f'EXECUTION_SOURCE_REPLACEMENTS.pop({name!r})\n'
    elif kind == 'add':
        mutation = 'EXECUTION_SOURCE_REPLACEMENTS["unknown.py"] = ("0" * 64, "1" * 64)\n'
    elif kind == 'historical_hash':
        mutation = f'EXECUTION_SOURCE_REPLACEMENTS[{name!r}] = ({"0" * 64!r}, {current!r})\n'
    else:
        mutation = f'EXECUTION_SOURCE_REPLACEMENTS[{name!r}] = ({old!r}, {"0" * 64!r})\n'
    path.write_text(text + '\n' + mutation)
    result, row = run_one(repo, 'qwen2_current_attention_execution_inventory', tmp_path)
    assert result.returncode == 1 and row['status'] == 'FAIL'


def test_v3_rehashed_historical_receipt_still_rejected(repo, tmp_path):
    module = gate.load_module(repo, 'scripts/observe_qwen2_attention_model.py')
    receipt = repo / module.RECEIPT
    receipt.write_text(receipt.read_text() + '\n')
    source = repo / 'scripts/observe_qwen2_attention_model.py'
    source.write_text(source.read_text().replace(module.RECEIPT_SHA, gate.sha(receipt)))
    before = fingerprint(repo)
    result, row = run_one(repo, 'qwen2_current_attention_execution_inventory', tmp_path)
    assert result.returncode == 1 and 'FROZEN_EXECUTION_RECEIPT_CHANGED' in row['error']
    assert before == fingerprint(repo)


def test_v3_any_unreviewed_one_of_seventy_source_entries_cannot_drift(repo, tmp_path):
    module = gate.load_module(repo, 'scripts/observe_qwen2_attention_model.py')
    historical = json.loads((repo / module.RECEIPT).read_text())['source_sha256']
    names = set(historical) - gate.V3_REPLACEMENT_NAMES
    assert len(names) == 70
    name = next(name for name in sorted(names) if name.endswith('.cpp'))
    path = repo / name
    path.write_text(path.read_text() + '\n// unreviewed inventory change\n')
    result, row = run_one(repo, 'qwen2_current_attention_execution_inventory', tmp_path)
    assert result.returncode == 1 and 'v3 execution source drift' in row['error']


@pytest.mark.parametrize('relative,constant', [
    ('candidates/qwen2_resident_matrix/official_bf16/observation.py', 'HELPER_SHA256'),
    ('candidates/qwen2_resident_matrix/dense_block_reduce/observation.py', 'CAPTURE_SHA256'),
    ('candidates/qwen2_resident_matrix/dense_block_reduce/observation.py', 'MONITORING_SHA256'),
])
def test_v3_active_observation_helper_pins_remain_strict(repo, tmp_path, relative, constant):
    path = repo / relative
    import re
    text, count = re.subn(r'(' + constant + r" = ')[0-9a-f]{64}(')", r'\g<1>' + '0' * 64 + r'\2', path.read_text())
    assert count == 1
    path.write_text(text)
    result, row = run_one(repo, 'qwen2_observation_helper_source_identity', tmp_path)
    assert result.returncode == 1 and 'source drift' in row['error']


def test_v3_profiled_observer_constructor_delta_is_checked_without_instantiation(repo, tmp_path):
    path = repo / 'candidates/qwen2_resident_matrix/dense_block_reduce/observation.py'
    text = path.read_text()
    marker = 'self.profiled_loaded_functions_checked = verify_profiled_dependencies(owner, self.sources)'
    assert marker in text
    path.write_text(text.replace('\n        ' + marker, '\n        ' + marker + '; self.unreviewed = True'))
    result, row = run_one(repo, 'qwen2_observation_helper_source_identity', tmp_path)
    assert result.returncode == 1 and 'minimal delta' in row['error']


def test_v3_receipt_separates_current_inventory_from_unchanged_historical_results(repo, tmp_path):
    result, row = run_one(repo, 'qwen2_current_attention_execution_inventory', tmp_path)
    assert result.returncode == 0
    detail = row['detail']
    assert (detail['inventory_entries'], detail['reviewed_replacements'], detail['unchanged_historical_entries']) == (75, 5, 70)
    assert detail['historical_receipt_sha256'] == gate.FROZEN_EXECUTION_RECEIPT_SHA256
    assert detail['source_commit'] is None and detail['source_base_commit'] == gate.V3_BASE_COMMIT
    assert detail['historical_results_inherited'] is False and detail['replay_executed'] is False
