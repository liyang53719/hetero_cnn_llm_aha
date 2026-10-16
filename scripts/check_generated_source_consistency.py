#!/usr/bin/env python3
"""Cold, read-only pre-publication consistency gate. No refresh or build mode.

Only the named active model pins are current-source contracts. Historical
candidate receipts/source snapshots are not automatically rebased or refreshed.
Exit 0: all checks pass; 1: consistency rejected; 2: arguments/receipt rejected;
3: prerequisite, timeout or validator execution blocked. All checks are attempted.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
PROJECT = Path('chisel/continuous_prefill')
ACTIVE_MODELS = (
    'qwen2_prefill_traffic_bound', 'qwen2_rectangular_attention_model',
    'qwen2_prefill_resource_schedule', 'qwen2_shared_sfu_schedule',
)
RUN_GROUPS = ('general', 'tiny', 'real', 'native')
EXTERNAL = {
    'frozen_actual_rms_epilogue': (
        'heteronpu.continuous.ElementwiseRegisterLoanReplaySpec',
        'scripts/run_elementwise_register_loan_tests.py',
        'HETERO_RMS_LOAN_FIXTURE_ROOT',
    ),
    'frozen_actual_h2048_rms': (
        'heteronpu.continuous.GdnRmsNormFixedBankReplaySpec',
        'scripts/run_h2048_rms_borrower_tests.py',
        'HETERO_H2048_FIXTURE_ROOT',
    ),
}
CHECKS = ('shape_vectors', 'block_checklist', *ACTIVE_MODELS,
          'qwen2_dense_residency_source_identity', 'qwen2_saved_v0_source_review',
          'continuous_suite_partition', 'continuous_external_contract',
          'qwen2_current_matrix_source_identity', 'qwen2_current_prefix_source_identity',
          'qwen2_current_attention_execution_inventory', 'qwen2_observation_helper_source_identity')


class Rejected(ValueError):
    pass


class Blocked(RuntimeError):
    pass


class ReadOnlyViolation(Rejected):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(root, relative):
    path = root / relative
    spec = importlib.util.spec_from_file_location('_consistency_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def install_read_only_guard(scratch):
    """Permit synthetic scratch only; reject repository writes and child tools."""
    scratch = scratch.resolve()

    def writable(value):
        if isinstance(value, int):
            raise ReadOnlyViolation('UNEXPECTED_DESCRIPTOR_WRITE')
        path = Path(os.fsdecode(value)).resolve()
        if not path.is_relative_to(scratch):
            raise ReadOnlyViolation('READ_ONLY_WRITE_REJECTED:' + str(path))

    def audit(event, args):
        if event == 'open':
            path, mode, flags = args
            if (mode and any(char in mode for char in 'wax+')) or (
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            ):
                writable(path)
        elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod',
                       'os.chown', 'os.truncate', 'os.utime'):
            writable(args[0])
        elif event in ('os.rename', 'os.link'):
            writable(args[0]); writable(args[1])
        elif event == 'os.symlink':
            writable(args[1])
        elif event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork'):
            raise ReadOnlyViolation('CHILD_TOOL_REJECTED:' + event)
    sys.addaudithook(audit)


def run_cli(root, relative, arguments):
    """Run the repository's real read-only CLI, with no recovery/refresh path."""
    previous = sys.argv
    sys.argv = [str(root / relative), *arguments]
    try:
        try:
            runpy.run_path(str(root / relative), run_name='__main__')
        except SystemExit as exc:
            require(exc.code in (None, 0), f'VALIDATOR_REJECTED:{relative}:{exc.code}')
    finally:
        sys.argv = previous
    return {'validator': relative, 'arguments': arguments}


def validate_pin_map(root, pins, label='ACTIVE'):
    require(isinstance(pins, dict) and bool(pins), 'EMPTY_ACTIVE_SOURCE_PINS')
    for name, expected in pins.items():
        require(isinstance(name, str) and not Path(name).is_absolute()
                and '..' not in Path(name).parts, 'UNSAFE_ACTIVE_SOURCE_PATH:' + str(name))
        path = (root / name).resolve()
        require(path.is_relative_to(root), 'OUTSIDE_ACTIVE_SOURCE_PATH:' + name)
        require(isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected),
                'INVALID_ACTIVE_SOURCE_PIN:' + name)
        require(path.is_file() and sha(path) == expected, label + '_SOURCE_DRIFT:' + name)
    return dict(pins)


def source_only_report(module, root, boundary):
    """Exercise the real embedded gate, stop before the model's first operation.

    These two historical report APIs have no separate verify_sources function.
    Fail closed if their prefix changes rather than silently running a model.
    Only the in-memory module is modified; no source or pin is changed.
    """
    tree = ast.parse(Path(module.__file__).read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'report')
    prefix = function.body
    offset = 0 if boundary == 'calculate' else 1
    if offset:
        require(isinstance(prefix[0], ast.If), 'SOURCE_GATE_API_CHANGED:tokens')
    require(isinstance(prefix[offset], ast.For), 'SOURCE_GATE_API_CHANGED:pin_loop')
    loop = prefix[offset]
    require(ast.unparse(loop.iter) == 'SOURCE_PINS.items()', 'SOURCE_GATE_API_CHANGED:pin_map')
    following = prefix[offset + 1]
    require(isinstance(following, ast.Assign), 'SOURCE_GATE_API_CHANGED:boundary')
    required_expression = 'calculate(tokens, contexts)' if boundary == 'calculate' else 'profile or timing_profile()'
    require(ast.unparse(following.value) == required_expression, 'SOURCE_GATE_API_CHANGED:model_boundary')
    # Only validation statements may run before the boundary. Model code is not
    # reachable even if the report implementation after that point changes.
    class BoundaryReached(Exception):
        pass
    reached = []
    def stop(*args, **kwargs):
        reached.append(True)
        raise BoundaryReached()
    original = getattr(module, boundary)
    setattr(module, boundary, stop)
    try:
        try:
            module.report(root, 128)
        except BoundaryReached:
            pass
    finally:
        setattr(module, boundary, original)
    require(reached == [True], 'SOURCE_GATE_API_CHANGED:boundary_not_reached')
    return dict(module.SOURCE_PINS)


def check_active_sources(root, name):
    module = load_module(root, 'scripts/' + name + '.py')
    if name in ('qwen2_prefill_traffic_bound', 'qwen2_shared_sfu_schedule'):
        pins = module.verify_sources(root)
        api = 'verify_sources'
    else:
        boundary = 'calculate' if name == 'qwen2_rectangular_attention_model' else 'timing_profile'
        pins = source_only_report(module, root, boundary)
        api = 'report source gate only; stopped before ' + boundary
    # Traffic's optional Host contract is also active. Resource merges it, but
    # checking it here makes the individual traffic receipt unambiguous.
    if name == 'qwen2_prefill_traffic_bound':
        pins = {**pins, **module.HOST_SOURCE_PINS}
    pins = validate_pin_map(root, pins)
    return {'validator': 'scripts/' + name + '.py', 'api': api,
            'validator_sha256': sha(module.__file__), 'source_sha256': pins,
            'model_executed': False}



def dense_residency_sources(root):
    relative = 'scripts/qwen2_dense_residency_numeric.py'
    module = load_module(root, relative)
    pins = {
        'scripts/qwen2_block_recipe_model.py': module.BASE_SHA256,
        'scripts/qwen2_prefill_resource_schedule.py': module.SCHEDULE_SHA256,
        'scripts/qwen2_rectangular_attention_model.py': module.ATTENTION_EVENT_SHA256,
    }
    # Reuse the numerical runner's real source-identity primitives, without
    # resident_source(), Git extraction, source generation or numerical work.
    for name, expected in pins.items():
        module.R.require(module.R.file_sha(root / name) == expected,
                         'dense-residency active source changed; explicit review required: ' + name)
    validate_pin_map(root, pins)
    return {'validator': relative, 'validator_sha256': sha(root / relative),
            'api': 'R.require / R.file_sha over BASE_SHA256, SCHEDULE_SHA256, ATTENTION_EVENT_SHA256',
            'source_sha256': pins, 'numerics_executed': False, 'source_generated': False}


def saved_v0_source_review(root):
    relative = 'scripts/qwen2_prefill_resource_schedule.py'
    module = load_module(root, relative)
    require(hasattr(module, '_current_v0_hardware_pins') and hasattr(module, 'V0_HOST_SOURCE_REVIEW'),
            'SAVED_V0_SOURCE_REVIEW_API_MISSING')
    path = root / module.V0_SILU_AUDIT
    require(module.V0_SILU_AUDIT_SHA256 == '14b65f7fe70416739ca2b5cebffdd5a4bb388077708c579b30aa1f40df247ebf'
            and sha(path) == module.V0_SILU_AUDIT_SHA256, 'SAVED_V0_RECEIPT_CHANGED')
    audit = json.loads(path.read_text())
    historical = {name: digest for name, digest in audit['source_sha256'].items()
                  if not name.startswith('scripts/')}
    historical.update(audit['receipt']['source_identity']['source_sha256'])
    review = module.V0_HOST_SOURCE_REVIEW
    expected_names = {module.ATT.BASE + name for name in ('Qwen2Block.scala', 'QwenOwnerProtocol.scala')}
    require(set(review) == expected_names, 'SAVED_V0_REVIEW_SCOPE_CHANGED')
    expected = {}
    for name, digest in historical.items():
        if name in review:
            require(review[name].get('historical_sha256') == digest, 'SAVED_V0_UNKNOWN_HISTORICAL_IDENTITY:' + name)
            expected[name] = review[name]['current_sha256']
        else:
            expected[name] = digest
    # Validate path and expected-byte shape before invoking the existing helper.
    validate_pin_map(root, expected)
    current = module._current_v0_hardware_pins(root, historical)
    require(current == expected, 'SAVED_V0_REVIEW_HELPER_RESULT_CHANGED')
    binding = module.SFU.timing_binding(root)  # Source metadata only, no schedule.
    upstream = audit['source_timing_binding']['upstream']
    require(upstream['commit'] == binding['upstream']['commit'] and
            all(binding['upstream']['source_sha256'].get(name) == digest
                for name, digest in upstream['source_sha256'].items()),
            'SAVED_V0_UPSTREAM_IDENTITY_CHANGED')
    # Enabled/non-boolean profiles must reject before any model can be reached.
    def no_model(*args, **kwargs):
        raise Blocked('SAVED_V0_PROFILE_GUARD_REACHED_MODEL')
    module.BOUND.host_schedule_report = no_model
    for flag in ('enable_h2048_rms_borrower', 'external_elementwise_loan'):
        for value in (True, 0, None):
            try:
                module.observed_silu_host_bound(root, **{flag: value})
            except ValueError as exc:
                require('default-disabled borrower/loan profile' in str(exc),
                        'SAVED_V0_PROFILE_GUARD_CHANGED')
            else:
                raise Rejected('SAVED_V0_PROFILE_FALSE_ACCEPTANCE:' + flag)
    return {'validator': relative, 'validator_sha256': sha(root / relative),
            'api': '_current_v0_hardware_pins / SFU.timing_binding / disabled-profile rejection',
            'historical_receipt': module.V0_SILU_AUDIT,
            'historical_receipt_sha256': module.V0_SILU_AUDIT_SHA256,
            'historical_hardware_sha256': historical, 'current_hardware_sha256': current,
            'reviewed_identity_pairs': review,
            'historical_receipt_rewritten': False, 'bound_calculated': False,
            'current_host_reexecuted': False, 'current_rtl_measured': False,
            'h2048_borrower_included': False}



V3_BASE_COMMIT = 'f16df50adfb0f1f4bc668c517a2e29accffe6753'
FROZEN_EXECUTION_RECEIPT_SHA256 = '3d0f449d3e2a62f87ea915d89930dc5788f0ea835b11ce265a169c1fc4e5570e'
V4_REPLACEMENT_NAMES = {
    'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
    'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala',
}


def reject_enabled_profiles(function, root):
    flags = ('enable_h2048_rms_borrower', 'external_elementwise_loan')
    require(isinstance(function.__kwdefaults__, dict) and set(function.__kwdefaults__) == set(flags)
            and all(function.__kwdefaults__[flag] is False for flag in flags), 'V3_DEFAULT_PROFILE_API_CHANGED')
    for flag in flags:
        for value in (True, 0, None):
            try:
                function(root / '__profile_guard_must_reject_before_io__', **{flag: value})
            except ValueError as exc:
                require('default-disabled borrower/loan profile' in str(exc), 'V3_PROFILE_REJECTION_CHANGED')
            else:
                raise Rejected('V3_PROFILE_FALSE_ACCEPTANCE:' + flag)


def function_return_keywords(path, function_name, class_name=None):
    tree = ast.parse(path.read_text())
    body = tree.body if class_name is None else next(
        n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    function = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == function_name)
    returns = [n for n in function.body if isinstance(n, ast.Return)]
    require(len(returns) == 1 and isinstance(returns[0].value, ast.Call)
            and ast.unparse(returns[0].value.func) == 'dict', 'V3_METADATA_API_CHANGED')
    return {kw.arg: kw.value for kw in returns[0].value.keywords}


def require_literal(metadata, key, value):
    require(key in metadata, 'V3_METADATA_MISSING:' + key)
    try:
        actual = ast.literal_eval(metadata[key])
    except (TypeError, ValueError):
        raise Rejected('V3_METADATA_NOT_LITERAL:' + key) from None
    require(type(actual) is type(value) and actual == value, 'V3_METADATA_CHANGED:' + key)


def verify_current_source_metadata(metadata, version):
    expected = dict(source_version=version, source_base_commit=V3_BASE_COMMIT,
                    source_commit=None, historical_results_inherited=False,
                    borrower_enabled=False, elementwise_loan_enabled=False,
                    hardware_simulation=False, model_ticks_are_hardware_cycles=False)
    for key, value in expected.items():
        require(key in metadata and type(metadata[key]) is type(value) and metadata[key] == value,
                'V3_CURRENT_SOURCE_METADATA_CHANGED:' + key)


def current_runtime_source_gate(root, name):
    """Check current Matrix/Prefix v3 and observation v4 gates while preserving frozen historical provenance."""
    if name == 'qwen2_current_matrix_source_identity':
        relative = 'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'
        module = load_module(root, relative)
        reject_enabled_profiles(module.source_identity, root)
        identity = module.source_identity(root)
        verify_current_source_metadata(identity, 'qwen2-matrix-source-guard-v3')
        pins = identity['source_sha256']
        api = 'source_identity and disabled-profile rejection'
        details = {'source_version': identity['source_version']}
    elif name == 'qwen2_current_prefix_source_identity':
        relative = 'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py'
        module = load_module(root, relative)
        reject_enabled_profiles(module.source_identity, root)
        pins = {module.SCALA_DIR + path: digest for path, digest in module.SOURCE_HASHES.items()}
        pins[module.ALU_SOURCE] = module.ALU_SHA256
        metadata = function_return_keywords(root / relative, 'source_identity')
        keys = ('source_version', 'source_base_commit', 'source_commit', 'historical_results_inherited',
                'borrower_enabled', 'elementwise_loan_enabled', 'hardware_simulation',
                'model_ticks_are_hardware_cycles')
        require(set(keys) <= set(metadata), 'V3_PREFIX_METADATA_MISSING')
        identity = {key: ast.literal_eval(metadata[key]) for key in keys}
        verify_current_source_metadata(identity, 'qwen2-prefix-source-guard-v3')
        api = 'SOURCE_HASHES / ALU_SHA256, metadata AST and disabled-profile rejection; no Git extraction'
        details = {'source_version': identity['source_version'], 'arithmetic_extraction_executed': False}
    else:
        relative = 'scripts/observe_qwen2_attention_model.py'
        module = load_module(root, relative)
        reject_enabled_profiles(module.verify_execution_sources, root)
        require(module.SOURCE_VERSION == 'qwen2-existing-attention-observation-v4'
                and module.SOURCE_COMMIT is None and module.SOURCE_BASE_COMMIT == V3_BASE_COMMIT,
                'V4_OBSERVER_CURRENT_SOURCE_METADATA_CHANGED')
        require(module.RECEIPT_SHA == FROZEN_EXECUTION_RECEIPT_SHA256
                and sha(root / module.RECEIPT) == FROZEN_EXECUTION_RECEIPT_SHA256,
                'FROZEN_EXECUTION_RECEIPT_CHANGED')
        historical = json.loads((root / module.RECEIPT).read_text())['source_sha256']
        local = module.verify_sources(root)
        execution = module.verify_execution_sources(root)
        replacements = module.EXECUTION_SOURCE_REPLACEMENTS
        require(set(replacements) == V4_REPLACEMENT_NAMES, 'V4_REPLACEMENT_SCOPE_CHANGED')
        require(len(historical) == len(execution) == 75 and set(execution) == set(historical),
                'V4_EXECUTION_INVENTORY_COVERAGE_CHANGED')
        for path in historical:
            if path in replacements:
                previous, current = replacements[path]
                require(previous == historical[path] and current == execution[path] and previous != current,
                        'V4_REPLACEMENT_PAIR_CHANGED:' + path)
            else:
                require(historical[path] == execution[path], 'V4_UNREVIEWED_SOURCE_CHANGED:' + path)
        metadata = function_return_keywords(root / relative, 'report', 'AttentionObservation')
        require_literal(metadata, 'schema', 'qwen2-existing-attention-observation-v4')
        for field in ('prior_observation_results_inherited', 'matrix_binary_provenance_verified_by_observer',
                      'hardware_simulation', 'full_29_node_gate', 'whole_block_terminal_observed'):
            require_literal(metadata, field, False)
        for field, variable in (('source_version', 'SOURCE_VERSION'), ('execution_source_commit', 'SOURCE_COMMIT'),
                                ('execution_source_base_commit', 'SOURCE_BASE_COMMIT')):
            require(field in metadata and ast.unparse(metadata[field]) == variable,
                    'V4_OBSERVER_METADATA_BINDING_CHANGED:' + field)
        frozen_metadata = metadata.get('historical_fullgraph')
        require(isinstance(frozen_metadata, ast.Call) and ast.unparse(frozen_metadata.func) == 'dict',
                'V4_HISTORICAL_METADATA_MISSING')
        require_literal({kw.arg: kw.value for kw in frozen_metadata.keywords}, 'results_inherited', False)
        pins = {**local, **execution}
        api = 'verify_sources / verify_execution_sources / immutable receipt / report metadata AST'
        details = {'source_version': module.SOURCE_VERSION, 'historical_receipt': module.RECEIPT,
                   'historical_receipt_sha256': FROZEN_EXECUTION_RECEIPT_SHA256,
                   'inventory_entries': 75, 'reviewed_replacements': 6, 'unchanged_historical_entries': 69,
                   'reviewed_identity_pairs': replacements}
    validate_pin_map(root, pins, 'CURRENT_RUNTIME')
    return {'validator': relative, 'validator_sha256': sha(root / relative), 'api': api,
            'source_sha256': pins, 'identity_class': ('current_v4_runtime_with_frozen_historical_provenance'
                if name == 'qwen2_current_attention_execution_inventory'
                else 'current_v3_runtime_with_frozen_historical_provenance'),
            'source_base_commit': V3_BASE_COMMIT, 'source_commit': None,
            'historical_results_inherited': False, 'historical_snapshot_rewritten': False,
            'replay_executed': False, **details}


def observation_helper_sources(root):
    # Canonical package names are required by the repository's real relative
    # imports and constructor-delta validator. No owner/service is constructed.
    sys.path.insert(0, str(root))
    official_name = 'candidates.qwen2_resident_matrix.official_bf16.observation'
    profiled_name = 'candidates.qwen2_resident_matrix.dense_block_reduce.observation'
    official = importlib.import_module(official_name)
    profiled = importlib.import_module(profiled_name)
    require(Path(official.__file__).resolve().is_relative_to(root)
            and Path(profiled.__file__).resolve().is_relative_to(root), 'OBSERVATION_HELPER_IMPORT_ROOT_DRIFT')
    require(official.SOURCE_VERSION == 'qwen2-official-bf16-attention-observation-v4'
            and official.HELPER_SOURCE_VERSION == 'qwen2-existing-attention-observation-v4'
            and profiled.SOURCE_VERSION == 'qwen2-profiled-attention-observation-v4'
            and profiled.CAPTURE_SOURCE_VERSION == official.SOURCE_VERSION, 'OBSERVATION_HELPER_VERSION_DRIFT')
    execution = official.base.verify_execution_sources(root)
    snapshot = {**execution, **{name: sha(root / name) for name in official.REQUIRED_SOURCES}}
    official.verify_source_snapshot(snapshot)
    profiled.verify_constructor_delta()
    pins = {official.HELPER: official.HELPER_SHA256,
            official.OBSERVER: profiled.CAPTURE_SHA256,
            profiled.monitoring.MONITORING: profiled.MONITORING_SHA256}
    validate_pin_map(root, pins, 'OBSERVATION_HELPER')
    return {'validators': [official_name.replace('.', '/') + '.py', profiled_name.replace('.', '/') + '.py'],
            'api': 'verify_source_snapshot / verify_constructor_delta', 'source_sha256': pins,
            'observer_instantiated': False, 'owner_or_service_executed': False,
            'historical_results_inherited': False, 'cold_snapshot_only': True}


def suite_partition(root):
    relative = PROJECT / 'scripts/plan_continuous_suites.py'
    module = load_module(root, relative)
    plan = module.plan(root / PROJECT)
    require(tuple(module.RUN_GROUPS) == RUN_GROUPS, 'RUN_GROUP_CLASSIFICATION_DRIFT')
    require(module.EXTERNAL_FIXTURE_SUITES == {k: v[0] for k, v in EXTERNAL.items()},
            'EXTERNAL_FIXTURE_CLASSIFICATION_DRIFT')
    require(set(plan) == set(RUN_GROUPS) | set(EXTERNAL), 'UNKNOWN_OR_MISSING_SUITE_GROUP')
    names = sorted('heteronpu.continuous.' + p.stem for p in
                   (root / PROJECT / 'src/test/scala/heteronpu/continuous').glob('*Spec.scala'))
    require(all(isinstance(v, list) and v and all(isinstance(x, str) for x in v)
                for v in plan.values()), 'EMPTY_OR_INVALID_SUITE_GROUP')
    flat = [suite for suites in plan.values() for suite in suites]
    require(sorted(flat) == names and len(flat) == len(set(flat)), 'SUITE_COVERAGE_MISMATCH')
    for group, (suite, _, _) in EXTERNAL.items():
        require(plan[group] == [suite], 'EXTERNAL_SUITE_MISCLASSIFIED:' + group)
        require(not any(suite in plan[g] for g in RUN_GROUPS), 'EXTERNAL_SUITE_COUNTED_AS_RUNNABLE:' + group)
    return {'validator': str(relative), 'validator_sha256': sha(root / relative),
            'suite_count': len(flat), 'runnable_suite_count': sum(len(plan[g]) for g in RUN_GROUPS),
            'external_suite_count': sum(len(plan[g]) for g in EXTERNAL), 'plan': plan,
            'scala_suites_executed': False}


def receipt_builder(root):
    runner = root / PROJECT / 'scripts/run_continuous_ci_gate.sh'
    text = runner.read_text()
    require(re.search(r'^for group in general tiny real native;do$', text, re.M) is not None,
            'SHELL_RUN_GROUP_CONTRACT_DRIFT')
    marker = 'python3 - "$OUT" <<\'PY\'\n'
    require(text.count(marker) == 1, 'CONTINUOUS_RECEIPT_BUILDER_API_CHANGED')
    code = text.split(marker, 1)[1]
    require(code.endswith('\nPY\n'), 'CONTINUOUS_RECEIPT_BUILDER_TERMINATOR_CHANGED')
    return runner, code[:-4]


def verify_external_report(report, plan):
    require(report.get('status') == 'PASS_CONTINUOUS_CONTROL_AND_ELEMENTWISE_REGRESSION',
            'CONTINUOUS_REPORT_STATUS_CHANGED')
    groups = report.get('groups', {})
    require(set(groups) == set(RUN_GROUPS), 'EXTERNAL_OR_MISSING_EXECUTED_GROUP')
    for group in RUN_GROUPS:
        require(groups[group].get('suites') == plan[group], 'RUNNABLE_SUITE_RECEIPT_DRIFT:' + group)
    require(report.get('total_tests') == sum(group['tests'] for group in groups.values()),
            'EXTERNAL_TESTS_COUNTED_AS_PASS')
    external = report.get('external_fixture_suites', {})
    require(set(external) == set(EXTERNAL), 'EXTERNAL_RECEIPT_CLASSIFICATION_DRIFT')
    for group, (suite, runner, _) in EXTERNAL.items():
        entry = external[group]
        require(entry.get('status') == 'NOT_EXECUTED_REQUIRES_FROZEN_ACTUAL_FIXTURE'
                and entry.get('counted_as_pass') is False and entry.get('suites') == [suite],
                'EXTERNAL_RECEIPT_FALSE_PASS:' + group)
        require(isinstance(entry.get('runner'), str) and entry['runner'].startswith(runner + ' ')
                and '--actual-fixture-root' in entry['runner'], 'EXTERNAL_RUNNER_RECEIPT_DRIFT:' + group)
        require(report.get('scope', {}).get(group + '_executed') is False,
                'EXTERNAL_EXECUTION_FALSE_CLAIM:' + group)
    for claim in ('matrix4096_full_numerical', 'official_model', 'dc'):
        require(report.get('scope', {}).get(claim) is False, 'COLD_GATE_FALSE_CLAIM:' + claim)


def external_contract(root, scratch):
    plan = suite_partition(root)['plan']
    runner, code = receipt_builder(root)
    for group, (suite, relative, environment) in EXTERNAL.items():
        source = (root / PROJECT / 'src/test/scala/heteronpu/continuous' /
                  (suite.rsplit('.', 1)[-1] + '.scala')).read_text()
        require(f'sys.env("{environment}")' in source, 'FROZEN_FIXTURE_REQUIREMENT_DRIFT:' + group)
        require('assume(' not in source and 'cancel(' not in source, 'EXTERNAL_SUITE_SKIP_OR_CANCEL:' + group)
        dedicated = (root / relative).read_text()
        require(suite.rsplit('.', 1)[-1] in dedicated and '--actual-fixture-root' in dedicated,
                'DEDICATED_EXTERNAL_RUNNER_MISSING:' + group)
    fixture = scratch / 'cold_continuous_receipt'
    fixture.mkdir()
    (fixture / 'suite_plan.json').write_text(json.dumps(plan))
    counts = {'general': 101, 'tiny': 8, 'real': 10, 'native': 10}
    for group in RUN_GROUPS:
        folder = fixture / group
        folder.mkdir()
        text = '\n'.join(s.rsplit('.', 1)[-1] + ':' for s in plan[group])
        text += f'\nTests: succeeded {counts[group]}, failed 0, canceled 0, ignored 0, pending 0\nAll tests passed.\n'
        (folder / 'chisel_tests.log').write_text(text)
    (fixture / 'source_verify.log').write_text('SOURCE_IMMUTABILITY_PASS\n')
    previous = sys.argv
    sys.argv = ['cold_receipt_contract', str(fixture)]
    try:
        exec(compile(code, str(runner) + ':receipt_builder', 'exec'), {'__name__': '__main__'})
    except SystemExit as exc:
        raise Rejected('CONTINUOUS_RECEIPT_BUILDER_REJECTED:' + str(exc)) from exc
    finally:
        sys.argv = previous
    report = json.loads((fixture / 'RESULT.json').read_text())
    verify_external_report(report, plan)
    return {'validator': str(runner.relative_to(root)), 'validator_sha256': sha(runner),
            'cold_mock_only': True, 'shell_gate_executed': False, 'suites_executed': False,
            'external_fixture_suites': report['external_fixture_suites'],
            'note': 'Only final Python receipt builder ran against synthetic temporary logs; no test execution claim.'}


def run_check(root, name, scratch):
    if name == 'shape_vectors':
        return run_cli(root, 'scripts/generate_shape_layout_vectors.py', ['--root', str(root), '--check'])
    if name == 'block_checklist':
        return run_cli(root, 'scripts/block_checklist.py', ['--root', str(root), 'validate'])
    if name in ACTIVE_MODELS:
        return check_active_sources(root, name)
    if name == 'qwen2_dense_residency_source_identity':
        return dense_residency_sources(root)
    if name == 'qwen2_saved_v0_source_review':
        return saved_v0_source_review(root)
    if name.startswith('qwen2_current_'):
        return current_runtime_source_gate(root, name)
    if name == 'qwen2_observation_helper_source_identity':
        return observation_helper_sources(root)
    if name == 'continuous_suite_partition':
        return suite_partition(root)
    if name == 'continuous_external_contract':
        return external_contract(root, scratch)
    raise Blocked('UNKNOWN_CHECK:' + name)


def child_main(root, name, scratch):
    install_read_only_guard(scratch)
    stdout, stderr = io.StringIO(), io.StringIO()
    start = time.monotonic()
    row = {'check': name}
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            row['detail'] = run_check(root, name, scratch)
        row['status'] = 'PASS'
    except (Rejected, ValueError, AssertionError, KeyError) as exc:
        row.update(status='FAIL', error=f'{type(exc).__name__}: {exc}')
    except Exception as exc:
        row.update(status='BLOCKED', error=f'{type(exc).__name__}: {exc}')
    row.update(seconds=round(time.monotonic() - start, 4),
               stdout=stdout.getvalue(), stderr=stderr.getvalue())
    print(json.dumps(row, ensure_ascii=False))
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 3}[row['status']]


def validate_receipt_destination(root, requested):
    if requested is None:
        return None
    path = requested.absolute()
    require(path.parent.is_dir(), 'RECEIPT_PARENT_MUST_EXIST')
    require(not path.exists() and not path.is_symlink(), 'RECEIPT_MUST_BE_NEW')
    resolved = path.resolve()
    # A checkout itself may live under /tmp, so the repository check comes first.
    if resolved.is_relative_to(root):
        require(resolved.is_relative_to(root / 'work'), 'RECEIPT_MUST_USE_IGNORED_WORK_OR_TEMP')
        check = subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', '--', str(resolved)],
                               env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}, capture_output=True)
        require(check.returncode == 0, 'RECEIPT_WORK_PATH_NOT_GIT_IGNORED')
    else:
        require(resolved.is_relative_to(Path(tempfile.gettempdir()).resolve()),
                'RECEIPT_MUST_USE_IGNORED_WORK_OR_TEMP')
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='repository root to read')
    parser.add_argument('--receipt', type=Path, help='new JSON path in ignored work/ or system temp; stdout always emitted')
    parser.add_argument('--timeout', type=float, default=30, help='seconds per cold check (default: 30)')
    parser.add_argument('--_check', choices=CHECKS, help=argparse.SUPPRESS)
    parser.add_argument('--_scratch', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args._check:
        if not args._scratch or not args._scratch.is_dir() or args._scratch.resolve().is_relative_to(root):
            parser.error('internal scratch must be an existing directory outside repository')
        return child_main(root, args._check, args._scratch.resolve())
    try:
        require(root.is_dir(), 'REPOSITORY_ROOT_MISSING')
        require(args.timeout > 0, 'TIMEOUT_MUST_BE_POSITIVE')
        receipt_path = validate_receipt_destination(root, args.receipt)
    except (Rejected, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rows = []
    with tempfile.TemporaryDirectory(prefix='hetero-cold-consistency-') as tmp:
        for name in CHECKS:
            scratch = Path(tmp) / name
            scratch.mkdir()
            command = [sys.executable, '-B', *(['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []), str(Path(__file__).resolve()), '--root', str(root),
                       '--_check', name, '--_scratch', str(scratch)]
            try:
                proc = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=args.timeout,
                                      env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'GIT_OPTIONAL_LOCKS': '0'})
                row = json.loads(proc.stdout)
                require(isinstance(row, dict) and row.get('check') == name
                        and row.get('status') in ('PASS', 'FAIL', 'BLOCKED'), 'INVALID_CHECK_RECEIPT')
                expected = {'PASS': 0, 'FAIL': 1, 'BLOCKED': 3}[row['status']]
                require(proc.returncode == expected, 'CHECK_EXIT_STATUS_MISMATCH')
                if proc.stderr:
                    row['process_stderr'] = proc.stderr
            except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
                row = {'check': name, 'status': 'BLOCKED', 'error': f'{type(exc).__name__}: {exc}'}
            rows.append(row)
    counts = Counter(row['status'] for row in rows)
    exit_code = 3 if counts['BLOCKED'] else (1 if counts['FAIL'] else 0)
    receipt = {'schema': 'heteronpu.generated-source-consistency-preflight.v2',
               'status': 'PASS' if exit_code == 0 else ('BLOCKED' if exit_code == 3 else 'FAIL'),
               'root': str(root), 'exit_code': exit_code, 'check_counts': dict(counts), 'checks': rows,
               'scope': {'read_only_repository': True, 'refresh_attempted': False,
                         'numerical_models_executed': False, 'weights_loaded': False,
                         'scala_or_rtl_executed': False, 'remote_ci_invoked': False,
                         'historical_candidate_snapshots_rebased': False},
               'historical_policy': 'Four explicitly named active models, downstream dense-residency source pins, '
                                    'the exact reviewed saved-v0 compatibility mapping, v3 Matrix/Prefix guards and v4 observation inventory are checked. '
                                    'The sealed 75-source historical receipt is unchanged, with six explicit runtime '
                                    'replacements and 69 exact identities; no old result is inherited.',
               'full_workflow_executed': False,
               'current_runtime_identity_blockers': [row['check'] for row in rows
                    if (row['check'].startswith('qwen2_current_') or row['check'] == 'qwen2_observation_helper_source_identity')
                    and row['status'] != 'PASS'],
               'hardware_acceptance_claimed': False}
    output = json.dumps(receipt, indent=2, ensure_ascii=False) + '\n'
    if receipt_path:
        try:
            with receipt_path.open('x', encoding='utf-8') as handle:
                handle.write(output)
        except OSError as exc:
            print('RECEIPT_WRITE_REJECTED:' + str(exc), file=sys.stderr)
            return 2
    print(output, end='')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
