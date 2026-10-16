#!/usr/bin/env python3
"""Bounded opt-in numerical bridge CI wrapper; never builds a native library.

The 120-second total includes the existing five-second process-group cleanup
and one second reserved for two small receipts. Raw child output is private,
transient /tmp storage and is never copied into CI output or artifact roots.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.raw_kv.run_unit import run_group
from candidates.qwen2_resident_matrix.raw_kv_attention import numeric_prepare
from scripts import build_shared_matrix_recipe as recipe

PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_attention/'
WORKFLOW = '.github/workflows/qwen2-matrix-interface-frontend.yml'
TOTAL_SECONDS = 120
CLEANUP_SECONDS = 5
RECEIPT_SECONDS = 1
CHILD_MODULE = 'candidates.qwen2_resident_matrix.raw_kv_attention.numeric_bridge'
OUTPUTS = ('summary.json', 'source_hashes.json')
MAX_CHILD_BYTES = 8192
MAX_EVIDENCE_BYTES = 64 * 1024
MATRIX_COUNTERS = frozenset(('owner_acquires', 'owner_responses', 'owner_releases',
    'normal_groups', 'normal_steps', 'normal_results', 'normal_done', 'legacy_replies'))
EXTRA_INPUTS = (WORKFLOW, *(PREFIX + n for n in (
    'numeric_pins.json', 'numeric_prepare.py', 'numeric_bridge.py',
    'run_numeric_ci.py', 'test_numeric_ci.py')))


class ReceiptError(ValueError):
    """Errors carry fixed reason codes, never child output or external paths."""


def need(ok, reason):
    if not ok:
        raise ReceiptError(reason)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        need(name not in result, 'duplicate_json_key')
        result[name] = value
    return result


def read_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ReceiptError('nonfinite_json')))


def exact_keys(value, names):
    need(type(value) is dict and set(value) == set(names), 'child_schema')


def integer(value, minimum=0, maximum=2000000):
    need(type(value) is int and minimum <= value <= maximum, 'child_counter')


def validate_child(raw):
    """Accept only the complete M1/M2 plus fault PASS receipt, no log prefixes."""
    need(type(raw) is bytes and len(raw) <= MAX_CHILD_BYTES, 'child_size')
    value = read_json(raw.decode('utf-8'))
    exact_keys(value, ('status', 'cases', 'fault', 'arithmetic_executed',
        'hardware_simulation', 'public_profiles_executed',
        'model_ticks_are_hardware_cycles', 'native_acceptance'))
    need(value['status'] == 'PASS_BOUNDED_NUMERIC' and value['arithmetic_executed'] is True,
         'child_not_pass')
    for name in ('hardware_simulation', 'public_profiles_executed', 'model_ticks_are_hardware_cycles'):
        need(value[name] is False, 'child_scope')
    need(value['native_acceptance'] == 'UNCHANGED_FAIL_POLICY_PENDING', 'child_scope')
    need(type(value['cases']) is list and len(value['cases']) == 2, 'child_cases')
    for tokens, case in enumerate(value['cases'], 1):
        exact_keys(case, ('tokens', 'status', 'kv_requests', 'unique_ddr_reads',
            'hits', 'accepted_matrix', 'scalar_operations', 'output_words'))
        integer(case['tokens'], tokens, tokens)
        need(case['status'] == 'PASS', 'child_case_not_pass')
        requests = 192 * tokens * (tokens + 1) // 2
        for name, expected in (('kv_requests', requests), ('unique_ddr_reads', 32 * tokens),
                               ('hits', requests - 32 * tokens), ('output_words', 1536 * tokens)):
            integer(case[name], expected, expected)
        integer(case['scalar_operations'], 1)
        exact_keys(case['accepted_matrix'], MATRIX_COUNTERS)
        for name, count in case['accepted_matrix'].items():
            integer(count, 1)
            if name.startswith('owner_'):
                integer(count, 1, 1)
    fault = value['fault']
    exact_keys(fault, ('tokens', 'status', 'revoked_reply_arithmetic_operations',
                       'core_replies', 'output_published'))
    integer(fault['tokens'], 1, 1)
    integer(fault['revoked_reply_arithmetic_operations'], 0, 0)
    integer(fault['core_replies'], 1, 1)
    need(fault['status'] == 'PASS' and fault['output_published'] is False, 'child_fault')
    return value


def repository_path(name):
    need(type(name) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+', name) is not None,
         'unsafe_source_name')
    path = Path(name)
    need(not path.is_absolute() and '..' not in path.parts and str(path) == name,
         'unsafe_source_name')
    full = ROOT / path
    need(full.resolve(strict=True).is_relative_to(ROOT.resolve()) and full.is_file(),
         'unsafe_source_path')
    return full


def source_snapshot():
    pins = read_json((HERE / 'numeric_pins.json').read_text())
    inputs = pins['inputs']
    need(type(inputs) is dict and len(inputs) == 52, 'numeric_closure')
    names = set(inputs) | set(EXTRA_INPUTS) | set(recipe.SOURCES)
    need('scripts/build_shared_matrix_recipe.py' in names and
         'candidates/qwen2_resident_matrix/raw_kv/run_unit.py' in names and
         'candidates/qwen2_resident_matrix/raw_kv/stimuli.py' in names, 'numeric_closure')
    return {name: digest(repository_path(name)) for name in sorted(names)}


def library_snapshot(env):
    library = Path(env['MATRIX_SERVICE_LIBRARY']).expanduser().resolve(strict=True)
    receipt = Path(env['MATRIX_SERVICE_COMPILE_RECEIPT']).expanduser().resolve(strict=True)
    # The original owner verifies the adjacent receipt. Require the strict
    # helper to validate that very same file, never a second loose receipt.
    need(receipt == library.with_name('compile.json'), 'adjacent_receipt_required')
    return library, receipt, {'library_sha256': digest(library), 'receipt_sha256': digest(receipt)}


def safe_summary(status='NOT_RUN', reason='prerequisite_missing'):
    return dict(schema=1, status=status, reason=reason, numerical_child_started=False,
                hardware_simulation=False, public_profiles_executed=False,
                model_ticks_are_hardware_cycles=False,
                native_acceptance='UNCHANGED_FAIL_POLICY_PENDING',
                total_budget_seconds=TOTAL_SECONDS, cleanup_grace_seconds=CLEANUP_SECONDS)


def save(out, summary, hashes, *, extra_outputs=()):
    need(extra_outputs in ((), ('progress.json',)), 'unexpected_output')
    need({p.name for p in out.iterdir()} <= set(OUTPUTS + extra_outputs), 'unexpected_output')
    for name, value in zip(OUTPUTS, (summary, hashes)):
        raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
        need(len(raw) <= MAX_EVIDENCE_BYTES, 'evidence_size')
        target = out / name
        need(not target.is_symlink(), 'unsafe_output')
        target.write_bytes(raw)


def run(out, environ=None, *, child_module=None, child_args=(), validator=None,
        snapshot=None, total_seconds=None, deadline_ns=None, budget_ceiling=None,
        pass_statuses=None, evidence_writer=None):
    """Return (nonzero on NOT_RUN/failure, sanitized summary); invoke child once."""
    start = time.monotonic()
    budget = TOTAL_SECONDS if total_seconds is None else total_seconds
    ceiling = TOTAL_SECONDS if budget_ceiling is None else budget_ceiling
    need(type(ceiling) in (int, float) and math.isfinite(ceiling) and
         ceiling in (TOTAL_SECONDS, 2400), 'total_budget')
    need(type(budget) in (int, float) and math.isfinite(budget) and
         CLEANUP_SECONDS + RECEIPT_SECONDS < budget <= ceiling, 'total_budget')
    end = start + budget
    if deadline_ns is not None:
        need(type(deadline_ns) is int and 0 < deadline_ns < 1 << 63, 'total_budget')
        end = min(end, deadline_ns / 1_000_000_000)
        budget = end - start
        need(budget > CLEANUP_SECONDS + RECEIPT_SECONDS, 'total_budget')
    module = CHILD_MODULE if child_module is None else child_module
    validate = validate_child if validator is None else validator
    snapshot = source_snapshot if snapshot is None else snapshot
    write_evidence = save if evidence_writer is None else evidence_writer
    statuses = ('PASS_BOUNDED_NUMERIC', 'PASS_CALIBRATION_ONLY') if pass_statuses is None else pass_statuses
    need(statuses in (('PASS_BOUNDED_NUMERIC', 'PASS_CALIBRATION_ONLY'),
                      ('PASS_M128_SYNTHETIC_ATTENTION',)), 'child_schema')
    need(type(module) is str and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module)
         and type(child_args) is tuple and all(type(arg) is str for arg in child_args), 'child_schema')
    out = Path(out).resolve()
    need(not out.exists(), 'fresh_output_required')
    out.mkdir(parents=True)
    env = dict(os.environ if environ is None else environ)
    summary = safe_summary()
    summary['total_budget_seconds'] = budget
    hashes = {'schema': 1, 'sources': {}, 'inputs_unchanged': False}
    code = 2
    before = native_before = None
    # Only one deadline owner is active at a time. SIGALRM bounds Python-only
    # pre/postflight; run_group owns the child wait AND its uninterrupted
    # TERM-to-KILL grace. An outer alarm must never interrupt that cleanup.
    work_deadline = end - CLEANUP_SECONDS - RECEIPT_SECONDS
    old_alarm = signal.getsignal(signal.SIGALRM)
    old_term = signal.getsignal(signal.SIGTERM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    need(old_timer == (0.0, 0.0), 'existing_deadline')
    def expired(signum, frame):
        raise TimeoutError('total_budget')
    def interrupted(signum, frame):
        raise InterruptedError('terminated')
    signal.signal(signal.SIGALRM, expired)
    signal.signal(signal.SIGTERM, interrupted)
    signal.setitimer(signal.ITIMER_REAL, max(.001, work_deadline - time.monotonic()))
    try:
        if not env.get('MATRIX_SERVICE_LIBRARY') or not env.get('MATRIX_SERVICE_COMPILE_RECEIPT'):
            return code, summary
        if not all(Path(env[name]).expanduser().is_file() for name in
                   ('MATRIX_SERVICE_LIBRARY', 'MATRIX_SERVICE_COMPILE_RECEIPT')):
            return code, summary
        before = snapshot()
        hashes['sources'] = before
        numeric_prepare.check()
        library, receipt, native_before = library_snapshot(env)
        hashes.update(native_before)
        validated = recipe.from_environment(ROOT, env)
        need(validated == library, 'library_identity')
        need(snapshot() == before and library_snapshot(env)[2] == native_before,
             'input_drift')
        # Do not inherit PYTHONPATH/PYTHONHOME or optimization that could select
        # a different module tree or disable original owner assertion guards.
        child_env = dict(env)
        for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE'):
            child_env.pop(name, None)
        child_env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
                         MATRIX_SERVICE_LIBRARY=str(library), MATRIX_SERVICE_COMPILE_RECEIPT=str(receipt))
        summary.update(status='FAIL', reason='child_failed', numerical_child_started=True)
        code = 1
        with tempfile.TemporaryFile(mode='w+b', dir='/tmp', prefix='kv-numeric-private-') as log:
            signal.setitimer(signal.ITIMER_REAL, 0)
            remaining = work_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('total_budget')
            try:
                rc = run_group([sys.executable, '-m', module, *child_args], cwd=ROOT,
                               env=child_env, log=log, timeout=remaining, grace=CLEANUP_SECONDS)
            finally:
                # run_group returns/raises only after its process-group cleanup.
                # Never rearm a signal while its TERM/KILL sequence is active.
                remaining = work_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('total_budget')
                signal.setitimer(signal.ITIMER_REAL, remaining)
            integer(rc, -128, 255)
            summary['child_exit_code'] = rc
            need(rc == 0, 'child_exit_nonzero')
            log.seek(0)
            result = validate(log.read(MAX_CHILD_BYTES + 1))
            need(result['status'] in statuses, 'child_not_pass')
        need(snapshot() == before and library_snapshot(env)[2] == native_before,
             'input_drift')
        need(recipe.from_environment(ROOT, env) == library, 'library_identity')
        hashes['inputs_unchanged'] = True
        summary.update(status=result['status'], reason='complete_numeric_receipt', result=result)
        code = 0
    except (TimeoutError, subprocess.TimeoutExpired):
        summary.update(status='TIMEOUT', reason='total_budget')
        code = 1
    except (InterruptedError, KeyboardInterrupt):
        summary.update(status='INTERRUPTED', reason='terminated')
        code = 1
    except Exception as error:
        # Never interpolate the exception, raw log, environment, paths or token.
        reason = str(error) if type(error) is ReceiptError else 'preflight_or_receipt_failed'
        allowed = {'input_drift', 'child_exit_nonzero', 'child_schema', 'child_counter',
                   'child_size', 'child_not_pass', 'child_scope', 'child_cases',
                   'child_case_not_pass', 'child_fault', 'duplicate_json_key', 'nonfinite_json',
                   'numeric_closure', 'unsafe_source_name', 'unsafe_source_path',
                   'adjacent_receipt_required', 'library_identity', 'total_budget'}
        summary.update(status='FAIL' if before is not None else 'NOT_RUN',
                       reason=reason if reason in allowed else 'preflight_or_receipt_failed')
        code = 1 if before is not None else 2
    finally:
        # Record postflight even on child failures, but never override failure
        # with PASS or expose a changed file/path. No native execution here.
        # Keep the alarm armed during hashing; after timeout do not spend the
        # cleanup/receipt reserve rehashing potentially slow files.
        try:
            if before is not None:
                if time.monotonic() >= work_deadline:
                    hashes['inputs_unchanged'] = False
                    summary.update(status='TIMEOUT', reason='total_budget')
                    code = 1
                else:
                    unchanged = snapshot() == before
                    if native_before is not None:
                        unchanged = unchanged and library_snapshot(env)[2] == native_before
                    hashes['inputs_unchanged'] = unchanged
                    if not unchanged:
                        summary.update(status='FAIL', reason='input_drift')
                        code = 1
        except TimeoutError:
            hashes['inputs_unchanged'] = False
            summary.update(status='TIMEOUT', reason='total_budget')
            code = 1
        except (InterruptedError, KeyboardInterrupt):
            hashes['inputs_unchanged'] = False
            summary.update(status='INTERRUPTED', reason='terminated')
            code = 1
        except Exception:
            hashes['inputs_unchanged'] = False
            summary.update(status='FAIL', reason='input_drift')
            code = 1
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if code:
            summary.pop('result', None)
        # Bound receipt I/O too. All child-group cleanup has finished before
        # this final deadline is armed, so it cannot interrupt that cleanup.
        signal.setitimer(signal.ITIMER_REAL, max(.001, end - time.monotonic()))
        try:
            summary['wall_seconds'] = round(time.monotonic() - start, 6)
            write_evidence(out, summary, hashes)
            if code == 0 and summary['status'] not in statuses:
                code = 1
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)
            signal.signal(signal.SIGTERM, old_term)
    return code, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deadline-ns', type=int)
    args = parser.parse_args(argv)
    try:
        options = {} if args.deadline_ns is None else {'deadline_ns': args.deadline_ns}
        code, summary = run(args.out, **options)
    except BaseException:
        code, summary = 1, safe_summary('FAIL', 'runner_setup_or_receipt_failed')
        if type(args.deadline_ns) is int and 0 < args.deadline_ns < 1 << 63:
            summary['total_budget_seconds'] = max(0., min(TOTAL_SECONDS,
                (args.deadline_ns - time.monotonic_ns()) / 1_000_000_000))
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
