"""Synthetic CI attestations and tiny Git repos only; no model, compiler or DUT."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('attention_block_split_acceptance',
                                            ROOT / '.github/scripts/verify_attention_block_split.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
from host_bf16_attention_block_reference import contract_schema


def digest(label):
    return hashlib.sha256(label.encode()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    return gate.sha(path)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()


def make_reference(sources, inputs, mode, failures, report_hashes):
    schema = contract_schema()
    manifest = digest(mode + ' official capture')
    cases, expected = {}, {}
    for index, phase in enumerate(gate.fixture.SOURCE_PHASES):
        proofs = dict(gqa=dict(status='PASS_INTEGER_C_EVERY_QK_PV_FMA', fmas=4096 * (index + 1),
                               bit_mismatches=0, flag_mismatches=0), norm_rope={'control_only': True})
        for role, (k, n) in gate.fixture.DENSE_SHAPES.items():
            proofs[role] = [dict(token=0, column_start=start, k=k, columns=256,
                matrix_accumulator_steps=k * 256, **{'pass': True}, uninterrupted_fp32_accumulation=True,
                terminal_bf16_roundings=1, bit_mismatches=0, flag_mismatches=0) for start in range(0, n, 256)]
        cases[phase] = dict(command_count=22, source_phase='cold', source_token=index, token_count=1,
            absolute_position=index, expected_length=index, expected_generation=index, cold=index == 0,
            native_accuracy_accepted=False, independent_proofs=proofs,
            producer_predecessors=deepcopy(schema['producer_predecessors']),
            raw_hidden_sha256=inputs[phase + '_hidden.bf16le'],
            selected_trig=dict(backing_sha256=inputs['trig.bf16le']))
        names = {name + '.bf16le' for name in (*gate.fixture.NAMES, 'sigmoid', 'silu')}
        names.update(f'producer_{i:02d}.f32le' for i in range(57))
        expected[phase] = {name: dict(bytes=2, sha256=digest(mode + phase + name)) for name in sorted(names)}
        for name, width in zip(gate.fixture.NAMES, gate.fixture.WIDTHS):
            expected[phase][name + '.bf16le'] = dict(bytes=width * 2,
                sha256=digest(mode + gate.fixture.PHASES[index] + name))
    original_failures = {variant: dict(
        **{key: deepcopy(row[key]) for key in ('gate_pass', 'status', 'failed_producers', 'failed_softmax_invariants')},
        report_sha256=report_hashes[variant]) for variant, row in failures.items()}
    return dict(status='PREPARED_FULL_BLOCK_EXPECTED_ONLY_NOT_NATIVE_PASS', schema_version=1,
        expected_only=True, intermediate_preload_allowed=False, dut_input_injection=False,
        actual_cache_execution=False, numerical_rtl_executed=False, native_full_block_pass=False,
        full128_reference_generated=False, launch_counts=[1, 1], cases=cases, expected=expected,
        inputs={name: dict(bytes=gate.fixture.INPUTS[name], sha256=value) for name, value in inputs.items()},
        source_sha256_before=deepcopy(sources), source_sha256_after=deepcopy(sources),
        official_manifest_sha256=manifest, schema=schema, variant='baseline',
        model_revision='2fc06364715b967f1860aea9cf38778875588b17',
        original_capture_evidence=dict(fresh_official_executions=2, reused_official_executions=0,
                                       official_manifest_sha256=manifest),
        original_native_report={'control_only': True, 'failed_producers': deepcopy(failures['baseline']['failed_producers'])},
        original_prefix_report={'control_only': True}, original_native_thresholds={'operator': {'max_abs': 0.03125}},
        original_projection_gate_pass=True, original_norm_rope_gate_pass=True,
        original_component_gate_scope=dict(projection_receipt_sha256=digest(mode + ' projection'),
                                           norm_rope_receipt_sha256=digest(mode + ' attention')),
        original_native_full_block_failures=original_failures,
        gqa_native_gate='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE')


def make_case(mode, inputs, trusted, block_digest):
    files, actual, runs, profiles = {}, {}, [], []
    for index, phase in enumerate(gate.fixture.PHASES):
        failing = mode != 'pass' and index == 1
        actual[phase] = {name: digest(mode + phase + name) for name in gate.fixture.NAMES}
        snapshots = {'writable_after_command' + str(pc) + '.bin': digest(mode + phase + str(pc))
                     for pc in gate.completion_plan(failing)}
        ddr = digest(mode + phase + ' DDR')
        files.update({phase + '/actual_' + name + '.bf16le': value for name, value in actual[phase].items()})
        files.update({phase + '/' + name: value for name, value in snapshots.items()})
        files[phase + '/ddr_after.bin'] = ddr
        runs.append(dict(phase=phase, status=3 if failing else 0, checkpoint_accepted=not failing,
            inferred_committed_length=1 if failing else index + 1,
            inferred_committed_generation=1 if failing else index + 1,
            inferred_final_output=4096 if failing else 4096 * (index + 1), snapshot_sha256=snapshots,
            ddr_sha256=ddr))
        profiles.append(dict(run=index, phase=phase, hardware_status=3 if failing else 0,
            begin_cycle=index * 200, end_cycle=index * 200 + 100, cycles=100,
            commands=[dict(pc=pc) for pc in gate.completion_plan(failing)]))
    identity = {key: trusted['expected_' + key] for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256')}
    result = dict(status=gate.CASE_STATUS, mode=mode, actual_dut_identity_verified=True,
        live_authorities_verified=True, source_immutability_verified=True, same_dut_launches=2,
        resets_between_launches=0, full_block_m1_executed=True, full_block_supported=True,
        full_block_artifact_consistency=True, numerical_acceptance_eligible=mode == 'pass',
        frozen_recipe_block_acceptance=mode == 'pass', intermediate_preload=False, prior_cache_preload=False,
        native_context_acceptance=False, native_full_block_acceptance=False, native_full_block_accepted=False,
        model_m128_accepted=False, overall_pass=False, reset_restore_executed=False,
        block_reference_receipt_sha256=block_digest, input_sha256=deepcopy(inputs), fixture_sha256=digest(mode + ' fixture'),
        log_sha256=digest(mode + ' log'), execution_identity=dict(log_sha256=digest(mode + ' log'), files_sha256=files),
        actual_sha256=actual, runs=runs, **identity)
    profile = dict(status=gate.PROFILE_STATUS, mode=mode, log_sha256=result['log_sha256'],
        actual_dut_identity_verified=True, numerical_acceptance=False, performance_acceptance=False,
        fixed_resources=dict(logical_matrix_engines=1, physical_slices=8, rows_per_slice=16,
                             columns_per_slice=32, macs_per_cycle=4096), runs=profiles, **identity)
    return result, profile


class Evidence:
    def __init__(self, tmp_path):
        self.repo = tmp_path / 'repo'
        self.repo.mkdir()
        for name in gate.REQUIRED_SOURCES:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# SYNTHETIC COMMITTED SOURCE: ' + name + '\n')
        git(self.repo, 'init', '-q')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'user.name=Control Tests', '-c', 'user.email=control@example.invalid', 'commit', '-qm', 'control sources')
        self.sources = {name: gate.sha(self.repo / name) for name in gate.REQUIRED_SOURCES}
        self.kwargs = dict(expected_commit=git(self.repo, 'rev-parse', 'HEAD'), repo=self.repo)
        self.kwargs.update({'expected_' + key: digest('trusted build ' + key) for key in gate.BUILD_KEYS})
        self.directories, self.summaries, self.hashes = {}, {}, {}
        for mode, label in zip(gate.MODES, ('pass', 'fault')):
            directory = tmp_path / label
            directory.mkdir()
            self.directories[mode] = directory
            self.kwargs[label + '_compact'] = directory
            inputs = {name: digest('shared input ' + name) for name in gate.fixture.INPUTS}
            failures = {variant: dict(status='BLOCKED_BF16_PRODUCER_GATE', gate_pass=False,
                failed_producers=[dict(producer=mode + ' ' + variant + ' original failing producer', **{'pass': False})],
                failed_softmax_invariants=[], thresholds={'operator': {'max_abs': 0.03125}})
                for variant in ('baseline', 'avx2')}
            report_hashes = {variant: digest(mode + variant + ' native report') for variant in failures}
            reference = make_reference(self.sources, inputs, mode, failures, report_hashes)
            hashes = dict(source_sha256=deepcopy(self.sources), input_sha256=inputs,
                official_capture_manifest_sha256=reference['official_manifest_sha256'],
                projection_reference_receipt_sha256=digest(mode + ' projection'),
                attention_reference_receipt_sha256=digest(mode + ' attention'))
            ready = dict(status=gate.BUILD_STATUS, numerical_pass=False, initial_verilation_exit=0,
                source_base_commit=self.kwargs['expected_commit'], native_full_block_acceptance=False,
                model_m128_accepted=False, overall_pass=False, actual_verilator=dict(actual_elf=dict(
                    kind='ELF', sha256=digest('actual Verilator ELF'), version='Verilator 5.032')))
            for key in ('binary_sha256', 'rtl_sha256', 'source_manifest_sha256', 'toolchain_sha256'):
                ready[key] = self.kwargs['expected_' + key]
            for key in ('scope_sha256', 'actual_verilator_sha256', 'compiler_jars_sha256', 'hardfloat_manifest_sha256'):
                ready[key] = digest(key)
            fields = {'obj/VHostBlockTop': 'binary_sha256', 'generated/HostBlockTop.sv': 'rtl_sha256',
                'sources.sha256.json': 'source_manifest_sha256', 'toolchain.json': 'toolchain_sha256',
                'generated/SCOPE.json': 'scope_sha256', 'actual_verilator_after.json': 'actual_verilator_sha256',
                'compiler_jars.sha256.json': 'compiler_jars_sha256', 'hardfloat.sha256.json': 'hardfloat_manifest_sha256'}
            hashes['build_identity_sha256'] = {name: ready[key] for name, key in fields.items()}
            hashes['build_identity_sha256']['build_ready.json'] = self.kwargs['expected_build_ready_sha256']
            for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256'):
                hashes[key] = self.kwargs['expected_' + key]
            transfer = dict(schema=1, status=gate.BUILD_STATUS, scope=gate.SCOPE, numerical_pass=False,
                            source_commit=self.kwargs['expected_commit'])
            transfer.update({key: self.kwargs['expected_' + key] for key in gate.BUILD_KEYS})
            toolchain = dict(compiler_jars_verified_after_build=True,
                compiler_jars_sha256={'compiler.jar': digest('compiler')},
                hardfloat_source_sha256={'HardFloat.scala': digest('HardFloat')},
                idma_export_source_sha256={'idma.sv': digest('iDMA')})
            summary = dict(status=gate.CONSUMER_PASS, stage='complete', scope=gate.SCOPE,
                git_head=self.kwargs['expected_commit'], requested_mode=mode,
                numerical_acceptance=mode == 'pass', frozen_recipe_block_acceptance=mode == 'pass',
                **deepcopy(gate.SUMMARY_VALUES), **{key: True for key in gate.TRUE_SUMMARY},
                **{key: False for key in gate.FALSE_SUMMARY})
            summary.update(build=ready, build_transfer=transfer, toolchain=toolchain, block_reference=reference,
                official_manifest_sha256=reference['official_manifest_sha256'], native_full_block_failures=failures,
                native_audit_report_sha256=report_hashes, projection_reference=dict(native_operator_gate_pass=True),
                attention_reference=dict(original_operator_gate_pass=True,
                    official_manifest_sha256=reference['official_manifest_sha256'],
                    projection_reference_receipt_sha256=hashes['projection_reference_receipt_sha256']))
            block_digest = self.reference_digest(reference)
            hashes['block_reference_receipt_sha256'] = block_digest
            case, profile = make_case(mode, inputs, self.kwargs, block_digest)
            summary['cases'] = [dict(mode=mode, result=case)]
            summary['measured_mac_profiles'] = {mode: profile}
            prefix = dict(report_sha256=digest(mode + ' prefix report'), deterministic_sha256=digest(mode + ' prefix state'),
                terminal_event_sha256=digest(mode + ' prefix terminal'), event_sha256=digest(mode + ' prefix events'),
                log_sha256=digest(mode + ' prefix log'), event_bytes=8192,
                counters=dict(cycles=gate.PREFIX_CYCLES, reset_cycles=6, active_cycles=gate.PREFIX_CYCLES - 36))
            summary['deterministic_prefixes'] = dict(status=gate.PREFIX_STATUS, numerical_acceptance=False,
                full_block_m1_executed=False, actual_dut_identity_verified=True, live_authorities_verified=True,
                raw_prefix_events_upload_allowed=False, cycles_per_prefix=gate.PREFIX_CYCLES,
                input_sha256=deepcopy(inputs), prefixes=[deepcopy(prefix), deepcopy(prefix)],
                **{key: self.kwargs['expected_' + key] for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256')})
            hashes['output_sha256'] = {mode: deepcopy(case['actual_sha256'])}
            self.summaries[mode], self.hashes[mode] = summary, hashes
        self.write()

    @staticmethod
    def reference_digest(reference):
        return hashlib.sha256((json.dumps(reference, sort_keys=True, separators=(',', ':')) + '\n').encode()).hexdigest()

    def rebind_reference(self, mode):
        sha = self.reference_digest(self.summaries[mode]['block_reference'])
        self.hashes[mode]['block_reference_receipt_sha256'] = sha
        self.summaries[mode]['cases'][0]['result']['block_reference_receipt_sha256'] = sha

    def set_input(self, mode, name, value):
        self.hashes[mode]['input_sha256'][name] = value
        summary = self.summaries[mode]
        summary['cases'][0]['result']['input_sha256'][name] = value
        summary['deterministic_prefixes']['input_sha256'][name] = value
        reference = summary['block_reference']
        reference['inputs'][name]['sha256'] = value
        if name in gate.HIDDEN_INPUTS:
            reference['cases'][name.split('_')[0]]['raw_hidden_sha256'] = value
        if name == 'trig.bf16le':
            for case in reference['cases'].values():
                case['selected_trig']['backing_sha256'] = value
        self.rebind_reference(mode)

    def write(self):
        for mode, label in zip(gate.MODES, ('pass', 'fault')):
            directory = self.directories[mode]
            self.kwargs['expected_' + label + '_summary_sha256'] = save(directory / 'summary.json', self.summaries[mode])
            self.kwargs['expected_' + label + '_hashes_sha256'] = save(directory / 'source_input_hashes.json', self.hashes[mode])

    def verify(self):
        return gate.verify(**self.kwargs)


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.delenv('GITHUB_SHA', raising=False)
    return Evidence(tmp_path)


def test_complete_trusted_jobs_accept_only_frozen_pair_and_fault_protocol(evidence):
    result = evidence.verify()
    assert result['status'] == gate.PASS
    assert result['split_case_acceptance'] and result['frozen_recipe_block_acceptance'] and result['fault_protocol_acceptance']
    assert result['exact_clean_commit_verified'] and result['source_immutability_verified']
    assert result['all_raw_hidden_observed_equal'] is True
    for key in ('live_authority_reissued', 'native_context_acceptance', 'native_full_block_acceptance',
                'model_m128_accepted', 'full128_executed', 'overall_pass', 'performance_acceptance',
                'timing_signoff', 'qor_signoff', 'paired_identical_stimulus_fault_comparison'):
        assert result[key] is False
    for mode in gate.MODES:
        assert result['consumer_evidence'][mode]['summary'] == evidence.summaries[mode]
        assert result['consumer_evidence'][mode]['source_input_hashes'] == evidence.hashes[mode]
        assert result['native_full_block_failures'][mode] == evidence.summaries[mode]['native_full_block_failures']
    assert 'No live authority' in result['authority_scope']


@pytest.mark.parametrize('label', ['pass', 'fault'])
@pytest.mark.parametrize('filename', ['summary.json', 'source_input_hashes.json'])
def test_missing_job_artifact_is_not_acceptance(evidence, label, filename):
    (evidence.kwargs[label + '_compact'] / filename).unlink()
    with pytest.raises(ValueError, match='missing regular file'):
        evidence.verify()


@pytest.mark.parametrize('mode', gate.MODES)
@pytest.mark.parametrize('mutation', ['partial', 'failed', 'no_cases', 'extra_cases', 'error', 'supervisor'])
def test_partial_failed_or_incomplete_job_is_not_acceptance(evidence, mode, mutation):
    summary = evidence.summaries[mode]
    if mutation == 'partial': summary['stage'] = 'actual_two_launch_pass'
    elif mutation == 'failed': summary['status'] = 'FAIL_FRESH_HOST_ATTENTION_BLOCK_CASE_M1'
    elif mutation == 'no_cases': summary['cases'] = []
    elif mutation == 'extra_cases': summary['cases'] *= 2
    elif mutation == 'error': summary['error'] = dict(message='actual timeout')
    else: summary['supervisor'] = dict(forced_shutdown=True, returncode=124, worker_returncode=-15)
    evidence.write()
    with pytest.raises(ValueError):
        evidence.verify()


@pytest.mark.parametrize('key', ['expected_' + field for field in gate.BUILD_KEYS] + [
    'expected_pass_summary_sha256', 'expected_pass_hashes_sha256',
    'expected_fault_summary_sha256', 'expected_fault_hashes_sha256'])
def test_wrong_trusted_digest_fails_closed(evidence, key):
    evidence.kwargs[key] = '0' * 64
    with pytest.raises(ValueError):
        evidence.verify()


@pytest.mark.parametrize('field', ['package_sha256', 'binary_sha256', 'rtl_sha256', 'build_ready_sha256',
                                   'source_manifest_sha256', 'toolchain_sha256'])
def test_one_consumer_cannot_switch_immutable_build(evidence, field):
    evidence.summaries[gate.MODES[1]]['build_transfer'][field] = '0' * 64
    evidence.write()
    with pytest.raises(ValueError, match=field):
        evidence.verify()


def test_exact_expected_commit_is_required(evidence):
    evidence.kwargs['expected_commit'] = '0' * 40
    with pytest.raises(ValueError):
        evidence.verify()
    evidence.kwargs['expected_commit'] = 'HEAD'
    with pytest.raises(ValueError, match='exact trusted Git commit'):
        evidence.verify()


def test_both_attestations_relabelled_to_non_head_commit_are_rejected(evidence):
    commit = '0' * 40
    evidence.kwargs['expected_commit'] = commit
    for summary in evidence.summaries.values():
        summary['git_head'] = commit
        summary['build']['source_base_commit'] = commit
        summary['build_transfer']['source_commit'] = commit
    evidence.write()
    with pytest.raises(ValueError, match='current HEAD'):
        evidence.verify()


@pytest.mark.parametrize('kind', ['tracked', 'untracked', 'index'])
def test_dirty_checkout_is_rejected(evidence, kind):
    path = evidence.repo / ('untracked.py' if kind == 'untracked' else 'pyproject.toml')
    path.write_text('# changed\n')
    if kind == 'index': git(evidence.repo, 'add', 'pyproject.toml')
    with pytest.raises(ValueError, match='clean checkout'):
        evidence.verify()


def test_current_github_sha_must_match(evidence, monkeypatch):
    monkeypatch.setenv('GITHUB_SHA', '0' * 40)
    with pytest.raises(ValueError, match='GITHUB_SHA'):
        evidence.verify()


def test_committed_source_bytes_are_checked_with_git_show(evidence, monkeypatch):
    original = gate._git
    name = 'pyproject.toml'
    calls = []
    def changed_git_blob(repo, *args):
        calls.append(args)
        if args == ('show', evidence.kwargs['expected_commit'] + ':' + name):
            return b'# different committed content\n'
        return original(repo, *args)
    monkeypatch.setattr(gate, '_git', changed_git_blob)
    with pytest.raises(ValueError, match='committed source drift'):
        evidence.verify()
    assert ('show', evidence.kwargs['expected_commit'] + ':' + name) in calls


@pytest.mark.parametrize('name', ['pyproject.toml', '.github/scripts/verify_attention_block_split.py'])
def test_missing_source_pin_is_rejected(evidence, name):
    for mode in gate.MODES:
        del evidence.hashes[mode]['source_sha256'][name]
        reference = evidence.summaries[mode]['block_reference']
        for key in ('source_sha256_before', 'source_sha256_after'):
            del reference[key][name]
        evidence.rebind_reference(mode)
    evidence.write()
    with pytest.raises(ValueError, match='source closure'):
        evidence.verify()


def test_source_digest_drift_is_rejected(evidence):
    for mode in gate.MODES:
        evidence.hashes[mode]['source_sha256']['pyproject.toml'] = '0' * 64
        for key in ('source_sha256_before', 'source_sha256_after'):
            evidence.summaries[mode]['block_reference'][key]['pyproject.toml'] = '0' * 64
        evidence.rebind_reference(mode)
    evidence.write()
    with pytest.raises(ValueError, match='worktree source drift'):
        evidence.verify()


@pytest.mark.parametrize('location', ['actual', 'snapshot', 'ddr', 'extra', 'hashes', 'phase'])
def test_missing_or_unlinked_actual_outputs_are_rejected(evidence, location):
    result = evidence.summaries['pass']['cases'][0]['result']
    files = result['execution_identity']['files_sha256']
    if location == 'actual': del files['cold0/actual_q.bf16le']
    elif location == 'snapshot': del result['runs'][1]['snapshot_sha256']['writable_after_command21.bin']
    elif location == 'ddr': result['runs'][1]['ddr_sha256'] = '0' * 64
    elif location == 'extra': files['injected-reference.bin'] = '0' * 64
    elif location == 'hashes': evidence.hashes['pass']['output_sha256']['pass']['cold0']['q'] = '0' * 64
    else: del result['actual_sha256']['carried1']
    evidence.write()
    with pytest.raises(ValueError):
        evidence.verify()


@pytest.mark.parametrize('location', ['requested_mode', 'case_mode', 'result_mode', 'profile_mode', 'output_mode'])
def test_wrong_mode_inventory_is_rejected(evidence, location):
    summary = evidence.summaries[gate.MODES[1]]
    if location == 'requested_mode': summary['requested_mode'] = 'pass'
    elif location == 'case_mode': summary['cases'][0]['mode'] = 'pass'
    elif location == 'result_mode': summary['cases'][0]['result']['mode'] = 'pass'
    elif location == 'profile_mode': summary['measured_mac_profiles'] = {'pass': summary['measured_mac_profiles'][gate.MODES[1]]}
    else: evidence.hashes[gate.MODES[1]]['output_sha256'] = {'pass': summary['cases'][0]['result']['actual_sha256']}
    evidence.write()
    with pytest.raises(ValueError):
        evidence.verify()


def test_fresh_capture_hidden_inputs_can_differ_without_identical_stimulus_claim(evidence):
    mode = gate.MODES[1]
    evidence.set_input(mode, 'cold0_hidden.bf16le', digest('different host row0'))
    evidence.set_input(mode, 'cold1_hidden.bf16le', digest('different host row1'))
    evidence.write()
    report = evidence.verify()
    assert report['split_case_acceptance'] is True
    assert report['all_raw_hidden_observed_equal'] is False
    assert report['raw_hidden_observed_equal'] == dict.fromkeys(sorted(gate.HIDDEN_INPUTS), False)
    assert report['actual_raw_hidden_sha256'][mode]['cold1_hidden.bf16le'] == digest('different host row1')
    assert report['paired_identical_stimulus_fault_comparison'] is False


@pytest.mark.parametrize('name', ['weight_q.bf16le', 'weight_post_norm.bf16le', 'trig.bf16le'])
def test_weight_and_trig_differences_cannot_be_relabelled_as_same_model(evidence, name):
    evidence.set_input(gate.MODES[1], name, digest('changed ' + name))
    evidence.write()
    with pytest.raises(ValueError, match='weight/trig'):
        evidence.verify()


def test_model_revision_difference_is_rejected(evidence):
    evidence.summaries[gate.MODES[1]]['block_reference']['model_revision'] = '0' * 40
    evidence.rebind_reference(gate.MODES[1]); evidence.write()
    with pytest.raises(ValueError, match='model_revision'):
        evidence.verify()


@pytest.mark.parametrize('mutation', ['eligibility', 'summary_acceptance', 'split_pair', 'reset', 'fault_checkpoint',
                                      'fault_output', 'log', 'profile_log', 'profile_binary', 'profile_commands',
                                      'native', 'm128', 'performance', 'live_authority', 'reference_hash', 'native_failures'])
def test_scope_and_authority_cannot_be_inflated(evidence, mutation):
    mode = gate.MODES[1]
    summary = evidence.summaries[mode]
    result = summary['cases'][0]['result']
    profile = summary['measured_mac_profiles'][mode]
    if mutation == 'eligibility': result['numerical_acceptance_eligible'] = True
    elif mutation == 'summary_acceptance': summary['frozen_recipe_block_acceptance'] = True
    elif mutation == 'split_pair': result['same_dut_launches'] = 1
    elif mutation == 'reset': result['resets_between_launches'] = 1
    elif mutation == 'fault_checkpoint': result['runs'][1]['checkpoint_accepted'] = True
    elif mutation == 'fault_output': result['runs'][1]['inferred_final_output'] += 256
    elif mutation == 'log': result['execution_identity']['log_sha256'] = '0' * 64
    elif mutation == 'profile_log': profile['log_sha256'] = '0' * 64
    elif mutation == 'profile_binary': profile['binary_sha256'] = '0' * 64
    elif mutation == 'profile_commands': profile['runs'][1]['commands'].pop()
    elif mutation == 'native': summary['native_full_block_acceptance'] = True
    elif mutation == 'm128': result['model_m128_accepted'] = True
    elif mutation == 'performance': profile['performance_acceptance'] = True
    elif mutation == 'live_authority': result['live_authorities_verified'] = False
    elif mutation == 'reference_hash': evidence.hashes[mode]['block_reference_receipt_sha256'] = '0' * 64
    else: summary['native_full_block_failures']['baseline']['failed_producers'] = []
    evidence.write()
    with pytest.raises(ValueError):
        evidence.verify()


@pytest.mark.parametrize('mutation', ['missing', 'different_trace', 'wrong_build', 'wrong_inputs', 'numerical'])
def test_retained_prefix_preparation_is_required_and_bound(evidence, mutation):
    summary = evidence.summaries['pass']
    prefix = summary['deterministic_prefixes']
    if mutation == 'missing': del summary['deterministic_prefixes']
    elif mutation == 'different_trace': prefix['prefixes'][1]['event_sha256'] = '0' * 64
    elif mutation == 'wrong_build': prefix['binary_sha256'] = '0' * 64
    elif mutation == 'wrong_inputs': prefix['input_sha256']['cold0_hidden.bf16le'] = '0' * 64
    else: prefix['numerical_acceptance'] = True
    evidence.write()
    with pytest.raises(ValueError):
        evidence.verify()


@pytest.mark.parametrize('key,value', [('fresh_official_executions', 1), ('reused_official_executions', 2),
                                     ('planned_actual_launches', 1), ('planned_actual_invocations', 2),
                                     ('full128_executed', True), ('numerical_acceptance', False),
                                     ('representative_tokens_per_launch', True)])
def test_fresh_complete_m1_case_inventory_is_required(evidence, key, value):
    evidence.summaries['pass'][key] = value
    evidence.write()
    with pytest.raises(ValueError):
        evidence.verify()


def test_self_consistent_actual_output_hashes_must_match_frozen_reference(evidence):
    result = evidence.summaries['pass']['cases'][0]['result']
    changed = digest('different actual q')
    result['actual_sha256']['cold0']['q'] = changed
    result['execution_identity']['files_sha256']['cold0/actual_q.bf16le'] = changed
    evidence.hashes['pass']['output_sha256']['pass']['cold0']['q'] = changed
    evidence.write()
    with pytest.raises(ValueError, match='q'):
        evidence.verify()


def test_build_identity_historical_field_requires_complete_map(evidence):
    evidence.hashes['pass']['build_identity_sha256'] = digest('not a build identity map')
    evidence.write()
    with pytest.raises(ValueError, match='source map'):
        evidence.verify()


def test_additional_live_source_cannot_escape_source_inventory(evidence):
    path = evidence.repo / 'chisel/continuous_prefill/scripts/unbound_helper.py'
    path.write_text('# control helper\n')
    git(evidence.repo, 'add', '.')
    git(evidence.repo, '-c', 'user.name=Control Tests', '-c', 'user.email=control@example.invalid', 'commit', '-qm', 'new helper')
    commit = git(evidence.repo, 'rev-parse', 'HEAD')
    evidence.kwargs['expected_commit'] = commit
    for summary in evidence.summaries.values():
        summary['git_head'] = commit
        summary['build']['source_base_commit'] = commit
        summary['build_transfer']['source_commit'] = commit
    evidence.write()
    with pytest.raises(ValueError, match='incomplete live source closure'):
        evidence.verify()


def test_no_authority_without_explicit_trusted_inputs(evidence):
    with pytest.raises(TypeError):
        gate.verify(evidence.kwargs['pass_compact'], evidence.kwargs['fault_compact'])
    for key in ('expected_pass_summary_sha256', 'expected_package_sha256'):
        values = dict(evidence.kwargs, **{key: None})
        with pytest.raises(ValueError, match='trusted SHA256'):
            gate.verify(**values)
    with pytest.raises(SystemExit) as raised:
        gate.parser().parse_args(['--pass-compact', 'pass', '--fault-compact', 'fault', '--output', 'result.json'])
    assert raised.value.code == 2


def test_duplicate_keys_and_symlinks_are_rejected(evidence):
    path = evidence.kwargs['pass_compact'] / 'summary.json'
    raw = path.read_text()
    path.write_text('{"status":"forged",' + raw[1:])
    evidence.kwargs['expected_pass_summary_sha256'] = gate.sha(path)
    with pytest.raises(ValueError, match='duplicate JSON key'):
        evidence.verify()
    path.unlink(); path.symlink_to(evidence.kwargs['fault_compact'] / 'summary.json')
    with pytest.raises(ValueError, match='symlink'):
        evidence.verify()


def test_cli_failure_preserves_authenticated_native_records(evidence, tmp_path, monkeypatch, capsys):
    evidence.summaries['pass']['status'] = 'FAIL_FRESH_HOST_ATTENTION_BLOCK_CASE_M1'
    evidence.write()
    output = tmp_path / 'acceptance.json'
    values = dict(evidence.kwargs)
    values.pop('repo')
    argv = [part for key, value in values.items() for part in ('--' + key.replace('_', '-'), str(value))]
    argv.extend(['--output', str(output)])
    assert gate.main(argv) == 1
    report = json.loads(output.read_text())
    assert report['status'] == gate.FAIL and report['split_case_acceptance'] is False
    assert report['authenticated_partial_evidence']['pass']['summary']['native_full_block_failures'] == evidence.summaries['pass']['native_full_block_failures']
    assert gate.AUTHORITY_SCOPE in capsys.readouterr().out
