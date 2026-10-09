"""Fail-closed isolation/identity tests; no EDA compiler or RTL runs here."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_selector_gate as S
import run_codegen as C
import run_profile as P


def original():
    root = Path(os.environ.get('ATTENTION_PROFILE_SOURCE_ROOT', P.DIAGNOSTIC_ROOT))
    return subprocess.check_output(['git', '-C', str(root), 'show',
        P.PIN+':chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh'])


def test_baseline_is_exact_emit_prefix_then_four_original_checks(tmp_path):
    root = tmp_path/'source with spaces'
    raw = original()
    base = P.relocated_builder(raw, root, root/'chisel/continuous_prefill/tests/host_bf16_attention_core.cpp')
    emitted = S.baseline_builder(raw, root)
    assert emitted == (base.split(S.PREPARE_IDMA, 1)[0]+S.PREPARE_IDMA+'\n'+
                       C.POST_CODEGEN_CHECKS+'echo BASELINE_EMIT_ONLY_STOP\nexit 0\n')
    assert emitted.count(P.rtl_admission_guard()) == 1
    assert emitted.count(C.POST_CODEGEN_CHECKS) == 1
    assert emitted.index(P.rtl_admission_guard()) < emitted.index(S.PREPARE_IDMA)
    assert 'hier_verilation' not in emitted and 'verilator --cc' not in emitted
    assert C.BUILD_STOP not in emitted
    assert '-J-Xmx1500m' in emitted
    path = tmp_path/'baseline.sh'
    path.write_text(emitted)
    subprocess.run(['bash', '-n', str(path)], check=True)


def test_candidate_changes_only_admission_cache_and_exit_boundary(tmp_path):
    root, baseline = tmp_path/'source', tmp_path/'baseline with spaces'
    raw = original()
    emitted = S.candidate_builder(raw, root, baseline)
    base = C.codegen_builder(raw, root)
    original_argv = next(line for line in base.splitlines() if 'MAKEFLAGS=-n verilator' in line)
    assert original_argv in emitted
    assert P.rtl_admission_guard() not in emitted
    assert P.RTL_SHA256 not in emitted
    assert 'gqa_selector_candidate.py' in emitted
    assert emitted.index('gqa_selector_candidate.py') < emitted.index('MAKEFLAGS=-n verilator')
    assert emitted.count('hier_verilation >"$OUT/hierarchy_verilation.log" 2>&1') == 1
    assert emitted.count(C.POST_CODEGEN_CHECKS) == 1 and C.BUILD_STOP not in emitted
    assert "cache=Path(os.environ['COURSIER_CACHE'])" in emitted
    assert 'str(p.relative_to(cache))' in emitted
    assert 'ln -s -- ' in emitted and ' "$OUT/maven"' in emitted
    assert 'OPT_FAST=-O2 OPT_SLOW=-O0' in emitted
    assert '-ffp-contract=off -fno-fast-math' in emitted
    assert 'native_weight_hierarchy.vlt' in emitted and '--expand-limit' not in emitted
    path = tmp_path/'candidate.sh'
    path.write_text(emitted)
    subprocess.run(['bash', '-n', str(path)], check=True)


@pytest.mark.parametrize('anchor', [S.PREPARE_IDMA, C.POST_CODEGEN_CHECKS])
def test_baseline_builder_fails_closed_on_frozen_anchor_drift(tmp_path, anchor):
    with pytest.raises(ValueError):
        S.baseline_builder(original().replace(anchor.encode(), b'changed'), tmp_path)


def test_candidate_rejects_changed_compiler_cache_recipe(tmp_path):
    raw = original().replace(b'export COURSIER_CACHE="$OUT/maven"', b'export COURSIER_CACHE="$OUT/changed"')
    with pytest.raises(ValueError, match='shared compiler cache anchor'):
        S.candidate_builder(raw, tmp_path, tmp_path/'baseline')


def git_fixture(tmp_path, monkeypatch, files, untracked=()):
    """Supply an exact Git tree without creating commits or using an index."""
    rows = []
    for name, value in files.items():
        mode, data = value
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == '120000':
            path.symlink_to(data.decode())
        else:
            path.write_bytes(data)
            path.chmod(0o755 if mode == '100755' else 0o644)
        oid = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        rows.append((mode+' blob '+oid+'\t'+name).encode())
    monkeypatch.setattr(S, 'git', lambda root, *args: S.PIN if args == ('rev-parse', 'HEAD') else '')
    def check_output(argv):
        if argv[3] == 'ls-tree':
            return b'\0'.join(rows)+b'\0'
        if argv[3] == 'ls-files':
            return '\0'.join(untracked).encode()
        raise AssertionError(argv)
    monkeypatch.setattr(S.subprocess, 'check_output', check_output)


def test_all_tracked_blobs_and_modes_are_checked(tmp_path, monkeypatch):
    files = {'a.scala':('100644', b'object A\n'), 'run.sh':('100755', b'exit 0\n'),
             'link':('120000', b'a.scala')}
    git_fixture(tmp_path, monkeypatch, files)
    actual = S.verify_git_sources(tmp_path, S.PIN)
    assert set(actual) == set(files)
    assert actual['link'] == hashlib.sha256(b'a.scala').hexdigest()
    (tmp_path/'a.scala').write_text('object Changed\n')
    with pytest.raises(ValueError, match='tracked source differs'):
        S.verify_git_sources(tmp_path, S.PIN)


def test_executable_mode_drift_is_rejected(tmp_path, monkeypatch):
    git_fixture(tmp_path, monkeypatch, {'run.sh':('100755', b'exit 0\n')})
    (tmp_path/'run.sh').chmod(0o644)
    with pytest.raises(ValueError, match='executable mode'):
        S.verify_git_sources(tmp_path, S.PIN)


def test_overlay_allows_exact_target_and_new_test_only(tmp_path, monkeypatch):
    files = {S.TARGET:('100644', b'baseline'), 'matrix.scala':('100644', b'fixed')}
    git_fixture(tmp_path, monkeypatch, files, untracked=(S.SPEC_TARGET,))
    target, spec = tmp_path/S.TARGET, tmp_path/S.SPEC_TARGET
    target.write_bytes(b'candidate')
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_bytes(b'test')
    overrides = {S.TARGET:S.sha(target), S.SPEC_TARGET:S.sha(spec)}
    actual = S.verify_git_sources(tmp_path, S.PIN, overrides)
    assert actual[S.TARGET] == overrides[S.TARGET] and actual[S.SPEC_TARGET] == overrides[S.SPEC_TARGET]
    (tmp_path/'matrix.scala').write_bytes(b'changed')
    with pytest.raises(ValueError, match='tracked source differs'):
        S.verify_git_sources(tmp_path, S.PIN, overrides)


def test_extra_override_or_untracked_file_is_rejected(tmp_path, monkeypatch):
    git_fixture(tmp_path, monkeypatch, {'a':('100644', b'a')}, untracked=('extra.scala',))
    with pytest.raises(ValueError, match='unapproved untracked'):
        S.verify_git_sources(tmp_path, S.PIN)
    with pytest.raises(ValueError, match='overlay whitelist'):
        S.verify_git_sources(tmp_path, S.PIN, {'a':'x'})


def test_recorded_sources_must_match_independent_verified_map():
    S.verify_recorded_sources({'a.scala':'expected'}, {'a.scala':'expected', 'b.scala':'other'})
    for recorded in ({}, {'new.scala':'x'}, {'a.scala':'wrong'}, {'../a.scala':'expected'}):
        with pytest.raises(ValueError):
            S.verify_recorded_sources(recorded, {'a.scala':'expected'})


def test_jar_cache_is_verified_against_original_baseline_bytes(tmp_path):
    jar = tmp_path/'repo/a.jar'
    jar.parent.mkdir()
    jar.write_bytes(b'original compiler jar')
    bound = {'repo/a.jar':S.sha(jar)}
    S.verify_jars(tmp_path, bound)
    jar.write_bytes(b'rebound compiler jar')
    with pytest.raises(ValueError, match='baseline compiler dependency changed'):
        S.verify_jars(tmp_path, bound)


def test_test_command_is_serial_pinned_and_has_no_test_exclusions(tmp_path):
    command = S.test_command(tmp_path)
    assert command[-2:] == ['testOnly '+suite for suite in S.SUITES]
    assert '-J-Xmx1500m' in command and '-J-XX:ActiveProcessorCount=1' in command
    assert '-Dsbt.task.cpus=1' in command
    assert '-Dsbt.ivy.home='+str(tmp_path/'sbt/ivy') in command
    assert S.MAKEFLAGS == '-j1 VK_PCH_I_FAST= VK_PCH_I_SLOW='
    assert not any(x in ' '.join(command) for x in (' -z ', ' -l ', ' -n ', 'testQuick'))


def write_test_reports(root, counts=(1, 6), skipped=False):
    output = root/'target/test-reports'
    output.mkdir(parents=True, exist_ok=True)
    for suite, count in zip(S.SUITES, counts):
        report = ET.Element('testsuite', name=suite, tests=str(count), failures='0', errors='0', skipped='0')
        for index in range(count):
            case = ET.SubElement(report, 'testcase', name='case '+str(index))
            if skipped and index == 0:
                ET.SubElement(case, 'skipped')
        ET.ElementTree(report).write(output/('TEST-'+suite+'.xml'))


def test_reports_require_actual_selector_plus_all_six_owner_tests(tmp_path):
    write_test_reports(tmp_path)
    receipts = S.test_receipts(tmp_path)
    assert receipts[S.SUITES[0]]['passed'] == 1 and receipts[S.SUITES[1]]['passed'] == 6
    write_test_reports(tmp_path, counts=(1, 5))
    with pytest.raises(ValueError, match='all six'):
        S.test_receipts(tmp_path)


def test_skipped_tests_cannot_establish_gate(tmp_path):
    write_test_reports(tmp_path, skipped=True)
    with pytest.raises(ValueError, match='skipped'):
        S.test_receipts(tmp_path)


@pytest.mark.parametrize('name', ['obj/test.o', 'obj/test.a', 'obj/test.gch', 'obj/VHostBlockTop'])
def test_full_top_compilation_is_rejected(tmp_path, name):
    path = tmp_path/name
    path.parent.mkdir()
    path.write_bytes(b'forbidden')
    with pytest.raises(ValueError, match='full-top compilation artifacts'):
        S.reject_full_top_compilation(tmp_path)


def test_log_tail_is_bounded(tmp_path):
    path = tmp_path/'log'
    path.write_bytes(b'a'*(S.LOG_TAIL_BYTES*3)+b'last line')
    result = S.tail(path)
    assert len(result.encode()) == S.LOG_TAIL_BYTES and result.endswith('last line')


def complete_concat_inventory():
    return dict(truncated=False, file_discovery_truncated=False, syntax_error_files=0,
        unresolved_calls=0, parameter_or_context_truncation_count=0, calls=128,
        literal_output_widths={'4096':64, '128':64}, selected_source_bytes=1024,
        selected_source_limit_bytes=12*1024*1024,
        selected_source=[{'file':'obj/VHostBlockTop___024root.h'},
                         {'file':'runtime_0/verilated_funcs.h', 'selection_reason':'runtime_helper_implementation'},
                         {'file':'obj/new_generated_caller.cpp'}],
        calls_by_file=[{'file':'obj/new_generated_caller.cpp', 'calls':128}])


def complete_concat_calls():
    return [dict(parse_status='parsed', function={'name':'caller'},
                 argument_count=6, parameters=[{} for _ in range(6)],
                 width_constants={'obits':width, 'lbits':width-32, 'rbits':32})
            for width in [4096]*64+[128]*64]


def test_structure_gate_uses_complete_scan_without_old_sampled_filenames():
    report = S.validate_concat_inventory(complete_concat_inventory(), complete_concat_calls())
    assert report['giant_concat_chain_absent'] is True
    assert report['largest_concat_output_bits'] == 4096
    assert report['concat_calls'] == 128 and report['old_sampled_filenames_required'] is False


@pytest.mark.parametrize('change', [
    {'truncated':True}, {'file_discovery_truncated':True}, {'syntax_error_files':1},
    {'unresolved_calls':1}, {'parameter_or_context_truncation_count':1},
    {'literal_output_widths':{'None':128}}, {'literal_output_widths':{'4096':127}},
    {'literal_output_widths':{'8192':128}}, {'calls_by_file':[{'file':'missing.cpp', 'calls':128}]},
    {'selected_source_bytes':12*1024*1024+1}, {'selected_source':[]},
])
def test_structure_gate_rejects_incomplete_or_still_giant_concats(change):
    inventory = complete_concat_inventory()
    inventory.update(change)
    with pytest.raises(ValueError):
        S.validate_concat_inventory(inventory, complete_concat_calls())


def test_structure_gate_requires_left_and_right_literal_widths_too():
    evidence = complete_concat_calls()
    evidence[0]['width_constants']['lbits'] = None
    with pytest.raises(ValueError, match='left/right width'):
        S.validate_concat_inventory(complete_concat_inventory(), evidence)


def test_structure_gate_reports_function_name_annotation_gap_without_hiding_widths():
    inventory, evidence = complete_concat_inventory(), complete_concat_calls()
    inventory['unresolved_calls'] = 64
    for call in evidence[:64]:
        call['function'] = None
    report = S.validate_concat_inventory(inventory, evidence)
    assert report['missing_function_annotations'] == 64
    assert report['giant_concat_chain_absent'] is True


def test_structure_gate_rejects_wrong_argument_count_and_width_equation():
    for change in ({'argument_count':5}, {'width_constants':{'obits':4096, 'lbits':1024, 'rbits':32}}):
        evidence = complete_concat_calls()
        evidence[0].update(change)
        with pytest.raises(ValueError):
            S.validate_concat_inventory(complete_concat_inventory(), evidence)


def module_source_fixture(tmp_path, remaining=None):
    from concat_inventory import MAX_SOURCE_BYTES
    module = 'Bf16CausalGqaOwner'
    sources, identities = {}, {}
    for variant, literal in (('baseline', b'0'), ('candidate', b'1')):
        raw = b'module '+module.encode()+b';\n  wire bit_value = '+literal+b';\nendmodule\n'
        path = tmp_path/(variant+'.sv')
        path.write_bytes(b'// Outside the extracted module.\n'+raw+b'module Other;\nendmodule\n')
        sources[variant] = path
        identities[variant] = {'modules':{module:{'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}}}
        identities[variant+'_sha256'] = S.sha(path)
    output = tmp_path/'selected-source'
    output.mkdir()
    selected = []
    if remaining is not None:
        used = MAX_SOURCE_BYTES-remaining
        prior = output/'source/existing.cpp'
        prior.parent.mkdir()
        with prior.open('wb') as stream:
            stream.truncate(used)
        selected.append(dict(file='existing.cpp', saved_as='source/existing.cpp', bytes=used, sha256=S.sha(prior)))
    else:
        used = 0
    inventory = dict(selected_source=selected, selected_source_bytes=used,
                     selected_source_limit_bytes=MAX_SOURCE_BYTES, selection_skipped=[])
    (output/'selected_source_manifest.json').write_text(json.dumps(selected))
    return sources, identities, output, inventory


def test_changed_owner_modules_are_preserved_verbatim_with_hash_manifest(tmp_path):
    sources, comparison, output, inventory = module_source_fixture(tmp_path)
    receipts = S.preserve_changed_modules(sources['baseline'], sources['candidate'], comparison, output, inventory)
    assert all(item['preserved'] for item in receipts)
    for item in receipts:
        raw = (output/item['saved_as']).read_bytes()
        assert raw.startswith(b'module Bf16CausalGqaOwner;\n') and raw.endswith(b'\nendmodule\n')
        assert b'Outside' not in raw and b'module Other' not in raw
        assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
    assert inventory['selected_source_bytes'] == sum(item['bytes'] for item in receipts)
    assert json.loads((output/'selected_source_manifest.json').read_text()) == inventory['selected_source']
    assert json.loads((output/'inventory_summary.json').read_text()) == inventory


def test_module_preservation_obeys_shared_cap_and_reports_skipped_sources(tmp_path):
    # Exactly enough remaining space for the baseline module; candidate skips.
    size = len(b'module Bf16CausalGqaOwner;\n  wire bit_value = 0;\nendmodule\n')
    sources, comparison, output, inventory = module_source_fixture(tmp_path, remaining=size)
    receipts = S.preserve_changed_modules(sources['baseline'], sources['candidate'], comparison, output, inventory)
    assert receipts[0]['preserved'] is True
    assert receipts[1]['preserved'] is False and receipts[1]['reason'] == 'source_byte_budget'
    assert inventory['selected_source_bytes'] == inventory['selected_source_limit_bytes']
    assert len(inventory['selection_skipped']) == 1
    assert not (output/'source/modules/candidate/Bf16CausalGqaOwner.sv').exists()


@pytest.mark.parametrize('changed', ['source', 'hash', 'size', 'manifest'])
def test_module_preservation_rejects_drift_without_saving_unverified_bytes(tmp_path, changed):
    sources, comparison, output, inventory = module_source_fixture(tmp_path)
    identity = comparison['baseline']['modules']['Bf16CausalGqaOwner']
    if changed == 'source':
        sources['baseline'].write_bytes(b'changed')
    elif changed == 'hash':
        identity['sha256'] = '0'*64
    elif changed == 'size':
        identity['bytes'] -= 1
    else:
        (output/'selected_source_manifest.json').write_text('[{}]')
    with pytest.raises(ValueError):
        S.preserve_changed_modules(sources['baseline'], sources['candidate'], comparison, output, inventory)
    assert not (output/'source/modules').exists()


def failure_module_fixture(tmp_path):
    from gqa_selector_candidate import preserve_failure
    out = tmp_path/'out'
    baseline, candidate = out/'host_build/generated/HostBlockTop.sv', out/'candidate_build/generated/HostBlockTop.sv'
    for path, bit in ((baseline, '0'), (candidate, '1')):
        path.parent.mkdir(parents=True)
        path.write_text('module Bf16CausalGqaOwner;\nwire value = '+bit+';\nendmodule\n'
                        'module mem_8x512;\nwire value = '+bit+';\nendmodule\n')
    failure = out/'candidate_build/generated_rtl_identity.failure.json'
    preserve_failure(baseline, candidate, failure.with_name('generated_rtl_identity.json'), 'strict module mismatch')
    summary = dict(status='INCOMPLETE_SELECTOR_GATE', error={'type':'ValueError','message':'original strict gate failure'},
                   numerical_acceptance=False)
    return out, failure, summary, {}


def test_pre_verilation_failure_modules_reach_compact_summary_and_hashes(tmp_path):
    out, receipt, summary, hashes = failure_module_fixture(tmp_path)
    original_error = dict(summary['error'])
    S.collect_failure_module_evidence(out, summary, hashes)
    assert summary['status'] == 'INCOMPLETE_SELECTOR_GATE' and summary['error'] == original_error
    assert summary['numerical_acceptance'] is False
    assert summary['generated_rtl_failure'] == json.loads(receipt.read_text())
    assert summary['failure_module_evidence']['verified'] is True
    assert summary['failure_module_evidence']['files'] == 4
    assert hashes['generated_rtl_failure_receipt_sha256'] == S.sha(receipt)
    assert hashes['selected_source_sha256'] == hashes['failure_module_source_sha256']
    for name, digest in hashes['failure_module_source_sha256'].items():
        assert name.startswith('selected-source/failure-module-diff/') and S.sha(out/name) == digest


@pytest.mark.parametrize('problem', ['hash', 'unlisted', 'symlink', 'traversal', 'oversized_receipt', 'claims_pass'])
def test_invalid_failure_modules_are_quarantined_without_replacing_original_error(tmp_path, problem):
    out, receipt, summary, hashes = failure_module_fixture(tmp_path)
    report = json.loads(receipt.read_text())
    first = out/'selected-source'/report['preserved_sources'][0]['path']
    if problem == 'hash':
        first.write_bytes(b'x'*first.stat().st_size)
    elif problem == 'unlisted':
        (first.parent/'unlisted.sv').write_text('module unlisted;\nendmodule\n')
    elif problem == 'symlink':
        first.unlink()
        first.symlink_to(out/'host_build/generated/HostBlockTop.sv')
    elif problem == 'traversal':
        report['preserved_sources'][0]['path'] = '../outside.sv'
        receipt.write_text(json.dumps(report))
    elif problem == 'oversized_receipt':
        receipt.write_bytes(b' '*(2*1024*1024+1))
    else:
        report['status'] = 'PASS'
        receipt.write_text(json.dumps(report))
    original_error = dict(summary['error'])
    S.collect_failure_module_evidence(out, summary, hashes)
    assert summary['status'] == 'INCOMPLETE_SELECTOR_GATE' and summary['error'] == original_error
    assert summary['failure_module_evidence_error']['quarantined_from_upload'] is True
    assert not hashes and 'generated_rtl_failure' not in summary
    assert not (out/'selected-source/failure-module-diff').exists()
    assert (out/'rejected-failure-module-diff').is_dir()


def test_failure_module_cap_includes_already_selected_source_bytes(tmp_path):
    from concat_inventory import MAX_SOURCE_BYTES
    out, receipt, summary, hashes = failure_module_fixture(tmp_path)
    existing = out/'selected-source/source/existing.cpp'
    existing.parent.mkdir()
    with existing.open('wb') as stream:
        stream.truncate(MAX_SOURCE_BYTES)
    S.collect_failure_module_evidence(out, summary, hashes)
    assert 'shared source cap' in summary['failure_module_evidence_error']['message']
    assert not hashes and existing.is_file()
    assert not (out/'selected-source/failure-module-diff').exists()


def test_failure_revalidation_revokes_stale_hash_claims_and_keeps_rejection_reason(tmp_path):
    out, receipt, summary, hashes = failure_module_fixture(tmp_path)
    S.collect_failure_module_evidence(out, summary, hashes)
    entry = next(iter(hashes['failure_module_source_sha256']))
    (out/entry).write_text('corrupted')
    S.collect_failure_module_evidence(out, summary, hashes)
    reason = dict(summary['failure_module_evidence_error'])
    assert 'failure_module_evidence' not in summary and 'generated_rtl_failure' not in summary
    assert 'failure_module_source_sha256' not in hashes and not hashes['selected_source_sha256']
    S.collect_failure_module_evidence(out, summary, hashes)
    assert summary['failure_module_evidence_error'] == reason


def test_missing_optional_failure_evidence_leaves_original_receipt_unchanged(tmp_path):
    summary, hashes = {'status':'INCOMPLETE_SELECTOR_GATE'}, {'existing':'hash'}
    S.collect_failure_module_evidence(tmp_path, summary, hashes)
    assert summary == {'status':'INCOMPLETE_SELECTOR_GATE'} and hashes == {'existing':'hash'}


def test_forced_supervisor_collects_precreated_failure_evidence(tmp_path):
    out, receipt, summary, hashes = failure_module_fixture(tmp_path)
    compact = out/'compact'
    compact.mkdir()
    (compact/'summary.json').write_text(json.dumps(summary))
    (compact/'source_input_hashes.json').write_text(json.dumps(hashes))
    assert S.finalize_selector_supervision(out, {'returncode':1, 'forced_shutdown':True}) == 1
    result = json.loads((compact/'summary.json').read_text())
    result_hashes = json.loads((compact/'source_input_hashes.json').read_text())
    assert result['status'] == 'INCOMPLETE_SELECTOR_GATE' and result['error'] == summary['error']
    assert result['failure_module_evidence']['files'] == 4
    assert result_hashes['generated_rtl_failure_receipt_sha256'] == S.sha(receipt)


def test_supervisor_uses_single_1800_second_process_tree_budget(tmp_path, monkeypatch):
    seen = {}
    def supervise(command, timeout_seconds):
        seen.update(command=command, seconds=timeout_seconds)
        return {'returncode':0, 'forced_shutdown':False}
    monkeypatch.setattr(S, 'arguments', lambda: object())
    monkeypatch.setattr(S, 'checked_paths', lambda args: (tmp_path/'source', tmp_path/'out'))
    monkeypatch.setattr(S, 'imports', lambda source: SimpleNamespace(supervise_process=supervise))
    monkeypatch.setattr(S, 'finalize_selector_supervision', lambda out, outcome: outcome['returncode'])
    with pytest.raises(SystemExit) as done:
        S.main()
    assert done.value.code == 0 and seen['seconds'] == 1800
    assert 'from run_selector_gate import worker_entry' in seen['command'][2]
    assert 'run_profile import worker_entry' not in seen['command'][2]


def test_timeout_supervision_preserves_selector_scope_and_partial_evidence(tmp_path):
    output = tmp_path/'out'
    compact = output/'compact'
    compact.mkdir(parents=True)
    (compact/'summary.json').write_text(json.dumps({'stage':'actual_selector_and_six_owner_rtl_tests',
        'status':'RUNNING_SELECTOR_GATE', 'baseline':{'rtl_sha256':S.RTL_SHA256}}))
    (compact/'source_input_hashes.json').write_text('{"source_sha256":{"source":"original"}}')
    result = {'returncode':1, 'forced_shutdown':True, 'reason':'total_budget_timeout'}
    assert S.finalize_selector_supervision(output, result) == 1
    report = json.loads((compact/'summary.json').read_text())
    assert report['status'] == 'INCOMPLETE_SELECTOR_GATE'
    assert report['stage'] == 'actual_selector_and_six_owner_rtl_tests'
    assert report['baseline']['rtl_sha256'] == S.RTL_SHA256
    assert report['numerical_acceptance'] is False and report['full_top_behavioral_equivalence'] is False
    assert json.loads((compact/'source_input_hashes.json').read_text()) == {'source_sha256':{'source':'original'}}


def test_no_model_or_full_top_execution_path_is_in_worker():
    text = (HERE/'run_selector_gate.py').read_text()
    assert 'frozen.rebuild_session(' not in text and 'generate_core_reference(' not in text
    assert 'frozen.run_case(' not in text and 'baseline_manifest =' in text
    assert 'frozen.verify_checkout(PIN, hashes[\'source_sha256\'])' in text
    assert "hashes['candidate_source_sha256']" in text
    assert 'comparison = module_diff(' in text
