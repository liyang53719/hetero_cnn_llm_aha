#!/usr/bin/env python3
"""1800-second, default-off GQA selector equivalence/codegen diagnostic.

The immutable baseline receipt and the candidate overlay receipt are separate.
Only the owner and bit-selector unit tests execute RTL. No full-top C++ build,
full-top simulation, model capture, reference execution, or acceptance rerun.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from run_codegen import codegen_builder, POST_CODEGEN_CHECKS
from run_profile import (PIN, RTL_SHA256, HERE, DIAGNOSTIC_ROOT, require, sha, git,
                         checked_paths, imports, frozen_file, relocated_builder,
                         rtl_admission_guard, source_environment, finalize_supervision)
from gqa_selector_candidate import TARGET, BASE_SHA256, transform, module_diff

BUDGET_SECONDS = 1800
FAILURE_RESERVE_SECONDS = 60
PREPARE_IDMA = 'python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"'
SPEC_NAME = 'GqaMatrixResultSelectSpec.scala'
SPEC_TARGET = 'chisel/continuous_prefill/src/test/scala/heteronpu/continuous/' + SPEC_NAME
SUITES = ('heteronpu.continuous.GqaMatrixResultSelectSpec',
          'heteronpu.continuous.Bf16CausalGqaOwnerSpec')
MAKEFLAGS = '-j1 VK_PCH_I_FAST= VK_PCH_I_SLOW='
LOG_TAIL_BYTES = 6000


def baseline_builder(raw, source):
    """Use original compile/emit and exact-SV admission, then read-only checks."""
    text = relocated_builder(raw, source,
                             source/'chisel/continuous_prefill/tests/host_bf16_attention_core.cpp')
    require(text.count(PREPARE_IDMA) == 1, 'frozen emit boundary changed')
    require(text.count(POST_CODEGEN_CHECKS) == 1, 'frozen read-only checks changed')
    # The toolchain verifier consumes idma_identity.json. This copied verifier
    # only checks the pinned export and writes a relocated filelist/receipt.
    return (text.split(PREPARE_IDMA, 1)[0] + PREPARE_IDMA + '\n' +
            POST_CODEGEN_CHECKS + 'echo BASELINE_EMIT_ONLY_STOP\nexit 0\n')


def candidate_builder(raw, source, baseline):
    """Same codegen recipe, explicit candidate admission and shared cache paths."""
    text = codegen_builder(raw, source)
    guard = rtl_admission_guard()
    require(text.count(guard) == 1, 'baseline admission anchor changed')
    candidate_guard = ('python3 ' + shlex.quote(str(HERE/'gqa_selector_candidate.py')) +
                       ' ' + shlex.quote(str(baseline/'generated/HostBlockTop.sv')) +
                       ' "$OUT/generated/HostBlockTop.sv" "$OUT/generated_rtl_identity.json"\n')
    text = text.replace(guard, candidate_guard, 1)
    # Both SBT invocations use these exact cache directories. Hash the actual
    # shared cache; never transplant a receipt from a different directory.
    replacements = {
        'export COURSIER_CACHE="$OUT/maven"':
            'export COURSIER_CACHE=' + shlex.quote(str(baseline/'maven')),
        '"-Dsbt.global.base=$OUT/sbt/global"': shlex.quote('-Dsbt.global.base='+str(baseline/'sbt/global')),
        '"-Dsbt.boot.directory=$OUT/sbt/boot"': shlex.quote('-Dsbt.boot.directory='+str(baseline/'sbt/boot')),
        '"-Dsbt.ivy.home=$OUT/sbt/ivy"': shlex.quote('-Dsbt.ivy.home='+str(baseline/'sbt/ivy')),
        'import hashlib,json,sys\nout=Path(sys.argv[1]);jars=sorted((out/\'maven\').rglob(\'*.jar\'))':
            'import hashlib,json,os,sys\nout=Path(sys.argv[1]);cache=Path(os.environ[\'COURSIER_CACHE\']);jars=sorted(cache.rglob(\'*.jar\'))',
        "str(p.relative_to(out/'maven'))": 'str(p.relative_to(cache))',
    }
    for old, new in replacements.items():
        require(text.count(old) == 1, 'shared compiler cache anchor changed: '+old)
        text = text.replace(old, new, 1)
    # The unchanged toolchain verifier resolves non-offline jars at OUT/maven.
    # This is an explicit cache link, not a copied/fabricated jar receipt.
    cache_link = 'ln -s -- ' + shlex.quote(str(baseline/'maven')) + ' "$OUT/maven"\n'
    anchor = 'source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"\n'
    require(text.count(anchor) == 1, 'runtime setup anchor changed')
    return text.replace(anchor, cache_link + anchor, 1)


def _safe_name(name):
    path = Path(name)
    require(bool(name) and not path.is_absolute() and '..' not in path.parts,
            'unsafe identity path: '+name)
    return path


def _entry_bytes(root, name, mode):
    path = root/_safe_name(name)
    require(path.parent.resolve().is_relative_to(root.resolve()), 'source parent escaped checkout: '+name)
    if mode == '120000':
        require(path.is_symlink(), 'tracked symlink changed: '+name)
        return os.fsencode(os.readlink(path))
    require(mode in ('100644', '100755') and path.is_file() and not path.is_symlink(),
            'tracked source missing or wrong type: '+name)
    require(bool(path.stat().st_mode & stat.S_IXUSR) == (mode == '100755'),
            'tracked executable mode changed: '+name)
    return path.read_bytes()


def verify_git_sources(root, commit, overrides=None):
    """Check every tracked blob/mode and reject every unapproved new source."""
    overrides = dict(overrides or {})
    require(not overrides or set(overrides) == {TARGET, SPEC_TARGET}, 'overlay whitelist changed')
    require(git(root, 'rev-parse', 'HEAD') == commit, 'source HEAD changed')
    require(not git(root, 'diff', '--cached', '--name-only', commit, '--'), 'source index changed')
    rows = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', commit]).split(b'\0')
    actual, tracked = {}, set()
    for row in filter(None, rows):
        header, raw_name = row.split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        name = raw_name.decode('utf-8')
        require(kind == 'blob', 'unsupported tracked object: '+name)
        raw = _entry_bytes(root, name, mode)
        digest = hashlib.sha256(raw).hexdigest()
        tracked.add(name)
        if name in overrides:
            require(digest == overrides[name], 'candidate source drift: '+name)
        else:
            blob_digest = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            require(blob_digest == blob, 'tracked source differs from baseline: '+name)
        actual[name] = digest
    untracked = set(filter(None, subprocess.check_output(
        ['git', '-C', str(root), 'ls-files', '--others', '--exclude-standard', '-z']).decode().split('\0')))
    allowed_new = set(overrides)-tracked
    require(untracked == allowed_new, 'unapproved untracked source: '+repr(sorted(untracked ^ allowed_new)))
    if overrides:
        require(TARGET in tracked and SPEC_TARGET not in tracked,
                'candidate must change one compiled source and add one test')
        for name in allowed_new:
            path = root/_safe_name(name)
            require(path.is_file() and not path.is_symlink() and
                    path.parent.resolve().is_relative_to(root.resolve()) and sha(path) == overrides[name],
                    'candidate test source drift: '+name)
            actual[name] = overrides[name]
    return actual


def verify_recorded_sources(recorded, expected):
    require(type(recorded) is dict and recorded, 'missing recorded source closure')
    for name, digest in recorded.items():
        _safe_name(name)
        require(expected.get(name) == digest, 'recorded source not in verified identity: '+name)


def verify_jars(cache, expected):
    require(type(expected) is dict and expected, 'missing compiler dependency map')
    for name, digest in expected.items():
        path = cache/_safe_name(name)
        require(path.is_file() and not path.is_symlink() and sha(path) == digest,
                'baseline compiler dependency changed: '+name)


def test_command(baseline):
    return ['sbt', '-batch', '-J-Xss8m', '-J-Xmx1500m', '-J-XX:ActiveProcessorCount=1',
            '-Dsbt.task.cpus=1', '-Dsbt.supershell=false',
            '-Dsbt.global.base='+str(baseline/'sbt/global'),
            '-Dsbt.boot.directory='+str(baseline/'sbt/boot'),
            '-Dsbt.ivy.home='+str(baseline/'sbt/ivy'),
            *('testOnly '+suite for suite in SUITES)]


def test_receipts(project):
    result = {}
    for suite in SUITES:
        path = project/'target/test-reports'/('TEST-'+suite+'.xml')
        require(path.is_file() and not path.is_symlink(), 'missing actual test report: '+suite)
        root = ET.parse(path).getroot()
        cases = root.findall('testcase')
        require(root.tag == 'testsuite' and root.attrib.get('name') == suite,
                'unexpected test suite report: '+suite)
        require(cases and int(root.attrib.get('tests', '-1')) == len(cases), 'test count mismatch: '+suite)
        require(all(int(root.attrib.get(key, '0')) == 0 for key in ('failures', 'errors', 'skipped')) and
                all(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for case in cases),
                'failed, skipped or errored RTL test: '+suite)
        if suite.endswith('.Bf16CausalGqaOwnerSpec'):
            require(len(cases) == 6, 'all six unchanged owner protocol tests are required')
        else:
            require(len(cases) == 1, 'exact selector equivalence test is required')
        result[suite] = dict(tests=len(cases), passed=len(cases), skipped=0,
                             cases=[case.attrib['name'] for case in cases], report_sha256=sha(path))
    return result


def reject_full_top_compilation(build):
    forbidden = [str(p.relative_to(build)) for p in build.rglob('*') if p.is_file() and
                 (p.suffix in ('.o', '.a', '.gch') or p.name == 'VHostBlockTop')]
    require(not forbidden, 'full-top compilation artifacts found: '+repr(forbidden[:20]))


def validate_concat_inventory(inventory, call_evidence):
    """Require a complete scan and removal of the giant generated concat chain."""
    require(inventory.get('truncated') is False and inventory.get('file_discovery_truncated') is False,
            'candidate concat inventory is incomplete')
    require(inventory.get('syntax_error_files') == 0 and
            inventory.get('parameter_or_context_truncation_count') == 0,
            'candidate concat syntax or parameter evidence is unresolved')
    calls = inventory.get('calls')
    require(type(calls) is int and calls >= 0, 'candidate concat count missing')
    require(type(call_evidence) is list and len(call_evidence) == calls, 'candidate detailed call inventory incomplete')
    actual_widths, missing_function_annotations = {}, 0
    for call in call_evidence:
        widths = call.get('width_constants', {})
        require(call.get('parse_status') == 'parsed' and call.get('argument_count') == 6 and
                len(call.get('parameters', [])) == 6 and
                set(widths) == {'obits', 'lbits', 'rbits'} and
                all(type(value) is int and value > 0 for value in widths.values()),
                'candidate concat output/left/right width is not a literal')
        require(widths['obits'] == widths['lbits']+widths['rbits'], 'candidate concat width equation differs')
        missing_function_annotations += call.get('function') is None
        actual_widths[widths['obits']] = actual_widths.get(widths['obits'], 0)+1
    require(inventory.get('unresolved_calls') == missing_function_annotations,
            'unresolved candidate call beyond known function-name annotation gap')
    widths = inventory.get('literal_output_widths')
    require(type(widths) is dict, 'candidate concat literal widths missing')
    parsed = {}
    for width, count in widths.items():
        require(type(width) is str and width.isdecimal() and int(width) > 0 and
                type(count) is int and count > 0, 'candidate concat output width is not a literal')
        parsed[int(width)] = parsed.get(int(width), 0)+count
    require(sum(parsed.values()) == calls and parsed == actual_widths,
            'not every concat output width was resolved consistently')
    largest = max(parsed, default=0)
    require(largest <= 4096, 'giant GQA concat chain remains in candidate codegen')
    selected = inventory.get('selected_source', [])
    saved = {item['file'] for item in selected}
    require('obj/VHostBlockTop___024root.h' in saved, 'candidate root header was not preserved')
    require(any(item.get('selection_reason') == 'runtime_helper_implementation' for item in selected),
            'candidate concat runtime helper was not preserved')
    callers = inventory.get('calls_by_file', [])
    require(sum(item['calls'] for item in callers) == calls, 'candidate caller counts incomplete')
    require(all(item['file'] in saved for item in callers), 'candidate concat caller source exceeded preservation cap')
    require(0 <= inventory.get('selected_source_bytes', -1) <= inventory.get('selected_source_limit_bytes', -1),
            'candidate selected source cap was exceeded')
    return dict(complete_scan=True, all_widths_literal=True, all_output_widths_literal=True, concat_calls=calls,
                missing_function_annotations=missing_function_annotations,
                function_annotation_gap_does_not_change_parsed_widths=True,
                largest_concat_output_bits=largest, maximum_allowed_output_bits=4096,
                giant_concat_chain_absent=True, all_concat_caller_sources_preserved=True,
                old_sampled_filenames_required=False, speedup_claimed=False,
                numerical_acceptance=False, physical_qor_acceptance=False)


def preserve_changed_modules(baseline, candidate, comparison, output, inventory):
    """Save exact owner module bytes inside the collector's existing source cap."""
    from concat_inventory import MAX_SOURCE_BYTES
    module = 'Bf16CausalGqaOwner'
    manifest_path = output/'selected_source_manifest.json'
    require(_json(manifest_path) == inventory['selected_source'], 'selected source manifest changed')
    used = inventory['selected_source_bytes']
    limit = inventory['selected_source_limit_bytes']
    require(limit == MAX_SOURCE_BYTES and 0 <= used <= limit and
            used == sum(item['bytes'] for item in inventory['selected_source']),
            'selected source byte accounting changed')
    receipts = []
    for variant, path in (('baseline', baseline), ('candidate', candidate)):
        identity = comparison[variant]['modules'][module]
        expected_bytes, expected_hash = identity['bytes'], identity['sha256']
        require(type(expected_bytes) is int and expected_bytes > 0, 'invalid changed module byte count')
        relative = 'modules/'+variant+'/'+module+'.sv'
        receipt = dict(variant=variant, module=module, file=relative,
                       bytes=expected_bytes, sha256=expected_hash, preserved=False)
        if expected_bytes > limit-used:
            receipt['reason'] = 'source_byte_budget'
            inventory['selection_skipped'].append(dict(receipt))
            receipts.append(receipt)
            continue
        require(sha(path) == comparison[variant+'_sha256'], 'module source SV changed before extraction')
        captured, active, finished = bytearray(), False, False
        with path.open('rb') as stream:
            for line in stream:
                start = re.match(rb'^module\s+([A-Za-z_][A-Za-z_0-9$]*)\b', line)
                if start and start[1] == module.encode():
                    require(not active, 'duplicate changed module during extraction')
                    active = True
                if active:
                    require(len(captured)+len(line) <= expected_bytes and len(captured)+len(line) <= limit-used,
                            'changed module exceeds admitted byte count or source cap')
                    captured.extend(line)
                    if re.match(rb'^endmodule\b', line):
                        finished = True
                        break
        require(finished and len(captured) == expected_bytes and
                hashlib.sha256(captured).hexdigest() == expected_hash,
                'changed module bytes differ from strict module comparison')
        destination = output/'source'/relative
        require(not destination.exists() and not destination.is_symlink(), 'module source destination already exists')
        destination.parent.mkdir(parents=True, exist_ok=True)
        require(destination.parent.resolve().is_relative_to(output.resolve()), 'module destination escaped selected source')
        destination.write_bytes(captured)
        used += len(captured)
        receipt.update(preserved=True, saved_as=str(destination.relative_to(output)))
        inventory['selected_source'].append(dict(file=relative, saved_as=receipt['saved_as'],
            bytes=expected_bytes, sha256=expected_hash, selection_reason='exact_changed_owner_module',
            variant=variant, module=module, source_rtl_sha256=comparison[variant+'_sha256']))
        receipts.append(receipt)
    inventory.update(selected_source_bytes=used, changed_module_source_preservation=receipts)
    manifest_path.write_text(json.dumps(inventory['selected_source'], indent=2)+'\n')
    (output/'inventory_summary.json').write_text(json.dumps(inventory, indent=2)+'\n')
    return receipts


def _json(path):
    require(path.is_file() and not path.is_symlink(), 'missing receipt: '+str(path))
    return json.loads(path.read_text())


def build_receipt(build, expected_sources):
    recorded = _json(build/'sources.sha256.json')
    verify_recorded_sources(recorded, expected_sources)
    require((build/'source_base_commit.txt').read_text().strip() == PIN, 'wrong build source base')
    require(_json(build/'source_scope.json').get('scope') == 'full', 'full source closure required')
    require((build/'build_source_verification.log').read_text().strip() == 'SOURCE_IMMUTABILITY_PASS',
            'source/HardFloat verification absent')
    require(_json(build/'actual_verilator_before.json') == _json(build/'actual_verilator_after.json'),
            'actual Verilator changed')
    reject_full_top_compilation(build)
    return dict(source_manifest_sha256=sha(build/'sources.sha256.json'),
                compiler_jars_sha256=sha(build/'compiler_jars.sha256.json'),
                hardfloat_manifest_sha256=sha(build/'hardfloat.sha256.json'),
                rtl_sha256=sha(build/'generated/HostBlockTop.sv'),
                toolchain=_json(build/'toolchain.json'),
                actual_verilator=_json(build/'actual_verilator_after.json'),
                generated_rtl_admission=_json(build/'generated_rtl_identity.json'),
                source_and_hardfloat_verify='SOURCE_IMMUTABILITY_PASS', cpp_compilation_performed=False)


def tail(path):
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size-LOG_TAIL_BYTES))
        return stream.read().decode('utf-8', errors='replace')


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    return parser.parse_args()


def run_worker(args):
    source, out = checked_paths(args)
    require(source != DIAGNOSTIC_ROOT.resolve(), 'separate diagnostic checkout required')
    frozen = imports(source)
    from run_host_bf16_v_fresh_gate import _write_compact
    from concat_inventory import collect
    out.mkdir(parents=True)
    diagnostic = git(DIAGNOSTIC_ROOT, 'rev-parse', 'HEAD')
    env = source_environment(os.environ, diagnostic, PIN)
    os.environ['GITHUB_SHA'] = PIN
    os.environ['ATTENTION_PROFILE_DIAGNOSTIC_SHA'] = diagnostic
    started = time.monotonic()
    deadline = started+BUDGET_SECONDS
    baseline, candidate = out/'host_build', out/'candidate_build'
    summary = dict(schema='GQA_SELECTOR_EQUIVALENCE_CODEGEN_DIAGNOSTIC_V1', status='RUNNING_SELECTOR_GATE',
        stage='preflight', production_source_commit=PIN, diagnostic_source_commit=diagnostic,
        budget_seconds=BUDGET_SECONDS, numerical_acceptance=False, physical_qor_acceptance=False,
        full_top_behavioral_equivalence=False, model_capture_executions=0, model_reference_executions=0,
        full_top_cpp_compilation_performed=False, full_top_simulation_executions=0,
        matrix_real_rtl_tested=False, owner_matrix_service='unchanged unit-test responder',
        scope='selector bit equivalence and existing real owner/protocol RTL tests, then full-top codegen only',
        hierarchy_changed=False, arithmetic_recipe_changed=False, state_protocol_changed=False,
        commands=[], artifact_upload_allowlist=['compact/summary.json','compact/source_input_hashes.json','selected-source/**'])
    hashes = dict(source_sha256={}, diagnostic_source_sha256={}, candidate_source_sha256={},
                  input_sha256={}, output_sha256={}, builder_sha256={})

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=time.monotonic()-started,
                       remaining_budget_seconds=max(0, int(deadline-time.monotonic())))
        _write_compact(out, summary, hashes)

    def log_tails():
        return {str(path.relative_to(out)):tail(path)
            for path in [out/'baseline.log', out/'selector_owner_tests.log', out/'candidate.log',
                         baseline/'compile_emit.log', candidate/'compile_emit.log', candidate/'hierarchy_verilation.log']
            if path.is_file()}

    def run(argv, log, cwd, environment):
        remaining = int(deadline-time.monotonic()-FAILURE_RESERVE_SECONDS)
        require(remaining > 0, 'selector gate budget exhausted')
        row = dict(argv=argv, cwd=str(cwd), log=str(log.relative_to(out)), timeout_seconds=remaining,
                   environment={k:environment.get(k) for k in ('BUILD_JOBS','MAKEFLAGS','JVM_OPTS','SBT_OPTS',
                     'COURSIER_CACHE','CHISEL_FIRTOOL_PATH','VERILATOR_ROOT','HARDFLOAT_SOURCE')},
                   returncode=None)
        summary['commands'].append(row)
        checkpoint(summary['stage'])
        begin = time.monotonic()
        try:
            with log.open('w') as stream:
                result = subprocess.run(argv, cwd=cwd, env=environment, stdout=stream,
                    stderr=subprocess.STDOUT, timeout=remaining, check=False)
            row['returncode'] = result.returncode
            require(result.returncode == 0, 'command failed: '+str(log.relative_to(out)))
        except (Exception, KeyboardInterrupt) as error:
            row.update(exception=type(error).__name__, timed_out=isinstance(error, (subprocess.TimeoutExpired, TimeoutError)))
            raise
        finally:
            row['elapsed_seconds'] = time.monotonic()-begin
            if log.is_file():
                row['log_tail'] = tail(log)
                row['log_sha256'] = sha(log)
            checkpoint(summary['stage'])

    try:
        with frozen.total_budget(BUDGET_SECONDS-FAILURE_RESERVE_SECONDS):
            require(not env.get('OFFLINE_TOOLS'), 'selector gate requires the same pinned SBT compiler/cache path')
            env.update(BUILD_JOBS='1', MAKEFLAGS=MAKEFLAGS)
            hashes['diagnostic_source_sha256'] = verify_git_sources(DIAGNOSTIC_ROOT, diagnostic)
            baseline_git = verify_git_sources(source, PIN)
            summary['baseline_tracked_files_verified'] = len(baseline_git)
            hashes['baseline_git_source_sha256'] = baseline_git
            summary['idma_preflight'] = frozen._preflight(env, out)
            raw = frozen_file(source, 'chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh')
            hashes['original_builder_sha256'] = hashlib.sha256(raw).hexdigest()
            baseline_script = out/'baseline_emit_only.sh'
            baseline_script.write_text(baseline_builder(raw, source))
            hashes['builder_sha256'][baseline_script.name] = sha(baseline_script)
            checkpoint('baseline_exact_compile_emit_only')
            run(['bash', str(baseline_script), str(baseline), '0'], out/'baseline.log', source, env)
            require(sha(baseline/'generated/HostBlockTop.sv') == RTL_SHA256, 'original exact RTL SHA mismatch')
            require(not (baseline/'obj').exists(), 'baseline unexpectedly performed Verilation')
            summary['baseline'] = build_receipt(baseline, baseline_git)
            hashes['source_sha256'] = _json(baseline/'sources.sha256.json')
            baseline_manifest = (baseline/'sources.sha256.json').read_bytes()
            baseline_jars = _json(baseline/'compiler_jars.sha256.json')
            frozen.verify_checkout(PIN, hashes['source_sha256'])
            require(verify_git_sources(source, PIN) == baseline_git, 'baseline Git source map changed')
            require(verify_git_sources(DIAGNOSTIC_ROOT, diagnostic) == hashes['diagnostic_source_sha256'],
                    'diagnostic changed before overlay')

            checkpoint('apply_exact_candidate_overlay')
            require(sha(source/TARGET) == BASE_SHA256, 'frozen selector source hash differs')
            transformed = transform((source/TARGET).read_bytes())
            spec = (HERE/SPEC_NAME).read_bytes()
            require(not (source/SPEC_TARGET).exists(), 'candidate spec must be new')
            overrides = {TARGET:hashlib.sha256(transformed).hexdigest(), SPEC_TARGET:hashlib.sha256(spec).hexdigest()}
            require(overrides[TARGET] != BASE_SHA256, 'candidate source did not change')
            (source/TARGET).write_bytes(transformed)
            (source/SPEC_TARGET).write_bytes(spec)
            candidate_git = verify_git_sources(source, PIN, overrides)
            summary['overlay'] = dict(base_commit=PIN, exact_overrides=overrides,
                compiled_source_changes=[TARGET], new_test_sources=[SPEC_TARGET],
                tracked_files_verified=len(baseline_git), baseline_git_receipt_unchanged=True)
            hashes['candidate_overlay_sha256'] = overrides
            project = source/'chisel/continuous_prefill'
            for suite in SUITES:
                require(not (project/'target/test-reports'/('TEST-'+suite+'.xml')).exists(),
                        'preexisting test report cannot establish this gate: '+suite)
            test_env = dict(env, COURSIER_CACHE=str(baseline/'maven'),
                JVM_OPTS='-Xmx1500m -Xss8m -XX:ActiveProcessorCount=1',
                SBT_OPTS='-Dsbt.supershell=false -Dsbt.task.cpus=1',
                OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MAKEFLAGS=MAKEFLAGS)
            checkpoint('actual_selector_and_six_owner_rtl_tests')
            run(test_command(baseline), out/'selector_owner_tests.log', project, test_env)
            summary['rtl_unit_tests'] = test_receipts(project)
            verify_jars(baseline/'maven', baseline_jars)
            require(verify_git_sources(source, PIN, overrides) == candidate_git, 'candidate drift during RTL tests')
            summary['selector_and_owner_tests_passed'] = True

            candidate_script = out/'candidate_codegen_only.sh'
            candidate_script.write_text(candidate_builder(raw, source, baseline))
            hashes['builder_sha256'][candidate_script.name] = sha(candidate_script)
            summary['candidate_build_adaptations'] = [
                'same original ROOT relocation and original driver',
                'replace old SV identity guard with strict module_diff against immutable baseline SV',
                'reuse baseline SBT global/boot/ivy and Maven paths; hash the actual shared Maven cache',
                'explicit OUT/maven symlink to shared cache for unchanged toolchain verification',
                'stop after original hier_verilation; append original read-only post-generation checks']
            checkpoint('candidate_full_top_compile_and_hier_verilation_only')
            run(['bash', str(candidate_script), str(candidate), '0'], out/'candidate.log', source, env)
            summary['candidate'] = build_receipt(candidate, candidate_git)
            hashes['candidate_source_sha256'] = _json(candidate/'sources.sha256.json')
            require(set(hashes['candidate_source_sha256']) == set(hashes['source_sha256']) | {SPEC_TARGET},
                    'candidate recorded source closure changed beyond new test')
            require(hashes['candidate_source_sha256'].get(TARGET) == overrides[TARGET] and
                    hashes['candidate_source_sha256'].get(SPEC_TARGET) == overrides[SPEC_TARGET],
                    'candidate compiled source/test missing from full source closure')
            for name, digest in hashes['source_sha256'].items():
                require(hashes['candidate_source_sha256'][name] == overrides.get(name, digest),
                        'candidate recorded source drift: '+name)
            require(summary['candidate']['actual_verilator'] == summary['baseline']['actual_verilator'],
                    'candidate used a different actual Verilator')
            require(summary['candidate']['toolchain']['tools'] == summary['baseline']['toolchain']['tools'],
                    'candidate compiler/toolchain differs from baseline')
            require(summary['candidate']['hardfloat_manifest_sha256'] == summary['baseline']['hardfloat_manifest_sha256'],
                    'HardFloat changed')
            comparison = module_diff(baseline/'generated/HostBlockTop.sv', candidate/'generated/HostBlockTop.sv')
            require(comparison == summary['candidate']['generated_rtl_admission'], 'candidate module admission changed')
            summary['module_comparison'] = comparison
            require(comparison['baseline_sha256'] == RTL_SHA256, 'module comparison baseline changed')
            verify_jars(baseline/'maven', baseline_jars)
            require((baseline/'sources.sha256.json').read_bytes() == baseline_manifest, 'baseline source receipt rewritten')
            require(verify_git_sources(source, PIN, overrides) == candidate_git, 'final candidate source drift')
            require(verify_git_sources(DIAGNOSTIC_ROOT, diagnostic) == hashes['diagnostic_source_sha256'],
                    'final diagnostic source drift')
            require(all(sha(out/name) == digest for name, digest in hashes['builder_sha256'].items()),
                    'generated diagnostic builder drift')
            checkpoint('collect_candidate_concat_callers')
            summary['candidate_concat_inventory'] = collect(candidate, out/'selected-source')
            summary['candidate_structure_gate'] = validate_concat_inventory(
                summary['candidate_concat_inventory'], _json(out/'selected-source/calls.json'))
            summary['changed_module_source_preservation'] = preserve_changed_modules(
                baseline/'generated/HostBlockTop.sv', candidate/'generated/HostBlockTop.sv',
                comparison, out/'selected-source', summary['candidate_concat_inventory'])
            hashes['selected_source_sha256'] = {str(p.relative_to(out)):sha(p)
                for p in sorted((out/'selected-source').rglob('*')) if p.is_file()}
            summary.update(status='COMPLETE_SELECTOR_OWNER_EQUIVALENCE_AND_CODEGEN_NOT_NUMERICAL_ACCEPTANCE',
                           baseline_source_receipt_preserved=True, candidate_rtl_changed=True,
                           full_top_cpp_compilation_performed=False)
            summary['diagnostic_log_tail'] = log_tails()
            checkpoint('complete')
            return 0
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status='INCOMPLETE_SELECTOR_GATE', error=dict(type=type(error).__name__, message=str(error)))
        summary['diagnostic_log_tail'] = log_tails()
        checkpoint(summary['stage'])
        return 1


def worker_entry():
    signal.pthread_sigmask(signal.SIG_UNBLOCK, (signal.SIGINT, signal.SIGTERM))
    raise SystemExit(run_worker(arguments()))


def finalize_selector_supervision(out, result):
    """Keep the existing partial-write/timeout protection, with our own scope."""
    code = finalize_supervision(out, result)
    path = out/'compact/summary.json'
    summary = _json(path)
    summary.update(schema='GQA_SELECTOR_EQUIVALENCE_CODEGEN_DIAGNOSTIC_V1',
                   numerical_acceptance=False, full_top_behavioral_equivalence=False,
                   physical_qor_acceptance=False)
    if code or summary['supervisor'].get('forced_shutdown'):
        summary['status'] = 'INCOMPLETE_SELECTOR_GATE'
    temporary = path.with_name('summary.json.tmp')
    temporary.write_text(json.dumps(summary, sort_keys=True, indent=2)+'\n')
    temporary.replace(path)
    (out/'summary.json').write_bytes(path.read_bytes())
    return code


def main():
    args = arguments()
    source, out = checked_paths(args)
    frozen = imports(source)
    command = [sys.executable, '-c',
        'import sys;sys.path.insert(0,sys.argv.pop(1));from run_selector_gate import worker_entry;worker_entry()',
        str(HERE), '--source-root', str(source), '--output', str(out)]
    result = frozen.supervise_process(command, timeout_seconds=BUDGET_SECONDS)
    raise SystemExit(finalize_selector_supervision(out, result))


if __name__ == '__main__':
    main()
