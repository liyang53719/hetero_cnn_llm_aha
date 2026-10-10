"""Synthetic control/retention tests: no model, compiler, simulator or download."""
from datetime import datetime, timezone
import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_pair_runner', ROOT / 'tools/attention_native/run_native_pair.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture(autouse=True)
def isolate_workflow_environment(monkeypatch):
    for name in ('GITHUB_RUN_ID', 'CURRENT_JOB_ID', 'CURRENT_JOB_STARTED_AT'):
        monkeypatch.delenv(name, raising=False)


def args(**overrides):
    values = dict(run_id='1234', job_id='5678', job_started_at='2026-10-10T06:00:00Z',
        expected_sha256=runner.ARCHIVE_SHA256, expected_commit=runner.PIN,
        baseline_run_id=runner.BASELINE_RUN_ID)
    values.update(overrides)
    return SimpleNamespace(**values)


def wall():
    return datetime(2026, 10, 10, 6, tzinfo=timezone.utc).timestamp()


@pytest.mark.parametrize('elapsed,outer,active', [(0, 12000, 11820), (1200, 11820, 11640), (3900, 9120, 8940)])
def test_budget_has_two_distinct_reserves_within_job(elapsed, outer, active):
    budget = runner.Budget(args(), wall=lambda: wall() + elapsed, monotonic=lambda: 50)
    assert budget.outer_seconds == outer
    assert budget.remaining() == active
    assert elapsed + outer + runner.UPLOAD_RESERVE_SECONDS <= runner.JOB_SECONDS
    if active < 9000:
        with pytest.raises(ValueError, match='9000'):
            budget.pair_timeout()
    else:
        assert budget.pair_timeout() == min(active, 10800)


@pytest.mark.parametrize('field,value', [('run_id', '0'), ('job_id', 'job-name'),
    ('job_started_at', '2026-10-10T06:00:00'), ('job_started_at', '2026-10-10T06:00:00+00:00'),
    ('job_started_at', '2026-10-10T06:00:01Z'), ('job_started_at', '2026-10-09T06:00:00Z')])
def test_budget_rejects_untrusted_identity_clock(field, value):
    with pytest.raises(ValueError):
        runner.Budget(args(**{field: value}), wall=wall)


def test_budget_rechecks_elapsed_before_actual_launch(monkeypatch):
    now = [0]
    budget = runner.Budget(args(), wall=wall, monotonic=lambda: now[0])
    now[0] = 2820
    assert budget.pair_timeout() == 9000
    now[0] += .01
    with pytest.raises(ValueError, match='actual pair not started'):
        budget.pair_timeout()
    monkeypatch.setenv('CURRENT_JOB_ID', '999')
    with pytest.raises(ValueError, match='identity mismatch'):
        runner.Budget(args(), wall=wall)


def test_production_environment_never_forges_trigger_and_restores_on_error(monkeypatch):
    trigger = 'a' * 40
    monkeypatch.setenv('GITHUB_SHA', trigger)
    with pytest.raises(RuntimeError):
        with runner.production_environment(trigger):
            assert 'GITHUB_SHA' not in runner.os.environ
            raise RuntimeError('interrupted')
    assert runner.os.environ['GITHUB_SHA'] == trigger
    with pytest.raises(ValueError, match='trigger changed'):
        with runner.production_environment('b' * 40):
            pytest.fail('mismatched trigger admitted')


@pytest.mark.parametrize('cached_capability', [None, 'DEFAULT', 'AVX2'])
def test_cpu_selection_does_not_relabel_initialized_avx2(monkeypatch, cached_capability):
    monkeypatch.setenv('ATEN_CPU_CAPABILITY', 'avx2')
    if cached_capability is None:
        monkeypatch.delitem(runner.sys.modules, 'torch', raising=False)
    else:
        monkeypatch.setitem(runner.sys.modules, 'torch', SimpleNamespace(backends=SimpleNamespace(
            cpu=SimpleNamespace(get_cpu_capability=lambda: cached_capability))))
    if cached_capability == 'AVX2':
        with pytest.raises(ValueError, match='already initialized'):
            runner.configure_baseline_cpu()
        assert runner.os.environ['ATEN_CPU_CAPABILITY'] == 'avx2'
    else:
        result = runner.configure_baseline_cpu()
        assert result['previous_setting'] == 'avx2'
        assert runner.os.environ['ATEN_CPU_CAPABILITY'] == 'default'


def test_exact_archive_and_run_pins_cannot_be_overridden(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.diagnostic, 'checked_paths', lambda arg: calls.append(arg))
    for change in ({'expected_sha256': '0' * 64}, {'baseline_run_id': '38015586841'}):
        with pytest.raises(ValueError, match='exact original'):
            runner.checked_paths(args(**change))
    assert not calls
    runner.checked_paths(args())
    assert len(calls) == 1


@pytest.mark.parametrize('drift', ['source_commit', 'source_dirty', 'wrapper_dirty', 'trigger'])
def test_dual_checkout_validation_precedes_imports(tmp_path, monkeypatch, drift):
    source, wrapper = tmp_path / 'production', tmp_path / 'wrapper'
    source.mkdir(); wrapper.mkdir()
    archive = tmp_path / 'archive'
    archive.write_bytes(b'trusted')
    for name in (runner.diagnostic.PREFIX_HEADER, runner.diagnostic.BUILD_SCRIPT):
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'source')
    wrapper_commit = 'a' * 40
    def git(root, *command):
        if command == ('rev-parse', 'HEAD'):
            return ('b' * 40 if drift == 'source_commit' else runner.PIN) if root == source else wrapper_commit
        if command == ('rev-parse', '--show-toplevel'):
            return str(root)
        if command == ('status', '--porcelain', '--untracked-files=normal'):
            return ' M dirty' if ((root == source and drift == 'source_dirty') or
                                (root == wrapper and drift == 'wrapper_dirty')) else ''
        raise AssertionError(command)
    def sha(path):
        if Path(path) == archive:
            return runner.ARCHIVE_SHA256
        return runner.diagnostic.HEADER_SHA256 if str(path).endswith('.h') else runner.diagnostic.BUILDER_SHA256
    monkeypatch.setattr(runner.diagnostic, 'DIAGNOSTIC_ROOT', wrapper)
    monkeypatch.setattr(runner.diagnostic, 'git', git)
    monkeypatch.setattr(runner.diagnostic, 'sha', sha)
    monkeypatch.setenv('GITHUB_SHA', 'b' * 40 if drift == 'trigger' else wrapper_commit)
    with pytest.raises(ValueError):
        runner.checked_paths(args(source_root=source, output=source / 'work/new', archive=archive))
    assert runner.os.environ['GITHUB_SHA'] == ('b' * 40 if drift == 'trigger' else wrapper_commit)


def input_fixture(tmp_path):
    fixture, out = tmp_path / 'fixture', tmp_path / 'out'
    (fixture / 'input').mkdir(parents=True); out.mkdir()
    inputs = {}
    for name, size, byte in [('cold0_hidden.bf16le', 2048, 1), ('cold1_hidden.bf16le', 2048, 2),
                             ('trig.bf16le', 32768, 3)]:
        raw = bytes([byte]) * size
        (fixture / 'input' / name).write_bytes(raw)
        inputs[name] = hashlib.sha256(raw).hexdigest()
    (fixture / 'reference_receipt.json').write_text('{}\n')
    return fixture, out, dict(input_sha256=inputs, manifest_sha256='f' * 64,
                            block_reference_receipt_sha256='c' * 64)


def test_input_retention_keeps_exact_new_stimulus_before_execution(tmp_path):
    fixture, out, admitted = input_fixture(tmp_path)
    result = runner.pack_inputs(fixture, out, admitted, args(), 'a' * 40)
    assert result['status'] == 'PREPARED_INPUT_ONLY_NOT_EXECUTED'
    assert result['archive_bytes'] <= 16384 and result['raw_bytes'] == 4352
    assert not result['actual_execution_included']
    with zipfile.ZipFile(out / 'input_replay.zip') as archive:
        assert set(archive.namelist()) == {'input/cold0_hidden.bf16le', 'input/cold1_hidden.bf16le',
            'input/trig_first_two_rows.bf16le', 'input_manifest.json'}
        manifest = json.loads(archive.read('input_manifest.json'))
        assert not manifest['hardware_authority_verified']
        assert archive.read('input/trig_first_two_rows.bf16le') == (fixture / 'input/trig.bf16le').read_bytes()[:256]
        assert manifest['files']['input/trig_first_two_rows.bf16le']['source_bytes'] == 32768
    with pytest.raises(ValueError, match='fresh input replay'):
        runner.pack_inputs(fixture, out, admitted, args(), 'a' * 40)


@pytest.mark.parametrize('fault', ['hidden', 'trig_suffix', 'symlink'])
def test_input_retention_rejects_full_input_drift_not_just_retained_prefix(tmp_path, fault):
    fixture, out, admitted = input_fixture(tmp_path)
    if fault == 'hidden':
        (fixture / 'input/cold0_hidden.bf16le').write_bytes(bytes(2048))
    elif fault == 'trig_suffix':
        path = fixture / 'input/trig.bf16le'
        path.write_bytes(path.read_bytes()[:-1] + b'\0')
    else:
        path = fixture / 'input/cold0_hidden.bf16le'
        replacement = tmp_path / 'hidden'; replacement.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(replacement)
    with pytest.raises(ValueError):
        runner.pack_inputs(fixture, out, admitted, args(), 'a' * 40)
    assert not (out / 'input_replay.zip').exists()


def report(*, actual=False, failed=False):
    result = dict(hardware_authority_verified=False, hardware_authority_upgrade_supported=False,
        native_full_block_acceptance=False, overall_pass=False, modes={})
    for mode in ['official_own_cache', 'canonical_prior_cache'] + (['retained_snapshot_prior_cache'] if actual else []):
        rows = []
        for pos, phase in enumerate(('cold0', 'carried1')):
            row = dict(host_phase=phase, absolute_position=pos, query_tokens=1,
                original_trig_bit_identity=True, producer_comparisons={'1': {'pass': False}})
            if actual:
                row.update(hardware_authority_verified=False,
                    receipt_hashed_terminal_comparisons={'q': {'pass': not failed, 'max_abs': .04 if failed else 0,
                        'max_abs_limit': .03}}, receipt_hashed_output_comparison={'pass': True, 'max_abs_limit': .05},
                    retained_cache_comparisons={role: {'pass': True} for role in ('k', 'v')})
            rows.append(row)
        result['modes'][mode] = dict(cases=rows)
    if actual:
        result.update(retained_replay_pack=dict(hardware_authority_verified=False, old_pass_revalidated=False),
            conditioned_gqa={p: {'stages': {'38': {'comparison': {'pass': False}}}} for p in ('cold0', 'carried1')},
            missing_actual_internal_gqa_producers={p: [33, 34, 35, 36, 37] for p in ('cold0', 'carried1')})
    return result


@pytest.fixture
def pair_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'ROOT', tmp_path / 'wrapper')
    monkeypatch.setenv('ATEN_CPU_CAPABILITY', 'default')
    out = tmp_path / 'out'; out.mkdir()
    (out / 'pair_fixture').mkdir()
    (out / 'pair_fixture/reference_receipt.json').write_text('{}\n')
    build = out / 'baseline'; build.mkdir()
    calls, summary, hashes = [], {'replay_pack_sealed': False}, {'output_sha256': {}}
    built = {'obj/VHostBlockTop': 'b' * 64, 'generated/HostBlockTop.sv': 'r' * 64, 'build_ready.json': 'd' * 64}
    admitted = {'manifest_sha256': 'f' * 64, 'block_reference_receipt_sha256': 'c' * 64, 'input_sha256': {'raw': 'i' * 64}}
    result = dict(status='ACTUAL_PAIR', mode='pass', same_dut_launches=2, resets_between_launches=0,
        binary_sha256=built['obj/VHostBlockTop'], rtl_sha256=built['generated/HostBlockTop.sv'],
        build_ready_sha256=built['build_ready.json'], fixture_sha256=admitted['manifest_sha256'],
        block_reference_receipt_sha256=admitted['block_reference_receipt_sha256'],
        input_sha256=admitted['input_sha256'], actual_sha256={'cold0': {}, 'carried1': {}}, log_sha256='l' * 64)
    result.update({k: True for k in ('actual_dut_identity_verified', 'live_authorities_verified',
        'source_immutability_verified', 'full_block_m1_executed', 'full_block_artifact_consistency',
        'frozen_recipe_block_acceptance', 'numerical_acceptance_eligible')})
    result.update({k: False for k in ('native_full_block_acceptance', 'intermediate_preload', 'prior_cache_preload')})
    state = SimpleNamespace(fault=None, failed=False, calls=calls, result=result)
    def check_fault(name):
        calls.append(name)
        if state.fault == name:
            raise ValueError('synthetic ' + name)
    def run_case(*pos, **kw):
        check_fault('run_case')
        assert pos == (build, out / 'pair_fixture', 'pass')
        assert kw['timeout_seconds'] == 10800
        assert set(kw) == {'timeout_seconds', 'block_session', 'session', 'projection_session', 'attention_session'}
        return result
    def audit(bundle, official, actual=None):
        check_fault('actual_audit' if actual else 'preflight')
        if actual:
            assert summary['replay_pack_sealed'] and (out / 'replay_pack.zip').exists()
            assert (out / 'pack_summary.json').exists()
        return report(actual=actual is not None, failed=state.failed)
    def pack_case(build, fixture, archive, **kw):
        check_fault('pack')
        assert kw['result'] is result
        archive.parent.mkdir(parents=True); archive.write_bytes(b'synthetic replay')
        return dict(archive_sha256=runner.sha(archive), hardware_authority_verified=False)
    def load_pack(*pos, **kw):
        check_fault('load_pack')
        return dict(hardware_authority_verified=False, replay_manifest={'verified': True})
    frozen = SimpleNamespace(CASE_STATUS='ACTUAL_PAIR', run_case=run_case,
        verify_case_outputs=lambda *a: check_fault('verify_outputs'),
        collect_mac_profile=lambda *a: {'log_sha256': result['log_sha256']})
    helper = SimpleNamespace(load_bundle=lambda *a: {'receipt': {'variant': 'baseline'}},
        OfficialM1=lambda b: SimpleNamespace(metadata={'torch_cpu_capability': 'DEFAULT'}),
        audit=audit, load_replay_pack=load_pack)
    packer = SimpleNamespace(pack_verified_case=pack_case, verify_pack=lambda *a, **kw: {'verified': True})
    budget = SimpleNamespace(pair_timeout=lambda: 10800)
    authorities = dict(block_session=SimpleNamespace(receipt_sha256='c' * 64),
        session=object(), projection_session=object(), attention_session=object())
    def execute():
        runner.perform_pair(args(), out, build, frozen, helper, packer, authorities, admitted,
            built, budget, summary, hashes, lambda stage: calls.append(stage), lambda: check_fault('postcheck'))
    state.execute, state.out, state.summary, state.budget = execute, out, summary, budget
    return state


def test_once_only_call_order_pack_precedes_actual_audit_and_preflight_failures_are_evidence(pair_adapters):
    state = pair_adapters
    state.execute()
    assert state.calls.count('run_case') == 1
    assert state.calls.index('preflight') < state.calls.index('run_case') < state.calls.index('pack') < state.calls.index('actual_audit')
    assert state.summary['status'] == 'TERMINAL_NATIVE_COMPARISONS_PASS'
    assert not state.summary['native_measurements']['native_full_block_acceptance']
    assert state.summary['native_measurements']['missing_actual_internal_gqa_producers']['cold0'] == list(range(33, 38))
    saved = json.loads((state.out / 'official_m1_preflight.json').read_text())
    assert not saved['modes']['official_own_cache']['cases'][0]['producer_comparisons']['1']['pass']


@pytest.mark.parametrize('fault', ['preflight', 'postcheck', 'run_case', 'pack', 'actual_audit'])
def test_failures_never_retry_pair_and_preserve_already_sealed_pack(pair_adapters, fault):
    state = pair_adapters; state.fault = fault
    with pytest.raises(ValueError, match='synthetic'):
        state.execute()
    assert state.calls.count('run_case') <= 1
    if fault in ('preflight', 'postcheck'):
        assert 'run_case' not in state.calls
    if fault == 'actual_audit':
        assert state.summary['replay_pack_sealed']
        assert (state.out / 'replay_pack.zip').read_bytes() == b'synthetic replay'
        assert (state.out / 'pack_summary.json').exists()
    else:
        assert not (state.out / 'replay_pack.zip').exists()


def test_low_budget_stops_after_preflight_before_pair(pair_adapters):
    state = pair_adapters
    def exhausted():
        raise ValueError('fewer than 9000 active seconds')
    state.budget.pair_timeout = exhausted
    with pytest.raises(ValueError, match='9000'):
        state.execute()
    assert 'preflight' in state.calls and 'run_case' not in state.calls


def test_actual_operator_failure_remains_separate_from_passing_final_output(pair_adapters):
    state = pair_adapters; state.failed = True; state.execute()
    assert state.summary['status'] == 'COMPLETE_NATIVE_LIMITS_FAILED'
    measured = state.summary['native_measurements']
    assert not measured['measured_terminal_and_output_limits_pass']
    assert measured['modes']['official_own_cache']['block_output_limits_pass']
    assert measured['modes']['official_own_cache']['failed_operators'] == {'cold0': ['q'], 'carried1': ['q']}
    saved = json.loads((state.out / 'official_m1_actual.json').read_text())
    assert saved['modes']['official_own_cache']['cases'][0]['receipt_hashed_terminal_comparisons']['q']['max_abs_limit'] == .03


@pytest.mark.parametrize('mode', ['official_own_cache', 'canonical_prior_cache', 'retained_snapshot_prior_cache'])
def test_cache_only_assigned_limit_failure_is_not_hidden_by_passing_terminals(mode):
    actual = report(actual=True)
    actual['modes'][mode]['cases'][1]['retained_cache_comparisons']['k'] = dict(
        **{'pass': False}, max_abs=.04, max_abs_limit=.03)
    outcome = runner.numeric_outcome(actual)
    assert not outcome['measured_terminal_and_output_limits_pass']
    assert outcome['modes'][mode]['operator_limits_pass']
    assert not outcome['modes'][mode]['retained_cache_limits_pass']
    assert outcome['modes'][mode]['failed_cache_roles']['carried1'] == ['k']
    assert outcome['conditioned_gqa_acceptance']['excluded_from_acceptance_reason'] == 'unassigned_stage_contract'


def test_unassigned_conditioned_gqa_does_not_create_new_gate(pair_adapters):
    state = pair_adapters; state.execute()
    saved = json.loads((state.out / 'official_m1_actual.json').read_text())
    assert not saved['conditioned_gqa']['cold0']['stages']['38']['comparison']['pass']
    assert saved['conditioned_gqa']['cold0']['excluded_from_acceptance_reason'] == 'unassigned_stage_contract'
    assert state.summary['status'] == 'TERMINAL_NATIVE_COMPARISONS_PASS'


def test_changed_actual_scope_cannot_reach_packer(pair_adapters):
    state = pair_adapters; state.result['resets_between_launches'] = 1
    with pytest.raises(ValueError, match='production gates/scope'):
        state.execute()
    assert state.calls.count('run_case') == 1 and 'pack' not in state.calls


@pytest.mark.parametrize('code,forced,status', [(2, False, 'COMPLETE_NATIVE_LIMITS_FAILED'),
    (1, False, 'FAILED_NATIVE_M1_PAIR'), (2, True, 'FAILED_NATIVE_M1_PAIR')])
def test_supervisor_preserves_measurement_failure_and_only_prints_compact_json(tmp_path, capsys, code, forced, status):
    out = tmp_path / 'out'; out.mkdir()
    runner.diagnostic.write_compact(out, {'status': 'COMPLETE_NATIVE_LIMITS_FAILED',
        'replay_pack_sealed': True, 'stage': 'complete'}, {'replay_pack_sha256': 'a' * 64})
    (out / 'replay_pack.zip').write_bytes(b'NEVER PRINT RAW')
    (out / 'pipeline.log').write_text('NEVER PRINT MODEL INPUT')
    returned = runner.finalize_supervision(out, {'returncode': code, 'forced_shutdown': forced})
    assert returned == code
    assert json.loads((out / 'compact/summary.json').read_text())['status'] == status
    assert (out / 'replay_pack.zip').read_bytes() == b'NEVER PRINT RAW'
    assert (out / 'diagnostic_tail.txt').stat().st_size <= 12288
    captured = capsys.readouterr().out
    assert 'BEGIN_ATTENTION_NATIVE_COMPACT' in captured and 'NEVER PRINT' not in captured


def test_cli_has_no_rebuild_fault_retry_or_budget_extension_switch():
    base = ['--source-root', '/source', '--output', '/source/work/new', '--archive', '/archive',
        '--expected-sha256', runner.ARCHIVE_SHA256, '--expected-commit', runner.PIN,
        '--baseline-run-id', runner.BASELINE_RUN_ID, '--payload-layer0', '/zero',
        '--payload-layer3', '/three', '--payload-extra', '/extra', '--run-id', '123',
        '--job-id', '456', '--job-started-at', '2026-10-10T06:00:00Z']
    assert runner.arguments(base).expected_commit == runner.PIN
    for option in ('--allow-extra-budget', '--build-only', '--mode', '--retry'):
        with pytest.raises(SystemExit):
            runner.arguments(base + [option])


@pytest.mark.parametrize('comparison', ['pass', 'numeric_failure', 'preflight_error'])
def test_worker_keeps_two_git_identities_restores_trigger_and_returns_numeric_exit2(tmp_path, monkeypatch, comparison):
    source, out, archive = tmp_path / 'production', tmp_path / 'production/work/new', tmp_path / 'original.tar.gz'
    driver = source / runner.DRIVER; driver.parent.mkdir(parents=True); driver.write_bytes(b'driver')
    archive.write_bytes(b'archive')
    trigger, calls = 'a' * 40, []
    monkeypatch.setenv('GITHUB_SHA', trigger)
    monkeypatch.setenv('OFFLINE_TOOLS', str(tmp_path / 'tools'))
    current = args(source_root=source, output=out, archive=archive)
    original_budget = runner.Budget
    monkeypatch.setattr(runner, 'Budget', lambda arg: original_budget(arg, wall=wall))
    def paths(arg):
        assert runner.os.environ['GITHUB_SHA'] == trigger
        calls.append('checked_both_roots')
        return source, out, trigger
    monkeypatch.setattr(runner, 'checked_paths', paths)
    monkeypatch.setattr(runner, 'wrapper_identity', lambda *a: {'wrapper.py': 'w' * 64})
    monkeypatch.setattr(runner, 'configure_baseline_cpu', lambda: {'requested': 'default'})
    build_sources = {runner.DRIVER: 'd' * 64, **{f'build_{i}': 'd' * 64 for i in range(654)}}
    built = {'obj/VHostBlockTop': runner.BINARY_SHA256, 'generated/HostBlockTop.sv': runner.RTL_SHA256}
    def production_call(name):
        assert 'GITHUB_SHA' not in runner.os.environ
        calls.append(name)
    def restore(*a):
        production_call('restore')
        a[1].mkdir(); (a[1] / 'sources.sha256.json').write_text(json.dumps(build_sources))
        return {'restored': True}
    artifact = SimpleNamespace(prepare_compiler_jars=lambda *a: production_call('prepare_jars'), restore=restore)
    session = SimpleNamespace(evidence=lambda: {'fresh_official_executions': 2, 'reused_official_executions': 0})
    admitted = {'input_sha256': {}}
    frozen = SimpleNamespace(total_budget=lambda seconds: contextlib.nullcontext(),
        verify_checkout=lambda *a: production_call('verify_production_sources'),
        verify_all_build_sources=lambda *a: production_call('verify_build_sources'),
        build_identity=lambda *a: built, admit_fixture=lambda *a, **kw: admitted,
        _native_failure_evidence=lambda s: {'baseline': {'gate_pass': False}})
    def imports(root):
        assert root == source and runner.os.environ['GITHUB_SHA'] == trigger
        calls.append('production_imports')
        return frozen, artifact
    monkeypatch.setattr(runner.diagnostic, 'imports', imports)
    class Inventory:
        def __init__(self, frozen, build_sources, stages, hashes):
            production_call('inventory')
            self.build = build_sources
            self.full = {**build_sources, **{f'reference_{i}': 'd' * 64 for i in range(3)}}
        def verify(self, *a):
            production_call('inventory_verify')
        def require_complete(self, *a):
            production_call('inventory_complete')
    monkeypatch.setattr(runner.diagnostic, 'SourceInventory', Inventory)
    monkeypatch.setattr(runner.diagnostic, 'source_stage_snapshots', lambda *a: {})
    monkeypatch.setattr(runner.diagnostic, 'selected_tools', lambda build: {})
    monkeypatch.setattr(runner, 'sha', lambda path: runner.ARCHIVE_SHA256 if path == archive else 'd' * 64)
    monkeypatch.setattr(runner, 'helper_modules', lambda root: (object(), object()))
    def fresh(frozen, args, output, summary, hashes, inventory):
        production_call('fresh_fixture')
        summary['native_full_block_failures'] = {'baseline': {'gate_pass': False}}
        return {'session': session}, admitted
    monkeypatch.setattr(runner.diagnostic, 'fresh_fixture', fresh)
    def inputs(*a):
        production_call('retain_inputs')
        (out / 'input_replay.zip').write_bytes(b'exact new input bytes')
        return {'archive_sha256': 'i' * 64}
    monkeypatch.setattr(runner, 'pack_inputs', inputs)
    def pair(*a):
        production_call('perform_pair')
        if comparison == 'preflight_error':
            raise ValueError('unsupported official runtime')
        summary = a[10]
        passed = comparison == 'pass'
        summary['native_measurements'] = {'measured_terminal_and_output_limits_pass': passed}
        summary['status'] = 'TERMINAL_NATIVE_COMPARISONS_PASS' if passed else 'COMPLETE_NATIVE_LIMITS_FAILED'
    monkeypatch.setattr(runner, 'perform_pair', pair)
    assert runner.run_worker(current) == {'pass': 0, 'numeric_failure': 2, 'preflight_error': 1}[comparison]
    assert runner.os.environ['GITHUB_SHA'] == trigger
    assert calls[:2] == ['checked_both_roots', 'production_imports']
    assert calls.index('prepare_jars') < calls.index('restore') < calls.index('fresh_fixture')
    assert calls.index('retain_inputs') < calls.index('perform_pair')
    summary = json.loads((out / 'compact/summary.json').read_text())
    assert summary['github_trigger_sha'] == trigger and summary['production_source_commit'] == runner.PIN
    assert not summary['input_retention_gap']
    assert summary['original_m128_native_failures']['baseline']['gate_pass'] is False
    assert not summary['native_full_block_acceptance']
